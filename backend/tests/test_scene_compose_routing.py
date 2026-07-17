"""P4D 4D-4 라우팅(D-11) 회귀 — 담당: 한의정.

SCENE_COMPOSE 플래그·Vision 적합성·합성 실패 시 자연 폴백을 검증한다.
실제 rembg/scene 렌더는 모킹하고 분기 로직만 확인한다.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import generation_service, gpt_service, style_gen


def _analysis(**overrides) -> gpt_service.PhotoAnalysis:
    values = {
        "match": True, "seen": "", "domain": "food", "display_name": "카페라떼",
        "subject_en": "cafe latte", "category": "default",
        "core_ingredients": ["espresso", "milk"], "texture_hero": False,
        "material": "default", "food_mode": "cafe", "lang": "ko",
        "container_kind": "cup", "container_color": "white",
        "container_opacity": "opaque", "temperature": "hot",
        "view_angle": "eye", "visible_text": "",
    }
    values.update(overrides)
    return gpt_service.PhotoAnalysis(**values)


# --- _compose_eligible ----------------------------------------------------------
def test_compose_eligible_object_requires_material_field():
    # 필드 자체가 없는 경우(구 MenuAnalysis 경로) — SimpleNamespace로 getattr 기본값 케이스 재현
    a_missing = SimpleNamespace()
    a_matte = _analysis(material="matte")
    a_reflective = _analysis(material="reflective")
    a_transparent = _analysis(material="transparent")
    assert generation_service._compose_eligible(a_missing, "object") is False
    assert generation_service._compose_eligible(a_matte, "object") is True
    assert generation_service._compose_eligible(a_reflective, "object") is False
    assert generation_service._compose_eligible(a_transparent, "object") is False


def test_compose_eligible_drink_requires_opaque_container():
    a_missing = SimpleNamespace()
    a_opaque = _analysis(container_opacity="opaque")
    a_transparent = _analysis(container_opacity="transparent")
    assert generation_service._compose_eligible(a_missing, "drink") is False
    assert generation_service._compose_eligible(a_opaque, "drink") is True
    assert generation_service._compose_eligible(a_transparent, "drink") is False


def test_compose_eligible_unknown_domain_is_false():
    assert generation_service._compose_eligible(_analysis(), "food") is False


# --- 라우팅(process_ad) -----------------------------------------------------------
def _forbid_kontext(monkeypatch):
    monkeypatch.setattr(
        style_gen, "generate_scene",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("Kontext must not run")),
    )


def _forbid_compose(monkeypatch):
    from app.services import scene_service
    monkeypatch.setattr(
        scene_service, "compose_scene",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("compose_scene must not run")),
    )


@pytest.fixture(autouse=True)
def _copy_and_env(monkeypatch):
    monkeypatch.setattr(
        generation_service, "_generate_copy",
        lambda *_a, **_kw: SimpleNamespace(copy_text="headline\nsubcopy"),
    )
    monkeypatch.delenv("SCENE_COMPOSE", raising=False)


def test_scene_compose_off_by_default_keeps_kontext_path(tmp_path, monkeypatch):
    """플래그 미설정(기본값 0) — scene_service는 아예 건드리지 않는다(안전 기본값)."""
    _forbid_compose(monkeypatch)
    source = tmp_path / "latte.png"
    source.write_bytes(b"input")
    generated = tmp_path / "generated.png"

    def fake_generate(*_a, **_kw):
        generated.write_bytes(b"result")
        return str(generated)

    monkeypatch.setattr(style_gen, "generate_scene", fake_generate)

    result = generation_service.process_ad(
        str(source), "카페라떼", style="realism", poster=False, log=False,
        output_dir=str(tmp_path), seed=1, analysis=_analysis(),
    )
    assert result.engine.startswith("style:")


def test_scene_compose_success_skips_kontext_entirely(tmp_path, monkeypatch):
    from app.services import scene_service

    _forbid_kontext(monkeypatch)
    monkeypatch.setenv("SCENE_COMPOSE", "1")
    scene_out = tmp_path / "scene.png"
    scene_out.write_bytes(b"scene-result")

    monkeypatch.setattr(
        scene_service, "compose_scene",
        lambda *_a, **_kw: {"ok": True, "path": str(scene_out),
                            "text_zone": "top_left", "plan": "warm_vintage/drink/linen_organic"},
    )
    source = tmp_path / "latte.png"
    source.write_bytes(b"input")

    result = generation_service.process_ad(
        str(source), "카페라떼", style="warm_vintage", poster=False, log=False,
        output_dir=str(tmp_path), seed=1,
        analysis=_analysis(container_opacity="opaque"),
    )
    assert result.engine == "scene:warm_vintage/drink/linen_organic"
    assert result.final_image_path == str(scene_out)


def test_scene_compose_ineligible_material_falls_back_to_kontext(tmp_path, monkeypatch):
    """Vision 적합성 미달(투명/반사) — compose_scene 호출 자체를 시도하지 않는다."""
    _forbid_compose(monkeypatch)
    monkeypatch.setenv("SCENE_COMPOSE", "1")
    generated = tmp_path / "generated.png"

    def fake_generate(*_a, **_kw):
        generated.write_bytes(b"result")
        return str(generated)

    monkeypatch.setattr(style_gen, "generate_scene", fake_generate)
    source = tmp_path / "perfume.png"
    source.write_bytes(b"input")

    result = generation_service.process_ad(
        str(source), "향수", style="editorial", poster=False, log=False,
        output_dir=str(tmp_path), seed=1,
        analysis=_analysis(domain="object", food_mode="dish", material="reflective",
                           subject_en="perfume bottle"),
    )
    assert result.engine.startswith("style:")


def test_scene_compose_failure_falls_back_to_kontext_naturally(tmp_path, monkeypatch):
    """compose_scene이 ok=False면 아무 것도 건드리지 않고 기존 경로로 자연 폴백한다(4D-4)."""
    from app.services import scene_service

    monkeypatch.setenv("SCENE_COMPOSE", "1")
    monkeypatch.setattr(
        scene_service, "compose_scene",
        lambda *_a, **_kw: {"ok": False, "reason": "mask"},
    )
    generated = tmp_path / "generated.png"

    def fake_generate(*_a, **_kw):
        generated.write_bytes(b"result")
        return str(generated)

    monkeypatch.setattr(style_gen, "generate_scene", fake_generate)
    source = tmp_path / "latte.png"
    source.write_bytes(b"input")

    result = generation_service.process_ad(
        str(source), "카페라떼", style="warm_vintage", poster=False, log=False,
        output_dir=str(tmp_path), seed=1,
        analysis=_analysis(container_opacity="opaque"),
    )
    assert result.engine.startswith("style:")
    assert Path(result.final_image_path).name.startswith("generated")
