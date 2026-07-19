"""국내 광고 문법 기반 결정론적 타이포 조판.

생성 모델은 글자를 그리지 않고, 이 모듈이 검증된 한글 폰트로 마지막 레이어만 렌더한다.
`enabled=False`는 원본 픽셀을 그대로 저장해 프론트 타이포 토글의 백엔드 계약으로 사용한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw

from . import overlay_service
from .reference_recipe import CommercialLayout
from .reference_recipe_data import COMMERCIAL_LAYOUTS


@dataclass(frozen=True)
class CommercialCopy:
    """광고 조판에 필요한 구조화 카피. 빈 필드는 해당 레이어를 생략한다."""

    headline: str
    subcopy: str = ""
    brand_label: str = ""
    kicker: str = ""
    cta: str = ""

    def __post_init__(self) -> None:
        if not self.headline.strip():
            raise ValueError("CommercialCopy.headline 비어있음")


@dataclass(frozen=True)
class TypographyRenderResult:
    """한 히어로에서 만든 OFF/ON 변형과 현재 선택 경로."""

    without_typography_path: str
    with_typography_path: str
    selected_image_path: str
    typography_enabled: bool
    layout_key: str


_COPY_ERROR_MARKERS = ("제공되지 않", "이미지 정보", "이미지 설명", "알 수 없")
_COPY_LIMITS = {"headline": 16, "subcopy": 22, "brand_label": 24, "kicker": 12, "cta": 12}
_AD_PUNCTUATION = str.maketrans("", "", ".,!?:;。．，！？?…")
_EXPLANATORY_SUBCOPY = ("테이블 위", "이미지 속", "한 잔의", "완성합니다", "선사합니다")
_AUTO_LAYOUT = "kr_single_hero"
_SINGLE_LAYOUTS = ("kr_hero_top_left", "kr_hero_top_center", "kr_hero_bottom_left")
_DIAGONAL_LAYOUT = "kr_diagonal_band"


def _safe_line(value: str, limit: int) -> str:
    """모델 응답의 개행·연속 공백을 제거하고 조판 가능한 길이로 제한한다."""
    line = " ".join((value or "").split()).translate(_AD_PUNCTUATION).strip()
    if len(line) <= limit:
        return line
    return line[:limit].rstrip()


def commercial_copy_from_text(
    copy_text: str,
    product_name: str,
    *,
    brand_label: str = "",
    kicker: str = "",
    cta: str = "",
) -> CommercialCopy:
    """기존 FR-09 `헤드라인\n서브카피`를 안전한 구조화 카피로 변환한다."""
    lines = [line.strip() for line in (copy_text or "").splitlines() if line.strip()]
    headline = lines[0] if lines else product_name.strip()
    subcopy = " ".join(lines[1:])
    if not headline or any(marker in headline for marker in _COPY_ERROR_MARKERS):
        headline, subcopy = product_name.strip(), ""
    if not headline:
        raise ValueError("copy_text와 product_name 모두 비어있음")
    # 장면 캡션처럼 긴 설명은 국내 단일 히어로 레퍼런스의 짧은 위계와 맞지 않아 생략한다.
    if len(subcopy) > _COPY_LIMITS["subcopy"] or any(p in subcopy for p in _EXPLANATORY_SUBCOPY):
        subcopy = ""
    return CommercialCopy(
        headline=_safe_line(headline, _COPY_LIMITS["headline"]),
        subcopy=_safe_line(subcopy, _COPY_LIMITS["subcopy"]),
        brand_label=_safe_line(brand_label, _COPY_LIMITS["brand_label"]),
        kicker=_safe_line(kicker, _COPY_LIMITS["kicker"]),
        cta=_safe_line(cta, _COPY_LIMITS["cta"]),
    )


def _bottom_is_bright(image: Image.Image) -> bool:
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    band = gray[int(gray.shape[0] * 0.76):]
    return bool(float(band.mean()) > 150)


def _draw_footer(image: Image.Image, copy: CommercialCopy,
                 token: overlay_service.TypographyToken) -> Image.Image:
    """하단 브랜드·CTA 위계. 제품을 가리지 않도록 바닥 안전영역에만 그린다."""
    if not copy.brand_label and not copy.cta:
        return image

    w, h = image.size
    draw = ImageDraw.Draw(image)
    margin = int(w * 0.067)
    y = int(h * 0.895)
    color = overlay_service.DARK if _bottom_is_bright(image) else overlay_service.IVORY
    body = overlay_service._font(token.body_font, max(14, int(h * 0.019)))

    if copy.brand_label:
        brand = copy.brand_label.upper() if copy.brand_label.isascii() else copy.brand_label
        overlay_service._spaced_text(
            draw, (margin, y), brand, body, color, spacing_frac=token.body_spacing,
        )

    if copy.cta:
        cta_font = overlay_service._fit_spaced_font(
            draw, copy.cta, token.body_font, max(14, int(h * 0.018)),
            w * 0.28, token.body_spacing,
        )
        text_w = overlay_service._spaced_width(draw, copy.cta, cta_font, token.body_spacing)
        pad_x, pad_y = int(w * 0.016), int(h * 0.008)
        x1 = w - margin
        x0 = int(x1 - text_w - 2 * pad_x)
        box = (x0, y - pad_y, x1, y + cta_font.size + pad_y)
        draw.rounded_rectangle(box, radius=max(3, int(cta_font.size * 0.45)), fill=token.accent)
        overlay_service._spaced_text(
            draw, (x0 + pad_x, y), copy.cta, cta_font, overlay_service.DARK,
            spacing_frac=token.body_spacing,
        )
    return image


def _region_clutter(gray: np.ndarray, box: tuple[float, float, float, float]) -> float:
    """카피 후보 영역의 질감·에지 양. 낮을수록 글자를 놓기 좋은 여백이다."""
    h, w = gray.shape
    x0, y0, x1, y1 = box
    crop = gray[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]
    if crop.size == 0:
        return float("inf")
    gx = np.abs(np.diff(crop, axis=1)).mean() if crop.shape[1] > 1 else 0.0
    gy = np.abs(np.diff(crop, axis=0)).mean() if crop.shape[0] > 1 else 0.0
    return float(crop.std() * 0.35 + gx + gy)


def select_typography_layout(image: Image.Image) -> str:
    """국내 단일 히어로 레퍼런스의 3개 카피존 중 가장 조용한 영역을 고른다."""
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    candidates = {
        "kr_hero_top_left": (0.05, 0.05, 0.62, 0.34),
        "kr_hero_top_center": (0.16, 0.04, 0.84, 0.30),
        "kr_hero_bottom_left": (0.05, 0.68, 0.68, 0.91),
    }
    return min(candidates, key=lambda key: _region_clutter(gray, candidates[key]))


def _commercial_token(style_key: str) -> overlay_service.TypographyToken:
    """레퍼런스 공통값: 굵은 산세리프, 정상 자간, 장식요소 없음."""
    import dataclasses

    return dataclasses.replace(
        overlay_service.get_typography_token(style_key),
        head_latin="anton", head_korean="pretendard_black",
        body_font="pretendard_bold", letter_spacing=0.0, body_spacing=0.0,
        head_weight=900, body_weight=700, accent_element="none",
    )


def _draw_reference_hierarchy(image: Image.Image, copy: CommercialCopy,
                              token: overlay_service.TypographyToken,
                              layout_key: str) -> Image.Image:
    """국내 카페 광고 실측의 상단 좌측·상단 중앙·하단 좌측 위계를 렌더한다."""
    w, h = image.size
    base = image.convert("RGBA")
    text_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(text_layer)
    center = layout_key == "kr_hero_top_center"
    bottom = layout_key == "kr_hero_bottom_left"
    x = int(w * 0.067)
    y = int(h * (0.70 if bottom else 0.075))
    max_w = w * (0.86 if center else 0.70)
    center_x = w / 2 if center else None
    color = overlay_service.DARK if overlay_service._bg_is_bright(
        image, y_frac=0.78 if bottom else 0.20,
    ) else overlay_service.IVORY

    if copy.kicker:
        kicker_font = overlay_service._fit_spaced_font(
            draw, copy.kicker, token.body_font, max(15, int(h * 0.020)), max_w, 0.0,
        )
        overlay_service._spaced_text(
            draw, (x, y), copy.kicker, kicker_font, (*color, 160),
            spacing_frac=0.0, anchor_center_x=center_x,
        )
        y += int(h * 0.040)

    headline = copy.headline.upper() if copy.headline.isascii() else copy.headline
    kind = token.head_latin if headline.isascii() else token.head_korean
    target = int(h * (0.078 if center else 0.070))
    font = overlay_service._fit_spaced_font(draw, headline, kind, target, max_w, 0.0)
    overlay_service._spaced_text(
        draw, (x, y), headline, font, (*color, 220),
        spacing_frac=0.0, anchor_center_x=center_x,
    )
    y += int(font.size * 1.18)

    if copy.subcopy:
        sub_font = overlay_service._fit_spaced_font(
            draw, copy.subcopy, token.body_font, max(15, int(h * 0.024)), max_w, 0.0,
        )
        overlay_service._spaced_text(
            draw, (x, y), copy.subcopy, sub_font, (*color, 178),
            spacing_frac=0.0, anchor_center_x=center_x,
        )
    return Image.alpha_composite(base, text_layer).convert("RGB")


def _draw_diagonal_hierarchy(image: Image.Image, copy: CommercialCopy) -> Image.Image:
    """사선 컬러띠 레퍼런스의 우하단 세리프 위계. 장식선과 긴 설명은 쓰지 않는다."""
    w, h = image.size
    base = image.convert("RGBA")
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    headline = copy.headline.upper() if copy.headline.isascii() else copy.headline
    kind = "didone" if headline.isascii() else "maru_bold"
    font = overlay_service._fit_spaced_font(draw, headline, kind, int(h * 0.055), w * 0.46, 0.0)
    x, y = int(w * 0.50), int(h * 0.72)
    overlay_service._spaced_text(
        draw, (x, y), headline, font, (*overlay_service.DARK, 224), spacing_frac=0.0,
    )
    if copy.subcopy:
        body = overlay_service._fit_spaced_font(
            draw, copy.subcopy, "maru_regular", int(h * 0.022), w * 0.44, 0.0,
        )
        overlay_service._spaced_text(
            draw, (x, y + int(font.size * 1.18)), copy.subcopy, body,
            (*overlay_service.DARK, 170), spacing_frac=0.0,
        )
    return Image.alpha_composite(base, layer).convert("RGB")


def render_commercial_poster(
    image_path: str,
    output_path: str,
    copy: CommercialCopy,
    *,
    enabled: bool = True,
    layout_key: str = "kr_single_hero",
    style_key: str = "editorial",
) -> str:
    """타이포 토글을 적용해 광고 이미지를 저장한다.

    현재 MVP는 사용자 입력 상품 1장 계약이므로 single hero만 렌더한다. 여러 상품 원본이
    필요한 lineup은 계약만 존재하고 여기서 침묵 폴백하지 않는다.
    """
    try:
        layout: CommercialLayout = COMMERCIAL_LAYOUTS[layout_key]
    except KeyError as exc:
        raise ValueError(f"등록되지 않은 commercial layout: {layout_key}") from exc
    if layout.product_count != "single":
        raise ValueError(f"단일 상품 renderer에 사용할 수 없는 layout: {layout_key}")

    image = Image.open(image_path).convert("RGB")
    if enabled:
        resolved_layout = select_typography_layout(image) if layout_key == _AUTO_LAYOUT else layout_key
        if resolved_layout == _DIAGONAL_LAYOUT:
            image = _draw_diagonal_hierarchy(image, copy)
        else:
            token = _commercial_token(style_key)
            image = _draw_reference_hierarchy(image, copy, token, resolved_layout)
            image = _draw_footer(image, copy, token)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, format="PNG")
    return str(out)


def render_typography_variants(
    image_path: str,
    output_dir: str,
    copy_text: str,
    product_name: str,
    *,
    typography_enabled: bool,
    layout_key: str = "kr_single_hero",
    style_key: str = "editorial",
    brand_label: str = "",
    kicker: str = "",
    cta: str = "",
) -> TypographyRenderResult:
    """GPU 재생성 없이 OFF/ON을 함께 만들고 토글에 맞는 경로를 선택한다."""
    copy = commercial_copy_from_text(
        copy_text, product_name, brand_label=brand_label, kicker=kicker, cta=cta,
    )
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(image_path).stem
    source = Image.open(image_path).convert("RGB")
    resolved_layout = select_typography_layout(source) if layout_key == _AUTO_LAYOUT else layout_key
    off_path = out_dir / f"{stem}_typography_off.png"
    on_path = out_dir / f"{stem}_typography_on.png"
    render_commercial_poster(
        image_path, str(off_path), copy, enabled=False,
        layout_key=layout_key, style_key=style_key,
    )
    render_commercial_poster(
        image_path, str(on_path), copy, enabled=True,
        layout_key=resolved_layout, style_key=style_key,
    )
    selected = on_path if typography_enabled else off_path
    return TypographyRenderResult(
        without_typography_path=str(off_path),
        with_typography_path=str(on_path),
        selected_image_path=str(selected),
        typography_enabled=typography_enabled,
        layout_key=resolved_layout,
    )
