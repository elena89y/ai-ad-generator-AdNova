"""STY-003~005 레퍼런스 StylePlan의 순수 로직 테스트."""
from app.services.reference_style_plans import (
    build_clip_anchor,
    build_reference_instruction,
    get_reference_plan,
    normalize_domain,
    normalize_style,
)


def test_all_six_moods_exist_for_each_domain() -> None:
    styles = ("editorial", "pop", "realism", "pastel_float", "monotone", "warm_vintage")
    for domain in ("food", "drink", "object"):
        for style in styles:
            plan = get_reference_plan(style, domain)
            assert plan is not None
            assert plan.domain == domain
            assert 2 <= len(plan.reference_ids) <= 3
            assert "No " in plan.direction


def test_style_and_domain_aliases_are_normalized() -> None:
    assert normalize_style("pastel_float") == "pastel"
    assert normalize_style("warm_vintage") == "warm_organic"
    assert normalize_domain("cafe") == "drink"
    assert normalize_domain("beauty") == "object"
    assert normalize_domain("dish") == "food"


def test_instruction_leads_with_domain_identity_lock() -> None:
    instruction = build_reference_instruction("pop", "object", "wireless mouse")
    assert instruction is not None
    assert instruction.startswith("The photographed subject is wireless mouse.")
    assert "identical silhouette" in instruction
    assert "Change only the background" in instruction
    assert "saturated electric-blue" in instruction
    assert "Do not generate any new logo" in instruction

    clip_anchor = build_clip_anchor("pop", "object", "wireless mouse")
    assert clip_anchor == (
        "wireless mouse, bold pop advertising, saturated color-block set, crisp hard light, "
        "original object unchanged, no text"
    )
    assert len(clip_anchor.split()) < 30


def test_special_format_is_left_to_existing_style_generator() -> None:
    assert get_reference_plan("cross_section", "food") is None
    assert build_reference_instruction("object_studio", "object", "perfume") is None
