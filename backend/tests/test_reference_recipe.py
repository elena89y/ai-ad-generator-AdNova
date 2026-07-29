"""ReferenceRecipe 스키마 회귀 — 4축 분리·검증 게이트·호환성·승인 게이트. 담당: 한의정."""
from __future__ import annotations

import pytest

from app.services.reference_recipe import (
    CommercialLayout, ConditioningReferenceSet, MoodToken, PaletteVariant,
    PropPolicy, ReferenceRecipe, SceneArchetype,
)


def test_conditioning_references_separate_identity_from_composition() -> None:
    refs = ConditioningReferenceSet(
        "latte_clean", "latte", "drink", "opaque",
        ("EXT-DRINK-002", "EXT-DRINK-014"), ("EXT-DRINK-005",),
    )
    assert refs.usable() is False
    assert set(refs.identity_reference_ids).isdisjoint(refs.composition_reference_ids)


@pytest.mark.parametrize("kwargs", [
    {"subject": "coffee"},
    {"opacity": "milky"},
    {"identity_reference_ids": ()},
    {"identity_reference_ids": ("same", "same")},
    {"composition_reference_ids": ("a", "b", "c", "d")},
])
def test_conditioning_references_reject_unsafe_contract(kwargs) -> None:
    base = dict(
        key="latte_clean", subject="latte", domain="drink", opacity="opaque",
        identity_reference_ids=("EXT-DRINK-002",),
    )
    base.update(kwargs)
    with pytest.raises(ValueError):
        ConditioningReferenceSet(**base)


def test_conditioning_references_reject_role_overlap_and_false_approval() -> None:
    with pytest.raises(ValueError, match="역할 중복"):
        ConditioningReferenceSet(
            "latte_clean", "latte", "drink", "opaque",
            ("EXT-DRINK-002",), ("EXT-DRINK-002",),
        )


def test_unapproved_conditioning_never_reaches_production_selector() -> None:
    from app.services.reference_recipe_data import get_conditioning_reference_set

    assert get_conditioning_reference_set("latte") is None
    candidate = get_conditioning_reference_set("latte", allow_unapproved=True)
    assert candidate is not None
    assert candidate.identity_reference_ids == ("EXT-DRINK-002", "EXT-DRINK-014")
    assert get_conditioning_reference_set("transparent_tea") is None
    assert get_conditioning_reference_set("unknown") is None
    with pytest.raises(ValueError, match="함께 설정"):
        ConditioningReferenceSet(
            "latte_clean", "latte", "drink", "opaque",
            ("EXT-DRINK-002",), approved=True,
        )


def test_commercial_layout_domestic_ad_grammar() -> None:
    hero = CommercialLayout(
        "kr_single_hero", "single_hero_headline", "single",
        "headline_product_brand", ("top", "bottom"), ("KR-AD-001", "KR-AD-011"),
        cta_zone="bottom_right",
    )
    lineup = CommercialLayout(
        "kr_lineup", "multi_product_lineup", "lineup_4_plus",
        "campaign_item_labels", ("top", "bottom"),
        ("KR-AD-002", "KR-AD-009", "KR-AD-016"), label_each_product=True,
    )
    assert hero.product_count == "single"
    assert lineup.label_each_product is True


@pytest.mark.parametrize("kwargs", [
    {"pattern": "catalog"},
    {"product_count": "many"},
    {"text_hierarchy": "huge_title"},
    {"text_zones": ("middle",)},
    {"cta_zone": "center_right"},
])
def test_commercial_layout_rejects_free_vocabulary(kwargs) -> None:
    base = dict(
        key="kr_layout", pattern="single_hero_headline", product_count="single",
        text_hierarchy="headline_product_brand", text_zones=("top", "bottom"),
        reference_ids=("KR-AD-001", "KR-AD-011"),
    )
    base.update(kwargs)
    with pytest.raises(ValueError):
        CommercialLayout(**base)


