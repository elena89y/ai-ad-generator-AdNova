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
        PropPolicy(categories=(), edible="always")


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
