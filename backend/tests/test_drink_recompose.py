"""P5 음료 재연출 회귀 — 담당: 한의정.

CLIP 앵커 staging 변형(#5)·재연출 계약 문구·Vision 기반 용기 묘사(#2)·D-4 개정 라우팅을
검증한다. Kontext 자체는 모킹 — 9장 시각 게이트(V4P5-001)는 VM에서 별도 실행.
"""
from __future__ import annotations

from types import SimpleNamespace


from app.services import generation_service, gpt_service, style_gen
from app.services.reference_style_plans import (
    build_clip_anchor,
    build_recompose_instruction,
)


def _analysis(**overrides) -> gpt_service.PhotoAnalysis:
    values = {
        "match": True, "seen": "", "domain": "food", "display_name": "딸기스무디",
        "subject_en": "strawberry smoothie", "category": "default",
        "core_ingredients": ["strawberry", "milk"], "texture_hero": False,
        "material": "default", "food_mode": "cafe", "lang": "ko",
        "container_kind": "glass", "container_color": "pink",
        "container_opacity": "transparent", "temperature": "iced",
        "view_angle": "eye", "visible_text": "",
    }
    values.update(overrides)
    return gpt_service.PhotoAnalysis(**values)


# --- CLIP 앵커 (#5) ---------------------------------------------------------------
def test_recompose_anchor_drops_preserve_wording_and_stays_short():
    for style in ("pop", "pastel", "editorial", "realism", "monotone", "warm_vintage"):
        preserve = build_clip_anchor(style, "drink", "strawberry smoothie")
        recompose = build_clip_anchor(style, "drink", "strawberry smoothie",
                                      staging="recompose")
        assert "unchanged" in preserve
        assert "unchanged" not in recompose          # 보존 문구 제거(#5)
        assert "beverage advertisement" in recompose
        assert len(recompose.split()) <= 25          # CLIP 77토큰 여유(단어≈토큰 1.5배 가정)
        assert "no text" in recompose


# --- 재연출 지시 계약 ----------------------------------------------------------------
def test_recompose_instruction_contract():
    instr = build_recompose_instruction(
        "pop", "strawberry smoothie", container_desc="pink glass",
        temperature="iced", text_zone="top_left",
    )
    # 같은 용기·같은 음료
    assert "pink glass" in instr
    assert "identical liquid color" in instr
    # 앵글·구도 자유 (보존 편집 어휘 금지)
    assert "freely change the camera angle" in instr
    assert "Do not add, remove, redraw" not in instr
    # 외래 재료·손·글자 금지 + text_zone 여백
    assert "Do not add any new ingredients" in instr
    assert "hands or people" in instr
    assert "top left area" in instr
    assert "logo, label, lettering" in instr


def test_recompose_direction_prop_bans_are_stripped():
    """direction 말미 'No fruit, ... ice ...' 금지문이 그대로 남으면 진짜 얼음·딸기까지
    지우라는 뜻으로 충돌한다 — 계약 문장이 금지를 일원화하므로 제거돼야 한다."""
    for style in ("pop", "pastel", "editorial"):
        instr = build_recompose_instruction(style, "strawberry smoothie")
        for banned_sentence_head in ("No fruit", "No shapes", "No spoon"):
            assert banned_sentence_head not in instr, (style, banned_sentence_head)


def test_recompose_temperature_effects_are_physically_true_only():
    iced = build_recompose_instruction("pop", "iced americano", temperature="iced")
    hot = build_recompose_instruction("pop", "cafe latte", temperature="hot")
    ambient = build_recompose_instruction("pop", "juice", temperature="ambient")
    assert "condensation" in iced and "steam" not in iced
    assert "steam" in hot and "condensation" not in hot
    assert "condensation" not in ambient and "steam" not in ambient


def test_recompose_unsupported_style_returns_none():
    assert build_recompose_instruction("cross_section", "cake") is None


# --- Vision 기반 용기 묘사 (#2) ------------------------------------------------------
def test_container_desc_comes_from_vision_fields_only():
    a = _analysis(container_kind="tumbler", container_color="matte black")
    assert generation_service._container_desc(a) == "matte black tumbler"
    no_container = _analysis(container_kind="none")
    assert generation_service._container_desc(no_container) is None
    missing = SimpleNamespace()  # 구 MenuAnalysis 경로 — 필드 자체가 없음
    assert generation_service._container_desc(missing) is None


# --- 라우팅 (D-4 개정) ---------------------------------------------------------------
def test_staging_preserve_when_flag_off(monkeypatch):
    monkeypatch.delenv("DRINK_RECOMPOSE", raising=False)
    staging, _ = generation_service._resolve_drink_staging(
        _analysis(), "drink", "pop", seed=1)
    assert staging == "preserve"


