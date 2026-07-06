"""MASK-001: rembg u2net 마스크 경계 검증 (A-2) — 담당: 한의정.

목적: IMG-002 생성 결과의 제품(쿠키) 접합부 붕괴가 마스크 경계·누락 영역과
일치하는지 확인 → SDXL 모델 문제 vs 마스킹/합성 문제 분리.

산출물 (backend/results/ai/mask001/, git 업로드 금지):
  - 0_processed.png / 0_mask.png        : 전처리 결과·마스크
  - 1_mask_edge_overlay.png             : 마스크 윤곽(빨강)을 제품 위에 오버레이
  - 2_<생성이미지>_diff_overlay.png      : |생성-원제품| 히트맵 + 마스크 윤곽(빨강)
  - 3_<생성이미지>_crop<k>.png           : 경계 인접 고차이 지점 확대 (생성|원본 비교)
  - mask001_summary.md                  : 통계·해석 기준

OpenAI 호출 없음 — 비용 0. GPU 있으면 rembg 가속.

실행:  .venv/bin/python backend/scripts/mask001_boundary_check.py \
         [--input backend/uploads/photoset/쿠키1.png] [--gen 생성이미지 ...]
"""
from __future__ import annotations

import argparse
import sys
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from PIL import Image

from app.services import image_service

OUT_DIR = BACKEND_DIR / "results" / "ai" / "mask001"


def _binary(mask: np.ndarray, thr: int = 128) -> np.ndarray:
    return (mask >= thr).astype(np.uint8)


def _dilate(binary: np.ndarray, iterations: int) -> np.ndarray:
    """3×3 max 필터 반복 (scipy 없이 numpy roll 로 구현)."""
    out = binary.copy()
    for _ in range(iterations):
        stacked = [out]
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                stacked.append(np.roll(np.roll(out, dy, axis=0), dx, axis=1))
        out = np.max(np.stack(stacked), axis=0)
    return out


def _edge(binary: np.ndarray) -> np.ndarray:
    return _dilate(binary, 1) - binary  # 바깥쪽 1px 윤곽


def _hole_pixels(binary: np.ndarray) -> int:
    """제품 영역 내부 구멍(배경으로 뚫린 픽셀) 수: 테두리에서 flood fill 후 남은 배경."""
    h, w = binary.shape
    visited = np.zeros_like(binary, dtype=bool)
    dq: deque = deque()
    for x in range(w):
        for y in (0, h - 1):
            if binary[y, x] == 0 and not visited[y, x]:
                visited[y, x] = True
                dq.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if binary[y, x] == 0 and not visited[y, x]:
                visited[y, x] = True
                dq.append((y, x))
    while dq:
        y, x = dq.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and binary[ny, nx] == 0 and not visited[ny, nx]:
                visited[ny, nx] = True
                dq.append((ny, nx))
    return int(((binary == 0) & ~visited).sum())


