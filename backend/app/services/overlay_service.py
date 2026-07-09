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
        # 스타일별 다양성 확장(OFL): 에디토리얼=고운바탕 / 팝=블랙한산스 / 레트로=구기 /
        #   캐주얼=개구 / 라운드=도현 / 영문 콘덴스드=베바스
        "serif_elegant": "GowunBatang-Regular.ttf",
        "display_heavy": "BlackHanSans-Regular.ttf",
        "display_quirky": "Gugi-Regular.ttf",
        "hand_casual": "Gaegu-Regular.ttf",
        "display_round": "DoHyeon-Regular.ttf",
        "condensed": "BebasNeue-Regular.ttf",
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


def _organic_blob_pts(cx, cy, rx, ry, seed=11, harmonics=((2, 0.09), (3, 0.06), (5, 0.045))):
    """저주파 하모닉 반경 함수 기반 유기 블롭 윤곽 (디자이너 잉크 블롭의 형태 특성)."""
    rng = np.random.default_rng(seed)
    theta = np.linspace(0, 2 * math.pi, 720)
    r = np.ones_like(theta)
    for k, amp in harmonics:
        r += amp * np.sin(k * theta + rng.uniform(0, 2 * math.pi))
    return np.stack([cx + rx * r * np.cos(theta), cy + ry * r * np.sin(theta)], axis=1)


def _liquid_smooth(shape: Image.Image, blur: int = 12) -> Image.Image:
    """블러+임계값 모폴로지 스무딩 — 획·블롭 접합부를 잉크처럼 융합."""
    from PIL import ImageFilter

    sm = shape.filter(ImageFilter.GaussianBlur(blur)).point(lambda p: 255 if p >= 128 else 0)
    return sm.filter(ImageFilter.GaussianBlur(1.6))


def _apply_banner(img, product_rgba, mask, info, headline, subcopy, color):
    """레트로 배너: 유기 블롭(헤드라인 하우징) + 흐르는 꼬리를 하나의 잉크
    실루엣으로 융합. 배경은 생성 단계에서 크림 아이보리 평면."""
    w, h = img.size
    sig = _deepen(color)
    rng = np.random.default_rng(11)

    head = headline.upper() if headline.isascii() else headline
    lines = _split_headline(head)

    # 1. 형태 마스크(L): 블롭 + 꼬리를 흰색으로 그린 뒤 액체 스무딩으로 융합
    shape = Image.new("L", img.size, 0)
    sd = ImageDraw.Draw(shape)

    blob_cy = h * (0.115 if len(lines) == 1 else 0.145)
    blob_rx, blob_ry = w * 0.40, h * (0.085 if len(lines) == 1 else 0.125)
    sd.polygon([tuple(p) for p in _organic_blob_pts(w * 0.50, blob_cy, blob_rx, blob_ry)],
               fill=255)

    # 우측 꼬리: 블롭에서 흘러내려 제품 옆을 감싸는 스트로크
    tail = np.concatenate([
        _bezier(np.array([w * 0.82, blob_cy + blob_ry * 0.55]),
                np.array([w * 0.97, h * 0.33]),
                np.array([w * 0.935, h * 0.50]), np.array([w * 0.86, h * 0.64])),
        _bezier(np.array([w * 0.86, h * 0.64]), np.array([w * 0.80, h * 0.75]),
                np.array([w * 0.68, h * 0.80]), np.array([w * 0.575, h * 0.77])),
    ])
    thick = h * 0.040
    n = len(tail)
    for i, (x, y) in enumerate(tail):
        r = thick * (1.0 - 0.55 * (i / max(n - 1, 1)))
        sd.ellipse([x - r, y - r, x + r, y + r], fill=255)

    # 좌측 짧은 꼬리 (비대칭 흐름)
    tail2 = _bezier(np.array([w * 0.16, blob_cy + blob_ry * 0.62]),
                    np.array([w * 0.02, h * 0.33]),
                    np.array([w * 0.055, h * 0.45]), np.array([w * 0.125, h * 0.50]))
    for i, (x, y) in enumerate(tail2):
        r = thick * 0.85 * (1.0 - 0.55 * (i / (len(tail2) - 1)))
        sd.ellipse([x - r, y - r, x + r, y + r], fill=255)

    shape = _liquid_smooth(shape, blur=14)

    # 2. 시그니처 컬러 채움 + 스크린프린트 그레인
    fill = np.zeros((h, w, 4), dtype=np.float64)
    fill[..., 0], fill[..., 1], fill[..., 2] = sig
    fill[..., :3] += rng.normal(0, 9, (h, w, 1))
    fill[..., 3] = np.array(shape, dtype=np.float64)
    ribbon = Image.fromarray(fill.clip(0, 255).astype(np.uint8))
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


