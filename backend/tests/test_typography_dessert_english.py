"""ENG-LABEL-NO-CAP(2026-07-28) — 음료·디저트·베이커리는 영문 라벨이 있으면 길이 무관 영문 TS-1.

배경: plan_typography 의 `has_english = 0 < len(head_en) <= 18` 캡이 2~3단어 디저트명
(BLUEBERRY CREAM CAKE=20·MATCHA BERRY COOKIE=19)을 탈락시켜 한글로 폴백하던 버그
(아트디렉터 "블루베리 생크림 케이크·말차 베리 쿠키가 한글 dish처럼 나옴"). 캡 제거로 규약
"음료·디저트=영문 통일" 회복. render_ts1 이 _fit_width 로 폭 맞춰 축소하므로 길이 무해.
"""
import pytest
from PIL import Image

from app.services import typography_system as T


def _img():
    return Image.new("RGB", (1024, 1024), (240, 210, 190))


@pytest.mark.parametrize("name,subj", [
    ("블루베리 생크림 케이크", "blueberry cream cake"),   # 20자 — 구 캡(<=18) 초과, 회귀 케이스
    ("말차 베리 쿠키", "matcha berry cookie"),           # 19자 — 구 캡 초과
    ("초코 케이크", "chocolate cake"),                   # 14자
    ("카페라떼", "cafe latte"),                          # 10자 — 짧은 것도 계속 영문
])
def test_dessert_drink_english_label_always_ts1_english(name, subj):
    plan = T.plan_typography(_img(), name, "", subj, domain="bakery")  # dessert/drink→'bakery'
    assert plan.style == T.TS1_BG_LETTERING, (name, plan.style)
    assert plan.head == subj.upper()
    assert plan.head.isascii()


def test_drink_domain_also_english():
    plan = T.plan_typography(_img(), "말차라떼", "", "matcha green tea latte", domain="drink")
    assert plan.style == T.TS1_BG_LETTERING
    assert plan.head == "MATCHA GREEN TEA LATTE"


def test_no_english_label_falls_back_to_korean():
    # 영문 라벨(subject_en)이 없으면 한글 폴백 — 회귀 방지(캡 제거가 폴백을 없애지 않게)
    plan = T.plan_typography(_img(), "블루베리 케이크", "", "", domain="bakery")
    assert not plan.head.isascii()
    assert plan.style != T.TS1_BG_LETTERING


def test_food_dish_keeps_input_language():
    # 음식점 dish(food)는 규약상 입력명 그대로 — 영문 통일 대상 아님(내 수정과 무관해야)
    plan = T.plan_typography(_img(), "육개장 칼국수", "", "spicy beef noodle soup", domain="food")
    assert not plan.head.isascii()  # 한글 유지


def test_object_keeps_input_language():
    plan = T.plan_typography(_img(), "무선 마우스", "", "wireless mouse", domain="object")
    assert not plan.head.isascii()  # 한글 유지