def _overlay_contour(base_rgb: np.ndarray, edge: np.ndarray) -> Image.Image:
    out = base_rgb.copy()
    out[edge > 0] = [255, 0, 0]
    return Image.fromarray(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(BACKEND_DIR / "uploads/photoset/쿠키1.png"))
    parser.add_argument("--gen", nargs="*", default=None,
                        help="검사할 생성 이미지들 (기본: results/ai 의 cookie1_ad_*.png)")
    parser.add_argument("--boundary-px", type=int, default=24, help="경계 인접 판정 거리(px)")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# MASK-001 결과 — {datetime.now().isoformat(timespec='seconds')}",
        f"- 입력: {args.input}",
        "",
    ]

    def record(t: str) -> None:
        print(t)
        lines.append(t)

    # 1) 전처리 → 마스크
    processed = image_service.preprocess(args.input, output_dir=str(OUT_DIR))
    proc_img = Image.open(processed.processed_image_path).convert("RGBA")
    mask_img = Image.open(processed.mask_path).convert("L")
    mask = np.array(mask_img)
    binary = _binary(mask)

    # 흰 배경 합성본 (post-composite 기준 이미지 = generate_ad_image 의 init 과 동일)
    base = Image.new("RGBA", proc_img.size, (255, 255, 255, 255))
    base.alpha_composite(proc_img)
    init_rgb = np.array(base.convert("RGB"))

    # 2) 마스크 통계
    total = mask.size
    product_px = int(binary.sum())
    soft_px = int(((mask > 16) & (mask < 240)).sum())
    holes = _hole_pixels(binary)
    record("## 마스크 통계")
    record(f"- 제품 영역: {product_px / total:.1%} ({product_px}px)")
    record(f"- 번짐(soft edge, 16<α<240): {soft_px}px — 제품 영역 대비 {soft_px / max(product_px, 1):.1%}")
    record(f"- 내부 구멍(hole): {holes}px — 제품 영역 대비 {holes / max(product_px, 1):.2%}")

    edge = _edge(binary)
    _overlay_contour(init_rgb, edge).save(OUT_DIR / "1_mask_edge_overlay.png")
    record("- 윤곽 오버레이: 1_mask_edge_overlay.png")

    # 3) 생성 이미지별 차이 분석
    if args.gen:
        gen_paths = [Path(p) for p in args.gen]
    else:
        results_ai = BACKEND_DIR / "results" / "ai"
        gen_paths = sorted(results_ai.glob("cookie1_ad_*.png")) + \
                    sorted(results_ai.glob("lat001_steps20/cookie1_ad_*.png"))

    record("\n## 생성 이미지별 붕괴-경계 분석")
    for gp in gen_paths:
        if not gp.is_file():
            record(f"- [스킵] 없음: {gp}")
            continue
        gen = np.array(Image.open(gp).convert("RGB").resize(proc_img.size))
        diff = np.abs(gen.astype(int) - init_rgb.astype(int)).sum(axis=2)  # 0~765

        # 제품 내부(마스크 안)는 post-composite 로 0 이어야 정상 — 잔차 확인
        inner = binary.astype(bool)
        inner_diff = float(diff[inner].mean())
        # 경계 밴드(마스크 밖 boundary_px 이내) 차이 — 배경이므로 다른 게 정상이지만
        # 원제품 픽셀과 '비슷했어야 할' 누락 영역이 있으면 여기서 육안 확인
        band_out = (_dilate(binary, args.boundary_px).astype(bool)) & ~inner
        band_diff = float(diff[band_out].mean())

        tag = gp.parent.name + "_" + gp.stem if gp.parent.name == "lat001_steps20" else gp.stem
        heat = np.zeros_like(gen)
        heat[..., 0] = np.clip(diff // 3, 0, 255)
        vis = (gen * 0.55 + heat * 0.45).astype(np.uint8)
        vis[edge > 0] = [255, 0, 0]
        Image.fromarray(vis).save(OUT_DIR / f"2_{tag}_diff_overlay.png")

        # 경계 인접 고차이 지점 top-2 확대 (생성|기준 나란히)
        masked_diff = np.where(band_out, diff, 0)
        crops = []
        tmp = masked_diff.copy()
        for k in range(2):
            idx = np.unravel_index(np.argmax(tmp), tmp.shape)
            if tmp[idx] <= 0:
                break
            y, x = idx
            y0, x0 = max(0, y - 128), max(0, x - 128)
            y1, x1 = min(gen.shape[0], y0 + 256), min(gen.shape[1], x0 + 256)
            pair = np.concatenate([gen[y0:y1, x0:x1], init_rgb[y0:y1, x0:x1]], axis=1)
            crop_path = OUT_DIR / f"3_{tag}_crop{k + 1}.png"
            Image.fromarray(pair).save(crop_path)
            crops.append(crop_path.name)
            tmp[max(0, y - 160):y + 160, max(0, x - 160):x + 160] = 0  # 중복 지점 제외

        record(f"- {tag}: 제품내부 잔차 {inner_diff:.1f} (0이어야 정상) / "
               f"경계밴드({args.boundary_px}px) 평균차 {band_diff:.1f} / 확대: {', '.join(crops) or '없음'}")

    record("\n## 판정 기준")
    record("- 제품내부 잔차 ≈ 0 → post-composite 정상 동작 (내부 붕괴는 없음)")
    record("- 붕괴 지점(확대 crop)이 마스크 윤곽·구멍과 겹침 → 마스킹 문제 (모델 교체 무관)")
    record("- 붕괴 지점이 마스크와 무관한 위치 → 생성 모델 품질 문제")
    record("\nOpenAI 호출 없음 — 비용 0")

    (OUT_DIR / "mask001_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n결과 저장: {OUT_DIR}/mask001_summary.md")


if __name__ == "__main__":
    main()