# --- 템플릿: text_only (그래픽 없이 타이포만 — FLUX 등 배경 자체가 그래픽인 경우) --
def _apply_text_only(img, info, headline, subcopy, color):
    """배경이 이미 완성된 그래픽(FLUX 생성)일 때: 블롭·리본 없이 글자만 얹는다.

    역할 분리 원칙(그래픽=생성모델 / 타이포=코드)의 코드 측 구현.
    헤드라인은 상단(배경 그래픽 위), 서브카피는 하단. 배경 명도로 색 자동 결정.
    """
    w, h = img.size
    d = ImageDraw.Draw(img)
    # 헤드라인 영역(상단) 명도로 색 결정
    head_color = IVORY if not _bg_is_bright(img, y_frac=0.18) else _deepen(color)

    head = headline.upper() if headline.isascii() else headline
    lines = _split_headline(head)
    fsize = int(h * (0.088 if len(lines) == 1 else 0.082))
    font = _font("display", fsize)
    for i, line in enumerate(lines):
        tw = d.textlength(line, font=font)
        if tw > w * 0.86:
            font = _font("display", int(fsize * w * 0.86 / tw))
            tw = d.textlength(line, font=font)
        d.text(((w - tw) / 2, int(h * 0.045) + i * int(fsize * 1.05)), line,
               font=font, fill=head_color)

    # 서브카피(하단) — 항상 시그니처 딥톤
    sub_font = _font("gothic_bold", int(h * 0.028))
    sw = d.textlength(subcopy, font=sub_font)
    d.text(((w - sw) / 2, int(h * 0.915)), subcopy, font=sub_font, fill=_deepen(color))
    return img


# --- 템플릿: food_poster (A모드 풀블리드 음식 광고) ------------------------------
def _dominant_warm(img: Image.Image) -> tuple[int, int, int]:
    """중앙 영역의 채도 있는 웜 컬러 (음식 액센트용). 마스크 불필요."""
    w, h = img.size
    crop = img.crop((int(w * 0.2), int(h * 0.2), int(w * 0.8), int(h * 0.8)))
    arr = np.asarray(crop.convert("RGB"), dtype=np.float64) / 255.0
    px = arr.reshape(-1, 3)
    mx, mn = px.max(1), px.min(1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    # 웜레드 계열만 (R 이 최대 채널) — 초록 가니시·채소 색이 액센트로 새는 것 방지
    warm = (px[:, 0] >= px[:, 1]) & (px[:, 0] >= px[:, 2])
    pool = px[(sat > 0.3) & warm]
    if len(pool) < 50:
        return (214, 150, 70)
    r, g, b = pool.mean(0)
    return _deepen((int(r * 255), int(g * 255), int(b * 255)))


def _deep_panel(color: tuple[int, int, int]) -> tuple[int, int, int]:
    """패널 배경용 딥톤 (명도 강하게 낮춰 아이보리 텍스트 대비 확보)."""
    h_, s, v = colorsys.rgb_to_hsv(*(c / 255.0 for c in color))
    v = min(v, 0.26)
    s = min(max(s, 0.35), 0.7)
    r, g, b = colorsys.hsv_to_rgb(h_, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))


def _draw_headline(d, x, y, lines, font, fill, line_h, center_x=None):
    """세리프 헤드라인 렌더 (자간 살짝). center_x 있으면 중앙정렬."""
    for line in lines:
        _spaced_text(d, (x, y), line, font, fill, spacing_frac=0.02, anchor_center_x=center_x)
        y += line_h
    return y


