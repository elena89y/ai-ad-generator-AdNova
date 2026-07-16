from __future__ import annotations

import hashlib

import numpy as np
from PIL import Image

from app.services import overlay_service


EXPECTED_STYLES = {
    "editorial",
    "pop",
    "realism",
    "pastel_float",
    "monotone",
    "warm_vintage",
}


def test_typography_tokens_cover_six_styles() -> None:
    assert set(overlay_service.TYPOGRAPHY_TOKENS) == EXPECTED_STYLES
    for token in overlay_service.TYPOGRAPHY_TOKENS.values():
        assert token.head_weight in {500, 600, 700, 800, 900}
        assert token.body_weight in {300, 400, 500, 600}
        assert token.align in {"left", "center"}
        assert token.accent_element in {"chip", "hairline", "rule"}
        assert token.head_size > token.body_size * 2


def test_pop_uses_curated_klein_blue_duo() -> None:
    token = overlay_service.get_typography_token("pop")
    assert token.palette[:2] == ("#2B3FBB", "#F2ECE3")
    assert token.head_korean == "pretendard_black"
    assert token.accent_element == "chip"


def test_every_token_font_is_bundled() -> None:
    for token in overlay_service.TYPOGRAPHY_TOKENS.values():
        for kind in {token.head_latin, token.head_korean, token.body_font}:
            font = overlay_service._font(kind, 32)
            assert font.size == 32


def test_complex_background_gets_scrim_but_flat_background_does_not() -> None:
    flat = Image.new("RGB", (320, 320), (43, 63, 187))
    checker = np.indices((320, 320)).sum(axis=0) % 2 * 255
    busy = Image.fromarray(np.stack([checker, checker, checker], axis=-1).astype(np.uint8))
    assert not overlay_service._needs_readability_scrim(flat)
    assert overlay_service._needs_readability_scrim(busy)


def test_style_layout_is_deterministic_and_opt_in(tmp_path) -> None:
    src = tmp_path / "bg.png"
    out_a = tmp_path / "a.png"
    out_b = tmp_path / "b.png"
    Image.new("RGB", (640, 640), (43, 63, 187)).save(src)

    kwargs = {
        "image_path": str(src),
        "headline": "오늘은, 더블로 간다",
        "subcopy": "두 배 두꺼운 패티의 정면승부",
        "kicker": "NEW MENU",
        "layout": "style",
        "style_key": "pop",
    }
    overlay_service.apply_food_poster(**kwargs, output_path=str(out_a))
    overlay_service.apply_food_poster(**kwargs, output_path=str(out_b))

    assert hashlib.sha256(out_a.read_bytes()).digest() == hashlib.sha256(out_b.read_bytes()).digest()
    assert out_a.read_bytes() != src.read_bytes()


def test_unknown_style_falls_back_to_editorial() -> None:
    assert overlay_service.get_typography_token("missing").key == "editorial"
