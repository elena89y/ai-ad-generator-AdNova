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
    # PALETTE-001: pop 색상은 이제 상품명 해시로 결정론적 선택 — 특정 색 하나로 고정 단언하지
    # 않고, {palette} 자리표시자가 실제로 채워졌는지(포맷 문자열이 그대로 안 남았는지)만 검증.
    assert "{palette}" not in instruction
    assert "saturated" in instruction and "background" in instruction
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


def test_pop_palette_varies_by_product_but_is_stable_per_product() -> None:
    """PALETTE-001(2026-07-20): "pop" 색상이 상품과 무관하게 도메인당 색조합 1개로 고정돼
    있던 문제 — 상품명 해시로 다른 상품은 다른 색, 같은 상품은 재생성해도 같은 색이어야 한다."""
    sandwich_1 = build_reference_instruction("pop", "food", "ham and cheese sandwich")
    sandwich_2 = build_reference_instruction("pop", "food", "ham and cheese sandwich")
    toast = build_reference_instruction("pop", "food", "french toast")
    assert sandwich_1 == sandwich_2
    assert sandwich_1 != toast


def test_pop_palette_stays_within_domain_specific_candidates() -> None:
    from app.services.reference_style_plans import _POP_PALETTES

    for domain, variants in _POP_PALETTES.items():
        for subject in ("product a", "product b", "product c", "product d", "product e"):
            instruction = build_reference_instruction("pop", domain, subject)
            assert any(variant in instruction for variant in variants), (domain, subject)


def test_pastel_and_monotone_palettes_also_vary_by_product() -> None:
    """PALETTE-002(2026-07-20): pastel(4 후보)·monotone(food/drink 2 후보)도 pop과 같은
    문제였다 — reference_recipe_data.PALETTE_VARIANTS에 후보가 있는데 실제로는 안 쓰이고
    있었음. 같은 상품명 해시 방식으로 다양화."""
    from app.services.reference_style_plans import _MONOTONE_PALETTES, _PASTEL_PALETTES

    for style_key, palettes in (("pastel", _PASTEL_PALETTES), ("monotone", _MONOTONE_PALETTES)):
        for domain, variants in palettes.items():
            seen = set()
            for subject in ("product a", "product b", "product c", "product d", "product e"):
                instruction = build_reference_instruction(style_key, domain, subject)
                assert "{palette}" not in instruction
                matched = [v for v in variants if v in instruction]
                assert len(matched) == 1, (style_key, domain, subject)
                seen.add(matched[0])
            if len(variants) > 1:
                assert len(seen) > 1, f"{style_key}/{domain} 항상 같은 팔레트만 선택됨"


def test_object_monotone_has_no_palette_placeholder() -> None:
    """object monotone은 원래도 색을 지정 안 함("one restrained color family") — 팔레트
    다양화 대상이 아니다. {palette} 자리표시자가 안 남아있는지만 확인."""
    instruction = build_reference_instruction("monotone", "object", "wireless mouse")
    assert instruction is not None
    assert "{palette}" not in instruction
    assert "restrained color family" in instruction


def test_food_identity_lock_forbids_propped_up_food_styling() -> None:
    """PLATING-001-2/3(2026-07-20): pop 스타일에서 프렌치토스트가 접시에 기대 세워진 채로
    나온 재현 케이스(2차 보강 후에도 재발) — "기대 세우기" 프로핑 연출을 명시적으로 금지해야
    한다. 빵/토스트류는 구체적으로 호명한다."""
    instruction = build_reference_instruction("pop", "food", "french toast")
    assert instruction is not None
    assert "propped up" in instruction
    assert "leaning against anything" in instruction
    assert "slice of bread, toast, cake" in instruction
    assert "never a food item standing upright" in instruction


