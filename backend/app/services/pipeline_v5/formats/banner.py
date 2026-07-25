"""v5 커머스 배너 조판. 히어로 생성과 독립적인 결정론적 CPU 렌더러.

v6-1 L4(2026-07-23) 소프트코딩(하이브리드):
  - wide/square/smartstore_detail(정적 좌표) → layouts/banner.yaml + layout_engine.
  - commerce_vertical(하단 역산·동적 폰트=절차적) → 여기 _render_vertical 코드 유지.
  카피는 detail_copy_for(F1): intro_headline(후킹) + cta_label(상품별). 팔레트=hero.style(D4).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from ..commercial_copy import DetailPageCopy, detail_copy_for
from ..compose import fit_hero
from ..format_spec import FormatSpec
from ..hero import HeroAsset
from ..layout_engine import load_layout, render_elements
from ..palette import palette


def render(hero: HeroAsset, spec: FormatSpec, output_dir: str) -> list[str]:
    """매체 규격마다 다른 커머스 문법으로 히어로와 카피를 조판한다."""
    img = Image.open(hero.image_path).convert("RGB")
    mask = _load_mask(hero.mask_path)
    canvas = fit_hero(img, spec, mask=mask).convert("RGB")
    copy = detail_copy_for(hero)
    pal = palette(hero.style)
    cw, ch = canvas.size
    if spec.label == "commerce_vertical":
        canvas = _render_vertical(canvas, copy, pal, spec, hero.style)  # 절차적 — 코드 유지
    else:
        layout = load_layout("banner")[spec.label]
        basis = ch if layout["margin_basis"] == "ch" else cw
        margin = int(basis * spec.safe_margin)
        ctx = {"domain": hero.domain, "density": spec.copy_density, "style": hero.style}  # L5/폰트 적응
        render_elements(canvas, layout["elements"], copy, pal, cw, ch, margin, ctx)
    cw, ch = canvas.size
    out = str(Path(output_dir) / f"banner_{cw}x{ch}_{spec.label}.jpg")
    canvas.save(out, quality=92)
    return [out]


def _render_vertical(canvas, copy: DetailPageCopy, pal, spec, style=None):
    # 2026-07-24: CTA 버튼(pill) 제거(사용자 요청). 헤드라인 폰트=스타일 원장(head_font).
    from ..layout_engine import _style_font_file
    ff = _style_font_file({"style": style}, "head") if style else None
    cw, ch = canvas.size
    canvas = _directional_scrim(canvas, wide=False, frac=.44)
    draw = ImageDraw.Draw(canvas)
    margin = int(min(cw, ch) * spec.safe_margin)
    text_width = int(cw * .84)
    max_font = int(min(ch * .10, cw * .10))
    min_font = max(24, int(min(cw, ch) * 0.035))
    lines, head_font = _fit_headline(copy.intro_headline, text_width, max_font, min_font, font_file=ff)
    line_height = _line_height(head_font)
    head_y = ch - margin - line_height * len(lines)
    kicker_font = _font("medium", max(18, int(min(cw, ch) * .028)))
    draw.text((margin, head_y - _line_height(kicker_font) - 10), copy.product_name or "SIGNATURE",
              font=kicker_font, fill=pal["tint"])
    for line in lines:
        draw.text((margin, head_y), line, font=head_font, fill=(255, 255, 255))
        head_y += line_height
    return canvas


def _font(kind: str, size: int, font_file: str | None = None):
    fonts = Path(__file__).resolve().parents[4] / "assets" / "fonts"
    name = font_file or ("Pretendard-Bold.otf" if kind == "bold" else "Pretendard-Medium.otf")
    try:
        return ImageFont.truetype(str(fonts / name), size)
    except Exception:
        return ImageFont.load_default()


def _directional_scrim(img: Image.Image, wide: bool, frac: float = 0.52) -> Image.Image:
    w, h = img.size
    if wide:
        scrim = Image.new("L", (w, 1), 0)
        px = scrim.load()
        end = int(w * frac)
        for x in range(end):
            px[x, 0] = int(190 * (1 - x / max(1, end)))
    else:
        scrim = Image.new("L", (1, h), 0)
        px = scrim.load()
        start = int(h * (1 - frac))
        for y in range(start, h):
            px[0, y] = int(190 * (y - start) / max(1, h - start))
    scrim = scrim.resize((w, h))
    black = Image.new("RGB", (w, h), (0, 0, 0))
    return Image.composite(black, img, scrim)


def _fit_headline(text: str, max_width: int, max_size: int, min_size: int,
                  font_file: str | None = None) -> tuple[list[str], ImageFont.ImageFont]:
    clean = " ".join((text or "광고 이미지").split())
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for size in range(max_size, min_size - 1, -2):
        font = _font("bold", size, font_file)
        if probe.textbbox((0, 0), clean, font=font)[2] <= max_width:
            return [clean], font
        lines = _split_two_lines(clean)
        if len(lines) == 2 and all(
            probe.textbbox((0, 0), line, font=font)[2] <= max_width for line in lines
        ):
            return lines, font
    font = _font("bold", min_size, font_file)
    return [_ellipsize(clean, font, max_width, probe)], font


def _split_two_lines(text: str) -> list[str]:
    words = text.split()
    if len(words) < 2:
        return [text]
    best = min(
        range(1, len(words)),
        key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))),
    )
    return [" ".join(words[:best]), " ".join(words[best:])]


def _ellipsize(text: str, font, max_width: int, draw: ImageDraw.ImageDraw) -> str:
    suffix = "…"
    value = text
    while value and draw.textbbox((0, 0), value + suffix, font=font)[2] > max_width:
        value = value[:-1]
    return (value.rstrip() + suffix) if value else suffix


def _line_height(font) -> int:
    left, top, right, bottom = font.getbbox("가Ag")
    return int((bottom - top) * 1.28)


def _load_mask(mask_path: Optional[str]) -> Optional[Image.Image]:
    if mask_path and Path(mask_path).is_file():
        return Image.open(mask_path).convert("L")
    return None