def apply_food_poster(
    image_path: str,
    headline: str,
    subcopy: str,
    kicker: str = "",
    output_path: Optional[str] = None,
    accent: Optional[tuple[int, int, int]] = None,
    layout: str = "overlay",
    head_kind: Optional[str] = None,
    style_key: Optional[str] = None,
) -> str:
    """A모드(리터치형) 프리미엄 음식 포스터 — 누끼 없음, 사진 위/아래 조판.

    타이포: 키커(레터스페이싱 대문자) → 얇은 룰 → 세리프 헤드라인 → 서브카피.
      한글 헤드라인=명조(Myeongjo), 영문=Playfair. 배달앱 룩(둥근폰트+스크림) 탈피,
      절제된 여백·세리프 지향.
    layout:
      - overlay : 풀블리드 사진 + 하단 부드러운 그라데이션 위 좌측 정렬 텍스트
      - panel   : 사진 상단 + 하단 솔리드 딥톤 패널(에디토리얼 카드), 중앙 정렬
    """
    # 스타일 키 주면 디자인시스템 스펙에서 폰트·액센트 자동 매핑(명시 인자가 우선)
    if style_key:
        from .style_specs import get_spec
        sp = get_spec(style_key)
        head_kind = head_kind or sp.head_font
        accent = accent or sp.accent

    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    acc = accent or _dominant_warm(img)
    margin = int(w * 0.08)

    head_lines = _split_headline(headline) if len(headline) > 9 else [headline]
    head_kind = head_kind or ("didone" if headline.isascii() else "serif")

    if layout == "panel":
        # 사진 상단 66% + 하단 34% 딥톤 패널
        panel_top = int(h * 0.66)
        panel = _deep_panel(acc)
        canvas = Image.new("RGB", (w, h), panel)
        photo = img.crop((0, 0, w, panel_top))
        canvas.paste(photo, (0, 0))
        img = canvas
        d = ImageDraw.Draw(img)
        cx = w / 2
        cy0 = panel_top + int(h * 0.055)
        # 키커
        if kicker:
            kf = _font("gothic_bold", int(h * 0.020))
            _spaced_text(d, (0, cy0), kicker.upper(), kf, acc,
                         spacing_frac=0.32, anchor_center_x=cx)
            cy0 += int(h * 0.040)
        # 얇은 룰
        d.rectangle([cx - w * 0.05, cy0, cx + w * 0.05, cy0 + 2], fill=acc)
        cy0 += int(h * 0.030)
        # 헤드라인 (명조/Playfair, 중앙)
        hf = int(h * 0.056)
        head_font = _font(head_kind, hf)
        while max(d.textlength(l, font=head_font) for l in head_lines) > w - 2 * margin and hf > 20:
            hf = int(hf * 0.93); head_font = _font(head_kind, hf)
        line_h = int(hf * 1.16)
        cy0 = _draw_headline(d, 0, cy0, head_lines, head_font, IVORY, line_h, center_x=cx)
        # 서브카피
        if subcopy:
            sf = _font("gothic", int(h * 0.023))
            sw = d.textlength(subcopy, font=sf)
            d.text((cx - sw / 2, cy0 + int(h * 0.012)), subcopy, font=sf, fill=(214, 208, 200))
    else:  # overlay
        from PIL import ImageFilter

        scrim_h = int(h * 0.52)
        grad = np.linspace(0.0, 1.0, scrim_h)[:, None] ** 1.5
        scrim = np.zeros((scrim_h, w, 4), dtype=np.uint8)
        scrim[..., 0], scrim[..., 1], scrim[..., 2] = 14, 11, 9
        scrim[..., 3] = np.repeat((grad * 210).astype(np.uint8), w, axis=1)
        img = img.convert("RGBA")
        img.paste(Image.fromarray(scrim), (0, h - scrim_h), Image.fromarray(scrim))

        # 텍스트는 별도 레이어에 그려 소프트 섀도우로 밝은 배경에서도 가독성 확보
        tl = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(tl)

        hf = int(h * 0.058)
        head_font = _font(head_kind, hf)
        while max(d.textlength(l, font=head_font) for l in head_lines) > w - 2 * margin and hf > 22:
            hf = int(hf * 0.93); head_font = _font(head_kind, hf)
        line_h = int(hf * 1.18)

        # 하단 앵커 역산: 키커 + 룰 + 헤드라인 + 서브카피
        sub_h = int(h * 0.026) + int(h * 0.016) if subcopy else 0
        kick_h = (int(h * 0.020) + int(h * 0.030)) if kicker else 0
        block_h = kick_h + len(head_lines) * line_h + sub_h
        y = int(h * 0.90) - block_h

        if kicker:
            kf = _font("gothic_bold", int(h * 0.019))
            # 키커 자간이 마진을 넘으면 축소
            ks = 0.30
            while _spaced_text(ImageDraw.Draw(Image.new("RGBA", (1, 1))), (0, 0),
                               kicker.upper(), kf, acc, spacing_frac=ks) > w - 2 * margin and ks > 0.08:
                ks -= 0.04
            _spaced_text(d, (margin, y), kicker.upper(), kf, acc, spacing_frac=ks)
            y += int(h * 0.020)
            d.rectangle([margin, y + int(h * 0.006), margin + int(w * 0.09),
                         y + int(h * 0.006) + 2], fill=acc)
            y += int(h * 0.030)
        y = _draw_headline(d, margin, y, head_lines, head_font, IVORY, line_h)
        if subcopy:
            sf = _font("gothic", int(h * 0.026))
            d.text((margin, y + int(h * 0.014)), subcopy, font=sf, fill=(220, 214, 206))

        # 섀도우: 텍스트 알파를 블러해 검정으로 깔고, 그 위에 텍스트
        alpha = tl.split()[3].filter(ImageFilter.GaussianBlur(5))
        shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        shadow.putalpha(alpha.point(lambda p: int(p * 0.85)))
        img.alpha_composite(shadow, (1, 2))
        img.alpha_composite(tl)
        img = img.convert("RGB")

    out = Path(output_path) if output_path else \
        Path(image_path).with_name(Path(image_path).stem + f"_poster_{layout}.png")
    img.save(out, format="PNG")
    logger.info(f"음식 포스터 적용 완료 ({layout}): {out}")
    return str(out)


