"""POP-V2 — 팝 4아키타입 로테이션 + 완화 잠금 (2026-07-23 아트디렉터 판정 채택분).

계약: food×pop(비-vessel)만 로테이션·food_pop 잠금, 그 외 스타일·도메인은 바이트 동일.
로테이션은 subject+scene_seed 결정론. {palette}는 PAL-002 적응형/고정 폴백이 채움.
"""
import pytest

from app.services.reference_style_plans import (_IDENTITY_LOCKS, _POP_FOOD_VARIANTS,
                                                build_reference_instruction)


def _instr(style="pop", domain="food", subject="strawberry cream cake", **kw):
    return build_reference_instruction(style, domain, subject, **kw)


def test_four_variants_exist_and_distinct():
    assert len(_POP_FOOD_VARIANTS) == 4
    assert len(set(_POP_FOOD_VARIANTS)) == 4


def test_rotation_deterministic():
    a = _instr(scene_seed=42)
    b = _instr(scene_seed=42)
    assert a == b


def test_rotation_varies_by_seed():
    """시드를 돌리면 복수 아키타입이 실제로 나와야 한다(로테이션 실효)."""
    outs = {_instr(scene_seed=s) for s in range(12)}
    assert len(outs) >= 3


def test_pop_food_uses_relaxed_lock():
    instr = _instr(scene_seed=0)
    assert "You MAY replace the plain plate" in instr          # 접시 교체 허용(판정)
    assert "same ingredients already visible" in instr          # 정직성: 보이는 재료만
    # 기존 드리프트 금지문("No extra food, props...")이 사라졌는지
    assert "No extra food, props" not in instr


def test_palette_placeholder_filled():
    for s in range(6):
        instr = _instr(scene_seed=s)
        assert "{palette}" not in instr
        assert "background" in instr


def test_non_pop_styles_unchanged():
    """editorial 등 타 스타일은 scene_seed 유무와 바이트 동일 — 회귀 없음."""
    base = _instr(style="editorial")
    with_seed = _instr(style="editorial", scene_seed=7)
    assert base == with_seed
    assert _IDENTITY_LOCKS["food"] .split(".")[0] in base  # 기존 food 잠금 유지


def test_drink_object_pop_unchanged():
    """v1 스코프: 로테이션은 food만 — drink/object pop은 기존 direction."""
    for dom in ("drink", "object"):
        base = _instr(domain=dom, subject="iced latte" if dom == "drink" else "hand cream")
        seeded = _instr(domain=dom, subject="iced latte" if dom == "drink" else "hand cream",
                        scene_seed=9)
        assert base == seeded
        assert "You MAY replace the plain plate" not in base


def test_vessel_excluded_from_rotation():
    """유리 디저트 용기(vessel)는 용기 보존 우선 — 로테이션·완화 잠금 미적용."""
    kw = dict(container_desc="glass", container_opacity="transparent")
    a = _instr(subject="mango bingsu", scene_seed=1, **kw)
    b = _instr(subject="mango bingsu", scene_seed=5, **kw)
    assert a == b                                   # 시드 무관(로테이션 안 탐)
    assert "You MAY replace the plain plate" not in a


@pytest.mark.parametrize("marker", [
    "joyful pop energy",         # ① ingredient_world
    "string of small pearls",    # ② styling_cut
    "floating weightlessly",     # ③ dynamic_float
    "captured mid-pour",         # ④ gradient_action
])
def test_each_archetype_reachable(marker):
    """12개 시드 안에서 4아키타입 각각이 최소 1회 등장."""
    joined = " ".join(_instr(scene_seed=s) for s in range(12))
    assert marker in joined


# --- POP-V2.1: 소품 구체명 ({props}) — "찰흙 덩어리" 핫픽스 -------------------

def test_props_clause_named_shapes():
    """재료명 → 형태 있는 소품 명사구. 치즈 우선(까르보나라→노란 큐브, 07-24 판정)."""
    from app.services.reference_style_plans import _props_clause
    carbonara = _props_clause(["pasta", "cream", "bacon", "parmesan"])
    assert "yellow parmesan cubes" in carbonara
    cake = _props_clause(["strawberry", "cream", "sponge"])
    assert "fresh whole strawberry" in cake and "freeze-dried strawberry chips" in cake
    assert "clearly shaped glossy props" in _props_clause(None)  # 폴백


def test_props_placeholder_filled_and_anti_lump():
    """{props} 잔존 금지 + 안티-덩어리 절 포함(①③ 계열)."""
    for s in range(12):
        instr = _instr(scene_seed=s, core_ingredients=["strawberry", "cream"])
        assert "{props}" not in instr
    joined = " ".join(_instr(scene_seed=s, core_ingredients=["strawberry", "cream"])
                      for s in range(12))
    assert "no shapeless lumps" in joined


def test_props_without_ingredients_safe():
    """core_ingredients 미전달(구캐시·스텁)이어도 {props}는 일반 폴백으로 채워진다."""
    for s in range(4):
        instr = _instr(scene_seed=s)
        assert "{props}" not in instr
