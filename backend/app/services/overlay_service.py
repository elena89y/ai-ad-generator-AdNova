"""타이포 오버레이 서비스 (층2) — 담당: 한의정. Issue #26.

생성된 광고 이미지 위에 헤드라인·문구·그래픽을 코드로 렌더링해 포스터 룩 완성.
SDXL 은 글자를 못 그리므로(층1 negative 로 억제) 타이포는 전부 PIL 렌더링:
한글 100% 정확, FR-09 카피와 직접 연결, 비용 0.

템플릿 (프리셋 → 자동 선택):
  - ring    (editorial)    : 상단 세리프 헤드라인 + 제품 둘레 원근 타원 텍스트 링
  - banner  (retro_paper)  : 시그니처 컬러 곡선 리본 + 손글씨 메뉴명 + 하단 설명
  - caption (그 외 4종)     : 상단 헤드라인 + 서브카피 (프리셋별 폰트 무드)

색: 제품 마스크 영역에서 주도색 추출(설계메모 '추출≠톤 적용') → 그래픽에 적용.
폰트: backend/assets/fonts/ (scripts/download_fonts.py 로 준비, 전부 OFL).
"""
from __future__ import annotations

import colorsys
import logging
import math
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..schemas.ads import StylePreset

logger = logging.getLogger(__name__)

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
IVORY = (250, 243, 227)
DARK = (45, 40, 35)

_TEMPLATE_BY_PRESET = {
    StylePreset.EDITORIAL: "ring",
    StylePreset.RETRO_PAPER: "banner",
    # 그 외 프리셋은 caption
}


# --- 폰트 -----------------------------------------------------------------------
def _font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    """kind: serif(명조) / hand(펜스크립트) / gothic / gothic_bold / didone(영문 세리프)."""
    names = {
        "serif": "NanumMyeongjo-Regular.ttf",
        "hand": "NanumPenScript-Regular.ttf",
        "gothic": "NanumGothic-Regular.ttf",
        "gothic_bold": "NanumGothic-Bold.ttf",
        "didone": "PlayfairDisplay.ttf",
    }
    path = FONT_DIR / names[kind]
    if not path.is_file():
        raise FileNotFoundError(
            f"폰트 없음: {path} — `python backend/scripts/download_fonts.py` 실행 필요"
        )
    return ImageFont.truetype(str(path), size)


def _headline_font(text: str, size: int) -> ImageFont.FreeTypeFont:
    """영문 전용이면 Didone(Playfair), 한글 포함이면 명조."""
    return _font("didone" if text.isascii() else "serif", size)


# --- 색 추출 --------------------------------------------------------------------
def extract_signature_color(image_path: str, mask_path: str) -> tuple[int, int, int]:
    """제품 마스크 영역의 주도색 (채도 있는 색 우선, 무채색 제품은 중간톤 폴백)."""
    img = np.array(Image.open(image_path).convert("RGB"), dtype=np.float64) / 255.0
    mask = np.array(Image.open(mask_path).convert("L").resize(
        (img.shape[1], img.shape[0]))) >= 128
    pixels = img[mask]
    if len(pixels) == 0:
        return (170, 90, 60)

    mx, mn = pixels.max(axis=1), pixels.min(axis=1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    valid = (sat > 0.25) & (mx > 0.15) & (mx < 0.95)
    pool = pixels[valid] if valid.sum() > 100 else pixels

    # 4비트 양자화 최빈 빈의 중앙값
    q = (pool * 15).astype(int)
    keys = q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]
    top = np.bincount(keys).argmax()
    sel = pool[keys == top]
    r, g, b = sel.mean(axis=0)
    return (int(r * 255), int(g * 255), int(b * 255))


def _deepen(color: tuple[int, int, int]) -> tuple[int, int, int]:
    """그래픽용으로 명도 상한·채도 하한 보정 (아이보리 텍스트 대비 확보)."""
    h, s, v = colorsys.rgb_to_hsv(*(c / 255.0 for c in color))
    v = min(v, 0.72)
    s = max(s, 0.45) if s > 0.1 else s  # 무채색 제품이면 채도 유지
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))


