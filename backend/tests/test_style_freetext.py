"""자유서술 스타일(직접 입력 탭, A-full) 백엔드 검증 — 담당: 한의정.

GPU·OpenAI 실호출 없음: 번역은 _chat_json mock, kontext 편집은 instr 캡처로 대체.
검증 축: (1) 한→영 번역·폴백 (2) generate_scene 말미 append (3) 빈값이면 프리셋 경로 바이트동일.
"""
from __future__ import annotations

from unittest.mock import patch

from PIL import Image

from app.services import gpt_service, style_gen


# --- 번역(함정#1) ---------------------------------------------------------------
def test_translate_style_note_returns_en_clause():
    with patch.object(gpt_service, "_chat_json",
                      return_value={"style_en": "warm golden-hour light, airy negative space"}):
        out = gpt_service.translate_style_note("따뜻한 골든아워 조명, 여백 넉넉히")
    assert out == "warm golden-hour light, airy negative space"


def test_translate_style_note_empty_input_skips_call():
    with patch.object(gpt_service, "_chat_json", side_effect=AssertionError("호출되면 안 됨")):
        assert gpt_service.translate_style_note("") == ""
        assert gpt_service.translate_style_note("   ") == ""


def test_translate_style_note_falls_back_on_failure():
    with patch.object(gpt_service, "_chat_json", side_effect=RuntimeError("boom")):
        assert gpt_service.translate_style_note("아무 무드") == ""
    with patch.object(gpt_service, "_chat_json", return_value=["not", "a", "dict"]):
        assert gpt_service.translate_style_note("아무 무드") == ""


# --- generate_scene 주입 --------------------------------------------------------
def _capture_edit(monkeypatch):
    cap: dict = {}

    def fake_edit(image_path, instruction, seed=42, output_dir="",  # noqa: ANN001
                  clip_prompt=None, **kw):
        cap["instr"] = instruction
        return "/tmp/scene_out.png"

    monkeypatch.setattr("app.services.kontext_service.edit", fake_edit)
    return cap


def _img(tmp_path):
    p = tmp_path / "in.png"
    Image.new("RGB", (8, 8), (180, 120, 90)).save(p)
    return str(p)


def test_generate_scene_swaps_free_style_and_stays_lean(monkeypatch, tmp_path):
    """맞교환 검증: 자유서술은 verbose 프리셋에 append되지 않고 짧은 보존 템플릿으로 들어간다
    (T5 512토큰 예산 초과·뒤부터 잘림 방지). 프리셋 지시문보다 짧아야 한다."""
    cap_p = _capture_edit(monkeypatch)
    style_gen.generate_scene(_img(tmp_path), "editorial", "korean fried chicken", domain="food")
    preset_instr = cap_p["instr"]

    cap_c = _capture_edit(monkeypatch)
    style_gen.generate_scene(
        _img(tmp_path), "editorial", "korean fried chicken", domain="food",
        extra_style_en="warm golden-hour light, generous negative space")
    custom_instr = cap_c["instr"]

    assert "warm golden-hour light, generous negative space" in custom_instr
    assert "Additional art direction" not in custom_instr   # append 아님(맞교환)
    assert "No text" in custom_instr                          # no-text 가드 보존
    assert len(custom_instr) < len(preset_instr)             # 프리셋보다 짧음 = 예산 안전


def test_build_style_edit_instruction_food_and_object():
    from app.services import api_image_service as ai

    f = ai.build_style_edit_instruction("french toast", "warm golden light", "food")
    assert "warm golden light" in f and "food item" in f and "Do not add any text" in f
    o = ai.build_style_edit_instruction("ceramic mug", "soft light", "object")
    assert "soft light" in o and "labels or logos" in o


# --- 엔진 라우팅: 직접입력 → gpt-image, 프리셋 → 로컬, 실패 → 로컬 폴백 -------------
def _fake_analysis():
    from types import SimpleNamespace
    return SimpleNamespace(subject_en="french toast", domain="food", food_mode="dish")


