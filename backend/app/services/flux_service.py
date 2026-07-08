"""FLUX.1 Fill 씬 엔진 (실험 단계, IMG-003) — 담당: 한의정.

역할 분담 (포스터 v4 방향, 2026-07-07):
  - 그래픽·씬(유기 리본, 부유 소재, 질감) = FLUX 생성  ← 코드 드로잉 접근 폐기
  - 타이포(헤드라인·문구)               = overlay_service (한글 100% 안전)

L4 24GB 제약: FLUX.1 Fill dev = 12B transformer + T5-XXL → bf16 풀로드 불가.
  → bitsandbytes NF4 양자화 (transformer + T5). 예상 VRAM ~11GB, 추론 1~3분/장.
  SDXL 스택과 동시 상주 불가 — 실험은 단독 프로세스, 서비스 통합 시 엔진 스왑 설계 필요.

⚠️ FLUX.1 dev 계열 = 비상업 라이선스. 부트캠프 데모/실험 한정 — 팀 공유 필수.
⚠️ gated 모델: HF 계정 라이선스 동의 + `huggingface-cli login` 필요.

FLUX Fill 특성: negative prompt 없음(guidance-distilled), guidance_scale 기본 30.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image, ImageFilter, ImageOps

from .image_service import MASK_EDGE_BLUR, RESULTS_DIR, PreprocessResult

logger = logging.getLogger(__name__)

FLUX_FILL_MODEL = "black-forest-labs/FLUX.1-Fill-dev"
DEFAULT_STEPS = 28
DEFAULT_GUIDANCE = 30.0   # Fill-dev 권장값 (SDXL 의 7.5 와 스케일이 다름)

_flux_pipeline = None


def _dilate(m, n):
    import numpy as np
    o = m.copy()
    for _ in range(n):
        s = [o]
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    s.append(np.roll(np.roll(o, dy, 0), dx, 1))
        o = np.max(np.stack(s), 0)
    return o


def clean_text_artifacts(image_path: str, mask_path: str, output_path: Optional[str] = None) -> str:
    """FLUX 가 배경에 지어낸 가짜 글자(gibberish) 제거.

    원리: 가짜글자 = 배경(제품X + 큰 리본X)의 '작고 어두운 고주파 마크'.
      - 큰 리본은 침식→팽창으로 보호(작은 마크는 침식에서 소멸 → 미보호)
      - 검출부는 정규화 컨볼루션 인페인팅으로 주변 배경을 매끈하게 채움(얼룩 없음)
    제품 내부(실제 라벨 글자 등)는 마스크로 보호. 로컬 연산 — 비용 0.
    """
    import numpy as np

    img = Image.open(image_path).convert("RGB")
    mask = Image.open(mask_path).convert("L").resize(img.size)
    arr = np.array(img).astype(np.float64)
    w, h = img.size

    def ero(m, n):
        return ~_dilate(~m, n)

    prod = _dilate(np.array(mask) >= 128, 14)
    mx, mn = arr.max(2), arr.min(2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
    ribbon_protect = _dilate(ero(sat > 0.30, 8), 14)  # 큰 컬러 리본만 보호

    gray = np.array(img.convert("L")).astype(np.float64)
    localbg = np.array(
        Image.fromarray(gray.astype(np.uint8)).filter(ImageFilter.GaussianBlur(14))
    ).astype(np.float64)
    blur6 = np.array(
        Image.fromarray(gray.astype(np.uint8)).filter(ImageFilter.GaussianBlur(6))
    ).astype(np.float64)
    text = (np.abs(gray - blur6) > 9) & (gray < localbg - 8) & (~prod) & (~ribbon_protect)
    text = _dilate(text, 3) & (~prod) & (~ribbon_protect)

    # 정규화 컨볼루션 인페인팅
    known = (~text).astype(np.float64)

    def gb(a, r):
        return np.array(
            Image.fromarray(a.clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(r))
        ).astype(np.float64)

    kb = gb(known * 255, 25) / 255.0 + 1e-6
    filled = np.zeros_like(arr)
    for c in range(3):
        filled[..., c] = gb(arr[..., c] * known, 25) / kb
    out = np.where(text[..., None], filled, arr)

    dest = output_path or image_path
    Image.fromarray(out.clip(0, 255).astype(np.uint8)).save(dest, format="PNG")
    logger.info(f"가짜글자 클린업 완료 ({text.sum() / text.size:.1%}): {dest}")
    return dest


@dataclass
class FluxResult:
    final_image_path: str
    seed: int
    infer_seconds: float
    load_seconds: float = 0.0
    peak_vram_gb: float = 0.0


def unload() -> None:
    """FLUX 파이프라인 언로드 — VRAM 확보 (SDXL/RealVis 로드 전). B모드 종료 후 호출."""
    import gc

    import torch

    global _flux_pipeline
    _flux_pipeline = None
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _load_flux_fill():  # noqa: ANN202
    """FLUX.1 Fill lazy 싱글턴 — transformer·T5 를 NF4 로 양자화해 L4 에 적재."""
    global _flux_pipeline
    if _flux_pipeline is None:
        import torch
        from diffusers import BitsAndBytesConfig as DiffusersBnb
        from diffusers import FluxFillPipeline, FluxTransformer2DModel
        from transformers import BitsAndBytesConfig as TransformersBnb
        from transformers import T5EncoderModel

        logger.info(f"FLUX Fill 로드 시작 (NF4): {FLUX_FILL_MODEL}")
        transformer = FluxTransformer2DModel.from_pretrained(
            FLUX_FILL_MODEL, subfolder="transformer",
            quantization_config=DiffusersBnb(
                load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
            ),
            torch_dtype=torch.bfloat16,
        )
        text_encoder_2 = T5EncoderModel.from_pretrained(
            FLUX_FILL_MODEL, subfolder="text_encoder_2",
            quantization_config=TransformersBnb(
                load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
            ),
            torch_dtype=torch.bfloat16,
        )
        _flux_pipeline = FluxFillPipeline.from_pretrained(
            FLUX_FILL_MODEL,
            transformer=transformer,
            text_encoder_2=text_encoder_2,
            torch_dtype=torch.bfloat16,
        )
        # ⚠️ enable_model_cpu_offload() + NF4 조합은 T5 인코딩이 CPU 로 떨어져 hang
        #    (15분 스텝 0/28, GPU 0MiB 실측). NF4 양자화 모듈(transformer·T5)은 로드
        #    시점에 이미 GPU 상주 → 나머지 비양자화 컴포넌트만 GPU 로 올려 전부 상주.
        #    NF4 transformer ~7GB + T5 ~5GB + VAE/CLIP ~1GB ≈ 13GB (L4 24GB 여유).
        _flux_pipeline.vae.to("cuda")
        _flux_pipeline.text_encoder.to("cuda")  # CLIP
        logger.info("FLUX Fill 로드 완료 (NF4, 전 컴포넌트 GPU 상주)")
    return _flux_pipeline


def generate_with_flux(
    processed: PreprocessResult,
    prompt: str,
    seed: Optional[int] = None,
    steps: int = DEFAULT_STEPS,
    guidance: float = DEFAULT_GUIDANCE,
    output_dir: Optional[str] = None,
    preserve_product: bool = True,
    clean_artifacts: bool = True,
) -> FluxResult:
    """FLUX Fill 로 배경/그래픽 생성 (제품 마스크 보존 + post-composite).

    prompt 는 영문 자연어 문장 (T5 — SDXL 키워드 나열보다 서술형이 잘 먹음).
    'no text, no letters' 를 프롬프트에 포함할 것 (negative 없음).
    """
    import torch

    src = Path(processed.processed_image_path)
    product_rgba = Image.open(src).convert("RGBA")
    product_mask = Image.open(processed.mask_path).convert("L")

    base = Image.new("RGBA", product_rgba.size, (255, 255, 255, 255))
    base.alpha_composite(product_rgba)
    init_image = base.convert("RGB")

    background_mask = ImageOps.invert(product_mask)
    if MASK_EDGE_BLUR > 0:
        background_mask = background_mask.filter(ImageFilter.GaussianBlur(MASK_EDGE_BLUR))

    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    t0 = time.perf_counter()
    pipe = _load_flux_fill()
    load_seconds = time.perf_counter() - t0

    torch.cuda.reset_peak_memory_stats()
    t0 = time.perf_counter()
    result = pipe(
        prompt=prompt,
        image=init_image,
        mask_image=background_mask,
        num_inference_steps=steps,
        guidance_scale=guidance,
        generator=torch.Generator("cpu").manual_seed(seed),
        height=init_image.height,
        width=init_image.width,
    ).images[0]
    infer_seconds = time.perf_counter() - t0
    peak_vram = torch.cuda.max_memory_allocated() / 1024**3

    result = result.convert("RGB")
    if result.size != product_rgba.size:
        result = result.resize(product_rgba.size, Image.LANCZOS)
    if preserve_product:
        result.paste(init_image, (0, 0), product_mask)

    out_dir = Path(output_dir) if output_dir else RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    final_path = out_dir / f"{src.stem.replace('_processed', '')}_flux_{seed}.png"
    result.save(final_path, format="PNG")

    # FLUX Fill 의 배경 가짜글자 제거 (제품 보존 후이므로 제품 라벨은 안전)
    if clean_artifacts:
        clean_text_artifacts(str(final_path), processed.mask_path)

    logger.info(
        f"FLUX 생성 완료: {final_path} (seed={seed}, {infer_seconds:.1f}s, VRAM {peak_vram:.1f}GB)"
    )
    return FluxResult(
        final_image_path=str(final_path), seed=seed,
        infer_seconds=infer_seconds, load_seconds=load_seconds,
        peak_vram_gb=round(peak_vram, 2),
    )
