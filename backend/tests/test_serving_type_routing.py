"""SRV-ROUTE-001 — serving_type 권위 라우팅 단위테스트.

계약: serving_type=None(미출력·오타·구캐시)이면 모든 소비처가 레거시 휴리스틱과
바이트 동일하게 동작한다. 값이 있으면 substring 오탐(P6: "milk tea cake" drink 승격)을
LLM 의미 판정으로 차단한다. 설계: ~/ai-ad-generator-AdNova-rule/SRV-ROUTE-001.
"""
import dataclasses
from types import SimpleNamespace

import pytest

from app.services import generation_service, gpt_service
from app.services.gpt_service import (MenuAnalysis, PhotoAnalysis,
                                      _clamp_serving_type)
from app.services.reference_style_plans import build_reference_instruction


# --- 클램프 -----------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("dish", "dish"), ("drink", "drink"), ("dessert", "dessert"),
    ("bakery", "bakery"), ("object", "object"),
    ("Dessert", "dessert"), ("  DRINK ", "drink"),   # 대소문자·공백 관대
    ("desert", None), ("beverage", None), ("", None), (None, None), (123, None),
])
def test_clamp_serving_type(raw, expected):
    """5값 통과, 오타·결측·타입 오류는 전부 None — raise 금지(함정 #6)."""
    assert _clamp_serving_type(raw) == expected


def test_menu_analysis_default_none():
    """serving_type 미지정 생성(기존 positional 호출·구캐시)이 그대로 동작해야 한다."""
    menu = MenuAnalysis(
        domain="food", display_name="라떼", subject_en="cafe latte",
        category="default", core_ingredients=["espresso"], texture_hero=False,
        material="default", food_mode="cafe", lang="ko",
    )
    assert menu.serving_type is None


# --- PhotoAnalysis 검증·라운드트립 -------------------------------------------

def _photo_kwargs(**over):
    base = dict(
        match=True, seen="라떼", domain="food", display_name="라떼",
        subject_en="cafe latte", category="default", core_ingredients=["espresso"],
        texture_hero=False, material="default", food_mode="cafe", lang="ko",
        container_kind="cup", container_color="white", container_opacity="opaque",
        temperature="hot", view_angle="eye", visible_text="",
    )
    base.update(over)
    return base


def test_photo_analysis_serving_type_none_and_valid():
    assert PhotoAnalysis(**_photo_kwargs()).serving_type is None
    assert PhotoAnalysis(**_photo_kwargs(serving_type="drink")).serving_type == "drink"


def test_photo_analysis_serving_type_invalid_rejected():
    """변조 캐시 방어 — 파스 클램프를 우회한 불량값은 기존 enum 계약대로 거부."""
    with pytest.raises(ValueError):
        PhotoAnalysis(**_photo_kwargs(serving_type="beverage"))


def test_photo_analysis_asdict_roundtrip():
    """캐시 직렬화(asdict)→재수화가 serving_type을 보존해야 한다."""
    photo = PhotoAnalysis(**_photo_kwargs(serving_type="dessert"))
    revived = PhotoAnalysis(**dataclasses.asdict(photo))
    assert revived.serving_type == "dessert"


def test_photo_analysis_legacy_cache_without_field():
    """구캐시(serving_type 키 없음) 재수화 = default None — TypeError 없어야 한다."""
    photo = PhotoAnalysis(**_photo_kwargs())
    data = dataclasses.asdict(photo)
    data.pop("serving_type")
    assert PhotoAnalysis(**data).serving_type is None


# --- _resolve_style_domain (P6 수정 핵심) ------------------------------------

def _menu_stub(subject_en, food_mode="cafe"):
    """container_kind 없는 이름 기반 분석 흉내 — 텍스트 폴백 경로 강제."""
    return SimpleNamespace(subject_en=subject_en, food_mode=food_mode)


def test_serving_type_drink_promotes_without_whitelist_hit():
    """화이트리스트 밖 이름도 LLM이 drink라면 승격 — 어휘 사전 경쟁 종료."""
    got = generation_service._resolve_style_domain(
        _menu_stub("sweet rice punch sikhye"), "food", "cafe",
        "sweet rice punch sikhye", serving_type="drink")
    assert got == "drink"


