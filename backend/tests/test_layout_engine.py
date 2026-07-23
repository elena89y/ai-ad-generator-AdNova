"""L2/L3 게이트: 레이아웃 DSL 엔진 + 카드뉴스 DSL 전환 — 담당: 한의정.

카드뉴스 조판이 layouts/cardnews.yaml(데이터) + layout_engine(범용 해석기)로 이전됐다.
데이터화 전 하드코딩 렌더와의 픽셀 동등은 전환 시점 파일럿에서 확인(ALL_IDENTICAL) — 여기서는
좌표/색/바인딩 resolve 단위 + DSL 렌더 결정론·구조를 고정한다.
"""
from __future__ import annotations

from PIL import Image, ImageChops, ImageDraw

from app.services.pipeline_v5 import layout_engine as le
from app.services.pipeline_v5.commercial_copy import DetailPageCopy
from app.services.pipeline_v5.hero import DetailCut, DetailCutRole, hero_from_existing
from app.services.pipeline_v5.palette import palette

R = DetailCutRole


def _fixture() -> DetailPageCopy:
    return DetailPageCopy(
        product_name="딸기 생크림 라떼", intro_headline="봄을 담은 한 잔",
        story_title="수제 딸기의 계절", story_body="매일 아침 갈아 만듭니다. 색소 없이 담습니다",
        benefit_bullets=("생딸기 그대로", "당일 제조", "무색소"),
        top_view_label="위에서 본 결", closeup_caption="과육이 그대로",
        profile_title="층층이\n쌓인 결", profile_caption="바닥까지 딸기",
        lifestyle_line="오후의 딸기 한 잔", cta_title="지금 맛보세요", cta_label="주문하기")


def _cuts(tmp_path):
    by_name = {}
    for i, role in enumerate(R):
        p = tmp_path / f"{role.value}.png"
        img = Image.new("RGB", (900, 1000), (238, 234, 228))
        ImageDraw.Draw(img).ellipse((90 + i * 90, 110, 380 + i * 90, 450), fill=(200, 90, 110))
        img.save(p)
        by_name[role.value] = str(p)
    return by_name


# --- resolve 단위 --------------------------------------------------------------

def test_coordinate_resolve():
    assert le._r(["margin"], 1000, 800, 70) == 70
    assert le._r(["margin", 238], 1000, 800, 70) == 308
    assert le._r(["rmargin"], 1000, 800, 70) == 930
    assert le._r(["rmargin", -120], 1000, 800, 70) == 810
    assert le._r(["fw", 1], 1000, 800, 70) == 1000
    assert le._r(["fh", 0.76], 1000, 800, 70) == 608
    assert le._r(["fh", 0.76, 42], 1000, 800, 70) == 650
    assert le._r(["fwm", 0.42, -2], 1000, 800, 70) == 280   # int(1000*.42) - 2*70
    assert le._r(["restw"], 1000, 800, 70, base=420) == 580
    assert le._r(["resth"], 1000, 800, 70, base=100) == 700
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
    # transform: 본문 첫 문장만
    assert le._bind_text({"bind": "story_body", "transform": "first_sentence"}, copy) == "매일 아침 갈아 만듭니다"


def test_conditional_element():
    copy = _fixture()
    assert le._cond({"if": "product_name"}, copy) is True
    empty = DetailPageCopy(product_name="", intro_headline="x", story_title="", story_body="",
                           benefit_bullets=(), top_view_label="", closeup_caption="",
                           profile_title="", profile_caption="", lifestyle_line="",
                           cta_title="", cta_label="")
    assert le._cond({"if": "benefit_bullets"}, empty) is False
    assert le._cond({}, copy) is True


def test_content_adaptation_conditions():
    """L5: if_domain/unless_domain/if_density — 콘텐츠(도메인·밀도)에 요소 표시 적응."""
    copy = _fixture()
    # if_domain: 지정 도메인일 때만 표시
    assert le._cond({"if_domain": ["food", "drink"]}, copy, {"domain": "drink"}) is True
    assert le._cond({"if_domain": ["food", "drink"]}, copy, {"domain": "object"}) is False
    # unless_domain: 지정 도메인이면 숨김
    assert le._cond({"unless_domain": ["object"]}, copy, {"domain": "object"}) is False
    assert le._cond({"unless_domain": ["object"]}, copy, {"domain": "drink"}) is True
    # if_density
    assert le._cond({"if_density": ["dense"]}, copy, {"density": "dense"}) is True
    assert le._cond({"if_density": ["dense"]}, copy, {"density": "medium"}) is False
    # if(copy 필드) + 도메인 복합
    assert le._cond({"if": "product_name", "unless_domain": ["object"]}, copy, {"domain": "drink"}) is True
    assert le._cond({"if": "product_name", "unless_domain": ["object"]}, copy, {"domain": "object"}) is False
    # ctx 없음 → domain=None: unless_domain 은 통과(표시), if_domain 은 숨김
    assert le._cond({"unless_domain": ["object"]}, copy, None) is True
    assert le._cond({"if_domain": ["food"]}, copy, None) is False


def test_cardnews_cover_kicker_adapts_to_domain(tmp_path):
    """L5 시연: 'SIGNATURE MENU' 키커가 object 도메인에서 생략 → drink 와 픽셀 다름."""
    layout = le.load_layout("cardnews")
    by_name = _cuts(tmp_path)
    copy = _fixture()
    pal = palette("pop")
    size = (1080, 1350)
    drink = le.render_slide(size, layout["cover"], by_name, copy, pal, 0.07, ctx={"domain": "drink"})
    obj = le.render_slide(size, layout["cover"], by_name, copy, pal, 0.07, ctx={"domain": "object"})
    assert ImageChops.difference(drink, obj).getbbox() is not None  # 키커 유무 차이


# --- DSL 레이아웃 로드·렌더 ----------------------------------------------------

def test_cardnews_layout_has_four_slides():
    layout = le.load_layout("cardnews")
    assert set(layout) == {"cover", "story", "detail", "cta"}
    assert layout["cover"]["bg"] == {"cut": "hero"}
    assert layout["story"]["bg"] == {"fill": "deep"}


def test_render_slide_deterministic_and_sized(tmp_path):
    layout = le.load_layout("cardnews")
    by_name = _cuts(tmp_path)
    copy = _fixture()
    pal = palette("pop")
    size = (1080, 1350)
    for name in ("cover", "story", "detail", "cta"):
        a = le.render_slide(size, layout[name], by_name, copy, pal, 0.07)
        b = le.render_slide(size, layout[name], by_name, copy, pal, 0.07)
        assert a.size == size
        assert ImageChops.difference(a, b).getbbox() is None, f"{name} 비결정론적"


def test_palette_makes_story_slide_differ_by_style(tmp_path):
    layout = le.load_layout("cardnews")
    by_name = _cuts(tmp_path)
    copy = _fixture()
    size = (1080, 1350)
    a = le.render_slide(size, layout["story"], by_name, copy, palette("pop"), 0.07)
    b = le.render_slide(size, layout["story"], by_name, copy, palette("editorial"), 0.07)
    assert ImageChops.difference(a, b).getbbox() is not None