def test_custom_style_routes_to_gptimage_not_local(monkeypatch, tmp_path):
    from app.services import api_image_service, generation_service as gs, gpt_service as gpt, style_gen

    img = str(tmp_path / "in.png"); Image.new("RGB", (16, 16), (200, 150, 100)).save(img)
    edited = str(tmp_path / "edited.png"); Image.new("RGB", (16, 16), (180, 140, 90)).save(edited)

    monkeypatch.setattr(gpt, "translate_style_note", lambda t: "warm golden light")
    seen = {}

    def fake_edit(image_path, instruction, out_dir=None, run=None, **kw):  # noqa: ANN001
        seen["instr"] = instruction
        return edited

    monkeypatch.setattr(api_image_service, "edit_image", fake_edit)

    def no_local(*a, **k):  # noqa: ANN002, ANN003
        raise AssertionError("직접입력인데 로컬 style_gen 이 호출됨")

    monkeypatch.setattr(style_gen, "generate_scene", no_local)
    monkeypatch.setattr(gs, "_generate_copy", lambda *a, **k: gpt.CopyResult(copy_text="헤드\n서브"))

    def no_pil(*a, **k):  # noqa: ANN002, ANN003
        raise AssertionError("타이포 baked인데 PIL 포스터가 호출됨")

    monkeypatch.setattr("app.services.overlay_service.apply_food_poster", no_pil)

    r = gs.process_ad(img, "프렌치토스트", style="editorial", style_text="따뜻하게",
                      poster=True, log=False, analysis=_fake_analysis(),
                      output_dir=str(tmp_path / "out"))
    assert r.final_image_path == edited          # baked 이미지 (PIL 조판 안 거침)
    assert r.engine == "api:edit:custom"
    assert "warm golden light" in seen["instr"]  # 연출절
    assert "헤드" in seen["instr"]                # 헤드라인이 지시문에 baked
    assert r.copy_text == "헤드\n서브"            # 사전 생성 카피 유지


def test_custom_style_falls_back_to_local_on_budget(monkeypatch, tmp_path):
    from app.services import api_image_service, generation_service as gs, gpt_service as gpt, style_gen

    img = str(tmp_path / "in.png"); Image.new("RGB", (16, 16)).save(img)
    local_out = str(tmp_path / "local.png"); Image.new("RGB", (16, 16)).save(local_out)

    monkeypatch.setattr(gpt, "translate_style_note", lambda t: "warm light")

    def boom(*a, **k):  # noqa: ANN002, ANN003
        raise api_image_service.ApiBudgetExceeded("over budget")

    monkeypatch.setattr(api_image_service, "edit_image", boom)
    seen = {}

    def fake_scene(image_path, style_key, subject_en, **kw):  # noqa: ANN001
        seen["extra"] = kw.get("extra_style_en")
        return local_out

    monkeypatch.setattr(style_gen, "generate_scene", fake_scene)
    monkeypatch.setattr(gs, "_tag_seed_output", lambda p, s: p)
    monkeypatch.setattr(gs, "_select_best", lambda cands, original_path=None: cands[0])
    monkeypatch.setattr(gs, "_generate_copy", lambda *a, **k: gpt.CopyResult(copy_text="H\nS"))

    r = gs.process_ad(img, "프렌치토스트", style="editorial", style_text="따뜻하게",
                      poster=False, log=False, analysis=_fake_analysis(),
                      output_dir=str(tmp_path / "out"))
    assert r.final_image_path == local_out
    assert seen["extra"] == "warm light"   # 폴백이 로컬 swap(extra_style_en) 사용


def test_generate_scene_byte_identical_without_free_style(monkeypatch, tmp_path):
    cap = _capture_edit(monkeypatch)
    style_gen.generate_scene(_img(tmp_path), "editorial", "korean fried chicken", domain="food")
    base = cap["instr"]

    cap2 = _capture_edit(monkeypatch)
    style_gen.generate_scene(_img(tmp_path), "editorial", "korean fried chicken",
                             domain="food", extra_style_en="")
    assert cap2["instr"] == base
    assert "Additional art direction" not in base