def test_serving_type_dessert_blocks_substring_false_positive():
    """P6: 'milk tea cake'는 'milk tea' substring에 걸려 레거시가 drink로 오승격 —
    serving_type=dessert가 이를 차단하고 food 유지."""
    subject = "milk tea cream cake"
    # 레거시(None)는 실제로 오탐 승격함을 먼저 고정(버그 존재 증명)
    legacy = generation_service._resolve_style_domain(
        _menu_stub(subject), "food", "cafe", subject)
    assert legacy == "drink"
    # serving_type이 있으면 의미 판정이 이김
    fixed = generation_service._resolve_style_domain(
        _menu_stub(subject), "food", "cafe", subject, serving_type="dessert")
    assert fixed == "food"


@pytest.mark.parametrize("st", ["dish", "dessert", "bakery"])
def test_serving_type_solid_food_never_promotes(st):
    got = generation_service._resolve_style_domain(
        _menu_stub("iced americano"), "food", "cafe", "iced americano",
        serving_type=st)
    assert got == "food"


def test_serving_type_none_falls_back_to_whitelist():
    """레거시 폴백 바이트 동일 — 화이트리스트 히트만 승격."""
    assert generation_service._resolve_style_domain(
        _menu_stub("iced americano"), "food", "cafe", "iced americano") == "drink"
    assert generation_service._resolve_style_domain(
        _menu_stub("chocolate cookie"), "food", "cafe", "chocolate cookie") == "food"


def test_vision_container_still_first_authority():
    """D-4 불변: Vision container_kind가 있으면 serving_type보다 우선."""
    photo = SimpleNamespace(subject_en="strawberry cake", food_mode="cafe",
                            container_kind="plate")
    got = generation_service._resolve_style_domain(
        photo, "food", "cafe", "strawberry cake", serving_type="drink")
    assert got == "food"  # plate는 _DRINK_CONTAINERS 밖 → serving_type 무시


def test_non_cafe_gate_unchanged():
    """dish·object는 serving_type과 무관하게 즉시 반환(게이트 불변)."""
    assert generation_service._resolve_style_domain(
        _menu_stub("beef soup", food_mode="dish"), "food", "dish", "beef soup",
        serving_type="drink") == "food"


# --- 배관: build_reference_instruction은 아직 무동작 --------------------------

def test_build_reference_instruction_ignores_serving_type_for_now():
    """develop엔 디저트 락이 없으므로 serving_type 유무와 지시문이 동일해야 한다
    (락 브랜치 머지 시 이 테스트를 tier-3 계약 테스트로 대체)."""
    base = build_reference_instruction("editorial", "food", "strawberry cake")
    with_st = build_reference_instruction("editorial", "food", "strawberry cake",
                                          serving_type="dessert")
    assert base == with_st


# --- 킬스위치 ----------------------------------------------------------------

def test_kill_switch_forces_none(monkeypatch):
    """SERVING_TYPE_ROUTING=0이면 추출 게이트가 None 강제 → 전 소비처 레거시."""
    monkeypatch.setenv("SERVING_TYPE_ROUTING", "0")
    import os
    serving_type = (
        None if os.environ.get("SERVING_TYPE_ROUTING", "1") == "0"
        else "drink"
    )
    assert serving_type is None


# --- analyze_menu 파스 통합 (LLM 스텁) ---------------------------------------

def test_analyze_menu_parses_serving_type(monkeypatch):
    canned = {
        "domain": "food", "category": "bakery", "subject_en": "butter red bean bread",
        "core_ingredients": ["bread", "butter", "red bean paste"],
        "texture_hero": False, "material": "default", "food_mode": "cafe",
        "lang": "ko", "serving_type": "bakery",
    }
    monkeypatch.setattr(gpt_service, "_chat_json", lambda *a, **k: canned)
    gpt_service.analyze_menu.cache_clear()
    menu = gpt_service.analyze_menu("앙버터")
    assert menu.serving_type == "bakery"
    gpt_service.analyze_menu.cache_clear()


def test_analyze_menu_missing_key_is_none(monkeypatch):
    """LLM이 키를 빼먹으면(형태 드리프트) None — 레거시 폴백 경로."""
    canned = {
        "domain": "food", "category": "default", "subject_en": "cafe latte",
        "core_ingredients": [], "texture_hero": False, "material": "default",
        "food_mode": "cafe", "lang": "ko",
    }
    monkeypatch.setattr(gpt_service, "_chat_json", lambda *a, **k: canned)
    gpt_service.analyze_menu.cache_clear()
    assert gpt_service.analyze_menu("라떼").serving_type is None
    gpt_service.analyze_menu.cache_clear()
