"""SRV-ROUTE-001 §4-4 — 디저트 재플레이팅 락의 serving_type 게이트 (이관 테스트).

계약: serving_type이 있으면 락 판정의 정본(dessert|bakery + _replate_unsafe 가드),
None이면 레거시 substring(_is_dessert_subject)과 바이트 동일. vessel 분류 선행 불변.
"""
import pytest

from app.services.reference_style_plans import (_is_dessert_subject,
                                                _replate_unsafe,
                                                build_reference_instruction)

_LOCK_MARK = "plated dessert photograph"  # food_dessert 락 고유 문구


def _instr(subject, **kw):
    return build_reference_instruction("editorial", "food", subject, **kw)


# --- P1/P2 수정 확인: substring 오탐·누락을 serving_type이 교정 -----------------

def test_rice_cake_soup_no_lock_with_dish():
    """P1: 떡국(rice cake soup)은 레거시 substring이 오탐(락)하지만 dish면 락 없음."""
    assert _is_dessert_subject("rice cake soup") is True          # 레거시 버그 존재 증명
    assert _LOCK_MARK in _instr("rice cake soup")                 # None → 레거시(오탐 유지)
    assert _LOCK_MARK not in _instr("rice cake soup", serving_type="dish")  # 교정


def test_bread_gets_lock_with_bakery():
    """P2: 앙버터(bread)는 레거시가 누락하지만 bakery면 락 적용."""
    assert _is_dessert_subject("butter red bean bread") is False  # 레거시 누락 증명
    assert _LOCK_MARK not in _instr("butter red bean bread")
    assert _LOCK_MARK in _instr("butter red bean bread", serving_type="bakery")


def test_cake_lock_both_paths():
    """케이크는 신구 경로 모두 락 — 동작 동일성."""
    assert _LOCK_MARK in _instr("strawberry cream cake")
    assert _LOCK_MARK in _instr("strawberry cream cake", serving_type="dessert")


def test_none_is_byte_identical_to_legacy():
    """serving_type=None이면 레거시와 지시문 바이트 동일(킬스위치·구캐시 안전망)."""
    for subject in ("strawberry cream cake", "rice cake soup", "kimchi stew"):
        assert _instr(subject) == _instr(subject, serving_type=None)


def test_dessert_bakery_equivalence():
    """v1 별칭 계약: dessert와 bakery는 동일 트리트먼트."""
    assert (_instr("croissant", serving_type="dessert")
            == _instr("croissant", serving_type="bakery"))


@pytest.mark.parametrize("st", ["dish", "drink", "object"])
def test_non_dessert_types_never_lock(st):
    assert _LOCK_MARK not in _instr("strawberry cream cake", serving_type=st)


# --- _replate_unsafe 가드 (적대검증 HIGH 방어) --------------------------------

def test_gift_set_skips_lock():
    """세트·박스 상품: 박스 정렬에 '접시 교체' 지시 금지 — 온라인셀러 보호."""
    assert _replate_unsafe("macaron gift set", None) is True
    assert _LOCK_MARK not in _instr("macaron gift set", serving_type="dessert")


def test_bingsu_without_vision_skips_lock():
    """유리용기 디저트 + Vision 용기 정보 없음 → 안전측(락 미적용)."""
    assert _replate_unsafe("strawberry bingsu", None) is True
    assert _LOCK_MARK not in _instr("strawberry bingsu", serving_type="dessert")
    # Vision 정보가 있으면(접시로 확인) 가드 해제 — 락 적용 가능
    assert _replate_unsafe("strawberry bingsu", "plate") is False


def test_whole_cake_skips_lock():
    """홀케이크(기립형): '평평히 누운 조각' 전제 모순 → 락 금지."""
    assert _replate_unsafe("whole strawberry cake", None) is True
    assert _LOCK_MARK not in _instr("whole strawberry cake", serving_type="dessert")


def test_plain_slice_not_unsafe():
    assert _replate_unsafe("strawberry cream cake slice", "plate") is False


# --- vessel 선행 순서 회귀 -----------------------------------------------------

def test_vessel_precedes_serving_type():
    """유리 디저트 용기(vessel) 분류가 락보다 선행 — serving_type 유무와 무관 동일."""
    kw = dict(container_desc="glass", container_opacity="transparent")
    base = _instr("mango bingsu", **kw)
    with_st = _instr("mango bingsu", serving_type="dessert", **kw)
    assert base == with_st
    assert _LOCK_MARK not in base  # vessel 경로는 food_dessert 락이 아님(용기 보존)
