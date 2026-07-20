"""v5 판매 상세페이지: 서로 다른 상품 사진 5컷 이상을 요구한다."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..format_spec import FormatSpec
from ..hero import DetailCut, DetailCutRole, HeroAsset
from ..commercial_copy import copy_for

MIN_UNIQUE_CUTS = 5
REQUIRED_ROLES = tuple(DetailCutRole)
MAX_STRUCTURE_CORRELATION = 0.84
DEFAULT_CTA_TITLE = "지금 만나보세요"
DEFAULT_CTA_LABEL = "자세히 보기"

# 도메인 무관 문구(2026-07-20, ROUTING-001): "한 잔" 등 음료 전용 표현이 하드코딩돼 있어
#   음식/사물 상세페이지에서도 그대로 나갔다. hero.domain(food|drink|object) 기준으로 분기.
_TOP_VIEW_LABELS = {
    "food": "위에서 보는 플레이팅",
    "drink": "위에서 만나는 한 잔",
    "object": "위에서 보는 디테일",
}


def render(hero: HeroAsset, spec: FormatSpec, output_dir: str) -> list[str]:
    cuts = {cut.role: cut.image_path for cut in _select_role_cuts(hero)}
    width = spec.canvas[0]
    margin = int(width * spec.safe_margin)
    heights = (940, 390, 760, 720, 650, 820, 320)
    total_h = sum(heights)
    canvas = Image.new("RGB", (width, total_h), "white")
    y = 0

    hero_section = _cover(Image.open(cuts[DetailCutRole.HERO]).convert("RGB"), (width, heights[0]))
    canvas.paste(hero_section, (0, y)); _title_overlay(canvas, hero, y, heights[0], width); y += heights[0]
    _story(canvas, hero, y, heights[1], margin, width); y += heights[1]

    top = _cover(Image.open(cuts[DetailCutRole.TOP_VIEW]).convert("RGB"), (width, heights[2]))
    top_view_label = _TOP_VIEW_LABELS.get(hero.domain, _TOP_VIEW_LABELS["food"])
    canvas.paste(top, (0, y)); _section_label(canvas, y, "01", top_view_label, light=False); y += heights[2]

    closeup = _cover(Image.open(cuts[DetailCutRole.TEXTURE_CLOSEUP]).convert("RGB"), (width, heights[3]))
    canvas.paste(closeup, (0, y)); _section_label(canvas, y, "02", "가까이 볼수록 선명하게", light=True); y += heights[3]

    _split_section(canvas, cuts[DetailCutRole.SIDE_PROFILE], hero, y, heights[4], width, margin); y += heights[4]

    lifestyle = _cover(Image.open(cuts[DetailCutRole.LIFESTYLE]).convert("RGB"), (width, heights[5]))
    canvas.paste(lifestyle, (0, y)); _lifestyle_overlay(canvas, hero, y, heights[5], width, margin); y += heights[5]

    _cta(canvas, y, heights[6], margin, width)
    out = Path(output_dir) / f"detail_{width}x{total_h}_{spec.label}.jpg"
    canvas.save(out, quality=93)
    return [str(out)]


def _unique_images(paths: tuple[str, ...]) -> list[str]:
    unique, hashes = [], set()
    for value in paths:
        path = Path(value)
        if not path.is_file():
            raise ValueError(f"상세페이지 이미지가 없습니다: {value}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest not in hashes:
            hashes.add(digest)
            unique.append(str(path))
    return unique


def _select_role_cuts(hero: HeroAsset) -> list[DetailCut]:
    """필수 구도 5종을 고정 순서로 선택하고 내용·역할 중복을 거부한다."""
    if not hero.detail_cuts:
        raise ValueError(
            "상세페이지 컷에 구도 역할이 필요합니다: "
            + ", ".join(role.value for role in REQUIRED_ROLES)
        )
    by_role: dict[DetailCutRole, DetailCut] = {}
    hashes: set[str] = set()
    structures: list[tuple[DetailCutRole, np.ndarray]] = []
    for cut in hero.detail_cuts:
        path = Path(cut.image_path)
        if not path.is_file():
            raise ValueError(f"상세페이지 이미지가 없습니다: {cut.image_path}")
        if cut.role in by_role:
            raise ValueError(f"상세페이지 구도 역할이 중복되었습니다: {cut.role.value}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in hashes:
            raise ValueError("같은 이미지 내용을 서로 다른 상세페이지 구도로 사용할 수 없습니다")
        structure = _structure_vector(path)
        for existing_role, existing in structures:
            # 동일 상품의 기본 히어로와 정면 측면컷은 실루엣이 유사할 수 있다.
            # 역할·파일 중복은 별도 게이트로 막고 이 정상 조합만 구조 비교에서 제외한다.
            if {existing_role, cut.role} == {DetailCutRole.HERO, DetailCutRole.SIDE_PROFILE}:
                continue
            if _correlation(existing, structure) >= MAX_STRUCTURE_CORRELATION:
                raise ValueError(
                    f"상세페이지 구도가 너무 유사합니다: {existing_role.value}, {cut.role.value}"
                )
        hashes.add(digest)
        structures.append((cut.role, structure))
        by_role[cut.role] = cut
    missing = [role.value for role in REQUIRED_ROLES if role not in by_role]
    if missing:
        raise ValueError("상세페이지 필수 구도가 부족합니다: " + ", ".join(missing))
    return [by_role[role] for role in REQUIRED_ROLES]


def _structure_vector(path: Path) -> np.ndarray:
    image = Image.open(path).convert("L").resize((32, 32), Image.BILINEAR)
    return np.asarray(image, dtype=np.float32).reshape(-1)


def _correlation(left: np.ndarray, right: np.ndarray) -> float:
    if float(left.std()) < 1e-6 or float(right.std()) < 1e-6:
        return 1.0 if np.allclose(left, right, atol=3.0) else 0.0
    return float(np.corrcoef(left, right)[0, 1])


def _cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    w, h = size
    scale = max(w / image.width, h / image.height)
    resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)
    left, top = (resized.width - w) // 2, (resized.height - h) // 2
    return resized.crop((left, top, left + w, top + h))


def _title_overlay(canvas, hero, y, height, width):
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle((0, y, width, y + 104), fill=(248, 247, 243, 242))
    draw.rectangle((0, y + int(height * .68), width, y + height), fill=(18, 18, 18, 220))
    margin = int(width * .07)
    copy = copy_for(hero)
    draw.text((margin, y + 37), copy.product_name or "ADNOVA SELECT", font=_font(22, True), fill=(24, 24, 24))
    draw.line((width - margin - 100, y + 52, width - margin, y + 52), fill=(43, 63, 187), width=4)
    draw.text((margin, y + int(height * .73)), copy.product_name, font=_font(23, True), fill=(195, 207, 255))
    font = _fit(copy.headline, width - margin * 2, 55, 34)
    draw.text((margin, y + int(height * .79)), copy.headline, font=font, fill="white")


def _story(canvas, hero, y, height, margin, width):
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, y, width, y + height), fill=(245, 243, 238))
    copy = copy_for(hero)
    draw.text((margin, y + 64), "PRODUCT STORY", font=_font(20, True), fill=(43, 63, 187))
    font = _fit(copy.headline, width - margin * 2, 43, 29)
    draw.text((margin, y + 118), copy.headline, font=font, fill=(25, 25, 25))
    if copy.subcopy:
        draw.text((margin, y + 205), copy.subcopy, font=_fit(copy.subcopy, width - margin * 2, 26, 20), fill=(90, 90, 90))
    draw.line((margin, y + height - 56, width - margin, y + height - 56), fill=(190, 187, 180), width=1)


def _section_label(canvas, y, number, title, light):
    draw = ImageDraw.Draw(canvas, "RGBA")
    fill = (248, 247, 243, 232) if light else (18, 18, 18, 205)
    text = (24, 24, 24) if light else (255, 255, 255)
    draw.rectangle((44, y + 42, 520, y + 145), fill=fill)
    draw.text((68, y + 67), number, font=_font(20, True), fill=(43, 63, 187))
    draw.text((128, y + 63), title, font=_font(27, True), fill=text)


def _split_section(canvas, path, hero, y, height, width, margin):
    image_w = int(width * .56)
    canvas.paste(_cover(Image.open(path).convert("RGB"), (image_w, height)), (0, y))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((image_w, y, width, y + height), fill=(35, 55, 167))
    x = image_w + margin
    draw.text((x, y + 85), "03 / PROFILE", font=_font(19, True), fill=(195, 207, 255))
    draw.text((x, y + 150), "형태까지\n또렷하게", font=_font(39, True), fill="white", spacing=8)
    copy = copy_for(hero)
    if copy.subcopy:
        draw.text((x, y + 310), copy.subcopy, font=_fit(copy.subcopy, width - x - margin, 23, 18), fill=(230, 233, 255))


def _lifestyle_overlay(canvas, hero, y, height, width, margin):
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle((0, y + int(height * .67), width, y + height), fill=(18, 18, 18, 205))
    copy = copy_for(hero)
    draw.text((margin, y + int(height * .72)), "04 / MOMENT", font=_font(20, True), fill=(195, 207, 255))
    draw.text((margin, y + int(height * .79)), copy.headline, font=_fit(copy.headline, width - margin * 2, 43, 29), fill="white")


def _cta(canvas, y, height, margin, width):
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, y, width, y + height), fill=(22, 22, 22))
    draw.text((margin, y + 62), DEFAULT_CTA_TITLE, font=_font(36, True), fill="white")
    draw.rectangle((margin, y + 172, margin + 220, y + 238), fill=(43, 63, 187))
    draw.text((margin + 34, y + 190), DEFAULT_CTA_LABEL, font=_font(23, True), fill="white")


def _font(size, bold=False):
    root = Path(__file__).resolve().parents[4] / "assets" / "fonts"
    return ImageFont.truetype(str(root / ("Pretendard-Bold.otf" if bold else "Pretendard-Medium.otf")), size)


def _fit(text, max_width, start, minimum):
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for size in range(start, minimum - 1, -2):
        font = _font(size, True)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
    return _font(minimum, True)


def _height(font):
    box = font.getbbox("가Ag")
    return int((box[3] - box[1]) * 1.25)
