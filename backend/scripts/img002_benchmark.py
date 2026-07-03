"""IMG-002: 광고 이미지 생성 모델 벤치마크 — 담당: 한의정.

비교 대상:
  - sdxl: SDXL Inpainting (A-1 1순위, image_service.generate_ad_image 공식 경로 사용)
  - flux: FLUX.1 Fill [dev] (A-1 2순위) — ⚠️ HF gated 모델: 라이선스 동의 + HF 토큰 필요.
          토큰 없으면 자동 스킵하고 사유를 출력한다. 비상업 라이선스 유의.

측정 항목: 추론 시간(s), Peak VRAM(GB), 출력 크기. GPU(L4) 전용.
OpenAI API 호출 없음 — 비용 없음. 반복 실행 가능.

실행:  .venv/bin/python backend/scripts/img002_benchmark.py [--input 이미지] [--runs 2] [--models sdxl,flux]
"""
from __future__ import annotations

import argparse
import io
import sys
import tempfile
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from PIL import Image, ImageDraw

from app.schemas.ads import ProductInfo, StylePreset
from app.services import image_service
from app.services.prompt_service import build_image_prompt


def _make_test_image(path: Path) -> None:
    img = Image.new("RGB", (1024, 768), (245, 240, 230))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([380, 250, 640, 620], radius=30, fill=(140, 90, 50))
    d.rectangle([470, 170, 550, 260], fill=(90, 60, 35))
    d.ellipse([420, 330, 600, 480], fill=(230, 220, 200))
    img.save(path, format="JPEG", quality=90)


def _vram_gb() -> float:
    import torch

    return torch.cuda.max_memory_allocated() / 1024**3


def bench_sdxl(processed, prompt, runs: int, out_dir: str) -> None:
    import torch

    print("\n=== SDXL Inpainting (공식 경로: image_service.generate_ad_image) ===")
    torch.cuda.reset_peak_memory_stats()

    t0 = time.perf_counter()
    image_service._load_pipeline()
    print(f"파이프라인 로드: {time.perf_counter() - t0:.2f}s, VRAM {_vram_gb():.2f}GB")

    for i in range(runs):
        torch.cuda.reset_peak_memory_stats()
        result = image_service.generate_ad_image(processed, prompt, seed=42 + i, output_dir=out_dir)
        print(
            f"run {i + 1}: 추론 {result.infer_seconds:.2f}s, "
            f"Peak VRAM {_vram_gb():.2f}GB, seed={result.seed}, "
            f"출력={result.final_image_path}"
        )


def bench_flux(processed, prompt, runs: int, out_dir: str) -> None:
    import torch

    print("\n=== FLUX.1 Fill [dev] ===")
    try:
        from diffusers import FluxFillPipeline

        t0 = time.perf_counter()
        pipe = FluxFillPipeline.from_pretrained(
            "black-forest-labs/FLUX.1-Fill-dev", torch_dtype=torch.bfloat16
        )
        # L4 24GB 에서 fp16/bf16 풀로드 불가 전제 → CPU offload
        pipe.enable_model_cpu_offload()
        print(f"파이프라인 로드(offload): {time.perf_counter() - t0:.2f}s")
    except Exception as e:
        print(f"[스킵] FLUX.1 Fill 로드 실패: {type(e).__name__}: {e}")
        print("  → gated 모델: https://huggingface.co/black-forest-labs/FLUX.1-Fill-dev 라이선스 동의")
        print("  → 후 `huggingface-cli login` 필요. 비상업 라이선스 주의.")
        return

    init_image = Image.open(processed.processed_image_path).convert("RGB")
    from PIL import ImageOps

    mask = ImageOps.invert(Image.open(processed.mask_path).convert("L"))

    for i in range(runs):
        torch.cuda.reset_peak_memory_stats()
        t0 = time.perf_counter()
        out = pipe(
            prompt=prompt.positive,
            image=init_image,
            mask_image=mask,
            num_inference_steps=30,
            guidance_scale=30.0,
            generator=torch.Generator("cpu").manual_seed(42 + i),
        ).images[0]
        elapsed = time.perf_counter() - t0
        out_path = Path(out_dir) / f"flux_ad_{42 + i}.png"
        out.save(out_path)
        print(f"run {i + 1}: 추론 {elapsed:.2f}s, Peak VRAM {_vram_gb():.2f}GB, 출력={out_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=None, help="입력 상품 이미지 (기본: 합성 이미지)")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--models", default="sdxl,flux")
    parser.add_argument("--outdir", default=None, help="결과 저장 디렉토리 (기본: backend/results)")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        if args.input:
            input_path = args.input
        else:
            input_path = str(Path(tmp) / "product.jpg")
            _make_test_image(Path(input_path))

        out_dir = args.outdir or str(image_service.RESULTS_DIR)

        print("--- FR-06 전처리 ---")
        t0 = time.perf_counter()
        processed = image_service.preprocess(input_path, output_dir=tmp)
        print(f"전처리: {time.perf_counter() - t0:.2f}s")

        prompt = build_image_prompt(
            ProductInfo(name="핸드드립 원두", description="다크 로스트"),
            StylePreset.WARM_VINTAGE,
        )

        models = [m.strip() for m in args.models.split(",")]
        if "sdxl" in models:
            bench_sdxl(processed, prompt, args.runs, out_dir)
        if "flux" in models:
            bench_flux(processed, prompt, args.runs, out_dir)


if __name__ == "__main__":
    main()
