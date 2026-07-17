"""FLUX.1 Kontext [dev] 명령기반 편집 (v2 A모드 주엔진 후보) — 담당: 한의정.

명령형 단문으로 정체성 보존 편집. 누끼+강도조절+마스크 조합을 명령 한 줄로 대체.
  v1 RealVis 의 실패(마블링 뭉갬·맨손 생성·토핑 드리프트)를 Kontext 는 "건드리지 말라"는
  보존절로 회피 — 명령에 없는 것은 안 바꾼다.

디스크·VRAM 절약(100G/L4 제약): Kontext 트랜스포머는 GGUF Q4(~6.5G)만 받고,
  T5/CLIP/VAE/tokenizer 는 FLUX.1-Fill-dev 의 서브컴포넌트만 개별 로드한다.
  Fill 파이프라인 전체나 Fill transformer 블롭은 운영 Kontext 경로에서 필요 없다.

프롬프트 규약(§6): 명령형 단문 + 구체 명사 + 사진어휘 + **보존절 필수**(negative 없음)
  + 정직성 가드. 영어만(CLIP/T5 한글 오염 금지).
"""
from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

# GPU 락(결정 D-10): 락을 generation_app.py 엔드포인트에서 여기(실제 GPU 사용 지점)로 내렸다.
#   합성(scene_service, CPU)은 Kontext 실행 중에도 이 락과 무관하게 즉시 진행된다.
_GPU_LOCK = threading.Lock()


class GpuBusyError(RuntimeError):
    """GPU 락 획득 타임아웃 — 호출부(generation_app)는 HTTP 503으로 매핑한다."""


@contextmanager
def acquire_gpu(timeout: Optional[float] = None):  # noqa: ANN201
    """GPU 작업(로드·추론) 직렬화. 타임아웃 시 GpuBusyError."""
    wait = timeout if timeout is not None else float(os.environ.get("GPU_QUEUE_TIMEOUT", "180"))
    acquired = _GPU_LOCK.acquire(timeout=max(0.0, wait))
    if not acquired:
        raise GpuBusyError("GPU busy")
    try:
        yield
    finally:
        _GPU_LOCK.release()


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
FILL_REPO = "black-forest-labs/FLUX.1-Fill-dev"   # T5/CLIP/VAE/토크나이저 재사용 소스


def _read_hf_token() -> Optional[str]:
    """공용 토큰 파일을 읽는다. 토큰 값을 프로세스 환경에 노출하지 않는다."""
    token_path = os.environ.get("HF_TOKEN_PATH", "").strip()
    if not token_path:
        return None
    try:
        return Path(token_path).read_text(encoding="utf-8").strip() or None
    except OSError as e:
        logger.warning("HF_TOKEN_PATH 읽기 실패: %s", e)
        return None


def _load_kontext():  # noqa: ANN202
    """Kontext 파이프라인 lazy 싱글턴. Fill 의 T5/CLIP/VAE 재사용, Kontext 트랜스포머만 GGUF.

    개선(2026-07-11): 기존엔 Fill 파이프라인 통째 로드 후 트랜스포머를 버렸다 —
    23GB fp16 트랜스포머를 로드했다 버리는 순수 낭비(콜드로드 2분+, RAM 압박).
    → 필요한 컴포넌트만 개별 로드. Fill 트랜스포머 블롭에 의존하지 않으므로
    디스크 절약을 위해 트랜스포머 블롭 삭제도 가능해짐(T5/CLIP/VAE 는 보존 필수).
    """
    global _kontext_pipeline
    if _kontext_pipeline is not None:
        return _kontext_pipeline

    with acquire_gpu():
        if _kontext_pipeline is not None:  # 락 대기 중 다른 스레드가 이미 로드 완료
            return _kontext_pipeline

        import torch
        from diffusers import (AutoencoderKL, FluxKontextPipeline,
                               FluxTransformer2DModel, GGUFQuantizationConfig)
        from huggingface_hub import hf_hub_download
        from transformers import (BitsAndBytesConfig, CLIPTextModel, CLIPTokenizer,
                                  T5EncoderModel, T5TokenizerFast)

        hf_token = _read_hf_token()
        logger.info("Kontext 로드: Fill 컴포넌트 개별 로드(T5 NF4) + 트랜스포머 GGUF")
        # T5 는 NF4 양자화(기존 flux_service 와 동일 설정 — 로드 시 GPU 상주, ~5GB)
        te2 = T5EncoderModel.from_pretrained(
            FILL_REPO, subfolder="text_encoder_2",
            quantization_config=BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16),
            torch_dtype=torch.bfloat16, token=hf_token)
        te = CLIPTextModel.from_pretrained(
            FILL_REPO, subfolder="text_encoder", torch_dtype=torch.bfloat16,
            token=hf_token).to("cuda")
        tok = CLIPTokenizer.from_pretrained(
            FILL_REPO, subfolder="tokenizer", token=hf_token)
        tok2 = T5TokenizerFast.from_pretrained(
            FILL_REPO, subfolder="tokenizer_2", token=hf_token)
        vae = AutoencoderKL.from_pretrained(
            FILL_REPO, subfolder="vae", torch_dtype=torch.bfloat16,
            token=hf_token).to("cuda")

        gguf = hf_hub_download(GGUF_REPO, GGUF_FILE, token=hf_token)
        transformer = FluxTransformer2DModel.from_single_file(
            gguf, quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
            config=KONTEXT_REPO, subfolder="transformer", torch_dtype=torch.bfloat16,
            token=hf_token,
        ).to("cuda")
        _kontext_pipeline = FluxKontextPipeline.from_pretrained(
            KONTEXT_REPO, transformer=transformer, text_encoder=te, text_encoder_2=te2,
            tokenizer=tok, tokenizer_2=tok2, vae=vae, torch_dtype=torch.bfloat16,
            token=hf_token,
        )
        logger.info("Kontext 로드 완료 (VRAM peak ~13GB 실측)")
        return _kontext_pipeline


def preload() -> None:
    """상주 생성 워커 시작 시 Kontext를 1회 미리 로드한다."""
    _load_kontext()


def unload() -> None:
    """Kontext 파이프라인 언로드 — VRAM 확보."""
    import gc

    import torch

    global _kontext_pipeline
    _kontext_pipeline = None
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()   # 프로세스 간 공유 핸들까지 정리(연정 PDF #4)


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
    clip_prompt: Optional[str] = None,
) -> str:
    """명령 기반 편집. 긴 instruction은 T5, 짧은 clip_prompt는 CLIP에 각각 전달한다."""
    import torch

    pipe = _load_kontext()
    img = _fit(Image.open(image_path).convert("RGB"))
    # FLUX 이중 인코더: prompt=CLIP(77토큰), prompt_2=T5(최대 512토큰).
    # StylePlan의 긴 정체성 잠금을 CLIP에 그대로 넣으면 핵심 무드가 잘리므로 역할을 분리한다.
    prompt = clip_prompt or instruction
    prompt_2 = instruction if clip_prompt else None
    with acquire_gpu():
        out = pipe(image=img, prompt=prompt, prompt_2=prompt_2, guidance_scale=guidance,
                   num_inference_steps=steps,
                   generator=torch.Generator("cuda").manual_seed(seed)).images[0]
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{Path(image_path).stem}_kontext.png"
    out.save(out_path)
    return str(out_path)
