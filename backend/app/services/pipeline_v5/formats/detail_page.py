"""v5 판매 상세페이지: 서로 다른 상품 사진 5컷 이상을 요구한다.

v6-1 F1(2026-07-21) 고도화:
  - 섹션별 전용 카피(detail_copy_for) — headline 3곳 복붙(D1)·하드코딩 문구(D2)·본문 부재(D3) 해소.
  - 스타일 원장 accent 연동 팔레트(D4) — 남색 고정 제거, 스타일이 다르면 상세 톤도 다르다.
  - 스토리 본문 길이 적응형 높이(D5) + 혜택 불릿 섹션 신설(카피가 있을 때만).
GPT 실패 시 detail_copy_for 폴백이 종전과 같은 문구 구성을 돌려주므로 화면 회귀 없음.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..format_spec import FormatSpec
from ..hero import DetailCut, DetailCutRole, HeroAsset
from ..commercial_copy import DetailPageCopy, detail_copy_for
from ..similarity import MAX_STRUCTURE_CORRELATION, correlation, structure_vector

logger = logging.getLogger(__name__)

MIN_UNIQUE_CUTS = 5
REQUIRED_ROLES = tuple(DetailCutRole)
DEFAULT_CTA_TITLE = "지금 만나보세요"
DEFAULT_CTA_LABEL = "자세히 보기"

_PAPER = (248, 247, 243)
_PAPER_WARM = (245, 243, 238)
_INK = (18, 18, 18)


def render(hero: HeroAsset, spec: FormatSpec, output_dir: str) -> list[str]:
    cuts = {cut.role: cut.image_path for cut in _select_role_cuts(hero)}
    width = spec.canvas[0]
    margin = int(width * spec.safe_margin)
    copy = detail_copy_for(hero)
    pal = _palette(hero.style)

    story_lines, story_h = _story_metrics(copy, width, margin)
    benefits_h = _benefits_height(copy)
    heights = (940, story_h, benefits_h, 760, 720, 650, 820, 320)
    total_h = sum(heights)
    canvas = Image.new("RGB", (width, total_h), "white")
    y = 0

    hero_section = _cover(Image.open(cuts[DetailCutRole.HERO]).convert("RGB"), (width, heights[0]))
    canvas.paste(hero_section, (0, y)); _title_overlay(canvas, copy, pal, y, heights[0], width); y += heights[0]
    _story(canvas, copy, pal, story_lines, y, heights[1], margin, width); y += heights[1]
    if benefits_h:
        _benefits(canvas, copy, pal, y, heights[2], margin, width)
        y += heights[2]

    top = _cover(Image.open(cuts[DetailCutRole.TOP_VIEW]).convert("RGB"), (width, heights[3]))
    canvas.paste(top, (0, y)); _section_label(canvas, pal, y, "01", copy.top_view_label, light=False); y += heights[3]

    closeup = _cover(Image.open(cuts[DetailCutRole.TEXTURE_CLOSEUP]).convert("RGB"), (width, heights[4]))
    canvas.paste(closeup, (0, y)); _section_label(canvas, pal, y, "02", copy.closeup_caption, light=True); y += heights[4]

    _split_section(canvas, cuts[DetailCutRole.SIDE_PROFILE], copy, pal, y, heights[5], width, margin); y += heights[5]

    lifestyle = _cover(Image.open(cuts[DetailCutRole.LIFESTYLE]).convert("RGB"), (width, heights[6]))
    canvas.paste(lifestyle, (0, y)); _lifestyle_overlay(canvas, copy, pal, y, heights[6], width, margin); y += heights[6]

    _cta(canvas, copy, pal, y, heights[7], margin, width)
    out = Path(output_dir) / f"detail_{width}x{total_h}_{spec.label}.jpg"
    canvas.save(out, quality=93)
    return [str(out)]


def _palette(style_key) -> dict:
    """스타일 원장(styles/specs.yaml) accent 기반 팔레트 (D4: 남색 하드코딩 제거).

    accent=원색(라벨·버튼), deep=진한 변형(패널 배경), tint=밝은 변형(어두운 배경 위 보조 텍스트).
    """
    from ...style_specs import get_spec
    accent = tuple(get_spec(style_key or "editorial").accent)
    deep = tuple(int(c * .78) for c in accent)
    tint = tuple(int(c + (255 - c) * .78) for c in accent)
    return {"accent": accent, "deep": deep, "tint": tint}


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
    structures: list[tuple[DetailCutRole, object]] = []
    for cut in hero.detail_cuts:
        path = Path(cut.image_path)
        if not path.is_file():
            raise ValueError(f"상세페이지 이미지가 없습니다: {cut.image_path}")
        if cut.role in by_role:
            raise ValueError(f"상세페이지 구도 역할이 중복되었습니다: {cut.role.value}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in hashes:
            raise ValueError("같은 이미지 내용을 서로 다른 상세페이지 구도로 사용할 수 없습니다")
        structure = structure_vector(path)
        for existing_role, existing in structures:
            # GATE-001(2026-07-20, 임시방편): 4개 구도(top_view/texture_closeup/side_profile/
            # lifestyle) 전부 생성 단계(generation_app._generate_with_retry)에서 이미 히어로와
            # 비교하며 여러 변형을 재시도해 최선의 결과를 골라온 뒤다. 원본이 이미 단순한 구도인
            # 상품(마우스, 문어모양 괄사 실측)은 그 최선의 결과조차 임계값을 못 넘을 수 있는데,
            # 여기서 hero와 다시 같은 기준으로 걸러버리면 5장 다 만들어놓고 전체를 실패시키는
            # 문제가 재발한다. 생성 단계의 재시도를 최종 판정으로 신뢰하고 hero가 낀 쌍은
            # 재검증하지 않는다.
            # [2026-07-21 개정] 위 "알려진 한계"의 전제는 낡았다 — 생성 단계가 이미
            # "지금까지 확정된 **모든 컷**"과 비교하며 재시도하고, 전 변형 소진 시 최저상관
            # 결과를 의도적으로 채택한다(_generate_with_retry). 여기서 같은 임계값으로 다시
            # 하드 실패시키면 상류의 그 결정을 기각해 "5장 만들고 전체 날리기"가 재발한다
            # (라이브 실측: 김치찌개 상세 561s 생성 → 400 → 전량 폐기). 비-히어로 쌍의
            # 유사는 경고 로그로 강등 — 완전 동일(해시 중복)만 하드 실패로 남긴다.
            if DetailCutRole.HERO in (existing_role, cut.role):
                continue
            if correlation(existing, structure) >= MAX_STRUCTURE_CORRELATION:
                logger.warning(
                    "상세페이지 구도 유사(상류 재시도의 최선 채택 존중): %s vs %s",
                    existing_role.value, cut.role.value,
                )
        hashes.add(digest)
        structures.append((cut.role, structure))
        by_role[cut.role] = cut
    missing = [role.value for role in REQUIRED_ROLES if role not in by_role]
    if missing:
        raise ValueError("상세페이지 필수 구도가 부족합니다: " + ", ".join(missing))
    return [by_role[role] for role in REQUIRED_ROLES]


def _cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    w, h = size
    scale = max(w / image.width, h / image.height)
    resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)
    left, top = (resized.width - w) // 2, (resized.height - h) // 2
    return resized.crop((left, top, left + w, top + h))


def _title_overlay(canvas, copy: DetailPageCopy, pal, y, height, width):
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle((0, y, width, y + 104), fill=(*_PAPER, 242))
    draw.rectangle((0, y + int(height * .68), width, y + height), fill=(*_INK, 220))
    margin = int(width * .07)
    draw.text((margin, y + 37), copy.product_name or "ADNOVA SELECT", font=_font(22, True), fill=(24, 24, 24))
    draw.line((width - margin - 100, y + 52, width - margin, y + 52), fill=pal["accent"], width=4)
    draw.text((margin, y + int(height * .73)), copy.product_name, font=_font(23, True), fill=pal["tint"])
    font = _fit(copy.intro_headline, width - margin * 2, 55, 34)
    draw.text((margin, y + int(height * .79)), copy.intro_headline, font=font, fill="white")


def _story_metrics(copy: DetailPageCopy, width, margin) -> tuple[list[str], int]:
    """스토리 본문을 픽셀 폭 기준으로 줄바꿈하고 섹션 높이를 계산한다 (D5 적응형)."""
    lines = _wrap_px(copy.story_body, _font(22), width - margin * 2) if copy.story_body else []
    # 라벨 64 + 제목 118~ + 본문 시작 205 + 줄당 38 + 하단 여백·룰 90. 종전 390 미만 금지.
    height = max(390, 295 + max(len(lines), 1) * 38 + 90)
    return lines, height


def _story(canvas, copy: DetailPageCopy, pal, body_lines, y, height, margin, width):
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, y, width, y + height), fill=_PAPER_WARM)
    draw.text((margin, y + 64), "PRODUCT STORY", font=_font(20, True), fill=pal["accent"])
    font = _fit(copy.story_title, width - margin * 2, 43, 29)
    draw.text((margin, y + 118), copy.story_title, font=font, fill=(25, 25, 25))
    for index, line in enumerate(body_lines):
        draw.text((margin, y + 205 + index * 38), line, font=_font(22), fill=(90, 90, 90))
    draw.line((margin, y + height - 56, width - margin, y + height - 56), fill=(190, 187, 180), width=1)


def _benefits_height(copy: DetailPageCopy) -> int:
    """혜택 불릿 섹션 높이 — 카피가 없으면 0(섹션 생략, 폴백 렌더는 종전과 동일 구성)."""
    if not copy.benefit_bullets:
        return 0
    return 96 + len(copy.benefit_bullets) * 72 + 48


def _benefits(canvas, copy: DetailPageCopy, pal, y, height, margin, width):
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, y, width, y + height), fill="white")
    draw.text((margin, y + 48), "WHY THIS", font=_font(20, True), fill=pal["accent"])
    for index, bullet in enumerate(copy.benefit_bullets):
        row_y = y + 96 + index * 72
        draw.ellipse((margin, row_y + 8, margin + 34, row_y + 42), fill=pal["accent"])
        draw.text((margin + 9, row_y + 13), f"{index + 1}", font=_font(19, True), fill="white")
        draw.text((margin + 56, row_y + 8),
                  _fit_line(bullet, width - margin * 2 - 56, 27), font=_font(27, True), fill=(30, 30, 30))


def _section_label(canvas, pal, y, number, title, light):
    draw = ImageDraw.Draw(canvas, "RGBA")
    fill = (*_PAPER, 232) if light else (*_INK, 205)
    text = (24, 24, 24) if light else (255, 255, 255)
    # 라이브 실측(2026-07-21): '잔' 같은 짧은 라벨이 고정 폭 바에 떠 보임 → 텍스트 폭 맞춤.
    label = _fit_line(title, 520 - 128 - 24, 27)
    font = _font(27, True)
    label_w = draw.textbbox((0, 0), label, font=font)[2]
    right = max(320, min(520, 128 + label_w + 36))
    draw.rectangle((44, y + 42, right, y + 145), fill=fill)
    draw.text((68, y + 67), number, font=_font(20, True), fill=pal["accent"])
    draw.text((128, y + 63), label, font=font, fill=text)


def _split_section(canvas, path, copy: DetailPageCopy, pal, y, height, width, margin):
    image_w = int(width * .56)
    canvas.paste(_cover(Image.open(path).convert("RGB"), (image_w, height)), (0, y))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((image_w, y, width, y + height), fill=pal["deep"])
    x = image_w + margin
    draw.text((x, y + 85), "03 / PROFILE", font=_font(19, True), fill=pal["tint"])
    draw.text((x, y + 150), copy.profile_title, font=_font(39, True), fill="white", spacing=8)
    if copy.profile_caption:
        for index, line in enumerate(_wrap_px(copy.profile_caption, _font(21), width - x - margin)[:3]):
            draw.text((x, y + 310 + index * 34), line, font=_font(21), fill=pal["tint"])


def _lifestyle_overlay(canvas, copy: DetailPageCopy, pal, y, height, width, margin):
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle((0, y + int(height * .67), width, y + height), fill=(*_INK, 205))
    draw.text((margin, y + int(height * .72)), "04 / MOMENT", font=_font(20, True), fill=pal["tint"])
    draw.text((margin, y + int(height * .79)), copy.lifestyle_line,
              font=_fit(copy.lifestyle_line, width - margin * 2, 43, 29), fill="white")


def _cta(canvas, copy: DetailPageCopy, pal, y, height, margin, width):
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, y, width, y + height), fill=(22, 22, 22))
    draw.text((margin, y + 62), copy.cta_title, font=_font(36, True), fill="white")
    draw.rectangle((margin, y + 172, margin + 220, y + 238), fill=pal["accent"])
    draw.text((margin + 34, y + 190), copy.cta_label, font=_font(23, True), fill="white")


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


def _fit_line(text: str, max_width: int, size: int) -> str:
    """폭을 넘는 한 줄 라벨을 말줄임으로 자른다(레이아웃 침범 방지)."""
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    font = _font(size, True)
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    while text and draw.textbbox((0, 0), text + "…", font=font)[2] > max_width:
        text = text[:-1]
    return text + "…"


def _wrap_px(text: str, font, max_width: int) -> list[str]:
    """픽셀 폭 기준 어절 줄바꿈 — 본문 문장용 (글자수 기준 _wrap 과 달리 폰트 실측)."""
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines, current = [], ""
    for word in (text or "").split():
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _height(font):
    box = font.getbbox("가Ag")
    return int((box[3] - box[1]) * 1.25)
