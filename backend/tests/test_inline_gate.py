"""P6B 인라인 게이트 회귀 — 담당: 한의정. numpy 경량 검사·모드 게이팅·enforce 개입 검증."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from PIL import Image

from app.services import generation_service, gpt_service, inline_gate, style_gen


def _img(tmp_path, name="x.png", color=(128, 128, 128), size=64):
    p = tmp_path / name
    Image.new("RGB", (size, size), color).save(p)
    return str(p)


def _colorful(tmp_path, name="c.png"):
    """채도 높은 그라디언트 — pop mean_sat 하한 통과용."""
    arr = np.zeros((64, 64, 3), dtype=np.uint8)
    arr[..., 0] = 230
    arr[..., 1] = np.linspace(0, 120, 64, dtype=np.uint8)[None, :]
    arr[..., 2] = 40
    p = tmp_path / name
    Image.fromarray(arr, "RGB").save(p)
    return str(p)


# --- gate_mode -------------------------------------------------------------------
def test_gate_mode_defaults_off_and_rejects_unknown(monkeypatch):
    monkeypatch.delenv("GATE_MODE", raising=False)
    assert inline_gate.gate_mode() == "off"
    monkeypatch.setenv("GATE_MODE", "banana")
    assert inline_gate.gate_mode() == "off"
    monkeypatch.setenv("GATE_MODE", "enforce")
    assert inline_gate.gate_mode() == "enforce"


# --- evaluate: compose_stats -----------------------------------------------------
def test_evaluate_flags_bad_compose_stats(tmp_path):
    final = _img(tmp_path)
    bad = {"fg_ratio": 0.92, "dominant_ratio": 0.4, "delta_e": 9.0}
    result = inline_gate.evaluate(final, style_key="realism", compose_stats=bad)
    checks = {f["check"] for f in result["failures"]}
    assert result["pass"] is False
    assert {"compose.fg_ratio", "compose.dominant_ratio", "compose.delta_e"} <= checks


def test_evaluate_passes_good_compose_stats(tmp_path):
    final = _img(tmp_path)
    good = {"fg_ratio": 0.25, "dominant_ratio": 0.99, "delta_e": 3.2}
    result = inline_gate.evaluate(final, style_key="realism", compose_stats=good)
    assert result["pass"] is True
    assert result["style_stats"] is not None  # 채점값은 항상 기록(캘리브레이션 원료)


# --- evaluate: style_stats -------------------------------------------------------
def test_evaluate_flags_desaturated_pop(tmp_path):
    gray = _img(tmp_path, color=(128, 128, 128))
    result = inline_gate.evaluate(gray, style_key="pop")
    assert any(f["check"] == "style.pop_mean_sat" for f in result["failures"])


def test_evaluate_accepts_saturated_pop(tmp_path):
    result = inline_gate.evaluate(_colorful(tmp_path), style_key="pop")
    assert all(not f["check"].startswith("style.") for f in result["failures"])


def test_evaluate_style_check_only_for_matching_style(tmp_path):
    gray = _img(tmp_path, color=(128, 128, 128))
    result = inline_gate.evaluate(gray, style_key="realism")  # realism엔 발색 하한 없음
    assert result["pass"] is True


def test_evaluate_survives_style_stats_failure(tmp_path, monkeypatch):
    from app.services import style_finish
    monkeypatch.setattr(style_finish, "style_stats",
                        lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("boom")))
    result = inline_gate.evaluate(_img(tmp_path), style_key="pop")
    assert result["style_stats"] is None
    assert result["pass"] is True  # 검사 자체가 죽으면 통과 처리(요청을 죽이지 않는다)


# --- enforce ---------------------------------------------------------------------
def test_enforce_refinishes_style_failure_once(tmp_path, monkeypatch):
    from app.services import style_finish

    gray = _img(tmp_path, color=(128, 128, 128))
    fixed = _colorful(tmp_path, name="fixed.png")
    calls = []

    def fake_apply(path, style_key, strength=0.6, **_kw):
        calls.append(strength)
        return fixed

    monkeypatch.setattr(style_finish, "apply", fake_apply)
    result = inline_gate.enforce(gray, style_key="pop")

    assert calls == [0.8]              # 재마감 1회, 강도 0.8(스펙)
    assert result["path"] == fixed
    assert result["refinished"] is True
    assert result["gate_failed"] is False  # 재마감본이 통과


def test_enforce_marks_gate_failed_when_refinish_does_not_help(tmp_path, monkeypatch):
    from app.services import style_finish

    gray = _img(tmp_path, color=(128, 128, 128))
    still_gray = _img(tmp_path, name="still.png", color=(129, 129, 129))
    monkeypatch.setattr(style_finish, "apply", lambda *a, **kw: still_gray)

    result = inline_gate.enforce(gray, style_key="pop")
    assert result["gate_failed"] is True
    assert result["path"] == still_gray  # 보수 결과는 그대로 반환(요청 실패 아님)


def test_enforce_does_not_touch_passing_result(tmp_path, monkeypatch):
    from app.services import style_finish
    monkeypatch.setattr(style_finish, "apply",
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("must not run")))
    good = _colorful(tmp_path)
    result = inline_gate.enforce(good, style_key="pop")
    assert result["path"] == good
    assert result["refinished"] is False


def test_enforce_compose_failure_has_no_retry_only_marking(tmp_path):
    """compose 통계 실패는 인라인에서 재생성하지 않는다(무거운 개입 금지) — 마킹만."""
    final = _img(tmp_path)
    result = inline_gate.enforce(final, style_key="realism",
                                 compose_stats={"fg_ratio": 0.9})
    assert result["gate_failed"] is True
    assert result["refinished"] is False
    assert result["path"] == final


# --- process_ad 통합 ---------------------------------------------------------------
def _analysis(**overrides) -> gpt_service.PhotoAnalysis:
    values = {
        "match": True, "seen": "", "domain": "food", "display_name": "카페라떼",
        "subject_en": "cafe latte", "category": "default",
        "core_ingredients": [], "texture_hero": False,
        "material": "default", "food_mode": "cafe", "lang": "ko",
        "container_kind": "cup", "container_color": "white",
        "container_opacity": "opaque", "temperature": "hot",
        "view_angle": "eye", "visible_text": "",
    }
    values.update(overrides)
    return gpt_service.PhotoAnalysis(**values)


def test_process_ad_gate_off_by_default_never_calls_gate(tmp_path, monkeypatch):
    monkeypatch.delenv("GATE_MODE", raising=False)
    monkeypatch.delenv("SCENE_COMPOSE", raising=False)
    monkeypatch.setattr(
        inline_gate, "evaluate",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("gate must not run")))
    monkeypatch.setattr(
        generation_service, "_generate_copy",
        lambda *_a, **_kw: SimpleNamespace(copy_text="h\ns"))
    generated = tmp_path / "g.png"

    def fake_generate(*_a, **_kw):
        Image.new("RGB", (32, 32)).save(generated)
        return str(generated)

    monkeypatch.setattr(style_gen, "generate_scene", fake_generate)
    src = _img(tmp_path, "in.png")
    result = generation_service.process_ad(
        src, "카페라떼", style="pop", poster=False, log=False,
        output_dir=str(tmp_path), seed=1, analysis=_analysis())
    assert result.engine.startswith("style:")


def test_process_ad_gate_enforce_swaps_final_path(tmp_path, monkeypatch):
    monkeypatch.setenv("GATE_MODE", "enforce")
    monkeypatch.delenv("SCENE_COMPOSE", raising=False)
    monkeypatch.setattr(
        generation_service, "_generate_copy",
        lambda *_a, **_kw: SimpleNamespace(copy_text="h\ns"))
    refinished = tmp_path / "refinished.png"
    Image.new("RGB", (32, 32)).save(refinished)
    monkeypatch.setattr(
        inline_gate, "enforce",
        lambda path, style_key, compose_stats: {
            "path": str(refinished), "gate": {"pass": True, "failures": [],
                                              "style_stats": None},
            "gate_failed": False, "refinished": True,
        })
    generated = tmp_path / "g.png"

    def fake_generate(*_a, **_kw):
        Image.new("RGB", (32, 32)).save(generated)
        return str(generated)

    monkeypatch.setattr(style_gen, "generate_scene", fake_generate)
    src = _img(tmp_path, "in.png")
    result = generation_service.process_ad(
        src, "카페라떼", style="pop", poster=False, log=False,
        output_dir=str(tmp_path), seed=1, analysis=_analysis())
    assert result.final_image_path == str(refinished)
