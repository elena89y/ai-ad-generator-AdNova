"""v4.2 P4B-R Tier 1 코드 장면 렌더러 기계 게이트 — 담당: 한의정."""
from __future__ import annotations

import hashlib
import time

import numpy as np
import pytest

from app.services import scene_render
from app.services.scene_plans import PLANS, plans_for


TIER1_CONTRACT = {
    "pop/drink/diagonal_field": ("#2146C7", "#FF7A1A"),
    "pop/drink/color_block_duo": ("#2146C7", "#FF7A1A"),
    "pop/object/color_block": ("#2146C7", "#B7E340"),
    "pop/object/concept_stage": ("#FF6F61", "#F5EFE6"),
    "editorial/drink/split_card": ("#F2EDE4", "#B7A48F"),
    "editorial/drink/asym_negative": ("#E8E0D4", "#D8CDBC"),
    "editorial/object/asym_negative": ("#E8E0D4", "#D8CDBC"),
    "editorial/object/seamless_min": ("#EDE8DF", "#FAF8F4"),
    "pastel/drink/soft_seamless": ("#F7D6E0", "#D9CDF2", "#CFE8DD"),
    "pastel/drink/cloud_gradient": ("#CDE4F7", "#F7DCE3"),
    "pastel/object/soft_seamless": ("#DFF0E8", "#F3D9DF"),
    "pastel/object/lilac_seamless": ("#E4D9F2", "#F7F4FB"),
    "monotone/drink/tone_seamless": ("#DCDCDC", "#9A9A9A"),
    "monotone/drink/dark_mono": ("#1E1E22", "#4A4A52"),
    "monotone/object/tone_seamless": ("#DCDCDC", "#9A9A9A"),
    "monotone/object/dark_mono": ("#1E1E22", "#4A4A52"),
}


def _code_plans():
    return [plan for plan in PLANS if plan.render_mode == "code"]


def _crop_array(image, bbox):  # noqa: ANN001, ANN202
    return np.asarray(image.crop(bbox), dtype=np.float32)


def _local_variation(arr: np.ndarray) -> float:
    """완만한 그라디언트는 허용하고 경계·장식의 고주파 변화만 측정한다."""
    horizontal = np.abs(np.diff(arr, axis=1)).mean(axis=2).ravel()
    vertical = np.abs(np.diff(arr, axis=0)).mean(axis=2).ravel()
    return float(np.percentile(np.concatenate((horizontal, vertical)), 95))


def test_tier1_contract_and_p5_recompose_split():
    code_plans = _code_plans()
    assert len(code_plans) == 16
    assert {plan.key for plan in code_plans} == set(TIER1_CONTRACT)
    assert {plan.style for plan in code_plans} == {"pop", "editorial", "pastel", "monotone"}
    for plan in code_plans:
        assert plan.palette == TIER1_CONTRACT[plan.key]
        assert plan.prop_slots == ()
        assert not plan.requires_recompose

    legacy_diagonal = next(plan for plan in PLANS if plan.key == "pop/drink/diagonal_splash")
    dreamy_cloud = next(plan for plan in PLANS if plan.key == "pastel/drink/dreamy_cloud")
    assert legacy_diagonal.requires_recompose and legacy_diagonal.render_mode == "sdxl"
    assert dreamy_cloud.requires_recompose and dreamy_cloud.render_mode == "sdxl"
    assert legacy_diagonal not in plans_for("pop", "drink")
    assert dreamy_cloud not in plans_for("pastel", "drink")


def test_d16_removes_3d_primitives_and_old_archetypes():
    forbidden = {"pedestal_min", "soft_pedestal", "floating_shelf", "tone_pedestal"}
    assert not ({plan.archetype for plan in _code_plans()} & forbidden)
    assert not hasattr(scene_render, "_pedestal")
    assert not hasattr(scene_render, "_soft_blobs")
    for plan in _code_plans():
        assert "pedestal" not in plan.scene.lower()
        assert "shelf" not in plan.scene.lower()


def test_hard_diagonal_and_asym_floor_contract():
    field = scene_render._dgrad(512, (33, 70, 199), (255, 122, 26), 82,
                                blend_px=6, split_at=0.74)
    first = np.all(field == (33, 70, 199), axis=2)
    second = np.all(field == (255, 122, 26), axis=2)
    transition_per_column = (~(first | second)).sum(axis=0)
    assert 0 < int(transition_per_column.max()) <= 10

    plan = next(p for p in _code_plans() if p.key == "editorial/drink/asym_negative")
    image = np.asarray(scene_render.render(plan, seed=11, size=512), dtype=np.float32)
    horizon = round((plan.surface_y - 0.04) * 512)
    wall_luma = float(image[horizon - 28:horizon - 16].mean())
    floor_luma = float(image[horizon + 28:horizon + 40].mean())
    assert wall_luma - floor_luma > 8.0


@pytest.mark.parametrize("plan", _code_plans(), ids=lambda plan: plan.key)
def test_render_is_deterministic_and_keeps_protected_regions_smooth(plan):  # noqa: ANN001
    first = scene_render.render(plan, seed=23, accent_hue=28, size=512)
    second = scene_render.render(plan, seed=23, accent_hue=28, size=512)
    assert first.mode == "RGB" and first.size == (512, 512)
    assert hashlib.sha256(first.tobytes()).digest() == hashlib.sha256(second.tobytes()).digest()

    slot = _crop_array(first, scene_render.slot_bbox(plan, 512))
    text_zone = _crop_array(first, scene_render.text_zone_bbox(plan, 512))
    assert _local_variation(slot) < 7.0, f"슬롯 장식 침범: {plan.key}"
    assert _local_variation(text_zone) < 7.0, f"카피 영역 장식 침범: {plan.key}"
    assert float(text_zone.std(axis=(0, 1)).max()) < 34.0, f"카피 영역 평활 미달: {plan.key}"


@pytest.mark.parametrize("plan", _code_plans(), ids=lambda plan: plan.key)
def test_render_1024_under_one_second(plan):  # noqa: ANN001
    started = time.perf_counter()
    image = scene_render.render(plan, seed=11, size=1024)
    elapsed = time.perf_counter() - started
    assert image.size == (1024, 1024)
    assert elapsed < 1.0, f"{plan.key} 렌더 {elapsed:.3f}s"


def test_renderer_rejects_sdxl_plan_and_invalid_size():
    sdxl_plan = next(plan for plan in PLANS if plan.render_mode == "sdxl")
    with pytest.raises(ValueError, match="code 플랜만"):
        scene_render.render(sdxl_plan)
    with pytest.raises(ValueError, match="256 이상"):
        scene_render.render(_code_plans()[0], size=128)
