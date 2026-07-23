"""v5 카드뉴스: 검증된 다구도 상품 컷을 4장 시퀀스로 조판한다.

v6-1 F2(2026-07-23) 고도화:
  - 카피 소스 통일: copy_for/section_copy_for → detail_copy_for(F1 엔진) 1회.
    4슬라이드가 intro_headline / story / profile / cta 각기 다른 전용 문구를 써
    표지·스토리 슬라이드에 같은 headline 이 복붙되던 문제(D1) 해소.
  - 팔레트 연동: 남색 하드코딩(35,55,167 등) → palette(hero.style) (D4). detail_page 와
    같은 스타일 accent 를 공유해, 스타일이 다르면 카드뉴스 톤도 달라진다.
  - 섹션 칩 per-product: 정적 'TOP VIEW' → top_view_label.
  - '동일 템플릿' 룩 제거(2026-07-23, detail_page c8faa8b 방향): 일률적 번호(01~04) 삭제,
    표지·CTA 솔리드 패널 → 하단 페이드 스크림(detail_page._scrim 재사용, 제품 이미지 노출↑).
GPT 실패 시 detail_copy_for 가 종전 문구 구성으로 폴백하므로 화면 회귀 없음.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..commercial_copy import DetailPageCopy, detail_copy_for
from ..format_spec import FormatSpec
from ..hero import DetailCutRole, HeroAsset
from ..palette import palette
from .detail_page import _scrim, _select_role_cuts

SLIDE_COUNT = 4
DEFAULT_CTA_TITLE = "지금 만나보세요"
DEFAULT_CTA_LABEL = "자세히 보기"

_PAPER = (248, 247, 243)
_INK = (18, 18, 18)


def render(hero: HeroAsset, spec: FormatSpec, output_dir: str) -> list[str]:
    """표지·상품 인상·디테일·CTA를 각기 다른 구도·전용 문구로 만든다."""
    cuts = {cut.role: cut.image_path for cut in _select_role_cuts(hero)}
    size = spec.canvas
    copy = detail_copy_for(hero)
    pal = palette(hero.style)
    slides = [
        _cover_slide(cuts[DetailCutRole.HERO], copy, pal, size, spec.safe_margin),
        _story_slide(cuts[DetailCutRole.TOP_VIEW], copy, pal, size, spec.safe_margin),
        _detail_slide(
            cuts[DetailCutRole.TEXTURE_CLOSEUP],
            cuts[DetailCutRole.SIDE_PROFILE],
            copy, pal, size, spec.safe_margin,
        ),
        _cta_slide(cuts[DetailCutRole.LIFESTYLE], copy, pal, size, spec.safe_margin),
    ]

    output = Path(output_dir)
    names = ("cover", "story", "detail", "cta")
    paths: list[str] = []
    for index, (name, slide) in enumerate(zip(names, slides), start=1):
        path = output / f"cardnews_{index:02d}_{name}_{size[0]}x{size[1]}.jpg"
        slide.save(path, quality=93)
        paths.append(str(path))
    return paths


def _cover_slide(path: str, copy: DetailPageCopy, pal, size: tuple[int, int], margin_ratio: float) -> Image.Image:
    canvas = _cover(Image.open(path).convert("RGB"), size)
    w, h = size
    margin = int(w * margin_ratio)
    # 하단 = 솔리드 페이퍼 패널 대신 페이드 스크림(제품 이미지 노출↑). 흰 타이포로 전환.
    _scrim(canvas, int(h * .70), h, w, _INK, 210, int(h * .12))
    draw = ImageDraw.Draw(canvas, "RGBA")
    # 상단 얇은 페이퍼 바(detail 표지와 동일) — 밝은 이미지 위 상품명 가독성 확보.
    draw.rectangle((0, 0, w, 108), fill=(*_PAPER, 235))
    draw.text((margin, 40), copy.product_name or "ADNOVA SELECT", font=_font(25, True), fill=(24, 24, 24))
    draw.line((w - margin - 120, 57, w - margin, 57), fill=pal["accent"], width=5)
    ty = int(h * .76)
    if copy.product_name:
        draw.text((margin, ty), "SIGNATURE MENU", font=_font(22, True), fill=pal["tint"])
    # 표지 메인 = intro_headline(후킹) — 스토리 슬라이드의 story_title 과 다른 문구(D1 해소).
    font = _fit(copy.intro_headline, w - margin * 2, 62, 38)
    draw.text((margin, ty + 42), copy.intro_headline, font=font, fill="white")
    # 보조 한 줄 = 혜택 불릿 첫 항목(다른 슬라이드 미사용 → 겹침 0). 없으면 생략.
    if copy.benefit_bullets:
        draw.text((margin, ty + 128), copy.benefit_bullets[0],
                  font=_fit(copy.benefit_bullets[0], w - margin * 2, 28, 22), fill=pal["tint"])
    return canvas


def _story_slide(path: str, copy: DetailPageCopy, pal, size: tuple[int, int], margin_ratio: float) -> Image.Image:
    w, h = size
    copy_w = int(w * .42)
    canvas = Image.new("RGB", size, pal["deep"])
    canvas.paste(_cover(Image.open(path).convert("RGB"), (w - copy_w, h)), (copy_w, 0))
    draw = ImageDraw.Draw(canvas)
    margin = int(w * margin_ratio)
    draw.text((margin, 120), copy.product_name or "오늘의 메뉴",
              font=_fit(copy.product_name or "오늘의 메뉴", copy_w - margin * 2, 47, 29), fill="white")
    draw.line((margin, 270, copy_w - margin, 270), fill=pal["tint"], width=3)
    # 제목 = story_title, 본문 = story_body 첫 문장(카드뉴스=요약 → 문장 중간 잘림 방지).
    for index, line in enumerate(_wrap(copy.story_title, 10)):
        draw.text((margin, 340 + index * 62), line, font=_font(42, True), fill="white")
    if copy.story_body:
        for index, line in enumerate(_wrap(_first_sentence(copy.story_body), 12)):
            draw.text((margin, 545 + index * 42), line, font=_font(26), fill=pal["tint"])
    # 섹션 칩 = per-product top_view_label(정적 'TOP VIEW' 대체).
    draw.text((margin, h - 115), copy.top_view_label or "TOP VIEW", font=_font(20, True), fill=pal["tint"])
    return canvas


def _detail_slide(
    closeup_path: str,
    side_path: str,
    copy: DetailPageCopy,
    pal,
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
    x = int(w * .51)
    draw.text((x, int(h * .70)), "DETAIL", font=_font(21, True), fill=pal["accent"])
    # 제목 = profile_title(형태·디테일 2줄), 보조 = profile_caption.
    draw.text((x, int(h * .76)), copy.profile_title, font=_font(46, True), fill=(22, 22, 22), spacing=10)
    if copy.profile_caption:
        for index, line in enumerate(_wrap(copy.profile_caption, 12)):
            draw.text((x, int(h * .88) + index * 34), line, font=_font(23), fill=(88, 84, 78))
    return canvas


def _cta_slide(path: str, copy: DetailPageCopy, pal, size: tuple[int, int], margin_ratio: float) -> Image.Image:
    canvas = _cover(Image.open(path).convert("RGB"), size)
    w, h = size
    margin = int(w * margin_ratio)
    # 전체 dim + 하단 불투명 패널 → 하단 페이드 스크림만(제품 이미지 노출↑).
    _scrim(canvas, int(h * .60), h, w, _INK, 220, int(h * .14))
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.text((margin, int(h * .68)), copy.product_name or "SIGNATURE", font=_font(24, True), fill=pal["tint"])
    draw.text((margin, int(h * .74)), copy.cta_title, font=_font(52, True), fill="white")
    draw.rectangle((margin, int(h * .86), margin + 238, int(h * .86) + 68), fill=pal["accent"])
    draw.text((margin + 38, int(h * .86) + 18), copy.cta_label, font=_font(25, True), fill="white")
    return canvas


def _first_sentence(text: str) -> str:
    """본문 첫 문장만 반환 — 카드뉴스 요약용. 문장부호 없으면 전체(끝 마침표 제거)."""
    t = (text or "").strip()
    for sep in (". ", "! ", "? "):
        if sep in t:
            return t.split(sep)[0].strip()
    return t.rstrip(".!?").strip()


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
