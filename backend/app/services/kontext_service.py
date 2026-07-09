"""FLUX.1 Kontext [dev] 명령기반 편집 (v2 A모드 주엔진 후보) — 담당: 한의정.

명령형 단문으로 정체성 보존 편집. 누끼+강도조절+마스크 조합을 명령 한 줄로 대체.
  v1 RealVis 의 실패(마블링 뭉갬·맨손 생성·토핑 드리프트)를 Kontext 는 "건드리지 말라"는
  보존절로 회피 — 명령에 없는 것은 안 바꾼다.

디스크·VRAM 절약(100G/L4 제약): 트랜스포머 GGUF Q4(~6.5G)만 수령, T5/CLIP/VAE 는
  기존 FLUX.1-Fill-dev 레포/파이프라인에서 재사용. 실측 VRAM peak 13.2G.
  ⚠️ Fill 과 트랜스포머 동시 상주 불가 → Kontext 로드 시 Fill 트랜스포머 해제.

프롬프트 규약(§6): 명령형 단문 + 구체 명사 + 사진어휘 + **보존절 필수**(negative 없음)
  + 정직성 가드. 영어만(CLIP/T5 한글 오염 금지).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

KONTEXT_REPO = "black-forest-labs/FLUX.1-Kontext-dev"
GGUF_REPO = "QuantStack/FLUX.1-Kontext-dev-GGUF"
GGUF_FILE = "flux1-kontext-dev-Q4_K_M.gguf"

DEFAULT_GUIDANCE = 2.5
# 스텝 스윕(P1-speed) 실측: 8~28 전 구간 품질 붕괴 없음, VRAM 13.6G 무관.
#   knee=12(58s, 프로덕션급) — 28(133s) 대비 2.3× 빠르고 품질 손실 무시. 기본값 채택.
DEFAULT_STEPS = 12

_kontext_pipeline = None


# --- 프롬프트 템플릿 (§6) ------------------------------------------------------
_GUARD = " Do not invent items that are not in the original photo."

_TEMPLATES = {
    # A 음식점 접시(일반) — 존재요소 강화, 새 재료·손 금지
    "A-dish": (
        "Make the {subject} look freshly served and more appetizing: enhance the glossy "
        "sheen on the surface, enrich the natural colors, add subtle steam rising. "
        "Keep the plate, bowl, utensils, composition and every ingredient exactly the same. "
        "Do not add any new ingredients, garnish, or hands."
    ),
    # A 텍스처=상품(마블링·파우더) — 조명·색만, 텍스처 절대 보존
    "A-hero": (
        "Improve only the lighting and color vibrancy of this {subject} photo, like a "
        "premium food advertisement. Preserve the exact marbling pattern, surface texture "
        "and fine details completely unchanged. Do not repaint or smooth any texture."
    ),
    # B 카페 배경교체(단발)
    "B-scene": (
        "Replace the background with {scene}. Keep the {subject} and its container exactly "
        "the same, and match its lighting and shadows naturally to the new scene. No text."
    ),
    # C 사물 스튜디오
    "C-studio": (
        "Place the product on a clean light-gray studio sweep background with soft "
        "professional lighting and a subtle contact shadow. Keep the product's shape, "
        "color, logo and proportions exactly the same. E-commerce product photography."
    ),
}
_DEFAULT_SCENE = "a bright minimalist cafe table by a sunlit window, soft morning light"


def build_instruction(template: str, subject_en: str,
                      core_ingredients: Optional[list[str]] = None,
                      scene: Optional[str] = None) -> str:
    """편집 명령 생성. template: A-dish|A-hero|B-scene|C-studio. subject_en 영어만."""
    base = _TEMPLATES.get(template, _TEMPLATES["A-dish"])
    text = base.format(subject=subject_en or "food", scene=scene or _DEFAULT_SCENE)
    # A-dish 에 한해 진짜 구성재료 강화 허용(정직성 경계 — 외래 데코 아님)
    if template == "A-dish" and core_ingredients:
        text += f" Enhance the natural look of the {', '.join(core_ingredients[:4])}."
    return text + _GUARD


# --- 로딩 (Fill 컴포넌트 재사용) -----------------------------------------------
def _load_kontext():  # noqa: ANN202
    """Kontext 파이프라인 lazy 싱글턴. Fill 의 T5/CLIP/VAE 재사용, Kontext 트랜스포머만 GGUF.

    ⚠️ Fill 트랜스포머를 해제하므로, 이후 B모드(FLUX Fill) 재사용 시 재로드 필요.
    """
    global _kontext_pipeline
    if _kontext_pipeline is not None:
        return _kontext_pipeline

    import gc

    import torch
    from diffusers import (FluxKontextPipeline, FluxTransformer2DModel,
                           GGUFQuantizationConfig)
    from huggingface_hub import hf_hub_download

    from . import flux_service

    logger.info("Kontext 로드: Fill 컴포넌트 재사용 + 트랜스포머 GGUF")
    fill = flux_service._load_flux_fill()
    te, te2 = fill.text_encoder, fill.text_encoder_2
    tok, tok2, vae = fill.tokenizer, fill.tokenizer_2, fill.vae
    fill.transformer = None
    flux_service._flux_pipeline = None      # Fill 트랜스포머 참조 제거 → GC
    del fill
    gc.collect(); torch.cuda.empty_cache()

    gguf = hf_hub_download(GGUF_REPO, GGUF_FILE)
    transformer = FluxTransformer2DModel.from_single_file(
        gguf, quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
        config=KONTEXT_REPO, subfolder="transformer", torch_dtype=torch.bfloat16,
    ).to("cuda")
    _kontext_pipeline = FluxKontextPipeline.from_pretrained(
        KONTEXT_REPO, transformer=transformer, text_encoder=te, text_encoder_2=te2,
        tokenizer=tok, tokenizer_2=tok2, vae=vae, torch_dtype=torch.bfloat16,
    )
    logger.info("Kontext 로드 완료 (VRAM peak ~13GB 실측)")
    return _kontext_pipeline


def unload() -> None:
    """Kontext 파이프라인 언로드 — VRAM 확보."""
    import gc

    import torch

    global _kontext_pipeline
    _kontext_pipeline = None
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _fit(img: Image.Image, long_side: int = 1024) -> Image.Image:
    w, h = img.size
    s = long_side / max(w, h)
    return img.resize((max(16, int(w * s) // 16 * 16), max(16, int(h * s) // 16 * 16)), Image.LANCZOS)


# --- 공개 API ------------------------------------------------------------------
def edit(
    image_path: str,
    instruction: str,
    seed: int = 42,
    guidance: float = DEFAULT_GUIDANCE,
    steps: int = DEFAULT_STEPS,
    output_dir: str = "backend/results/ai/kontext",
) -> str:
    """명령 기반 편집. instruction 은 build_instruction 산출(영어). 저장 경로 반환."""
    import torch

    pipe = _load_kontext()
    img = _fit(Image.open(image_path).convert("RGB"))
    out = pipe(image=img, prompt=instruction, guidance_scale=guidance,
               num_inference_steps=steps,
               generator=torch.Generator("cuda").manual_seed(seed)).images[0]
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{Path(image_path).stem}_kontext.png"
    out.save(out_path)
    return str(out_path)
