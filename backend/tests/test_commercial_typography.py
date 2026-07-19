from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from app.services import overlay_service
from app.services.commercial_typography import (
    CommercialCopy, commercial_copy_from_text, render_commercial_poster,
    render_typography_variants, select_typography_layout,
)
from app.services.generation_service import ProcessedAd, build_typography_variants


def _image(path) -> None:
    Image.new("RGB", (640, 800), (225, 215, 195)).save(path)


def test_typography_toggle_preserves_original_pixels(tmp_path) -> None:
    src, out = tmp_path / "src.png", tmp_path / "off.png"
    _image(src)
    render_commercial_poster(
        str(src), str(out), CommercialCopy("시그니처 라떼"), enabled=False,
    )
    assert np.array_equal(np.asarray(Image.open(src)), np.asarray(Image.open(out)))


def test_single_hero_renders_top_and_bottom_hierarchy(tmp_path) -> None:
    src, out = tmp_path / "src.png", tmp_path / "on.png"
    _image(src)
    render_commercial_poster(
        str(src), str(out),
        CommercialCopy("시그니처 라떼", "오늘의 부드러운 한 잔", "ADNOVA CAFE", "NEW", "지금 만나기"),
        style_key="pop",
    )
    before = np.asarray(Image.open(src), dtype=np.int16)
    after = np.asarray(Image.open(out), dtype=np.int16)
    delta = np.abs(after - before).mean(axis=2)
    assert float(delta[: int(delta.shape[0] * 0.45)].mean()) > 0.8
    assert float(delta[int(delta.shape[0] * 0.82):].mean()) > 1.0


def test_commercial_typography_removes_decorative_top_hairline(tmp_path, monkeypatch) -> None:
    src, out = tmp_path / "src.png", tmp_path / "on.png"
    _image(src)
    captured = {}
    def capture_token(image, copy, token, layout_key):
        captured["accent_element"] = token.accent_element
        return image

    monkeypatch.setattr("app.services.commercial_typography._draw_reference_hierarchy", capture_token)
    render_commercial_poster(
        str(src), str(out), CommercialCopy("ICE 라떼의 정점"), style_key="warm_vintage",
    )
    assert captured["accent_element"] == "none"


def test_layout_selector_chooses_quiet_top_left_region() -> None:
    arr = np.full((800, 640, 3), 220, dtype=np.uint8)
    rng = np.random.default_rng(42)
    arr[:260, 180:] = rng.integers(0, 255, arr[:260, 180:].shape, dtype=np.uint8)
    arr[540:] = rng.integers(0, 255, arr[540:].shape, dtype=np.uint8)
    assert select_typography_layout(Image.fromarray(arr)) == "kr_hero_top_left"


def test_reference_typography_blends_with_background_instead_of_opaque_ink(tmp_path) -> None:
    src, out = tmp_path / "src.png", tmp_path / "on.png"
    Image.new("RGB", (640, 800), (240, 220, 180)).save(src)
    render_commercial_poster(
        str(src), str(out), CommercialCopy("라떼"),
        layout_key="kr_hero_top_center", style_key="warm_vintage",
    )
    arr = np.asarray(Image.open(out))
    # 완전 불투명 DARK(27,24,21)이 아니라 배경과 혼합된 중간색 픽셀이 생긴다.
    changed = arr[np.any(arr != np.array([240, 220, 180]), axis=2)]
    assert changed.size
    assert not np.any(np.all(changed == np.array(overlay_service.DARK), axis=1))


def test_lineup_layout_does_not_silently_render_single_product(tmp_path) -> None:
    src = tmp_path / "src.png"
    _image(src)
    with pytest.raises(ValueError, match="단일 상품 renderer"):
        render_commercial_poster(
            str(src), str(tmp_path / "out.png"), CommercialCopy("여름 신메뉴"),
            layout_key="kr_multi_product_lineup",
        )


def test_commercial_copy_requires_headline() -> None:
    with pytest.raises(ValueError, match="headline"):
        CommercialCopy("  ")


def test_copy_adapter_falls_back_from_error_text() -> None:
    copy = commercial_copy_from_text("이미지 정보가 제공되지 않았습니다\n오류", "카페라떼")
    assert copy.headline == "카페라떼"
    assert copy.subcopy == ""


def test_copy_adapter_normalizes_multiline_and_limits_layout_width() -> None:
    copy = commercial_copy_from_text(
        "  여름을 닮은 아주 길고 길고 긴 시그니처 아이스 카페라떼 헤드라인  \n"
        "첫 번째 설명 문장\n두 번째로 잘못 나온 추가 줄도 하나의 서브카피로 합쳐진다",
        "카페라떼",
        brand_label="  ADNOVA   CAFE  ", kicker="SEASONAL NEW MENU", cta="지금 바로 만나기",
    )
    assert "\n" not in copy.headline and len(copy.headline) <= 16
    assert copy.subcopy == ""
    assert not copy.headline.endswith((".", ",", "!", "?", "…"))
    assert copy.brand_label == "ADNOVA CAFE"
    assert len(copy.kicker) <= 12 and len(copy.cta) <= 12


def test_copy_adapter_removes_terminal_punctuation_and_caption_like_subcopy() -> None:
    copy = commercial_copy_from_text(
        "차갑게 더 깊어진 라떼의 품격.\n테이블 위 한 잔의 ICE 카페 라떼가 완성합니다.",
        "ICE 카페 라떼",
    )
    assert copy.headline == "차갑게 더 깊어진 라떼의 품격"
    assert copy.subcopy == ""


def test_copy_adapter_removes_all_ad_punctuation() -> None:
    copy = commercial_copy_from_text("ICE 라떼의 정점!\n담백하게, 깊게.", "ICE 라떼")
    assert copy.headline == "ICE 라떼의 정점"
    assert copy.subcopy == "담백하게 깊게"


@pytest.mark.parametrize("enabled", [False, True])
def test_variant_result_selects_without_gpu_regeneration(tmp_path, enabled) -> None:
    src = tmp_path / "hero.png"
    _image(src)
    result = render_typography_variants(
        str(src), str(tmp_path / "variants"), "시그니처 라떼\n부드러운 한 잔", "카페라떼",
        typography_enabled=enabled, brand_label="ADNOVA CAFE",
    )
    assert result.selected_image_path == (
        result.with_typography_path if enabled else result.without_typography_path
    )
    assert result.layout_key in {
        "kr_hero_top_left", "kr_hero_top_center", "kr_hero_bottom_left",
    }
    assert Image.open(result.with_typography_path).size == (640, 800)
    assert np.array_equal(
        np.asarray(Image.open(src)), np.asarray(Image.open(result.without_typography_path)),
    )


def test_processed_ad_internal_typography_bridge(tmp_path) -> None:
    src = tmp_path / "hero.png"
    _image(src)
    ad = ProcessedAd(
        final_image_path=str(src), domain="food", engine="test", subject_en="latte",
        copy_text="시그니처 라떼\n부드러운 한 잔", poster=False, seconds=1.0,
        seed=42, style="editorial",
    )
    variants = build_typography_variants(
        ad, "카페라떼", typography_enabled=True,
        output_dir=str(tmp_path / "variants"), brand_label="ADNOVA CAFE",
    )
    assert variants.typography_enabled is True
    assert variants.selected_image_path == variants.with_typography_path
