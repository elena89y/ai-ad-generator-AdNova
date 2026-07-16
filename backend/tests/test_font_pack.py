"""P4T 광고 조판 폰트 팩 무결성 — 담당: 한의정."""
from pathlib import Path

import pytest
from PIL import ImageFont


FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
P4T_FONTS = (
    "Pretendard-Light.otf",
    "Pretendard-Medium.otf",
    "Pretendard-Bold.otf",
    "Pretendard-Black.otf",
    "Paperlogy-6SemiBold.ttf",
    "Paperlogy-8ExtraBold.ttf",
    "MaruBuri-Regular.ttf",
    "MaruBuri-Bold.ttf",
    "SpaceGrotesk-Medium.ttf",
    "Anton-Regular.ttf",
)


@pytest.mark.parametrize("name", P4T_FONTS)
def test_p4t_font_loads_with_pillow(name: str):
    path = FONT_DIR / name
    assert path.stat().st_size > 50_000
    font = ImageFont.truetype(str(path), 48)
    assert font.getbbox("AdNova 2026") is not None


def test_p4t_font_licenses_and_official_sources_are_bundled():
    license_text = (FONT_DIR / "OFL-1.1.txt").read_text(encoding="utf-8")
    notices = (FONT_DIR / "FONT_LICENSES.md").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE Version 1.1" in license_text
    for family in ("Pretendard", "Paperlogy", "MaruBuri", "Space Grotesk", "Anton"):
        assert family in notices
    assert "github.com/Freesentation/paperlogy" in notices
    assert "fonts-archive" not in notices
