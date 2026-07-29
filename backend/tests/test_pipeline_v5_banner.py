from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from app.schemas.ads import AdPurpose
from app.services.pipeline_v5 import generate_v5
from app.services.pipeline_v5.format_spec import specs_for
from app.services.pipeline_v5.hero import hero_from_existing


def _hero(tmp_path, *, mask: bool = False):
    src = tmp_path / "hero.png"
    yy, xx = np.mgrid[:900, :900]
    pixels = np.zeros((900, 900, 3), dtype=np.uint8)
    pixels[..., 0] = (xx / 900 * 180 + 40).astype(np.uint8)
    pixels[..., 1] = (yy / 900 * 140 + 50).astype(np.uint8)
    pixels[..., 2] = 90
    Image.fromarray(pixels).save(src)
    mask_path = None
    if mask:
        mask_image = Image.new("L", (900, 900), 0)
        mask_image.paste(255, (590, 260, 850, 760))
        mask_path = tmp_path / "mask.png"
        mask_image.save(mask_path)
    return hero_from_existing(
        str(src), headline="여름을 닮은 시그니처 아이스 카페라떼",
        subcopy="한 잔의 부드러운 균형", domain="cafe",
        mask_path=str(mask_path) if mask_path else None,
    )


def test_banner_pack_renders_every_registered_size(tmp_path) -> None:
    result = generate_v5(
        "unused.png", "카페라떼", purpose=AdPurpose.BANNER,
        hero_asset=_hero(tmp_path, mask=True), output_dir=str(tmp_path / "out"),
    )
    expected = {spec.canvas for spec in specs_for(AdPurpose.BANNER)}
    actual = {Image.open(path).size for path in result.outputs}
    assert actual == expected
    assert len(result.outputs) == 4


def test_banner_size_filter_is_explicit(tmp_path) -> None:
    result = generate_v5(
        "unused.png", "카페라떼", purpose=AdPurpose.BANNER,
        hero_asset=_hero(tmp_path), sizes=["commerce_wide"],
        output_dir=str(tmp_path / "out"),
    )
    assert len(result.outputs) == 1
    assert Image.open(result.outputs[0]).size == (1920, 600)


def test_unknown_banner_size_does_not_render_full_pack(tmp_path) -> None:
    with pytest.raises(ValueError, match="지원하지 않는 규격"):
        generate_v5(
            "unused.png", "카페라떼", purpose=AdPurpose.BANNER,
            hero_asset=_hero(tmp_path), sizes=["print_xbanner"],
            output_dir=str(tmp_path / "out"),
        )


def test_long_unbroken_headline_renders_without_overflow_error(tmp_path) -> None:
    hero = _hero(tmp_path)
    hero.headline = "초초초초초초초초초초초초초초초초초초초초초초초초초초초초긴제목"
    result = generate_v5(
        "unused.png", "상품", purpose=AdPurpose.BANNER, hero_asset=hero,
        sizes=["smartstore_detail"], output_dir=str(tmp_path / "out"),
    )
    assert Image.open(result.outputs[0]).size == (860, 860)