def test_commercial_layout_rejects_product_count_contradictions() -> None:
    with pytest.raises(ValueError, match="2개 이상"):
        CommercialLayout(
            "bad_lineup", "multi_product_lineup", "single",
            "campaign_item_labels", ("top",), ("KR-AD-001", "KR-AD-011"),
        )
    with pytest.raises(ValueError, match="단일 상품"):
        CommercialLayout(
            "bad_label", "single_hero_headline", "single",
            "headline_product_brand", ("top",), ("KR-AD-001", "KR-AD-011"),
            label_each_product=True,
        )


def test_commercial_layout_requires_unique_reference_evidence() -> None:
    with pytest.raises(ValueError, match="대표 2~3장"):
        CommercialLayout(
            "few_refs", "single_hero_headline", "single",
            "headline_product_brand", ("top",), ("KR-AD-001",),
        )
    with pytest.raises(ValueError, match="중복"):
        CommercialLayout(
            "dupe_refs", "single_hero_headline", "single",
            "headline_product_brand", ("top",), ("KR-AD-001", "KR-AD-001"),
        )


def _mood() -> MoodToken:
    return MoodToken(key="warm_organic", lighting="warm directional daylight",
                     materials=("wood", "linen"), prop_density="medium")


def _pv(mood="warm_organic") -> PaletteVariant:
    return PaletteVariant("travertine", mood, ("#E8E0D4", "#D8CDBC"),
                          "P4BR warm/travertine")


def _arch(domains=("drink",), opacity=("opaque",)) -> SceneArchetype:
    return SceneArchetype(key="tabletop_lifestyle", domains=frozenset(domains),
                          allowed_opacity=frozenset(opacity),
                          camera_angles=("eye", "slightly_high"), subject_scale=(0.42, 0.58),
                          placements=("center", "right_third"), text_zones=("top_left", "left"))


def _recipe(**kw) -> ReferenceRecipe:
    base = dict(domain="drink", archetype=_arch(), mood=_mood(), palette_variant=_pv(),
                prop_policy=PropPolicy(categories=("tableware", "textile"), edible="none"),
                reference_ids=("06_웜빈티지__IMG_4667", "06_웜빈티지__IMG_4678"),
                composition_note="top-down flat-lay, warm props around centered drink")
    base.update(kw)
    return ReferenceRecipe(**base)


def test_mood_rejects_bad_density():
    with pytest.raises(ValueError):
        MoodToken(key="pop", lighting="x", materials=("wood",), prop_density="ultra")


def test_palette_variant_validation():
    variant = PaletteVariant("cobalt_duo", "pop", ("#2B3FBB", "#F2ECE3"),
                             "P4BR pop/drink", ("drink",))
    assert variant.variant_id == "pop/cobalt_duo"
    with pytest.raises(ValueError):
        PaletteVariant("bad", "pop", ("2B3FBB",), "src")          # # 없음
    with pytest.raises(ValueError):
        PaletteVariant("bad", "popp", ("#2B3FBB",), "src")        # mood 오타
    with pytest.raises(ValueError):
        PaletteVariant("bad", "pop", ("#2B3FBB",), "")            # source 비어있음
    with pytest.raises(ValueError):
        PaletteVariant("bad", "pop", ("#2B3FBB",), "s", ("beverage",))  # domain_scope 오타
    with pytest.raises(ValueError):
        PaletteVariant("bad/key", "pop", ("#2B3FBB",), "src")


def test_recipe_palette_variant_mood_must_match():
    with pytest.raises(ValueError):
        _recipe(palette_variant=_pv("pop"))  # recipe mood=warm_organic인데 variant=pop


def test_recipe_palette_variant_domain_scope_must_match():
    object_only = PaletteVariant("teal_duo", "warm_organic", ("#2D6A6F",),
                                 "test", ("object",))
    with pytest.raises(ValueError):
        _recipe(palette_variant=object_only)


