"""STYLE-V3(2026-07-26) — 디저트 재연출 게이트.

editorial/realism/warm 이 styled 아키타입 로테이션으로 편입되며 구 food_dessert 락은 폐기.
디저트 특별 처리는 이제 styled 경로 안에서:
  - dessert|bakery(비-unsafe) → 이상화 스왑(_IDEALIZE) + 접시 레지스트리(_STYLED)
  - dish → styled 로테이션은 받되 이상화 미적용(재드로잉 리스크)
재플레이팅 안전가드 _replate_unsafe(세트/박스·홀케이크·무Vision 유리용기)는 styled_v2 로 이관 —
부적합 디저트는 로테이션·접시교체 없이 플레인 food 락(씬 고정)으로 폴백. vessel 분류 선행 불변.
"""
import pytest

from app.services.reference_style_plans import (_replate_unsafe,
                                                build_reference_instruction)

_IDEALIZE = "Idealize this dessert"           # 디저트 이상화 스왑(dessert|bakery)
_STYLED = "premium designer serving piece"    # styled 로테이션 + 접시 레지스트리 주입


def _instr(subject, **kw):
    return build_reference_instruction("editorial", "food", subject, scene_seed=0, **kw)


# --- 디저트 이상화 게이트 (serving_type 정본) -----------------------------------

def test_dessert_gets_idealize_and_styled():
    """dessert/bakery(비-unsafe)는 styled 아키타입 + 이상화 스왑 둘 다."""
    for st in ("dessert", "bakery"):
        out = _instr("strawberry cream cake", serving_type=st)
        assert _IDEALIZE in out and _STYLED in out, st


def test_dish_styled_but_no_idealize():
    """dish(짭짤)는 styled 로테이션은 받되 이상화는 미적용(면류 재드로잉 계열 리스크)."""
    out = _instr("grilled beef", serving_type="dish")
    assert _STYLED in out
    assert _IDEALIZE not in out


def test_dessert_bakery_equivalence():
    """v1 별칭 계약: dessert와 bakery는 동일 트리트먼트."""
    assert (_instr("croissant", serving_type="dessert")
            == _instr("croissant", serving_type="bakery"))


@pytest.mark.parametrize("st", ["dish", "drink", "object"])
def test_non_dessert_types_never_idealize(st):
    assert _IDEALIZE not in _instr("strawberry cream cake", serving_type=st)


# --- _replate_unsafe: styled 제외 → 플레인 food 락 폴백 (안전가드 이관) ----------

def test_gift_set_not_styled():
    """세트·박스: 박스 정렬에 '접시 교체' 금지 → styled 제외, 이상화·접시교체 없음."""
    assert _replate_unsafe("macaron gift set", None) is True
    out = _instr("macaron gift set", serving_type="dessert")
    assert _STYLED not in out and _IDEALIZE not in out


def test_bingsu_without_vision_not_styled():
    """유리용기 디저트 + Vision 용기 정보 없음 → 안전측(styled 제외)."""
    assert _replate_unsafe("strawberry bingsu", None) is True
    assert _STYLED not in _instr("strawberry bingsu", serving_type="dessert")
    # Vision 정보가 있으면(접시로 확인) 가드 해제
    assert _replate_unsafe("strawberry bingsu", "plate") is False


def test_whole_cake_not_styled():
    """홀케이크(기립형): '평평히 누운 조각' 전제 모순 → styled 제외."""
    assert _replate_unsafe("whole strawberry cake", None) is True
    assert _STYLED not in _instr("whole strawberry cake", serving_type="dessert")


def test_plain_slice_styled():
    """평범한 조각 케이크는 unsafe 아님 → styled + 이상화."""
    assert _replate_unsafe("strawberry cream cake slice", "plate") is False
    out = _instr("strawberry cream cake slice", serving_type="dessert")
    assert _STYLED in out and _IDEALIZE in out


# --- vessel 선행 순서 회귀 -----------------------------------------------------

def test_vessel_precedes_styling():
    """유리 디저트 용기(vessel) 분류가 styled 보다 선행 — 용기 보존, serving_type 무관 동일."""
    kw = dict(container_desc="glass", container_opacity="transparent")
    base = _instr("mango bingsu", **kw)
    with_st = _instr("mango bingsu", serving_type="dessert", **kw)
    assert base == with_st
    assert _STYLED not in base  # vessel 경로는 styled 아키타입이 아님(용기 보존)
