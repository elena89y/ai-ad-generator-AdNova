"""L2/L3 게이트: 레이아웃 DSL 엔진이 기존 조판을 픽셀 동등 재현 — 담당: 한의정.

DSL 접근의 핵심 리스크(데이터로 기존 하드코딩 조판을 정확히 재현 가능한가?)를 고정한다.
카드뉴스 cover 를 DSL 요소로 표현하고, 기존 _cover_slide 와 픽셀 동등(bbox=None)임을 검증.
좌표/색/폰트 resolve 단위 검증 포함.
"""
from __future__ import annotations

from PIL import Image, ImageChops, ImageDraw

from app.services.pipeline_v5 import layout_engine as le
from app.services.pipeline_v5.commercial_copy import DetailPageCopy
from app.services.pipeline_v5.formats import cardnews
from app.services.pipeline_v5.palette import palette


def _fixture() -> DetailPageCopy:
    return DetailPageCopy(
        product_name="딸기 생크림 라떼", intro_headline="봄을 담은 한 잔",
        story_title="수제 딸기의 계절", story_body="매일 아침 갈아 만듭니다",
        benefit_bullets=("생딸기 그대로", "당일 제조", "무색소"),
        top_view_label="위에서 본 결", closeup_caption="과육이 그대로",
        profile_title="층층이\n쌓인 결", profile_caption="바닥까지 딸기",
        lifestyle_line="오후의 딸기 한 잔", cta_title="지금 맛보세요", cta_label="주문하기")


# 카드뉴스 표지 = DSL 요소 (기존 _cover_slide 1:1 매핑)
_COVER = [
    {"type": "scrim", "frm": [0, ["fh", 0.70]], "to": [["fw", 1], ["fh", 1]],
     "color": "ink", "amax": 210, "fade": ["fh", 0.12]},
    {"type": "bar", "box": [0, 0, ["fw", 1], 108], "color": "paper", "alpha": 235},
    {"type": "text", "at": [["margin"], 40], "bind": "product_name", "fallback": "ADNOVA SELECT",
     "font": 25, "bold": True, "color": [24, 24, 24]},
    {"type": "rule", "box": [["rmargin", -120], 57, ["rmargin"], 57], "color": "accent", "width": 5},
    {"type": "text", "at": [["margin"], ["fh", 0.76]], "text": "SIGNATURE MENU",
     "font": 22, "bold": True, "color": "tint", "if": "product_name"},
    {"type": "text", "at": [["margin"], ["fh", 0.76, 42]], "bind": "intro_headline",
     "font": {"fit": [62, 38]}, "color": "white"},
    {"type": "text", "at": [["margin"], ["fh", 0.76, 128]], "bind": "benefit_bullets.0",
     "font": {"fit": [28, 22]}, "color": "tint", "if": "benefit_bullets"},
]


def _hero(tmp_path):
    p = tmp_path / "hero.png"
    img = Image.new("RGB", (900, 1000), (238, 234, 228))
    ImageDraw.Draw(img).ellipse((150, 150, 500, 550), fill=(228, 90, 110))
    img.save(p)
    return str(p)


def test_cover_dsl_is_pixel_identical_to_hardcoded(tmp_path):
    hero = _hero(tmp_path)
    copy = _fixture()
    pal = palette("pop")
    size = (1080, 1350)
    margin = int(size[0] * 0.07)

    old = cardnews._cover_slide(hero, copy, pal, size, 0.07).convert("RGB")
    new = cardnews._cover(Image.open(hero).convert("RGB"), size)
    le.render_elements(new, _COVER, copy, pal, size[0], size[1], margin)

    assert ImageChops.difference(old, new.convert("RGB")).getbbox() is None


def test_coordinate_resolve():
    assert le._r(["margin"], 1000, 800, 70) == 70
    assert le._r(["rmargin"], 1000, 800, 70) == 930
    assert le._r(["rmargin", -120], 1000, 800, 70) == 810
    assert le._r(["fw", 1], 1000, 800, 70) == 1000
    assert le._r(["fh", 0.76], 1000, 800, 70) == 608
    assert le._r(["fh", 0.76, 42], 1000, 800, 70) == 650
    assert le._r(200, 1000, 800, 70) == 200


def test_color_and_bind_resolve():
    pal = {"accent": (10, 20, 30), "deep": (5, 10, 15), "tint": (200, 210, 220)}
    assert le._color("ink", pal) == (18, 18, 18)
    assert le._color("accent", pal) == (10, 20, 30)
    assert le._color([1, 2, 3], pal) == (1, 2, 3)
    copy = _fixture()
    assert le._bind_text({"bind": "intro_headline"}, copy) == "봄을 담은 한 잔"
    assert le._bind_text({"bind": "benefit_bullets.0"}, copy) == "생딸기 그대로"
    assert le._bind_text({"text": "STATIC"}, copy) == "STATIC"
    assert le._bind_text({"bind": "missing", "fallback": "FB"}, copy) == "FB"


def test_conditional_element():
    copy = _fixture()
    assert le._cond({"if": "product_name"}, copy) is True
    empty = DetailPageCopy(product_name="", intro_headline="x", story_title="", story_body="",
                           benefit_bullets=(), top_view_label="", closeup_caption="",
                           profile_title="", profile_caption="", lifestyle_line="",
                           cta_title="", cta_label="")
    assert le._cond({"if": "benefit_bullets"}, empty) is False
    assert le._cond({}, copy) is True