def test_archetype_rejects_bad_scale_and_angle():
    with pytest.raises(ValueError):
        SceneArchetype("k", frozenset({"drink"}), frozenset({"opaque"}),
                       ("eye",), (0.9, 0.4), ("center",), ("top",))  # min>max
    with pytest.raises(ValueError):
        SceneArchetype("k", frozenset({"drink"}), frozenset({"opaque"}),
                       ("worm_eye",), (0.4, 0.5), ("center",), ("top",))  # bad angle


def test_prop_policy_edible_enum():
    PropPolicy(categories=("botanical",), edible="source_only")
    with pytest.raises(ValueError):
        PropPolicy(categories=("botanical",), edible="always")


def test_prop_policy_rejects_concrete_noun_categories():
    # P1: 'coffee beans'·'salt shaker' 같은 구체명사는 category enum이 아니라 거부돼야 한다.
    with pytest.raises(ValueError):
        PropPolicy(categories=("coffee beans", "salt shaker"))
    PropPolicy(categories=("tableware", "botanical"))  # 정상


def test_prop_policy_maxcount_requires_categories():
    with pytest.raises(ValueError):
        PropPolicy(categories=(), max_count=2)  # 소품 허용인데 category 비면 모순
    PropPolicy(categories=(), max_count=0)  # 소품 없음은 OK


def test_vocabulary_typos_rejected():
    # P1: mood/domain/opacity/placement/text_zone 오타는 침묵 통과하면 안 된다.
    with pytest.raises(ValueError):
        MoodToken(key="warm-organic", lighting="x", materials=("wood",),
                  prop_density="medium")  # 하이픈 오타
    with pytest.raises(ValueError):
        _arch(opacity=("transparant",))  # opacity 오타
    with pytest.raises(ValueError):
        SceneArchetype("k", frozenset({"drink"}), frozenset({"opaque"}),
                       ("eye",), (0.4, 0.5), ("right-third",), ("top",))  # placement 오타
    with pytest.raises(ValueError):
        _recipe(domain="beverage")  # domain 오타


def test_empty_fields_rejected():
    with pytest.raises(ValueError):
        MoodToken(key="pop", lighting="x", materials=(), prop_density="low")  # materials 빈
    with pytest.raises(ValueError):
        PaletteVariant("bad", "pop", (), "src")  # palette 빈
    with pytest.raises(ValueError):
        _recipe(composition_note="   ")


def test_recipe_rejects_duplicate_refs():
    with pytest.raises(ValueError):
        _recipe(reference_ids=("same", "same"))


def test_recipe_id_stable():
    r = _recipe()
    assert r.recipe_id == "drink/tabletop_lifestyle/warm_organic"
    assert r.is_cross_domain is False


def test_cross_domain_bootstrap_requires_metadata():
    arch = _arch(domains=("drink", "food"))  # 아키타입은 두 도메인 호환 유지(전면 agnostic 아님)
    # cross-domain인데 transfer_reason/evidence_scope 없으면 거부
    with pytest.raises(ValueError):
        _recipe(archetype=arch, source_domains=("food",))
    # 직접 target 근거와 타 domain 근거가 섞인 부트스트랩도 추적 가능
    mixed = _recipe(archetype=arch, source_domains=("drink", "food"),
                    transfer_reason="직접 근거 보강", evidence_scope="camera only")
    assert mixed.is_cross_domain is True
    # 정상 부트스트랩: 메타 완비 + approved=False
    r = _recipe(archetype=arch, source_domains=("food",),
                transfer_reason="카메라·구도는 도메인 불변",
                evidence_scope="camera+composition only, not palette/props")
    assert r.is_cross_domain is True
    assert r.usable() is False  # 시각 게이트 전엔 미승인
    # 동일 domain 근거뿐인데 전이 메타를 붙이면 거부
    with pytest.raises(ValueError):
        _recipe(source_domains=("drink",), transfer_reason="x", evidence_scope="y")


def test_recipe_requires_two_or_three_refs():
    with pytest.raises(ValueError):
        _recipe(reference_ids=("only_one",))
    with pytest.raises(ValueError):
        _recipe(reference_ids=("a", "b", "c", "d"))


