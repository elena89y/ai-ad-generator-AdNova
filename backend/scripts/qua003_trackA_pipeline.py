"""QUA-003: 트랙A 통합 검증 — BiRefNet + 그림자 + 조화 + 코어 보호 — 담당: 한의정.

체인: BiRefNet 마스크 → SDXL 배경 생성(negative v2) → 접촉 그림자
      → 조화 패스(img2img, strength 0.25) → 코어 보호 재합성(침식 6px + 페더 6px)

지표: 제품 코어 SSIM/L1 (조화 전 합성본 대비), 단계별 지연시간(warm).
산출물 (backend/results/ai/qua003/, git 업로드 금지). 비용 0.

실행:  .venv/bin/python backend/scripts/qua003_trackA_pipeline.py \
         [--inputs 쿠키1 쿠키2 스프1] [--seed 42]
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

from app.schemas.ads import ProductInfo, StylePreset
from app.services import image_service
from app.services.prompt_service import ImagePrompt, build_image_prompt
from pres001_preservation import _ssim_map
from qua002_harmonization import _add_contact_shadow, _get_img2img

OUT_DIR = BACKEND_DIR / "results" / "ai" / "qua003"
HARMONIZE_STRENGTH = 0.25
ERODE_PX = 6
FEATHER_PX = 6

# A-4 v2 (텍스트 아티팩트 억제 확인본) — 채택 확정 전이므로 실험 내 인라인 사용
V2_NEGATIVE_EXTRA = (
    "words, typography, writing, signage, label, price tag, packaging design, "
    "brand name, poster, extra food, extra cookies, additional products, people"
)


def _build_v2_prompt(product: ProductInfo) -> ImagePrompt:
    v1 = build_image_prompt(product, StylePreset.WARM_VINTAGE)
    return ImagePrompt(
        positive=v1.positive.replace("sharp focus", "high detail"),
        negative=f"{v1.negative}, {V2_NEGATIVE_EXTRA}",
    )


def _erode(binary: np.ndarray, iterations: int) -> np.ndarray:
    inv = 1 - binary
    for _ in range(iterations):
        s = [inv]
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    s.append(np.roll(np.roll(inv, dy, axis=0), dx, axis=1))
        inv = np.max(np.stack(s), axis=0)
    return 1 - inv


def _protect_core(
    harmonized: Image.Image, composite: Image.Image, product_mask: Image.Image
) -> Image.Image:
    """제품 내부=합성본(원본 픽셀), 경계 링=조화 픽셀 블렌딩."""
    binary = (np.array(product_mask) >= 128).astype(np.uint8)
    eroded = _erode(binary, ERODE_PX)
    feather = np.array(
        Image.fromarray((eroded * 255).astype(np.uint8)).filter(
            ImageFilter.GaussianBlur(FEATHER_PX)
        ),
        dtype=np.float64,
    ) / 255.0
    h = np.array(harmonized, dtype=np.float64)
    c = np.array(composite, dtype=np.float64)
    out = h * (1 - feather[..., None]) + c * feather[..., None]
    return Image.fromarray(out.clip(0, 255).astype(np.uint8))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="*", default=["쿠키1", "쿠키2", "스프1"])
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# QUA-003 결과 — {datetime.now().isoformat(timespec='seconds')}",
        f"- 체인: BiRefNet → SDXL 생성(v2 negative, seed={args.seed}) → 그림자 → 조화({HARMONIZE_STRENGTH}) → 코어 보호(침식{ERODE_PX}px+페더{FEATHER_PX}px)",
        "",
        "| 입력 | 마스크(s) | 생성(s) | 조화(s) | 총(s) | 코어 SSIM | 코어 L1 |",
        "|---|---|---|---|---|---|---|",
    ]

    # BiRefNet 세션으로 교체 (QUA-001 채택 권고 — 서비스 반영 전 실험 주입)
    import torch  # noqa: F401  (ORT CU13 선로드)
    from rembg import new_session

    image_service._get_rembg_session()  # torch/ORT preload 경로 통과
    image_service._rembg_session = new_session("birefnet-general")

    # --- 1페이즈: 마스크 + 배경 생성 (inpaint 파이프라인만 상주) --------------
    # ⚠️ L4 22GB 에서 inpaint(6.6GB)+img2img(7GB) 동시 상주 시 OOM 실측 → 순차 로드.
    #    서비스 통합 시에도 동일 제약 — 조화 파이프라인은 cpu offload 필요 (보고사항)
    staged = []
    for name in args.inputs:
        src = BACKEND_DIR / "uploads" / "photoset" / f"{name}.png"
        if not src.is_file():
            print(f"[스킵] 없음: {src}")
            continue

        t0 = time.perf_counter()
        processed = image_service.preprocess(str(src), output_dir=str(OUT_DIR))
        t_mask = time.perf_counter() - t0

        prompt = _build_v2_prompt(ProductInfo(name=name))
        gen = image_service.generate_ad_image(
            processed, prompt, seed=args.seed, output_dir=str(OUT_DIR)
        )
        staged.append((name, processed, gen, t_mask))

    # inpaint 파이프라인 해제 후 조화 파이프라인 로드
    image_service._sdxl_pipeline = None
    torch.cuda.empty_cache()
    pipe_harm = _get_img2img()

    # --- 2페이즈: 그림자 + 조화 + 코어 보호 ------------------------------------
    for name, processed, gen, t_mask in staged:
        composite = Image.open(gen.final_image_path).convert("RGB")
        product_mask = Image.open(processed.mask_path).convert("L")

        t0 = time.perf_counter()
        shadowed = _add_contact_shadow(composite, product_mask)
        harmonized = pipe_harm(
            prompt=(
                "professional product advertisement photo, warm vintage atmosphere, "
                "cozy retro cafe mood, soft natural shadows, coherent lighting"
            ),
            negative_prompt="text, letters, watermark, logo, human, hands, lowres, blurry, distorted",
            image=shadowed,
            strength=HARMONIZE_STRENGTH,
            guidance_scale=5.0,
            num_inference_steps=30,
            generator=torch.Generator("cuda").manual_seed(args.seed),
        ).images[0]
        if harmonized.size != composite.size:
            harmonized = harmonized.resize(composite.size, Image.LANCZOS)
        final = _protect_core(harmonized, composite, product_mask)
        t_harm = time.perf_counter() - t0

        final_path = OUT_DIR / f"{name}_final.png"
        final.save(final_path)
        harmonized.save(OUT_DIR / f"{name}_harmonized_raw.png")

        # 코어 보존 지표 (조화 전 합성본 대비, 침식 코어 한정)
        core = _erode((np.array(product_mask) >= 128).astype(np.uint8), ERODE_PX).astype(bool)
        ref_g = np.array(composite.convert("L"))
        out_g = np.array(final.convert("L"))
        ssim = float(_ssim_map(ref_g, out_g)[core].mean())
        l1 = float(
            np.abs(np.array(final, dtype=int) - np.array(composite, dtype=int))
            .mean(axis=2)[core].mean()
        )

        total = t_mask + gen.infer_seconds + t_harm
        row = (
            f"| {name} | {t_mask:.2f} | {gen.infer_seconds:.2f} | {t_harm:.2f} | "
            f"{total:.2f} | {ssim:.4f} | {l1:.2f} |"
        )
        print(row)
        lines.append(row)

    lines += [
        "",
        "## 판정 기준 / 육안 기입",
        "- 코어 SSIM ≥ 0.95 + '붙여넣은 티' 소멸 + 마스크 누락 얼룩 없음 → 트랙A 레시피 확정",
        "- 확정 시 image_service 반영: BiRefNet 교체 + 조화 패스(+코어 보호) 옵션 — feat(image) 커밋",
        "",
        "OpenAI 호출 없음 — 비용 0",
    ]
    (OUT_DIR / "qua003_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n결과 저장: {OUT_DIR}/qua003_summary.md")


if __name__ == "__main__":
    main()
