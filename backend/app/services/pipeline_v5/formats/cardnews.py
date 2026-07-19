"""v5 카드뉴스: 검증된 다구도 상품 컷을 4장 시퀀스로 조판한다."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..format_spec import FormatSpec
from ..hero import DetailCutRole, HeroAsset
from ..commercial_copy import copy_for
from .detail_page import _select_role_cuts

SLIDE_COUNT = 4
DEFAULT_CTA_TITLE = "지금 만나보세요"
DEFAULT_CTA_LABEL = "자세히 보기"


def render(hero: HeroAsset, spec: FormatSpec, output_dir: str) -> list[str]:
    """표지·상품 인상·디테일·CTA를 각기 다른 구도로 만든다."""
    cuts = {cut.role: cut.image_path for cut in _select_role_cuts(hero)}
    size = spec.canvas
    slides = [
        _cover_slide(cuts[DetailCutRole.HERO], hero, size, spec.safe_margin),
        _story_slide(cuts[DetailCutRole.TOP_VIEW], hero, size, spec.safe_margin),
        _detail_slide(
            cuts[DetailCutRole.TEXTURE_CLOSEUP],
            cuts[DetailCutRole.SIDE_PROFILE],
            hero,
            size,
            spec.safe_margin,
        ),
        _cta_slide(cuts[DetailCutRole.LIFESTYLE], hero, size, spec.safe_margin),
    ]

    output = Path(output_dir)
    names = ("cover", "story", "detail", "cta")
    paths: list[str] = []
    for index, (name, slide) in enumerate(zip(names, slides), start=1):
        path = output / f"cardnews_{index:02d}_{name}_{size[0]}x{size[1]}.jpg"
        slide.save(path, quality=93)
        paths.append(str(path))
    return paths


def _cover_slide(path: str, hero: HeroAsset, size: tuple[int, int], margin_ratio: float) -> Image.Image:
    canvas = _cover(Image.open(path).convert("RGB"), size)
    draw = ImageDraw.Draw(canvas, "RGBA")
    w, h = size
    margin = int(w * margin_ratio)
    copy = copy_for(hero)
    draw.rectangle((0, 0, w, 118), fill=(248, 247, 243, 242))
    draw.text((margin, 42), copy.product_name or "ADNOVA SELECT", font=_font(25, True), fill=(24, 24, 24))
    draw.line((w - margin - 120, 59, w - margin, 59), fill=(43, 63, 187), width=5)
    panel_y = int(h * .69)
    draw.rectangle((0, panel_y, w, h), fill=(248, 247, 243, 246))
    font = _fit(copy.headline, w - margin * 2, 68, 40)
    if copy.product_name:
        draw.text((margin, panel_y + 45), "SIGNATURE MENU", font=_font(22, True), fill=(43, 63, 187))
    draw.text((margin, panel_y + 91), copy.headline, font=font, fill=(20, 20, 20))
    if copy.subcopy:
        draw.text((margin, panel_y + 186), copy.subcopy, font=_fit(copy.subcopy, w - margin * 2, 30, 22), fill=(78, 76, 72))
    draw.text((w - margin - 42, h - 64), "01", font=_font(22, True), fill=(120, 118, 112))
    return canvas


def _story_slide(path: str, hero: HeroAsset, size: tuple[int, int], margin_ratio: float) -> Image.Image:
    w, h = size
    copy_w = int(w * .42)
    canvas = Image.new("RGB", size, (35, 55, 167))
    canvas.paste(_cover(Image.open(path).convert("RGB"), (w - copy_w, h)), (copy_w, 0))
    draw = ImageDraw.Draw(canvas)
    margin = int(w * margin_ratio)
    copy = copy_for(hero)
    draw.text((margin, 90), "02", font=_font(24, True), fill=(195, 207, 255))
    draw.text((margin, 175), copy.product_name or "오늘의 메뉴", font=_fit(copy.product_name or "오늘의 메뉴", copy_w - margin * 2, 47, 29), fill="white")
    draw.line((margin, 270, copy_w - margin, 270), fill=(195, 207, 255), width=3)
    title = copy.headline
    for index, line in enumerate(_wrap(title, 10)):
        draw.text((margin, 340 + index * 62), line, font=_font(42, True), fill="white")
    if copy.subcopy:
        for index, line in enumerate(_wrap(copy.subcopy, 12)):
            draw.text((margin, 545 + index * 42), line, font=_font(26), fill=(225, 230, 255))
    draw.text((margin, h - 115), "TOP VIEW", font=_font(20, True), fill=(195, 207, 255))
    return canvas


def _detail_slide(
    closeup_path: str,
    side_path: str,
    hero: HeroAsset,
    size: tuple[int, int],
    margin_ratio: float,
) -> Image.Image:
    w, h = size
    canvas = Image.new("RGB", size, (242, 239, 232))
    canvas.paste(_cover(Image.open(closeup_path).convert("RGB"), (w, int(h * .66))), (0, 0))
    inset_w, inset_h = int(w * .38), int(h * .27)
    inset = _cover(Image.open(side_path).convert("RGB"), (inset_w, inset_h))
    canvas.paste(inset, (int(w * .07), int(h * .69)))
    draw = ImageDraw.Draw(canvas)
    copy = copy_for(hero)
    x = int(w * .51)
    draw.text((x, int(h * .70)), "03 / DETAIL", font=_font(21, True), fill=(43, 63, 187))
    draw.text((x, int(h * .76)), "한 잔의\n디테일", font=_font(46, True), fill=(22, 22, 22), spacing=10)
    if copy.subcopy:
        for index, line in enumerate(_wrap(copy.subcopy, 12)):
            draw.text((x, int(h * .88) + index * 34), line, font=_font(23), fill=(88, 84, 78))
    return canvas


def _cta_slide(path: str, hero: HeroAsset, size: tuple[int, int], margin_ratio: float) -> Image.Image:
    canvas = _cover(Image.open(path).convert("RGB"), size)
    draw = ImageDraw.Draw(canvas, "RGBA")
    w, h = size
    margin = int(w * margin_ratio)
    draw.rectangle((0, 0, w, h), fill=(0, 0, 0, 38))
    draw.rectangle((0, int(h * .65), w, h), fill=(18, 18, 18, 228))
    copy = copy_for(hero)
    draw.text((margin, int(h * .69)), copy.product_name or "SIGNATURE", font=_font(24, True), fill=(195, 207, 255))
    draw.text((margin, int(h * .75)), DEFAULT_CTA_TITLE, font=_font(52, True), fill="white")
    draw.rectangle((margin, int(h * .85), margin + 238, int(h * .85) + 68), fill=(35, 55, 167))
    draw.text((margin + 38, int(h * .85) + 18), DEFAULT_CTA_LABEL, font=_font(25, True), fill="white")
    draw.text((w - margin - 36, h - 62), "04", font=_font(22, True), fill=(170, 170, 170))
    return canvas


def _wrap(text: str, length: int) -> list[str]:
    """짧은 한글 광고 문구를 의미 손상 없이 글자 수 기준으로 나눈다."""
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > length:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:3]


def _cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    w, h = size
    scale = max(w / image.width, h / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    left, top = (resized.width - w) // 2, (resized.height - h) // 2
    return resized.crop((left, top, left + w, top + h))


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    root = Path(__file__).resolve().parents[4] / "assets" / "fonts"
    name = "Pretendard-Bold.otf" if bold else "Pretendard-Medium.otf"
    return ImageFont.truetype(str(root / name), size)


def _fit(text: str, max_width: int, start: int, minimum: int) -> ImageFont.FreeTypeFont:
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for size in range(start, minimum - 1, -2):
        font = _font(size, True)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
    return _font(minimum, True)