def test_recipe_domain_must_match_archetype():
    with pytest.raises(ValueError):
        _recipe(domain="object", archetype=_arch(domains=("drink",)))


def test_approval_gate():
    r = _recipe()
    assert r.usable() is False  # 미승인은 조립부가 못 씀
    with pytest.raises(ValueError):
        _recipe(approved=True)  # approved인데 approved_by 없음
    r2 = _recipe(approved=True, approved_by="의정")
    assert r2.usable() is True


def test_compatibility_filter():
    r = _recipe(archetype=_arch(domains=("drink",), opacity=("opaque",)))
    assert r.is_compatible("drink", "opaque") is True
    assert r.is_compatible("drink", "transparent") is False  # 투명 아이스음료는 이 아키타입 제외
    assert r.is_compatible("object", "opaque") is False


def test_data_module_loads():
    from app.services.reference_recipe_data import (
        CONDITIONING_REFERENCE_SETS, MOOD_TOKENS, PALETTE_VARIANTS, PALETTE_VARIANTS_BY_ID,
        REFERENCE_RECIPES, SCENE_ARCHETYPES,
    )
    from app.services.reference_recipe import MOODS
    assert set(MOOD_TOKENS) == set(MOODS)              # MoodToken 6무드
    assert set(PALETTE_VARIANTS) == set(MOODS)         # palette 후보도 6무드
    for k, mt in MOOD_TOKENS.items():
        assert mt.key == k
        assert not hasattr(mt, "palette")              # palette는 MoodToken 소유 아님
    # pop은 domain별 복수 variant(코발트/틸/코랄)
    assert len(PALETTE_VARIANTS["pop"]) >= 3
    for mood, variants in PALETTE_VARIANTS.items():
        for v in variants:
            assert v.mood == mood and v.palette[0].startswith("#")
            assert PALETTE_VARIANTS_BY_ID[v.variant_id] is v
    assert len(SCENE_ARCHETYPES) == 6
    assert len(REFERENCE_RECIPES) == 6
    assert {recipe.mood.key for recipe in REFERENCE_RECIPES.values()} == set(MOODS)
    assert all(not recipe.usable() for recipe in REFERENCE_RECIPES.values())
    assert set(CONDITIONING_REFERENCE_SETS) == {"latte_clean", "transparent_tea_clean"}
    assert all(not refs.usable() for refs in CONDITIONING_REFERENCE_SETS.values())


def test_reference_ids_are_unicode_canonicalized():
    r = _recipe(reference_ids=("03_리얼리즘__IMG_4602", "04_파스텔__IMG_4710"))
    decomposed = tuple(__import__("unicodedata").normalize("NFD", x) for x in r.reference_ids)
    assert tuple(__import__("unicodedata").normalize("NFC", x) for x in decomposed) == r.canonical_reference_ids


def test_production_drink_plans_follow_recipe_references():
    from app.services.reference_recipe import canonical_reference_id
    from app.services.reference_recipe_data import REFERENCE_RECIPES
    from app.services.reference_style_plans import get_reference_plan

    for recipe in REFERENCE_RECIPES.values():
        plan = get_reference_plan(recipe.mood.key, recipe.domain)
        assert tuple(canonical_reference_id(value) for value in plan.reference_ids) == \
            recipe.canonical_reference_ids


def test_unapproved_recipe_requires_explicit_experiment_gate(monkeypatch):
    from app.services.reference_recipe_data import get_reference_recipe
    from app.services.reference_style_plans import _recipe_staging

    assert get_reference_recipe("drink", "editorial") is None
    assert get_reference_recipe("drink", "editorial", allow_unapproved=True) is not None
    monkeypatch.delenv("REFERENCE_RECIPE_EXPERIMENT", raising=False)
    assert _recipe_staging("editorial") is None
    monkeypatch.setenv("REFERENCE_RECIPE_EXPERIMENT", "1")
    staging = _recipe_staging("editorial")
    assert "eye level" in staging and "right third" in staging
