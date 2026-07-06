"""QUA-002: 조화(harmonization) 패스 — 합성 '붙여넣은 티' 제거 실험 — 담당: 한의정.

방법: FR-08 합성 결과(제품 픽셀 보존본)에
  ① (선택) 접촉 그림자 합성 — 제품 마스크 오프셋+블러 기반
  ② SDXL base img2img 저강도 패스 (strength 0.15 / 0.25 / 0.35)
를 적용해 조명·색·경계 융합 정도와 제품 변형량(마스크내 SSIM/L1)을 측정.

산출물 (backend/results/ai/qua002/, git 업로드 금지):
  - baseline.png, s{15,25,35}_shadow{0,1}.png, qua002_summary.md
비용 0. SDXL base 최초 다운로드 ~7GB.

실행:  .venv/bin/python backend/scripts/qua002_harmonization.py \
         [--composite backend/results/ai/cookie1_ad_42.png] \
         [--mask backend/results/ai/mask001/쿠키1_mask.png]
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

from PIL import Image, ImageFilter

from pres001_preservation import _ssim_map  # 동일 SSIM 정의 재사용 (A-3)

OUT_DIR = BACKEND_DIR / "results" / "ai" / "qua002"
STRENGTHS = (0.15, 0.25, 0.35)
SHADOW_OFFSET = (10, 14)
SHADOW_BLUR = 18
SHADOW_OPACITY = 0.35

POSITIVE = (
    "professional product advertisement photo, warm vintage atmosphere, "
    "cozy retro cafe mood, soft natural shadows, coherent lighting"
)
NEGATIVE = "text, letters, watermark, logo, human, hands, lowres, blurry, distorted"


def _add_contact_shadow(img: Image.Image, product_mask: Image.Image) -> Image.Image:
    """제품 마스크 기반 접촉 그림자: 오프셋+블러 후 배경 영역만 어둡게."""
    mask = np.array(product_mask, dtype=np.float64) / 255.0
    shadow = np.zeros_like(mask)
    dy, dx = SHADOW_OFFSET[1], SHADOW_OFFSET[0]
    shadow[dy:, dx:] = mask[:-dy, :-dx]
    shadow = np.array(
        Image.fromarray((shadow * 255).astype(np.uint8)).filter(
            ImageFilter.GaussianBlur(SHADOW_BLUR)
        ),
        dtype=np.float64,
    ) / 255.0
    shadow *= (1.0 - mask)  # 제품 위에는 그림자 없음

    arr = np.array(img, dtype=np.float64)
    darken = 1.0 - SHADOW_OPACITY * shadow[..., None]
    return Image.fromarray((arr * darken).clip(0, 255).astype(np.uint8))


_img2img = None


def _get_img2img():  # noqa: ANN202
    global _img2img
    if _img2img is None:
        import torch
        from diffusers import AutoPipelineForImage2Image

        _img2img = AutoPipelineForImage2Image.from_pretrained(
            "stabilityai/stable-diffusion-xl-base-1.0",
            torch_dtype=torch.float16, variant="fp16",
        ).to("cuda")
    return _img2img


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--composite", default=str(BACKEND_DIR / "results/ai/cookie1_ad_42.png"))
    parser.add_argument("--mask", default=str(BACKEND_DIR / "results/ai/mask001/쿠키1_mask.png"))
    args = parser.parse_args()

    import torch

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base_img = Image.open(args.composite).convert("RGB")
    product_mask = Image.open(args.mask).convert("L").resize(base_img.size)
    inner = np.array(product_mask) >= 128

    base_img.save(OUT_DIR / "baseline.png")
    ref_gray = np.array(base_img.convert("L"))
    ref_rgb = np.array(base_img)

    lines = [
        f"# QUA-002 결과 — {datetime.now().isoformat(timespec='seconds')}",
        f"- 합성본: {args.composite} / 그림자 offset={SHADOW_OFFSET}, blur={SHADOW_BLUR}, opacity={SHADOW_OPACITY}",
        "- 지표: 조화 패스 전(baseline) 대비 마스크내 SSIM/L1 — 제품 변형량. 융합 자연스러움은 육안",
        "",
        "| 변형 | strength | 그림자 | 시간(s) | 마스크내 SSIM | 마스크내 L1 |",
        "|---|---|---|---|---|---|",
    ]

    pipe = _get_img2img()
    for shadow_on in (0, 1):
        src = _add_contact_shadow(base_img, product_mask) if shadow_on else base_img
        for s in STRENGTHS:
            t0 = time.perf_counter()
            out = pipe(
                prompt=POSITIVE,
                negative_prompt=NEGATIVE,
                image=src,
                strength=s,
                guidance_scale=5.0,
                num_inference_steps=30,  # 유효 스텝 = 30×strength
                generator=torch.Generator("cuda").manual_seed(42),
            ).images[0]
            elapsed = time.perf_counter() - t0
            if out.size != base_img.size:
                out = out.resize(base_img.size, Image.LANCZOS)

            name = f"s{int(s * 100)}_shadow{shadow_on}"
            out.save(OUT_DIR / f"{name}.png")

            out_gray = np.array(out.convert("L"))
            out_rgb = np.array(out)
            ssim = float(_ssim_map(ref_gray, out_gray)[inner].mean())
            l1 = float(np.abs(out_rgb.astype(int) - ref_rgb.astype(int)).mean(axis=2)[inner].mean())
            row = f"| {name} | {s} | {'O' if shadow_on else 'X'} | {elapsed:.2f} | {ssim:.4f} | {l1:.2f} |"
            print(row)
            lines.append(row)

    lines += [
        "",
        "## 판정 기준 / 육안 기입",
        "- 목표: 마스크내 SSIM ≥ 0.85 유지하면서 '붙여넣은 티'(경계·조명 이질감) 소멸",
        "- 최적 조합: (기입)",
        "- 파이프라인 반영 여부: (기입 — 반영 시 image_service 조화 패스 추가, feat(image) 커밋)",
        "",
        "OpenAI 호출 없음 — 비용 0",
    ]
    (OUT_DIR / "qua002_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n결과 저장: {OUT_DIR}/qua002_summary.md")


if __name__ == "__main__":
    main()
