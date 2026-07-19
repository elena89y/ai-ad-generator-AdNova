"""v5 커머스 배너 조판. 히어로 생성과 독립적인 결정론적 CPU 렌더러."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from ..compose import fit_hero
from ..commercial_copy import copy_for
from ..format_spec import FormatSpec
from ..hero import HeroAsset


def render(hero: HeroAsset, spec: FormatSpec, output_dir: str) -> list[str]:
    """매체 규격마다 다른 커머스 문법으로 히어로와 카피를 조판한다."""
    img = Image.open(hero.image_path).convert("RGB")
    mask = _load_mask(hero.mask_path)
    canvas = fit_hero(img, spec, mask=mask).convert("RGB")
    copy = copy_for(hero)
    renderers = {
        "commerce_wide": _render_wide,
        "commerce_square": _render_square,
        "smartstore_detail": _render_catalog,
        "commerce_vertical": _render_vertical,
    }
    canvas = renderers.get(spec.label, _render_vertical)(canvas, copy, spec)
    cw, ch = canvas.size
    out = str(Path(output_dir) / f"banner_{cw}x{ch}_{spec.label}.jpg")
    canvas.save(out, quality=92)
    return [out]


def _render_wide(canvas, copy, spec):
    cw, ch = canvas.size
    panel_w = int(cw * .39)
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle((0, 0, panel_w, ch), fill=(35, 55, 167, 246))
    margin = int(ch * spec.safe_margin)
    draw.text((margin, margin), copy.product_name or "ADNOVA SELECT", font=_font("medium", 24), fill=(205, 214, 255))
    lines, font = _fit_headline(copy.headline, panel_w - margin * 2, 62, 34)
    y = int(ch * .30)
    for line in lines:
        draw.text((margin, y), line, font=font, fill="white"); y += _line_height(font)
    _cta_pill(canvas, copy.cta, _font("bold", 22), (margin, int(ch * .72)), fill=(255, 255, 255), fg=(35, 55, 167))
    draw.text((cw - margin - 40, ch - margin - 24), "WIDE", font=_font("medium", 18), fill="white")
    return canvas


def _render_square(canvas, copy, spec):
    cw, ch = canvas.size
    draw = ImageDraw.Draw(canvas, "RGBA")
    margin = int(cw * spec.safe_margin)
    draw.rectangle((0, 0, cw, 92), fill=(248, 247, 243, 240))
    draw.text((margin, 31), copy.product_name or "SIGNATURE", font=_font("bold", 22), fill=(24, 24, 24))
    panel_y = int(ch * .72)
    draw.rectangle((0, panel_y, cw, ch), fill=(248, 247, 243, 244))
    lines, font = _fit_headline(copy.headline, cw - margin * 2, 54, 31)
    y = panel_y + 45
    for line in lines:
        draw.text((margin, y), line, font=font, fill=(22, 22, 22)); y += _line_height(font)
    draw.line((cw - margin - 110, 46, cw - margin, 46), fill=(43, 63, 187), width=4)
    return canvas


def _render_catalog(canvas, copy, spec):
    cw, ch = canvas.size
    draw = ImageDraw.Draw(canvas, "RGBA")
    margin = int(cw * spec.safe_margin)
    draw.rectangle((0, 0, cw, 108), fill=(255, 255, 255, 244))
    draw.text((margin, 35), copy.product_name or "상품", font=_font("bold", 25), fill=(24, 24, 24))
    draw.rectangle((0, ch - 150, cw, ch), fill=(255, 255, 255, 244))
    draw.text((margin, ch - 108), copy.headline, font=_fit_headline(copy.headline, cw - margin * 2, 38, 25)[1], fill=(24, 24, 24))
    draw.text((cw - margin - 98, 38), "DETAIL", font=_font("medium", 18), fill=(43, 63, 187))
    return canvas


def _render_vertical(canvas, copy, spec):
    cw, ch = canvas.size
    canvas = _directional_scrim(canvas, wide=False, frac=.44)
    draw = ImageDraw.Draw(canvas)
    margin = int(min(cw, ch) * spec.safe_margin)
    text_width = int(cw * .84)
    max_font = int(min(ch * .10, cw * .10))
    min_font = max(24, int(min(cw, ch) * 0.035))
    lines, head_font = _fit_headline(copy.headline, text_width, max_font, min_font)
    line_height = _line_height(head_font)
    cta_font = _font("bold", max(20, int(min(cw, ch) * 0.040)))
    cta_height = _cta_size(copy.cta, cta_font)[1]
    head_y = ch - margin - cta_height - int(min(cw, ch) * .04) - line_height * len(lines)
    kicker_font = _font("medium", max(18, int(min(cw, ch) * .028)))
    draw.text((margin, head_y - _line_height(kicker_font) - 10), copy.product_name or "SIGNATURE",
              font=kicker_font, fill=(205, 214, 255))
    for line in lines:
        draw.text((margin, head_y), line, font=head_font, fill=(255, 255, 255))
        head_y += line_height
    _cta_pill(canvas, copy.cta, cta_font, xy=(margin, head_y + int(line_height * .24)), fill=(43, 63, 187), fg="white")
    return canvas


def _font(kind: str, size: int):
    fonts = Path(__file__).resolve().parents[4] / "assets" / "fonts"
    name = "Pretendard-Bold.otf" if kind == "bold" else "Pretendard-Medium.otf"
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


def _fit_headline(text: str, max_width: int, max_size: int,
                  min_size: int) -> tuple[list[str], ImageFont.ImageFont]:
    clean = " ".join((text or "광고 이미지").split())
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for size in range(max_size, min_size - 1, -2):
        font = _font("bold", size)
        if probe.textbbox((0, 0), clean, font=font)[2] <= max_width:
            return [clean], font
        lines = _split_two_lines(clean)
        if len(lines) == 2 and all(
            probe.textbbox((0, 0), line, font=font)[2] <= max_width for line in lines
        ):
            return lines, font
    font = _font("bold", min_size)
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


def _cta_size(text: str, font, pad: int = 20) -> tuple[int, int]:
    left, top, right, bottom = font.getbbox(text)
    return right - left + 2 * pad, bottom - top + int(pad * 1.2)


def _cta_pill(img: Image.Image, text: str, font, xy: tuple[int, int],
              pad: int = 20, fill=(255, 255, 255), fg=(20, 20, 20)) -> None:
    draw = ImageDraw.Draw(img)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    tw, th = right - left, bottom - top
    x, y = xy
    box = [x, y, x + tw + 2 * pad, y + th + int(pad * 1.2)]
    radius = (box[3] - box[1]) // 2
    draw.rounded_rectangle(box, radius=radius, fill=fill)
    draw.text((x + pad, y + int(pad * 0.6)), text, font=font, fill=fg)


def _load_mask(mask_path: Optional[str]) -> Optional[Image.Image]:
    if mask_path and Path(mask_path).is_file():
        return Image.open(mask_path).convert("L")
    return None
