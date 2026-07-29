"""템플릿 생성물 결정론적 후처리 크롭 (TEMPLATE-PIPE-V2 · 2026-07-21 · 담당: 한의정).

프롬프트 프레이밍은 복불복이라, '풀 슬라이스를 여백과 함께 생성 → 코드로 크롭'하는
2단계로 구도를 결정론적으로 보장한다. 현재 레시피:

  layers_oneside — 케이크 단면 히어로. 층이 프레임을 가로로 꽉 채우고, 배경 여백이 더
    넓은 한쪽 끝(단면 가장자리)만 5mm 근사 여백을 두고 노출, 반대쪽 끝은 프레임 밖으로
    흘려보낸다. 윗면 데코(과일 등)는 수직 길이의 ~70%까지 노출(위 일부만 컷).

배경색이 매번 달라지므로(프롬프트가 '케이크에 어울리는 단색') 배경 감지는 테두리 링
중앙값 + 비배경 열/행의 최장 연속 구간으로 견고화한다. 크롭 실패는 무해 폴백(원본 유지).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def apply(recipe: str, path: str) -> None:
    """recipe 에 따라 path 이미지를 제자리 크롭한다. 실패해도 예외를 삼켜 생성은 유효."""
    try:
        if recipe == "layers_oneside":
            _crop_layers_oneside(path)
        else:
            logger.warning("template_crop: 미지 레시피 '%s' — 건너뜀", recipe)
    except Exception:  # noqa: BLE001 — 후처리 실패가 생성 결과를 버리면 안 됨
        logger.exception("template_crop 실패 — 원본 유지: %s", path)


def _bg_color(img):
    """배경색 = 바깥 테두리 링 채널별 중앙값 (그라데이션·비네팅에 견고)."""
    small = img.resize((64, max(1, round(64 * img.height / img.width))))
    sw, sh = small.size
    px = small.load()
    b = max(2, sw // 12)
    ring = [px[x, y][:3] for y in range(sh) for x in range(sw)
            if x < b or x >= sw - b or y < b or y >= sh - b]
    return tuple(sorted(c[i] for c in ring)[len(ring) // 2] for i in range(3))


def _longest_run(fracs, f):
    """frac >= f 인 최장 연속 구간 (start, end). 흩어진 배경 오탐 배제."""
    best = (0, len(fracs) - 1, -1)
    start = None
    for i, v in enumerate(list(fracs) + [0.0]):
        if v >= f and start is None:
            start = i
        elif v < f and start is not None:
            if i - start > best[2]:
                best = (start, i - 1, i - start)
            start = None
    return best[0], best[1]


def _bbox(img, bg, thresh=80, frac=0.20):
    """케이크 바운딩박스 = 비배경 비율이 높은 열/행의 최장 연속 구간."""
    W, H = img.size
    small = img.resize((256, max(1, round(256 * H / W))))
    sw, sh = small.size
    px = small.load()

    def d(p):
        return abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2])

    col = [sum(1 for y in range(sh) if d(px[x, y]) > thresh) / sh for x in range(sw)]
    row = [sum(1 for x in range(sw) if d(px[x, y]) > thresh) / sw for y in range(sh)]
    x0s, x1s = _longest_run(col, frac)
    y0s, y1s = _longest_run(row, frac)
    sx, sy = W / sw, H / sh
    return int(x0s * sx), int(y0s * sy), int((x1s + 1) * sx), int((y1s + 1) * sy)


def _crop_layers_oneside(path: str, deco_expose=0.70, deco_frac=0.28,
                         end_gap=0.05, opp_bleed=0.08, out_w=1024) -> None:
    from PIL import Image

    img = Image.open(path).convert("RGB")
    W, H = img.size
    bg = _bg_color(img)
    x0, y0, x1, y1 = _bbox(img, bg)
    cw, ch = x1 - x0, y1 - y0
    if cw < W * 0.2 or ch < H * 0.2:  # 감지 실패 방어 — 원본 유지
        logger.warning("template_crop: bbox 비정상(%s) — 원본 유지", (x0, y0, x1, y1))
        return
    gap = int(end_gap * cw)       # 노출 끝의 배경 여백 (≈5mm)
    bleed = int(opp_bleed * cw)   # 반대 끝을 프레임 밖으로
    # 세로: 윗면 데코(상단 deco_frac 추정)를 deco_expose 만큼만 노출
    top = y0 + int((1 - deco_expose) * deco_frac * ch)
    bot = min(H, y1 + int(0.015 * ch))
    # 가로: 배경 여백이 더 넓은 쪽 끝을 노출, 반대쪽은 프레임 밖으로
    show_right = (W - x1) >= x0
    if show_right:
        right, left = min(W, x1 + gap), max(0, x0 + bleed)
    else:
        left, right = max(0, x0 - gap), min(W, x1 - bleed)
    region = img.crop((left, top, right, bot))
    rw, rh = region.size
    region = region.resize((out_w, max(1, round(out_w * rh / rw))), Image.LANCZOS)
    region.save(path)
    logger.info("template_crop layers_oneside: bbox=%s end=%s out=%s",
                (x0, y0, x1, y1), "R" if show_right else "L", region.size)
