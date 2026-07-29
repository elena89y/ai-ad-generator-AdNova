from pathlib import Path

from PIL import Image, ImageChops, ImageDraw
import pytest

from app.schemas.ads import AdPurpose
from app.services.pipeline_v5 import generate_v5
from app.services.pipeline_v5.formats.cardnews import DEFAULT_CTA_LABEL, DEFAULT_CTA_TITLE, SLIDE_COUNT
from app.services.pipeline_v5.hero import DetailCut, DetailCutRole, hero_from_existing


def _cuts(tmp_path):
    cuts = []
    for index, role in enumerate(DetailCutRole):
        path = tmp_path / f"{role.value}.png"
        image = Image.new("RGB", (820, 940), (225 - index * 18, 220, 205 + index * 9))
        draw = ImageDraw.Draw(image)
        draw.ellipse((40 + index * 115, 70 + index * 85, 250 + index * 115, 310 + index * 85), fill=(50 + index * 28, 80, 120))
        draw.rectangle((index * 65, 700 - index * 90, 280 + index * 65, 850 - index * 90), fill=(135, 55 + index * 24, 75))
        image.save(path)
        cuts.append(DetailCut(str(path), role))
    return tuple(cuts)


def _render(tmp_path, cuts):
    hero = hero_from_existing(
        cuts[0].image_path,
        headline="시그니처 라떼",
        subcopy="부드러운 한 잔의 여유",
        detail_cuts=cuts,
    )
    return generate_v5(
        cuts[0].image_path,
        "라떼",
        purpose=AdPurpose.CARD_NEWS,
        hero_asset=hero,
        output_dir=str(tmp_path / "out"),
    )


def test_cardnews_renders_four_distinct_slides(tmp_path):
    result = _render(tmp_path, _cuts(tmp_path))
    assert len(result.outputs) == SLIDE_COUNT
    images = [Image.open(path).convert("RGB") for path in result.outputs]
    assert all(image.size == (1080, 1350) for image in images)
    assert all(ImageChops.difference(images[0], image).getbbox() for image in images[1:])


def test_cardnews_reuses_detail_role_validation(tmp_path):
    cuts = _cuts(tmp_path)[:-1]
    with pytest.raises(ValueError, match="lifestyle"):
        _render(tmp_path, cuts)


def test_customer_copy_does_not_expose_internal_slide_language():
    assert DEFAULT_CTA_TITLE == "지금 만나보세요"
    assert DEFAULT_CTA_LABEL == "자세히 보기"
    assert "4장" not in DEFAULT_CTA_TITLE and "슬라이드" not in DEFAULT_CTA_TITLE
