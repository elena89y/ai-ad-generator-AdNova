"""v6-1 F2/F3 카드뉴스·배너 고도화 테스트 — 담당: 한의정.

검증: ① 공용 palette 스타일 분화 ② cardnews/banner 가 detail_copy_for(F1 엔진) 사용
③ 팔레트가 스타일을 따라 카드뉴스/배너 톤이 달라짐. 전부 GPT 모킹(비용 0).
"""
from __future__ import annotations

from unittest.mock import patch

from PIL import Image, ImageChops, ImageDraw

from app.schemas.ads import AdPurpose
from app.services.pipeline_v5 import generate_v5
from app.services.pipeline_v5.commercial_copy import DetailPageCopy
from app.services.pipeline_v5.formats import banner, cardnews
from app.services.pipeline_v5.hero import DetailCut, DetailCutRole, hero_from_existing
from app.services.pipeline_v5.palette import palette


def _fixture() -> DetailPageCopy:
    return DetailPageCopy(
        product_name="딸기 라떼", intro_headline="봄을 담은 한 잔",
        story_title="수제 딸기의 계절", story_body="매일 아침 딸기를 갈아 만듭니다",
        benefit_bullets=("생딸기 그대로", "당일 제조", "무색소"),
        top_view_label="위에서 본 결", closeup_caption="과육이 그대로",
        profile_title="층층이\n쌓인 결", profile_caption="바닥까지 딸기가 가득",
        lifestyle_line="오후의 딸기 한 잔", cta_title="지금 맛보세요", cta_label="주문하기")


def _cuts(base):
    base.mkdir(parents=True, exist_ok=True)
    cuts = []
    for i, role in enumerate(DetailCutRole):
        p = base / f"{role.value}.png"
        img = Image.new("RGB", (820, 940), (225 - i * 18, 220, 205 + i * 9))
        d = ImageDraw.Draw(img)
        d.ellipse((40 + i * 115, 70 + i * 85, 250 + i * 115, 310 + i * 85), fill=(50 + i * 28, 80, 120))
        d.rectangle((i * 65, 700 - i * 90, 280 + i * 65, 850 - i * 90), fill=(135, 55 + i * 24, 75))
        img.save(p)
        cuts.append(DetailCut(str(p), role))
    return tuple(cuts)


def _hero(base, style):
    cuts = _cuts(base)
    return hero_from_existing(cuts[0].image_path, headline="라떼", subcopy="한 잔",
                              domain="drink", subject_en="strawberry latte",
                              style=style, detail_cuts=cuts)


# --- 공용 palette ------------------------------------------------------------

def test_palette_varies_by_style_and_falls_back():
    assert palette("pop")["accent"] != palette("editorial")["accent"]
    assert palette("no-such-style")["accent"] == palette("editorial")["accent"]
    pal = palette("pop")
    # deep=진한 변형(≤accent), tint=밝은 변형(≥accent) 성질
    assert all(d <= a for d, a in zip(pal["deep"], pal["accent"]))
    assert all(t >= a for t, a in zip(pal["tint"], pal["accent"]))


# --- 카드뉴스 F2 -------------------------------------------------------------

def test_cardnews_uses_detail_copy_engine(tmp_path):
    hero = _hero(tmp_path / "c", "pop")
    with patch.object(cardnews, "detail_copy_for", return_value=_fixture()) as m:
        out = generate_v5(hero.image_path, "딸기 라떼", purpose=AdPurpose.CARD_NEWS,
                          hero_asset=hero, output_dir=str(tmp_path / "o"))
    m.assert_called_once()          # copy_for/section_copy_for 혼재 아님, 단일 엔진 1회
    assert len(out.outputs) == 4
    imgs = [Image.open(p).convert("RGB") for p in out.outputs]
    assert all(ImageChops.difference(imgs[0], x).getbbox() for x in imgs[1:])


def test_cardnews_palette_follows_style(tmp_path):
    ha, hb = _hero(tmp_path / "pop", "pop"), _hero(tmp_path / "edi", "editorial")
    with patch.object(cardnews, "detail_copy_for", return_value=_fixture()):
        oa = generate_v5(ha.image_path, "딸기 라떼", purpose=AdPurpose.CARD_NEWS,
                         hero_asset=ha, output_dir=str(tmp_path / "oa"))
        ob = generate_v5(hb.image_path, "딸기 라떼", purpose=AdPurpose.CARD_NEWS,
                         hero_asset=hb, output_dir=str(tmp_path / "ob"))
    # story 슬라이드(idx1) 배경 = palette deep → 스타일이 다르면 픽셀도 다름
    sa = Image.open(oa.outputs[1]).convert("RGB")
    sb = Image.open(ob.outputs[1]).convert("RGB")
    assert ImageChops.difference(sa, sb).getbbox() is not None


# --- 배너 F3 -----------------------------------------------------------------

def test_banner_uses_detail_copy_and_renders(tmp_path):
    hero = _hero(tmp_path / "b", "pop")
    with patch.object(banner, "detail_copy_for", return_value=_fixture()) as m:
        out = generate_v5(hero.image_path, "딸기 라떼", purpose=AdPurpose.BANNER,
                          hero_asset=hero, output_dir=str(tmp_path / "o"))
    m.assert_called()
    assert len(out.outputs) >= 1
    assert all(Image.open(p).convert("RGB").size[0] > 0 for p in out.outputs)


def test_banner_palette_follows_style(tmp_path):
    ha, hb = _hero(tmp_path / "bp", "pop"), _hero(tmp_path / "be", "editorial")
    with patch.object(banner, "detail_copy_for", return_value=_fixture()):
        oa = generate_v5(ha.image_path, "딸기 라떼", purpose=AdPurpose.BANNER,
                         hero_asset=ha, output_dir=str(tmp_path / "oa"))
        ob = generate_v5(hb.image_path, "딸기 라떼", purpose=AdPurpose.BANNER,
                         hero_asset=hb, output_dir=str(tmp_path / "ob"))
    sa = Image.open(oa.outputs[0]).convert("RGB")
    sb = Image.open(ob.outputs[0]).convert("RGB")
    assert ImageChops.difference(sa, sb).getbbox() is not None
