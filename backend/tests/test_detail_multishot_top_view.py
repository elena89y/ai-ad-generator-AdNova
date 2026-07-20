"""TOPVIEW-001/LIFESTYLE-001 회귀 테스트: top_view·lifestyle 각도 재시도용 프롬프트 생성기."""
from scripts.detail_multishot_generate import (
    LIFESTYLE_ANGLES,
    TOP_VIEW_ANGLES,
    lifestyle_prompt,
    role_prompts_for,
    top_view_prompt,
)


def test_top_view_angles_step_down_from_90_by_15():
    assert TOP_VIEW_ANGLES == (90, 75, 60, 45)


def test_top_view_prompt_at_90_keeps_birds_eye_wording():
    prompt = top_view_prompt("object", 90)
    assert "90-degree bird's-eye" in prompt
    assert "perpendicular" in prompt


def test_top_view_prompt_below_90_uses_tilted_wording_not_birds_eye():
    prompt = top_view_prompt("object", 60)
    assert "90-degree bird's-eye" not in prompt
    assert "60 degrees" in prompt


def test_top_view_prompt_domain_specific_preserve_clause():
    assert "vessel" in top_view_prompt("drink", 90)
    assert "food items" in top_view_prompt("food", 90)
    assert "label, material" in top_view_prompt("object", 90)


def test_role_prompts_for_defaults_top_view_to_90_degrees():
    prompts = role_prompts_for("object")
    assert prompts["top_view"] == top_view_prompt("object", 90)


def test_role_prompts_for_unsupported_domain_falls_back_to_food():
    assert role_prompts_for("nonexistent") == role_prompts_for("food")


def test_lifestyle_angles_step_up_from_eye_level():
    assert LIFESTYLE_ANGLES == (0, 30, 50, 70)


def test_lifestyle_prompt_at_zero_uses_eye_level_wording():
    prompt = lifestyle_prompt("object", 0)
    assert "eye level" in prompt
    assert "degrees downward" not in prompt


def test_lifestyle_prompt_above_zero_uses_tilted_wording():
    prompt = lifestyle_prompt("object", 50)
    assert "50 degrees downward" in prompt


def test_lifestyle_prompt_domain_specific_scene_and_preserve():
    assert "cafe" in lifestyle_prompt("drink", 0)
    assert "restaurant" in lifestyle_prompt("food", 0)
    assert "label and proportions" in lifestyle_prompt("object", 0)


def test_role_prompts_for_defaults_lifestyle_to_eye_level():
    prompts = role_prompts_for("object")
    assert prompts["lifestyle"] == lifestyle_prompt("object", 0)
