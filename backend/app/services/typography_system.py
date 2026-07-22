"""타이포 시스템 v0 조판기 — 코퍼스 파생 레지스트리(TS-1~3b) + 구도 자동 분기.

근거: ~/Desktop/AdNova/템플릿_프롬프트/11_타이포_시스템_v0.md (2026-07-21 아트디렉터 판정:
전 스타일 채택 + 구도별 자동 분기). overlay_service 기본 룩(키커+명조 오버레이)은
템플릿·홈페이지 사용 금지 판정이라 이 모듈이 그 자리를 대체한다.

역할 분리 원칙 유지: 여기는 전부 코드(PIL) 조판 — 생성 모델은 관여하지 않는다.
z-order 가림(TS-1)은 v0에서 배경 균일색 거리 마스크로 근사한다. 스튜디오/단색 배경에서
잘 동작하고, 마스크 신뢰도가 낮은 복잡 배경은 분기 단계에서 TS-1이 선택되지 않으므로
rembg 왕복 비용 없이 안전하다 (busy 배경 → bg fraction 낮음 → TS-3b 폴백).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

_FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"

# 레지스트리 키 (schema typography.layers[].font_class 와 일치)
TS1_BG_LETTERING = "ts1_bg_lettering"
TS2_EDITORIAL_SERIF = "ts2_editorial_serif"
TS3_KOREAN_BLOCK = "ts3_korean_block"
TS3B_PANEL = "ts3b_panel"


@dataclass(frozen=True)
class TypoPlan:
    """분기 결과 — 어떤 스타일로, 어떤 텍스트를 조판할지."""

    style: str
    head: str
    sub: str


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONT_DIR / name), max(12, int(size)))


def _fit_width(draw: ImageDraw.ImageDraw, text: str, fname: str,
               target_w: float, spacing: float = 0.0) -> ImageFont.FreeTypeFont:
    """target_w 이하로 들어가는 최대 폰트 크기 탐색 (자간 비율 포함)."""
    size = 400
    while size > 16:
        f = _font(fname, size)
        w = draw.textlength(text, font=f) + spacing * size * max(0, len(text) - 1)
        if w <= target_w:
            return f
        size -= 6
    return _font(fname, 16)


def _spaced_text(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str,
                 f: ImageFont.FreeTypeFont, fill, spacing_frac: float) -> None:
    x, y = xy
    sp = f.size * spacing_frac
    for ch in text:
        draw.text((x, y), ch, font=f, fill=fill)
        x += draw.textlength(ch, font=f) + sp


def _bg_color(img: Image.Image) -> tuple[int, int, int]:
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    corners = np.concatenate([a[:40, :40].reshape(-1, 3), a[:40, -40:].reshape(-1, 3)])
    return tuple(int(c) for c in corners.mean(axis=0))


def _subject_mask(img: Image.Image) -> np.ndarray:
    """배경 균일색 거리 마스크 (True=피사체). 단색·스튜디오 배경 전용 근사.

    소프트 그라데이션 배경(FLUX/Kontext 씬)에서 과민해지지 않도록, 테두리 링의
    거리 분포 90퍼센타일을 노이즈 플로어로 삼는 적응형 임계값을 쓴다 (07-21 실측:
    고정 30은 아메리카노 씬의 배경 비네팅을 피사체로 오인 → TS-1 분기 실패).
    """
    a = np.asarray(img.convert("RGB"), dtype=np.int16)
    h, w = a.shape[:2]
    corners = np.concatenate([a[:40, :40].reshape(-1, 3), a[:40, -40:].reshape(-1, 3),
                              a[-40:, :40].reshape(-1, 3), a[-40:, -40:].reshape(-1, 3)])
    bg = corners.mean(axis=0)
    dist = np.abs(a - bg).sum(axis=2)
    m = max(8, int(min(h, w) * 0.06))
    ring = np.concatenate([dist[:m].ravel(), dist[-m:].ravel(),
                           dist[:, :m].ravel(), dist[:, -m:].ravel()])
    thresh = float(np.percentile(ring, 90)) + 22.0
    return dist > thresh


def _subject_mask_precise(img: Image.Image) -> np.ndarray:
    """TS-1 z-order 가림용 정밀 마스크 — 스펙(렌더→누끼 재합성)대로 rembg 우선.

    워커에는 birefnet 세션이 상주하므로 추가 로드 비용이 거의 없다. rembg 미설치/
    가중치 없는 로컬 환경에서는 색거리 근사로 폴백 (시안·테스트 용도로 충분).
    """
    try:
        from rembg import remove

        from .image_service import _get_rembg_session

        alpha = remove(img.convert("RGB"), session=_get_rembg_session(), only_mask=True)
        return np.asarray(alpha.convert("L")) > 96
    except Exception:
        return _subject_mask(img)


def _is_light(color: tuple[int, int, int]) -> bool:
    r, g, b = color
    return (0.299 * r + 0.587 * g + 0.114 * b) > 140


def _ink_for(bg: tuple[int, int, int]) -> tuple[int, int, int]:
    """배경 밝기에 따른 잉크색 — 밝으면 웜 차콜, 어두우면 크림."""
    return (30, 27, 24) if _is_light(bg) else (248, 244, 236)


def select_style(img: Image.Image, has_english: bool, domain: str = "food") -> str:
    """구도 분석으로 스타일 자동 분기 (v0 휴리스틱, 판정 07-21).

    상단 1/3에 배경이 넉넉하면 TS-1(배경 레터링), 우하단 코너가 비면 TS-2(에디토리얼),
    그 외(탑뷰 풀플레이트 등)는 캔버스 확장 패널 TS-3b — 겹침 제로라 항상 안전.

    사물(object)은 스튜디오 단품 구도라 배경 여백이 넉넉 → 무조건 TS-1 배경 레터링으로
    통일한다(07-21 지시). 제품이 글자를 완전히 가리지 않고 살짝 걸쳐도 무방.
    """
    if domain == "object":
        return TS1_BG_LETTERING
    mask = _subject_mask(img)
    h, w = mask.shape
    top_bg = 1.0 - float(mask[: int(h * 0.32)].mean())
    # TS-1 판별은 레터링 라인(y 0.20~0.40) 높이의 피사체 '폭' — 탑뷰 접시(~85%)는
    # 글자가 다 가려지고, 측면 음료(~40%)는 글자가 양옆으로 살아난다 (07-21 실측)
    band_subject = float(mask[int(h * 0.20): int(h * 0.40)].mean())
    corner = mask[int(h * 0.78):, int(w * 0.62):]
    corner_bg = 1.0 - float(corner.mean())
    if has_english and band_subject < 0.45:
        return TS1_BG_LETTERING
    if has_english and corner_bg > 0.85:
        return TS2_EDITORIAL_SERIF
    if top_bg > 0.88:
        return TS3_KOREAN_BLOCK
    return TS3B_PANEL


def render_ts1(img: Image.Image, head_en: str) -> Image.Image:
    """TS-1 대형 배경 레터링 — 한 줄, 피사체가 글자를 가린다(z-order).

    영문=Anton, 한글=BlackHanSans (사물 강제 분기 시 한글 상품명도 두부 없이 렌더).
    """
    im = img.convert("RGB")
    w, h = im.size
    layer = im.copy()
    d = ImageDraw.Draw(layer)
    fname = "Anton-Regular.ttf" if head_en.isascii() else "BlackHanSans-Regular.ttf"
    f = _fit_width(d, head_en, fname, w * 0.86)
    tw = d.textlength(head_en, font=f)
    bg = _bg_color(im)
    # 스펙: 크림·아이보리·베이지 (순백 금지). 밝은 배경에선 대비 위해 소프트 베이지 딥톤.
    fill = (196, 168, 138) if _is_light(bg) else (240, 233, 220)
    d.text(((w - tw) / 2, int(h * 0.30) - f.size // 2), head_en, font=f, fill=fill)
    mask_arr = _subject_mask_precise(im)
    mask_img = Image.fromarray((mask_arr * 255).astype(np.uint8))
    layer.paste(im, (0, 0), mask_img)
    return layer


def render_ts2(img: Image.Image, head_en: str, sub_kr: str) -> Image.Image:
    """TS-2 에디토리얼 세리프 — Playfair 대문자(자간 9%) 우하단 + 나눔펜 필기 서브."""
    im = img.convert("RGB")
    d = ImageDraw.Draw(im)
    w, h = im.size
    ink = _ink_for(_bg_color(im))
    f = _fit_width(d, head_en, "PlayfairDisplay.ttf", w * 0.30, spacing=0.09)
    tw = d.textlength(head_en, font=f) + 0.09 * f.size * (len(head_en) - 1)
    x, y = w - tw - int(w * 0.035), int(h * 0.905)
    _spaced_text(d, (x, y), head_en, f, ink, 0.09)
    if sub_kr:
        sf = _font("NanumPenScript-Regular.ttf", int(f.size * 1.15))
        sw = d.textlength(sub_kr, font=sf)
        d.text((w - sw - int(w * 0.035), y - sf.size - 4), sub_kr, font=sf, fill=ink)
    return im


def render_ts3(img: Image.Image, head_kr: str, sub_kr: str) -> Image.Image:
    """TS-3 한글 블록 — BlackHanSans 초대형 상단 + 좌하단 룰·소카피."""
    im = img.convert("RGB")
    d = ImageDraw.Draw(im)
    w, h = im.size
    ink = _ink_for(_bg_color(im))
    f = _fit_width(d, head_kr, "BlackHanSans-Regular.ttf", w * 0.90, spacing=-0.02)
    _spaced_text(d, (int(w * 0.05), int(h * 0.012)), head_kr, f, ink, -0.02)
    if sub_kr:
        sf = _font("Pretendard-Medium.otf", int(h * 0.028))
        sx, sy = int(w * 0.05), int(h * 0.935)
        d.line([(sx, sy + sf.size // 2), (sx + int(w * 0.10), sy + sf.size // 2)],
               fill=ink, width=3)
        d.text((sx + int(w * 0.12), sy), sub_kr, font=sf, fill=ink)
    return im


def render_ts3b(img: Image.Image, head_kr: str, sub_kr: str) -> Image.Image:
    """TS-3b 패널 확장 — 캔버스를 위로 늘려 단색 패널에 블록 타이포 (겹침 제로, 4:5 지향)."""
    im = img.convert("RGB")
    w, h = im.size
    bg = _bg_color(im)
    ink = _ink_for(bg)
    # 패널 높이는 내용(헤드+서브) 실측으로 계산 — 고정 비율은 서브가 밀려나옴 (07-21 실측)
    probe = ImageDraw.Draw(im)
    f = _fit_width(probe, head_kr, "BlackHanSans-Regular.ttf", w * 0.88, spacing=-0.02)
    sub_h = int(f.size * 0.62) if sub_kr else 0
    panel_h = int(f.size * 0.34 + f.size * 1.22 + sub_h + f.size * 0.30)
    canvas = Image.new("RGB", (w, h + panel_h), bg)
    canvas.paste(im, (0, panel_h))
    d = ImageDraw.Draw(canvas)
    tw = d.textlength(head_kr, font=f) - 0.02 * f.size * max(0, len(head_kr) - 1)
    ty = int(f.size * 0.34)
    _spaced_text(d, ((w - tw) / 2, ty), head_kr, f, ink, -0.02)
    if sub_kr:
        kf = _font("Pretendard-Medium.otf", int(f.size * 0.30))
        kw = d.textlength(sub_kr, font=kf)
        ky = ty + int(f.size * 1.22)
        lw, gap = int(w * 0.07), int(w * 0.02)
        cx = (w - kw) / 2
        mid = ky + kf.size // 2
        d.line([(cx - gap - lw, mid), (cx - gap, mid)], fill=ink, width=2)
        d.text((cx, ky), sub_kr, font=kf, fill=ink)
        d.line([(cx + kw + gap, mid), (cx + kw + gap + lw, mid)], fill=ink, width=2)
    return canvas


def plan_typography(img: Image.Image, product_name: str, copy_headline: str,
                    subject_en: str, domain: str = "food") -> TypoPlan:
    """텍스트 소스 결정 + 스타일 분기. 영문 라벨이 없으면 한글 계열만 사용."""
    head_en = (subject_en or "").strip().upper()
    # CLIP 함정과 동일 원칙 — 배경 레터링은 짧아야 산다 (스펙: 한 줄, 올캡스)
    has_english = 0 < len(head_en) <= 18
    style = select_style(img, has_english, domain)
    head_kr = (product_name or copy_headline or "").strip()
    sub_kr = (copy_headline or "").strip()
    if sub_kr == head_kr:
        sub_kr = ""
    if style == TS2_EDITORIAL_SERIF:
        return TypoPlan(style=style, head=head_en, sub=sub_kr)
    if style == TS1_BG_LETTERING:
        # 사물 강제 분기 등으로 영문 라벨이 없으면 한글 상품명으로 배경 레터링
        return TypoPlan(style=style, head=head_en if has_english else head_kr, sub=sub_kr)
    return TypoPlan(style=style, head=head_kr, sub=sub_kr)


def render_typography(image_path: str, out_path: str, product_name: str,
                      copy_headline: str, subject_en: str = "",
                      domain: str = "food") -> str:
    """조판기 v0 진입점 — 스타일 자동 분기 후 렌더, 실패 시 TS-3b 폴백.

    반환: 사용한 스타일 키 (로그·실험 기록용).
    """
    img = Image.open(image_path)
    plan = plan_typography(img, product_name, copy_headline, subject_en, domain)
    try:
        if plan.style == TS1_BG_LETTERING:
            out = render_ts1(img, plan.head)
        elif plan.style == TS2_EDITORIAL_SERIF:
            out = render_ts2(img, plan.head, plan.sub)
        elif plan.style == TS3_KOREAN_BLOCK:
            out = render_ts3(img, plan.head, plan.sub)
        else:
            out = render_ts3b(img, plan.head, plan.sub)
        used = plan.style
    except Exception:
        # 어떤 입력에서도 죽지 않는다 — 패널은 소스와 무관하게 항상 성립
        out = render_ts3b(img, (product_name or copy_headline or "").strip() or " ",
                          "")
        used = TS3B_PANEL
    out.save(out_path)
    return used