def test_staging_preserves_transparent_vessel_even_with_legacy_flag(monkeypatch):
    monkeypatch.setenv("DRINK_RECOMPOSE", "1")
    staging, zone = generation_service._resolve_drink_staging(
        _analysis(container_opacity="transparent"), "drink", "editorial", seed=1)
    assert staging == "preserve"
    assert zone is None


def test_staging_preserve_for_opaque_when_plan_is_normal(monkeypatch):
    """불투명 용기(합성 적격) + 일반 플랜 → 보존 편집 유지(재연출은 opt-in 조건에서만)."""
    from app.services import scene_plans

    monkeypatch.setenv("DRINK_RECOMPOSE_EXPERIMENT", "1")
    normal = next(p for p in scene_plans.PLANS
                  if p.domain == "drink" and not p.requires_recompose)
    monkeypatch.setattr(scene_plans, "get_plan", lambda *a, **kw: normal)
    staging, _ = generation_service._resolve_drink_staging(
        _analysis(container_opacity="opaque"), "drink", "pop", seed=1)
    assert staging == "preserve"


def test_staging_recompose_when_rotation_picks_recompose_plan(monkeypatch):
    from app.services import scene_plans

    monkeypatch.setenv("DRINK_RECOMPOSE_EXPERIMENT", "1")
    splash = next(p for p in scene_plans.PLANS if p.requires_recompose)
    monkeypatch.setattr(scene_plans, "get_plan", lambda *a, **kw: splash)
    staging, zone = generation_service._resolve_drink_staging(
        _analysis(container_opacity="opaque"), "drink", "pop", seed=0)
    assert staging == "recompose"
    assert zone == splash.text_zone


def test_staging_never_recompose_for_non_drink(monkeypatch):
    monkeypatch.setenv("DRINK_RECOMPOSE", "1")
    staging, _ = generation_service._resolve_drink_staging(
        _analysis(domain="object"), "object", "pop", seed=1)
    assert staging == "preserve"


# --- 통합: process_ad 경로 -----------------------------------------------------------
def test_process_ad_preserves_transparent_drink_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DRINK_RECOMPOSE", "1")
    monkeypatch.delenv("SCENE_COMPOSE", raising=False)
    monkeypatch.setattr(
        generation_service, "_generate_copy",
        lambda *_a, **_kw: SimpleNamespace(copy_text="headline\nsubcopy"),
    )
    captured = {}
    generated = tmp_path / "generated.png"

    def fake_generate(*_a, **kw):
        captured.update(kw)
        generated.write_bytes(b"result")
        return str(generated)

    monkeypatch.setattr(style_gen, "generate_scene", fake_generate)
    source = tmp_path / "smoothie.png"
    source.write_bytes(b"input")

    result = generation_service.process_ad(
        str(source), "딸기스무디", style="pop", poster=False, log=False,
        output_dir=str(tmp_path), seed=1,
        analysis=_analysis(container_opacity="transparent"),
    )
    assert captured.get("staging") is None
    # CONTAINER-001: 용기 묘사는 보존 경로에도 항상 전달된다(장식 용기 프리앰블 분기용).
    #   재연출 전용 kwargs(staging·temperature)가 안 넘어가는 것이 preserve 보장의 본질.
    assert captured.get("container_desc") == "pink glass"
    assert captured.get("temperature") is None
    assert result.engine.startswith("style:pop")


def test_process_ad_keeps_preserve_when_flag_off(tmp_path, monkeypatch):
    monkeypatch.delenv("DRINK_RECOMPOSE", raising=False)
    monkeypatch.delenv("SCENE_COMPOSE", raising=False)
    monkeypatch.setattr(
        generation_service, "_generate_copy",
        lambda *_a, **_kw: SimpleNamespace(copy_text="headline\nsubcopy"),
    )
    captured = {}
    generated = tmp_path / "generated.png"

    def fake_generate(*_a, **kw):
        captured.update(kw)
        generated.write_bytes(b"result")
        return str(generated)

    monkeypatch.setattr(style_gen, "generate_scene", fake_generate)
    source = tmp_path / "smoothie.png"
    source.write_bytes(b"input")

    result = generation_service.process_ad(
        str(source), "딸기스무디", style="pop", poster=False, log=False,
        output_dir=str(tmp_path), seed=1,
        analysis=_analysis(container_opacity="transparent"),
    )
    assert "staging" not in captured  # 기존 preserve 호출 시그니처 그대로
    assert result.engine.startswith("style:pop")
