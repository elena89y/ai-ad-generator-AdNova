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
        "display": "Jua-Regular.ttf",
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
    fsize = int(h * 0.05)
    font = _headline_font(head, fsize)
    _spaced_text(draw, (0, int(h * 0.07)), head, font, text_color,
                 spacing_frac=0.14, anchor_center_x=w / 2)

    # 2. 원근 타원 텍스트 링 (제품 둘레, 반복 문구) — 레퍼런스처럼 큼직하게
    phrase = (subcopy.upper() if subcopy.isascii() else subcopy).strip()
    ring_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    cx = info["cx"]
    cy = int(info["y1"] - (info["y1"] - info["y0"]) * 0.12)  # 제품 하단부 = 바닥면
    a = max(int((info["x1"] - info["x0"]) * 0.72), int(w * 0.34))
    a = min(a, int(w * 0.46))
    b = int(a * 0.34)

    ring_font = _font("didone" if phrase.isascii() else "serif", int(h * 0.046))
    letter_gap = 1.15  # 자간 (글자폭 배수)

    # 진행 파라미터: 하단 중앙(φ=π/2)에서 시작, φ 감소 = 화면상 좌→우 진행.
    # 이미지 좌표(y-down)에서 하단 호 텍스트가 정방향으로 읽히는 유일한 방향.
    phis = np.linspace(math.pi / 2, math.pi / 2 - 2 * math.pi, 1440)
    pts = np.stack([a * np.cos(phis), b * np.sin(phis)], axis=1)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    total_len = cum[-1]

    unit = phrase + "  •  "
    unit_w = sum(ring_font.getlength(ch) * letter_gap for ch in unit)
    reps = max(1, round(total_len / unit_w))
    text = unit * reps
    # 반복 문구가 정확히 한 바퀴를 채우도록 자간을 미세 조정
    scale_gap = total_len / max(sum(ring_font.getlength(c) * letter_gap for c in text), 1)

    dist = 0.0
    for ch in text:
        ch_w = ring_font.getlength(ch) * letter_gap * scale_gap
        phi = float(np.interp((dist + ch_w / 2) % total_len, cum, phis))
        x = cx + a * math.cos(phi)
        y = cy + b * math.sin(phi)
        # 시각 기준 회전각 (y-down 보정 포함): 하단 0° / 우측 +90° / 상단 180°
        rot = math.degrees(math.atan2(b * math.cos(phi), a * math.sin(phi)))
        gw = int(ring_font.getlength(ch)) + 8
        glyph = Image.new("RGBA", (gw, ring_font.size + 10), (0, 0, 0, 0))
        ImageDraw.Draw(glyph).text((4, 0), ch, font=ring_font, fill=text_color)
        glyph = glyph.rotate(rot, expand=True, resample=Image.BICUBIC)
        ring_layer.paste(glyph, (int(x - glyph.width / 2), int(y - glyph.height / 2)), glyph)
        dist += ch_w

    img.paste(ring_layer, (0, 0), ring_layer)
    # 3. 깊이: 제품을 링 위에 다시 얹음 (상단 호가 제품 뒤로)
    img.paste(product_rgba, (0, 0), product_rgba)
    return img


