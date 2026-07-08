"""PRES-001: 제품 영역 픽셀 보존율 측정 — SSIM + L1 (A-3) — 담당: 한의정.

원본 제품 픽셀(전처리 산출, 흰 배경 합성) vs 생성 결과를
  ① 마스크 한정 (제품 내부 — post-composite 로 보존됐어야 하는 영역)
  ② 경계 밴드 (마스크 외곽 24px — MASK-001 에서 확인된 누락 손상 영역)
두 구간에서 SSIM·L1 로 정량화. 로컬 연산 — OpenAI 호출 없음, 비용 0.

SSIM: 7×7 box window, C1=(0.01·255)², C2=(0.03·255)² (표준 상수), 그레이스케일.

실행:  .venv/bin/python backend/scripts/pres001_preservation.py \
         [--input backend/uploads/photoset/쿠키1.png] [--gen 생성이미지 ...]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from PIL import Image

from app.services import image_service

OUT_DIR = BACKEND_DIR / "results" / "ai" / "pres001"
WIN = 7  # SSIM window


def _box_filter(img: np.ndarray, win: int) -> np.ndarray:
    """win×win 평균 필터 (cumsum 기반, 가장자리는 유효영역 축소 평균)."""
    pad = win // 2
    padded = np.pad(img, pad, mode="edge").astype(np.float64)
    c = padded.cumsum(axis=0).cumsum(axis=1)
    c = np.pad(c, ((1, 0), (1, 0)))
    h, w = img.shape
    s = c[win:win + h, win:win + w] - c[:h, win:win + w] - c[win:win + h, :w] + c[:h, :w]
    return s / (win * win)


def _ssim_map(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """그레이스케일 SSIM 맵."""
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    mu_a, mu_b = _box_filter(a, WIN), _box_filter(b, WIN)
    var_a = _box_filter(a * a, WIN) - mu_a**2
    var_b = _box_filter(b * b, WIN) - mu_b**2
    cov = _box_filter(a * b, WIN) - mu_a * mu_b
    return ((2 * mu_a * mu_b + c1) * (2 * cov + c2)) / (
        (mu_a**2 + mu_b**2 + c1) * (var_a + var_b + c2)
    )


def _dilate(binary: np.ndarray, iterations: int) -> np.ndarray:
    out = binary.copy()
    for _ in range(iterations):
        stacked = [out]
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    stacked.append(np.roll(np.roll(out, dy, axis=0), dx, axis=1))
        out = np.max(np.stack(stacked), axis=0)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(BACKEND_DIR / "uploads/photoset/쿠키1.png"))
    parser.add_argument("--gen", nargs="*", default=None)
    parser.add_argument("--band-px", type=int, default=24)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# PRES-001 결과 — {datetime.now().isoformat(timespec='seconds')}",
        f"- 입력: {args.input} / SSIM {WIN}×{WIN} box window / 경계 밴드 {args.band_px}px",
        "- 기준 이미지 = 전처리 산출(제품 + 흰 배경 합성) — generate_ad_image 의 init 과 동일",
        "",
        "| 생성 이미지 | 마스크내 SSIM | 마스크내 L1 | 경계밴드 SSIM | 경계밴드 L1 |",
        "|---|---|---|---|---|",
    ]

    processed = image_service.preprocess(args.input, output_dir=str(OUT_DIR))
    proc = Image.open(processed.processed_image_path).convert("RGBA")
    base = Image.new("RGBA", proc.size, (255, 255, 255, 255))
    base.alpha_composite(proc)
    ref_rgb = np.array(base.convert("RGB"))
    ref_gray = np.array(base.convert("L"))

    mask = np.array(Image.open(processed.mask_path).convert("L"))
    inner = (mask >= 128).astype(np.uint8)
    band = (_dilate(inner, args.band_px).astype(bool)) & ~inner.astype(bool)
    inner_b = inner.astype(bool)

    if args.gen:
        gen_paths = [Path(p) for p in args.gen]
    else:
        results_ai = BACKEND_DIR / "results" / "ai"
        gen_paths = sorted(results_ai.glob("cookie1_ad_*.png")) + \
                    sorted(results_ai.glob("lat001_steps20/cookie1_ad_*.png"))

    for gp in gen_paths:
        if not gp.is_file():
            continue
        gen_img = Image.open(gp).convert("RGB").resize(proc.size)
        gen_rgb = np.array(gen_img)
        gen_gray = np.array(gen_img.convert("L"))

        ssim = _ssim_map(ref_gray, gen_gray)
        l1 = np.abs(gen_rgb.astype(int) - ref_rgb.astype(int)).mean(axis=2)

        tag = gp.parent.name + "_" + gp.stem if gp.parent.name == "lat001_steps20" else gp.stem
        row = (
            f"| {tag} | {ssim[inner_b].mean():.4f} | {l1[inner_b].mean():.2f} | "
            f"{ssim[band].mean():.4f} | {l1[band].mean():.2f} |"
        )
        print(row)
        lines.append(row)

    lines += [
        "",
        "## 해석 기준",
        "- 마스크내 SSIM ≈ 1.0 / L1 ≈ 0 → post-composite 보존 보장 확인 (IMG-002 '보존 5점' 정량 근거)",
        "- 경계밴드 수치는 배경 교체 특성상 낮게 나오는 게 정상이나, MASK-001 확인 결과",
        "  이 밴드에 '마스크가 놓친 실제 제품 픽셀'이 포함됨 — 낮은 값 = 누락 제품 영역 손상의 정량 증거",
        "- 주의: 마스크 자체가 제품을 다 못 잡는 입력(다중 객체·프레임 잘림)에서는 '마스크내 보존율'이",
        "  실제 제품 보존율의 상한이 아님 (A-2 개선 후 재측정 필요)",
        "",
        "OpenAI 호출 없음 — 비용 0",
    ]
    (OUT_DIR / "pres001_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n결과 저장: {OUT_DIR}/pres001_summary.md")


if __name__ == "__main__":
    main()