def test_container_default_path_keeps_measured_bug_fix_phrases() -> None:
    """CONTAINER-001 회귀 가드: 용기 근거가 없거나 불투명 접시·그릇이면 컵 변환(BUG-KTX-001)·
    프로핑(PLATING-001) 대응 문구가 바이트 동일하게 유지돼야 한다. 실측(2026-07-21) 샌드위치·
    프렌치토스트는 opacity=opaque, kind=plate — vessel 분기는 투명 유리 디저트 용기만 탄다."""
    base = build_reference_instruction("realism", "food", "club sandwich")
    assert base is not None
    default_inputs = [
        (None, None),
        ("", None),
        ("none", "opaque"),
        ("pink plate", "opaque"),          # 샌드위치 실측
        ("white plate", "opaque"),         # 프렌치토스트 실측
        ("black stone bowl", "opaque"),    # 불투명 뚝배기 — 깊은 용기지만 opaque라 default
        ("clear glass", None),             # opacity 근거 없으면 안전측 default
        ("clear glass plate", "transparent"),  # 투명해도 flat(plate) → default(PLATING-001 가드)
    ]
    for desc, opacity in default_inputs:
        assert build_reference_instruction(
            "realism", "food", "club sandwich",
            container_desc=desc, container_opacity=opacity) == base, (desc, opacity)
    assert "There is no cup, mug, tumbler, lid or straw anywhere" in base
    assert "the plate resting flat on a dark charcoal stone table" in base
    assert "Never convert the food, its plate or bowl into a cup" in base
    # 자리표시자가 그대로 노출되지 않아야 한다
    assert "{hero}" not in base and "{container_clause}" not in base
    # editorial·pop의 {hero} 기본 치환도 기존 문구와 동일해야 한다
    editorial = build_reference_instruction("editorial", "food", "club sandwich")
    assert "generous quiet copy space above the plate." in editorial
    pop = build_reference_instruction("pop", "food", "club sandwich")
    assert "diagonal shadow behind the plate." in pop


def test_vessel_container_switches_to_positive_preservation() -> None:
    """CONTAINER-001(2026-07-21): 굽 유리볼 빙수가 (food,realism)에서 밋밋한 흰 접시+차콜로
    강제 변환된 운영 실측(historyId=107) — 투명 유리 디저트 용기는 "원본 용기 유지+프리미엄
    연출" 긍정 단언으로 전환하고, 그 사진에서 거짓이 되는 부정문(no cup anywhere)과 접시 강제
    문구를 치운다. 실측 container_kind='glass', opacity='transparent'."""
    instr = build_reference_instruction(
        "realism", "food", "fruit shaved ice",
        container_desc="transparent glass", container_opacity="transparent")
    assert instr is not None
    # 긍정 단언이 부정문보다 앞(BUG-KTX-001 성공 패턴)
    assert "served in its original transparent glass" in instr
    assert instr.index("served in its original") < instr.index("Never convert")
    # 용기→접시 변환 차단 + 실측 거짓 부정문 제거
    assert "Never convert the transparent glass into a plain flat plate" in instr
    assert "There is no cup" not in instr
    assert "the plate resting flat" not in instr
    # realism 접지 문구는 굽 용기에 물리적으로 참인 서술로 치환
    assert ("with the transparent glass standing upright on its own base "
            "on a dark charcoal stone table") in instr
    assert "{container_clause}" not in instr and "{hero}" not in instr


def test_vessel_explicit_shape_keyword_fires_regardless_of_opacity() -> None:
    """Vision이 굽·스템 형태를 명시적으로 주면(고블릿·파르페 등) opacity 근거가 없어도
    vessel — 이름 기반 폴백·미래 프롬프트 강화 대비."""
    for desc in ("clear pedestal glass bowl", "tall parfait glass", "footed goblet"):
        instr = build_reference_instruction(
            "realism", "food", "strawberry parfait", container_desc=desc)
        assert instr is not None, desc
        assert f"served in its original {desc}" in instr, desc
        assert "There is no cup" not in instr, desc


def test_vessel_preamble_applies_across_all_food_moods() -> None:
    """vessel 분기는 realism만이 아니라 food 6무드 전부의 프리앰블에 적용된다."""
    styles = ("editorial", "pop", "realism", "pastel_float", "monotone", "warm_vintage")
    for style in styles:
        instr = build_reference_instruction(
            style, "food", "strawberry parfait",
            container_desc="clear glass", container_opacity="transparent")
        assert instr is not None, style
        assert "served in its original clear glass" in instr, style
        assert "There is no cup" not in instr, style
        assert "{hero}" not in instr and "{container_clause}" not in instr, style
        assert "{palette}" not in instr, style


def test_vessel_branch_only_applies_to_food_domain() -> None:
    """drink·object 프리앰블은 용기 묘사와 무관하게 기존 그대로 — drink는 이미 용기 실루엣
    보존 계약이 있고, object는 정직성 경계(형태·색 왜곡 금지)가 담당한다."""
    for domain in ("drink", "object"):
        base = build_reference_instruction("realism", domain, "iced tea")
        with_desc = build_reference_instruction(
            "realism", domain, "iced tea",
            container_desc="transparent glass", container_opacity="transparent")
        assert with_desc == base, domain