def _mask_info(mask_path: str, size: tuple[int, int]) -> dict:
    """제품 중심·바운딩박스 (레이아웃 회피·링 반경 계산용)."""
    m = np.array(Image.open(mask_path).convert("L").resize(size)) >= 128
    ys, xs = np.nonzero(m)
    if len(xs) == 0:
        w, h = size
        return {"cx": w // 2, "cy": h // 2, "x0": w // 4, "y0": h // 4,
                "x1": 3 * w // 4, "y1": 3 * h // 4}
    return {"cx": int(xs.mean()), "cy": int(ys.mean()),
            "x0": int(xs.min()), "y0": int(ys.min()),
            "x1": int(xs.max()), "y1": int(ys.max())}


def _bg_is_bright(img: Image.Image, y_frac: float = 0.12) -> bool:
    """상단 밴드 평균 명도로 텍스트 색(아이보리/다크) 결정."""
    arr = np.array(img.convert("L"), dtype=np.float64)
    band = arr[: max(1, int(arr.shape[0] * y_frac))]
    return float(band.mean()) > 150


def _spaced_text(draw, xy, text, font, fill, spacing_frac=0.10, anchor_center_x=None):
    """자간(letter-spacing) 텍스트. anchor_center_x 지정 시 중앙 정렬."""
    sizes = [draw.textlength(ch, font=font) for ch in text]
    gap = font.size * spacing_frac
    total = sum(sizes) + gap * (len(text) - 1)
    x = (anchor_center_x - total / 2) if anchor_center_x is not None else xy[0]
    y = xy[1]
    for ch, w in zip(text, sizes):
        draw.text((x, y), ch, font=font, fill=fill)
        x += w + gap
    return total


# --- 템플릿: ring (원형 타이포, editorial) --------------------------------------
def _apply_ring(img, product_rgba, mask, info, headline, subcopy, color):
    w, h = img.size
    draw = ImageDraw.Draw(img)
    text_color = IVORY if not _bg_is_bright(img) else DARK

    # 1. 상단 헤드라인 (대문자·자간)
    head = headline.upper() if headline.isascii() else headline
    fsize = int(h * 0.042)
    font = _headline_font(head, fsize)
    _spaced_text(draw, (0, int(h * 0.085)), head, font, text_color,
                 spacing_frac=0.14, anchor_center_x=w / 2)

    # 2. 원근 타원 텍스트 링 (제품 둘레, 반복 문구)
    phrase = (subcopy.upper() if subcopy.isascii() else subcopy).strip()
    ring_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    cx, cy = info["cx"], int(info["cy"] + (info["y1"] - info["y0"]) * 0.18)
    a = max(int((info["x1"] - info["x0"]) * 0.78), int(w * 0.30))
    a = min(a, int(w * 0.44))
    b = int(a * 0.40)

    ring_font = _font("didone" if phrase.isascii() else "serif", int(h * 0.033))
    letter_gap = 1.18  # 자간 (글자폭 배수)

    # 호 길이 테이블 — 그리기와 동일한 파라미터화(시작각 -π/2 포함)로 구축해야
    # 간격이 정확함 (시프트 불일치 시 글자 뭉침)
    phis = np.linspace(-math.pi / 2, 1.5 * math.pi, 1440)
    pts = np.stack([a * np.cos(phis), b * np.sin(phis)], axis=1)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    total_len = cum[-1]

    unit = phrase + "  •  "
    unit_w = sum(ring_font.getlength(ch) * letter_gap for ch in unit)
    reps = max(1, int(total_len // unit_w))
    text = unit * reps

    dist = 0.0
    for ch in text:
        ch_w = ring_font.getlength(ch)
        phi = float(np.interp((dist + ch_w / 2) % total_len, cum, phis))
        x = cx + a * math.cos(phi)
        y = cy + b * math.sin(phi)
        tangent = math.degrees(math.atan2(b * math.cos(phi), -a * math.sin(phi)))
        glyph = Image.new("RGBA", (int(ch_w) + 8, ring_font.size + 8), (0, 0, 0, 0))
        ImageDraw.Draw(glyph).text((4, 0), ch, font=ring_font, fill=text_color)
        glyph = glyph.rotate(-tangent, expand=True, resample=Image.BICUBIC)
        ring_layer.paste(glyph, (int(x - glyph.width / 2), int(y - glyph.height / 2)), glyph)
        dist += ch_w * letter_gap

    img.paste(ring_layer, (0, 0), ring_layer)
    # 3. 깊이: 제품을 링 위에 다시 얹음 (상단 호가 제품 뒤로)
    img.paste(product_rgba, (0, 0), product_rgba)
    return img


# --- 템플릿: banner (곡선 리본, retro_paper) ------------------------------------
def _bezier(p0, p1, p2, p3, n=120):
    t = np.linspace(0, 1, n)[:, None]
    return ((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1
            + 3 * (1 - t) * t**2 * p2 + t**3 * p3)


def _apply_banner(img, product_rgba, mask, info, headline, subcopy, color):
    w, h = img.size
    sig = _deepen(color)
    thick = int(h * 0.058)

    # 1. 제품 위·옆을 흐르는 리본 경로 (제품 bbox 회피)
    top_y = max(int(info["y0"] * 0.55), int(h * 0.10))
    side_x = int(w * 0.10) if info["cx"] > w // 2 else int(w * 0.90)
    path = np.concatenate([
        _bezier(np.array([w * 0.06, h * 0.30]), np.array([w * 0.10, top_y * 0.5]),
                np.array([w * 0.45, top_y * 0.35]), np.array([w * 0.62, top_y])),
        _bezier(np.array([w * 0.62, top_y]), np.array([w * 0.88, top_y * 1.25]),
                np.array([side_x, h * 0.45]), np.array([side_x, h * 0.62])),
    ])
    ribbon = Image.new("RGBA", img.size, (0, 0, 0, 0))
    rd = ImageDraw.Draw(ribbon)
    n = len(path)
    for i, (x, y) in enumerate(path):
        # 끝단 테이퍼: 중앙부 최대, 양 끝 45% (뭉툭한 벌레 느낌 방지)
        r = thick * (0.45 + 0.55 * math.sin(math.pi * i / max(n - 1, 1)))
        rd.ellipse([x - r, y - r, x + r, y + r], fill=sig + (255,))
    img.paste(ribbon, (0, 0), ribbon)

    # 2. 손글씨 메뉴명 — 리본 상단 벌지 위 (기울임)
    fsize = int(h * 0.075)
    font = _font("hand", fsize)
    d = ImageDraw.Draw(img)
    tw = d.textlength(headline, font=font)
    tx, ty = int(w * 0.34 - tw / 2), int(top_y * 0.72 - fsize / 2)
    glyph = Image.new("RGBA", (int(tw) + 20, fsize + 24), (0, 0, 0, 0))
    ImageDraw.Draw(glyph).text((10, 4), headline, font=font, fill=IVORY)
    glyph = glyph.rotate(-4, expand=True, resample=Image.BICUBIC)
    img.paste(glyph, (tx, ty), glyph)

    # 3. 제품 손그림 윤곽선 (마스크 팽창 밴드)
    m = (np.array(mask.resize(img.size)) >= 128).astype(np.uint8)
    grown = m.copy()
    for _ in range(5):
        s = [grown]
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    s.append(np.roll(np.roll(grown, dy, 0), dx, 1))
        grown = np.max(np.stack(s), 0)
    outline = (grown - m).astype(bool)
    arr = np.array(img)
    arr[outline] = sig
    img = Image.fromarray(arr)

    # 4. 하단 설명 (시그니처 컬러)
    d = ImageDraw.Draw(img)
    sub_font = _font("hand", int(h * 0.034))
    sw = d.textlength(subcopy, font=sub_font)
    d.text(((w - sw) / 2, int(h * 0.90)), subcopy, font=sub_font, fill=sig)

    img.paste(product_rgba, (0, 0), product_rgba)
    return img


# --- 템플릿: caption (미니멀) ---------------------------------------------------
_CAPTION_FONT = {
    StylePreset.MONOTONE: "gothic",
    StylePreset.WARM_VINTAGE: "serif",
    StylePreset.POP: "gothic_bold",
    StylePreset.PASTEL_FLOAT: "gothic",
}


def _apply_caption(img, preset, info, headline, subcopy):
    w, h = img.size
    draw = ImageDraw.Draw(img)
    text_color = IVORY if not _bg_is_bright(img) else DARK

    # 제품이 위쪽에 있으면 하단 배치, 아니면 상단
    top = info["y0"] > h * 0.30
    y = int(h * 0.07) if top else int(h * 0.82)

    kind = _CAPTION_FONT.get(preset, "gothic")
    font = _font(kind, int(h * 0.05))
    _spaced_text(draw, (0, y), headline, font, text_color,
                 spacing_frac=0.06, anchor_center_x=w / 2)
    sub_font = _font(kind if kind != "gothic_bold" else "gothic", int(h * 0.026))
    sw = draw.textlength(subcopy, font=sub_font)
    draw.text(((w - sw) / 2, y + int(h * 0.065)), subcopy, font=sub_font, fill=text_color)
    return img


# --- 공개 API -------------------------------------------------------------------
def apply_overlay(
    final_image_path: str,
    preset: StylePreset,
    headline: str,
    subcopy: str,
    mask_path: str,
    output_path: Optional[str] = None,
) -> str:
    """생성 이미지에 프리셋별 타이포 오버레이 적용 → 저장 경로 반환.

    headline/subcopy 는 FR-09 generate_copy 의 '헤드라인\\n서브카피' 를 분리해 전달.
    """
    img = Image.open(final_image_path).convert("RGB")
    mask = Image.open(mask_path).convert("L").resize(img.size)
    info = _mask_info(mask_path, img.size)

    # 깊이 처리용 제품 레이어 (원본 픽셀)
    product_rgba = img.convert("RGBA").copy()
    product_rgba.putalpha(mask)

    template = _TEMPLATE_BY_PRESET.get(preset, "caption")
    color = extract_signature_color(final_image_path, mask_path)

    if template == "ring":
        img = _apply_ring(img, product_rgba, mask, info, headline, subcopy, color)
    elif template == "banner":
        img = _apply_banner(img, product_rgba, mask, info, headline, subcopy, color)
    else:
        img = _apply_caption(img, preset, info, headline, subcopy)

    out = Path(output_path) if output_path else \
        Path(final_image_path).with_name(Path(final_image_path).stem + "_poster.png")
    img.convert("RGB").save(out, format="PNG")
    logger.info(f"오버레이 적용 완료 ({template}): {out}")
    return str(out)
