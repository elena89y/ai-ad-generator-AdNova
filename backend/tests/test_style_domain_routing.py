"""디저트→drink 오라우팅 회귀 테스트 (2026-07-17 라이브 결함: 쿠키가 라떼로 재생성) — 담당: 한의정."""
from __future__ import annotations

from types import SimpleNamespace

from app.services.generation_service import _resolve_style_domain


def _menu(**kw):
    """analyze_menu 결과 모사 (container_kind 없음 = 텍스트 경로)."""
    base = dict(domain="food", food_mode="cafe", category="default", subject_en="")
    base.update(kw)
    ns = SimpleNamespace(**base)
    # analyze_menu(MenuAnalysis)에는 container_kind 속성 자체가 없다
    assert not hasattr(ns, "container_kind") or ns.container_kind is None
    return ns


def _photo(**kw):
    """PhotoAnalysis 모사 (container_kind 보유 = Vision 경로)."""
    base = dict(domain="food", food_mode="cafe", category="default",
                subject_en="", container_kind="none")
    base.update(kw)
    return SimpleNamespace(**base)


def test_cookie_stays_food_via_text_hints():
    """라이브 결함 재현 케이스: 말차베리쿠키 → drink 승격 금지."""
    a = _menu(subject_en="matcha berry cookie", category="bakery")
    assert _resolve_style_domain(a, "food", "cafe", a.subject_en) == "food"
    # category가 default로 와도 어휘 폴백이 잡아야 함
    b = _menu(subject_en="matcha berry cookie", category="default")
    assert _resolve_style_domain(b, "food", "cafe", b.subject_en) == "food"


def test_bakery_desserts_stay_food():
    for subject in ("strawberry cake slice", "butter croissant", "chocolate brownie",
                    "cherry scone", "sweet red bean bread"):
        a = _menu(subject_en=subject)
        assert _resolve_style_domain(a, "food", "cafe", subject) == "food", subject


def test_actual_beverages_still_route_to_drink():
    for subject in ("cafe latte", "iced americano", "strawberry smoothie"):
        a = _menu(subject_en=subject)
        assert _resolve_style_domain(a, "food", "cafe", subject) == "drink", subject


def test_photoanalysis_container_is_first_authority():
    # 사진에 컵이 보이면 drink (이름이 애매해도)
    cup = _photo(subject_en="matcha drink", container_kind="glass")
    assert _resolve_style_domain(cup, "food", "cafe", cup.subject_en) == "drink"
    # 사진에 용기 없음 → 이름이 음료 같아도 food 유지 (D-4: Vision 우선)
    none = _photo(subject_en="matcha latte", container_kind="none")
    assert _resolve_style_domain(none, "food", "cafe", none.subject_en) == "food"


def test_non_cafe_paths_unchanged():
    dish = _menu(food_mode="dish", subject_en="beef soup")
    assert _resolve_style_domain(dish, "food", "dish", dish.subject_en) == "food"
    obj = _menu(domain="object", food_mode="dish", subject_en="perfume bottle")
    assert _resolve_style_domain(obj, "object", "dish", obj.subject_en) == "object"