# --- 에디토리얼 포스터 (평면 단색 + 중앙 히어로 + 상단 세리프) ----------------------
def _muted_bg_from_rgba(product_rgba: Image.Image) -> tuple[int, int, int]:
    """누끼 제품의 주도색 → 채도 낮춘 중간 웜톤 배경색 (제품과 조화)."""
    arr = np.asarray(product_rgba.convert("RGBA"), dtype=np.float64)
    rgb = arr[..., :3] / 255.0
    a = arr[..., 3]
    px = rgb[a > 40]
    if len(px) < 50:
        return (150, 120, 95)
    mx, mn = px.max(1), px.min(1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    pool = px[(sat > 0.22) & (mx > 0.18) & (mx < 0.95)]
    pool = pool if len(pool) > 80 else px
    q = (pool * 12).astype(int)
    keys = q[:, 0] * 169 + q[:, 1] * 13 + q[:, 2]
    sel = pool[keys == np.bincount(keys).argmax()]
    r, g, b = sel.mean(0)
    hh, ss, vv = colorsys.rgb_to_hsv(r, g, b)
    ss = min(max(ss * 0.55, 0.26), 0.46)
    vv = min(max(vv, 0.58), 0.70)
    r, g, b = colorsys.hsv_to_rgb(hh, ss, vv)
    return (int(r * 255), int(g * 255), int(b * 255))


def apply_editorial_poster(
    product_rgba: Image.Image,
    headline: str,
    sub_headline: str,
    caption: str = "",
    bg_color: Optional[tuple[int, int, int]] = None,
    canvas_size: tuple[int, int] = (900, 1125),
    output_path: Optional[str] = None,
    product_frac: float = 0.52,
    base_frac: float = 0.72,
) -> str:
    """에디토리얼 포스터 (단색 배경 + 중앙 히어로) — 누끼 제품(RGBA) 입력.

    평면 단색 배경(제품색 뮤트) + 중앙 히어로 + 형상인식 그라운딩 그림자 + 상단 세리프.
    headline=대형 세리프(예 'SIGNATURE'), sub_headline=제품명, caption=서브헤드(sans).
    카페 디저트(B) 기본 룩 — FLUX 씬보다 싸고 통제 쉬움.
    """
    from PIL import ImageFilter

    # 1. 제품 bbox 크롭 + 엣지 페더링
    alpha = np.asarray(product_rgba.split()[-1])
    ys, xs = np.nonzero(alpha > 20)
    if len(xs) == 0:
        raise ValueError("빈 제품 마스크")
    prod = product_rgba.crop((int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())))
    prod.putalpha(prod.split()[-1].filter(ImageFilter.GaussianBlur(1.3)))

    W, H = canvas_size
    bg = bg_color or _muted_bg_from_rgba(product_rgba)
    canvas = Image.new("RGBA", (W, H), bg + (255,))

    # 2. 제품 중앙-하단 히어로 배치 — 폭·높이 둘 다 맞춰(긴 제품=음료는 높이 기준)
    max_w = int(W * product_frac)
    max_h = int(H * (base_frac - 0.30))       # 상단 텍스트 아래 ~ 바닥선
    scale = min(max_w / prod.width, max_h / prod.height)
    pw, ph = int(prod.width * scale), int(prod.height * scale)
    prod_r = prod.resize((pw, ph), Image.LANCZOS)
    px = (W - pw) // 2
    base_y = int(H * base_frac)
    py = base_y - ph

    # 3. 형상인식 접촉 그림자 (알파 세로 압축 → 바닥에 깔고 블러)
    sq_h = max(10, int(ph * 0.13))
    squashed = prod_r.split()[-1].resize((pw, sq_h), Image.LANCZOS)
    contact = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    contact.paste(Image.new("RGBA", (pw, sq_h), (18, 12, 10, 165)),
                  (px, base_y - sq_h // 2), squashed)
    canvas = Image.alpha_composite(canvas, contact.filter(ImageFilter.GaussianBlur(15)))
    canvas.paste(prod_r, (px, py), prod_r)
    canvas = canvas.convert("RGB")

    # 4. 상단 세리프 타이포 (배경 명도로 색 결정)
    d = ImageDraw.Draw(canvas)
    text_color = (247, 242, 230) if (0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]) < 165 else DARK
    head = headline.upper() if headline.isascii() else headline
    f1 = _font("didone" if head.isascii() else "serif", int(H * 0.082))
    _spaced_text(d, (0, int(H * 0.068)), head, f1, text_color, spacing_frac=0.03, anchor_center_x=W / 2)
    sub = sub_headline.upper() if sub_headline.isascii() else sub_headline
    f2 = _font("didone" if sub.isascii() else "serif", int(H * 0.048))
    _spaced_text(d, (0, int(H * 0.165)), sub, f2, text_color, spacing_frac=0.03, anchor_center_x=W / 2)
    if caption:
        f3 = _font("gothic_bold", int(H * 0.021))
        cw = d.textlength(caption, font=f3)
        d.text(((W - cw) / 2, int(H * 0.238)), caption, font=f3, fill=text_color)

    out = Path(output_path) if output_path else Path("editorial_poster.png")
    canvas.save(out, format="PNG")
    logger.info(f"에디토리얼 포스터 적용 완료: {out}")
    return str(out)


# --- 공개 API -------------------------------------------------------------------
def apply_overlay(
    final_image_path: str,
    preset: StylePreset,
    headline: str,
    subcopy: str,
    mask_path: str,
    output_path: Optional[str] = None,
    text_only: bool = False,
) -> str:
    """생성 이미지에 프리셋별 타이포 오버레이 적용 → 저장 경로 반환.

    headline/subcopy 는 FR-09 generate_copy 의 '헤드라인\\n서브카피' 를 분리해 전달.
    text_only=True: 배경이 이미 완성 그래픽(FLUX)인 경우 — 블롭·리본 없이 글자만.
    """
    img = Image.open(final_image_path).convert("RGB")
    mask = Image.open(mask_path).convert("L").resize(img.size)
    info = _mask_info(mask_path, img.size)

    # 깊이 처리용 제품 레이어 (원본 픽셀)
    product_rgba = img.convert("RGBA").copy()
    product_rgba.putalpha(mask)

    color = extract_signature_color(final_image_path, mask_path)
    template = "text_only" if text_only else _TEMPLATE_BY_PRESET.get(preset, "caption")

    if template == "text_only":
        img = _apply_text_only(img, info, headline, subcopy, color)
    elif template == "ring":
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
