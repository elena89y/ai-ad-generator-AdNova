"""ReferenceRecipe 스키마 회귀 — 4축 분리·검증 게이트·호환성·승인 게이트. 담당: 한의정."""
from __future__ import annotations

import pytest

from app.services.reference_recipe import (
    MoodToken, PropPolicy, ReferenceRecipe, SceneArchetype,
)


def _mood() -> MoodToken:
    return MoodToken(key="warm_organic", palette=("#C9A66B",),
                     lighting="warm directional daylight",
                     materials=("wood", "linen"), prop_density="medium")


def _arch(domains=("drink",), opacity=("opaque",)) -> SceneArchetype:
    return SceneArchetype(key="tabletop_lifestyle", domains=frozenset(domains),
                          allowed_opacity=frozenset(opacity),
                          camera_angles=("eye", "slightly_high"), subject_scale=(0.42, 0.58),
                          placements=("center", "right_third"), text_zones=("top_left", "left"))


def _recipe(**kw) -> ReferenceRecipe:
    base = dict(domain="drink", archetype=_arch(), mood=_mood(),
                prop_policy=PropPolicy(categories=("tableware", "textile"), edible="none"),
                reference_ids=("06_웜빈티지__IMG_4667", "06_웜빈티지__IMG_4678"),
                composition_note="top-down flat-lay, warm props around centered drink")
    base.update(kw)
    return ReferenceRecipe(**base)


def test_mood_rejects_bad_density():
    with pytest.raises(ValueError):
        MoodToken(key="pop", palette=(), lighting="x", materials=(), prop_density="ultra")


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
        MoodToken(key="warm-organic", palette=("#fff",), lighting="x", materials=("wood",),
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
        MoodToken(key="pop", palette=(), lighting="x", materials=("wood",), prop_density="low")
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
    # target이 source에 포함되면 전이가 아니므로 거부
    with pytest.raises(ValueError):
        _recipe(archetype=arch, source_domains=("drink", "food"),
                transfer_reason="x", evidence_scope="y")
    # 정상 부트스트랩: 메타 완비 + approved=False
    r = _recipe(archetype=arch, source_domains=("food",),
                transfer_reason="카메라·구도는 도메인 불변",
                evidence_scope="camera+composition only, not palette/props")
    assert r.is_cross_domain is True
    assert r.usable() is False  # 시각 게이트 전엔 미승인


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