# --- 템플릿: banner (곡선 리본, retro_paper) ------------------------------------
def _bezier(p0, p1, p2, p3, n=120):
    t = np.linspace(0, 1, n)[:, None]
    return ((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1
            + 3 * (1 - t) * t**2 * p2 + t**3 * p3)


def _dilate_np(binary: np.ndarray, iterations: int) -> np.ndarray:
    out = binary.copy()
    for _ in range(iterations):
        s = [out]
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    s.append(np.roll(np.roll(out, dy, 0), dx, 1))
        out = np.max(np.stack(s), 0)
    return out


def _split_headline(text: str) -> list[str]:
    """긴 헤드라인을 균형 있게 1~2줄로 분할."""
    words = text.split()
    if len(words) <= 1 or len(text) <= 12:
        return [text]
    best, best_diff = None, 1e9
    for i in range(1, len(words)):
        l1, l2 = " ".join(words[:i]), " ".join(words[i:])
        diff = abs(len(l1) - len(l2))
        if diff < best_diff:
            best, best_diff = [l1, l2], diff
    return best


def _apply_banner(img, product_rgba, mask, info, headline, subcopy, color):
    """레트로 배너 (레퍼런스: 두툼한 유기 블롭이 영문 헤드라인을 품고, 꼬리가
    제품 옆을 감아 내려가는 구조. 배경은 생성 단계에서 크림 아이보리 평면)."""
    w, h = img.size
    sig = _deepen(color)
    rng = np.random.default_rng(11)

    head = headline.upper() if headline.isascii() else headline
    lines = _split_headline(head)

    # 1. 헤드라인 블롭: 상단을 가로지르는 물결 경로를 따라 큰 원들을 겹쳐 유기 블롭 생성
    ribbon = Image.new("RGBA", img.size, (0, 0, 0, 0))
    rd = ImageDraw.Draw(ribbon)
    blob_cy = h * (0.10 if len(lines) == 1 else 0.13)
    blob_r = h * (0.075 if len(lines) == 1 else 0.115)
    ts = np.linspace(0, 1, 160)
    for t in ts:
        x = w * (0.10 + 0.80 * t)
        y = blob_cy + h * 0.028 * math.sin(t * math.pi * 1.7 + 0.4)
        r = blob_r * (1.0 + 0.10 * math.sin(t * math.pi * 2.3))
        # 양 끝 라운딩
        edge = min(t, 1 - t) / 0.12
        r *= min(1.0, 0.55 + 0.45 * edge)
        rd.ellipse([x - r, y - r, x + r, y + r], fill=sig + (255,))

    # 2. 꼬리: 블롭 끝에서 제품 옆을 감아 내려가는 테이퍼 곡선
    tail = np.concatenate([
        _bezier(np.array([w * 0.88, blob_cy + blob_r * 0.5]),
                np.array([w * 0.985, h * 0.36]),
                np.array([w * 0.93, h * 0.52]), np.array([w * 0.88, h * 0.62])),
        _bezier(np.array([w * 0.88, h * 0.62]), np.array([w * 0.83, h * 0.72]),
                np.array([w * 0.72, h * 0.78]), np.array([w * 0.60, h * 0.76])),
    ])
    thick = h * 0.032
    n = len(tail)
    for i, (x, y) in enumerate(tail):
        r = thick * (1.0 - 0.62 * (i / max(n - 1, 1)))
        rd.ellipse([x - r, y - r, x + r, y + r], fill=sig + (255,))

    # 반대편 짧은 꼬리 (좌하 — 레퍼런스의 비대칭 흐름)
    tail2 = _bezier(np.array([w * 0.12, blob_cy + blob_r * 0.6]),
                    np.array([w * 0.015, h * 0.34]),
                    np.array([w * 0.06, h * 0.46]), np.array([w * 0.13, h * 0.52]))
    for i, (x, y) in enumerate(tail2):
        r = thick * 0.9 * (1.0 - 0.62 * (i / (len(tail2) - 1)))
        rd.ellipse([x - r, y - r, x + r, y + r], fill=sig + (255,))

    # 스크린프린트 그레인
    rib = np.array(ribbon, dtype=np.float64)
    rib[..., :3] = (rib[..., :3] + rng.normal(0, 9, (h, w, 1))).clip(0, 255)
    ribbon = Image.fromarray(rib.astype(np.uint8))
    img.paste(ribbon, (0, 0), ribbon)

    # 3. 헤드라인 (아이보리 손글씨, 블롭 안 가득, 살짝 기울임)
    fsize = int((h * 0.092 if len(lines) == 1 else h * 0.085))
    font = _font("display", fsize)
    d = ImageDraw.Draw(img)
    for li, line in enumerate(lines):
        tw = d.textlength(line, font=font)
        max_w = w * 0.74
        if tw > max_w:  # 블롭 폭 초과 시 축소
            fsize2 = int(fsize * max_w / tw)
            font_l = _font("hand", fsize2)
            tw = d.textlength(line, font=font_l)
        else:
            font_l = font
        y = blob_cy - (len(lines) * fsize * 0.62) + li * fsize * 1.06
        glyph = Image.new("RGBA", (int(tw) + 24, font_l.size + 30), (0, 0, 0, 0))
        ImageDraw.Draw(glyph).text((12, 6), line, font=font_l, fill=IVORY)
        glyph = glyph.rotate(-2.5, expand=True, resample=Image.BICUBIC)
        img.paste(glyph, (int(w / 2 - glyph.width / 2), int(y)), glyph)

    # 4. 제품 아이보리 손그림 윤곽선 (약간의 갭을 두고 — 레퍼런스 스타일)
    m = (np.array(mask.resize(img.size)) >= 128).astype(np.uint8)
    outline = (_dilate_np(m, 12) - _dilate_np(m, 7)).astype(bool)
    arr = np.array(img)
    arr[outline] = IVORY
    img = Image.fromarray(arr)

    # 5. 하단 설명 (시그니처 컬러, 고딕, 1~2줄)
    d = ImageDraw.Draw(img)
    sub_font = _font("display", int(h * 0.028))
    sub_lines = _split_headline(subcopy) if len(subcopy) > 24 else [subcopy]
    for li, line in enumerate(sub_lines):
        sw = d.textlength(line, font=sub_font)
        d.text(((w - sw) / 2, int(h * 0.905) + li * int(h * 0.036)), line,
               font=sub_font, fill=sig)

    img.paste(product_rgba, (0, 0), product_rgba)
    return img


# --- 템플릿: caption (미니멀) ---------------------------------------------------
_CAPTION_FONT = {
    StylePreset.MONOTONE: "gothic",
    StylePreset.WARM_VINTAGE: "serif",
    StylePreset.POP: "gothic_bold",
    StylePreset.PASTEL_FLOAT: "gothic",
}


def _apply_caption(img, preset, info, headline, subcopy, color=None):
    w, h = img.size
    draw = ImageDraw.Draw(img)
    # 밝은 배경에서는 시그니처 딥톤(있으면), 어두우면 아이보리
    if _bg_is_bright(img):
        text_color = _deepen(color) if color else DARK
    else:
        text_color = IVORY

    # 히어로 배치(FILL_CENTER_Y=0.56)로 상단 여백이 항상 확보됨 → 상단 고정
    y = int(h * 0.06)

    kind = _CAPTION_FONT.get(preset, "gothic")
    font = _font("display" if preset == StylePreset.PASTEL_FLOAT else kind, int(h * 0.055))
    _spaced_text(draw, (0, y), headline, font, text_color,
                 spacing_frac=0.06, anchor_center_x=w / 2)
    sub_font = _font(kind if kind != "gothic_bold" else "gothic", int(h * 0.026))
    sw = draw.textlength(subcopy, font=sub_font)
    draw.text(((w - sw) / 2, y + int(h * 0.075)), subcopy, font=sub_font, fill=text_color)
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
        img = _apply_caption(img, preset, info, headline, subcopy, color)

    out = Path(output_path) if output_path else \
        Path(final_image_path).with_name(Path(final_image_path).stem + "_poster.png")
    img.convert("RGB").save(out, format="PNG")
    logger.info(f"오버레이 적용 완료 ({template}): {out}")
    return str(out)
