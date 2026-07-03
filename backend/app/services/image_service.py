"""이미지 서비스 — 담당: 한의정.

대응 FR:
  - FR-06 상품 이미지 전처리 (배경 제거/마스킹 · 크기 조정 · 품질 보정) ← 구현 완료
  - FR-08 상품 이미지 기반 광고 생성 (제품 보존 + 배경 교체 inpainting) ← 구현 완료
  - FR-12 재생성 (동일 입력 · seed 변경) ← 구현 완료

파이프라인 위치 (4단계 확정):
  전처리(FR-06) → 스타일 결정(2경로) → [이미지 생성 FR-08] → 문구 생성(FR-09)

마스킹(A-2) 확정: rembg(u2net, ONNX). GPU 환경(onnxruntime-gpu)에서 가속,
  미지원 환경에서는 onnxruntime(CPU)로 자동 폴백.
모델(A-1): SDXL Inpainting 1순위로 구현 (IMG-001: 8.45s, VRAM 8.95GB — L4 안정권).
  FLUX.1 Fill 비교(IMG-002)는 gated 모델 접근 확보 후. 생성 파라미터는 A-4 실험으로 조정.

제품 보존 전략: inpainting 후 원본 제품 픽셀을 마스크 기준으로 재합성(post-composite)
  → 제품 영역 픽셀 보존 보장 (A-3 SSIM/L1 지표 유리).

실행 환경: 전처리(FR-06)는 CPU에서도 동작(느림). FR-08은 GPU 필요(GCP L4).
"""
from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PIL import Image, ImageEnhance, ImageOps

if TYPE_CHECKING:
    from .prompt_service import ImagePrompt

logger = logging.getLogger(__name__)

# 광고 이미지 표준 규격 (FR-18의 비율 옵션 중 기본값 1:1 기준, 추후 옵션화)
DEFAULT_OUTPUT_SIZE: tuple[int, int] = (1024, 1024)
MAX_INPUT_DIMENSION = 2048  # 과도하게 큰 업로드 이미지에 대한 리사이즈 상한

# 전처리 산출물 저장 위치: backend/processed/ · 생성 결과: backend/results/
PROCESSED_DIR = Path(__file__).resolve().parents[2] / "processed"
RESULTS_DIR = Path(__file__).resolve().parents[2] / "results"

# FR-08 생성 파라미터 (v1 잠정치 — A-4 실험으로 조정)
SDXL_INPAINT_MODEL = "diffusers/stable-diffusion-xl-1.0-inpainting-0.1"
DEFAULT_STEPS = 30
DEFAULT_GUIDANCE = 7.5
# ⚠️ strength < 1.0 이면 init(흰 배경) 잔재로 배경 생성이 붕괴됨 (IMG-002 실측: 0.99 → 흰 배경)
DEFAULT_STRENGTH = 1.0
MASK_EDGE_BLUR = 4  # 배경/제품 경계 블렌딩용 (0 = 미사용)

# rembg 세션은 최초 사용 시 1회만 생성 (요청마다 재생성하면 GPU 초기화 비용 발생).
# 모듈 import 시점에 만들지 않는 이유: rembg 미설치 환경(로컬 CPU 개발 등)에서도
# 본 모듈을 import 하는 서버 기동 자체는 가능해야 함.
_rembg_session = None


def _get_rembg_session():  # noqa: ANN202
    """u2net 세션 lazy 초기화. 범용 배경 제거 모델, L4 24GB 환경에서 VRAM 여유."""
    global _rembg_session
    if _rembg_session is None:
        # onnxruntime-gpu(CU13 빌드)는 import 시 libcudart.so.13 을 요구하지만
        # pip NVIDIA 라이브러리 경로를 스스로 찾지 못함 → torch(CU13)를 먼저 import
        # 하면 RPATH 로 CUDA 런타임이 프로세스에 로드됨. torch 미설치 환경(CPU 개발)은 무시.
        try:
            import torch  # noqa: F401
        except Exception:
            pass
        # pip 으로 설치된 cuDNN 등 나머지 라이브러리는 preload 필요
        # (없으면 CPU 로 조용히 폴백됨).
        try:
            import onnxruntime

            if hasattr(onnxruntime, "preload_dlls"):
                onnxruntime.preload_dlls()
        except Exception:  # CPU 전용 onnxruntime 등 — GPU 미사용 환경은 그대로 진행
            pass

        from rembg import new_session

        _rembg_session = new_session("u2net")
        logger.info(
            f"rembg 세션 초기화 완료 (providers: {_rembg_session.inner_session.get_providers()})"
        )
    return _rembg_session


# --- 데이터 컨테이너 ----------------------------------------------------------
@dataclass
class PreprocessResult:
    """FR-06 산출물."""
    processed_image_path: str
    mask_path: Optional[str] = None   # 제품/배경 분리 마스크 (제품=흰색, L모드 PNG)
    original_image_path: Optional[str] = None  # A-3 픽셀 보존율 측정용 원본 참조


@dataclass
class GenerateResult:
    """FR-08 산출물."""
    final_image_path: str
    seed: int
    infer_seconds: float          # A-1 추론시간 실측 기록용
    # TODO: 제품 보존율(SSIM/L1) 필드 — A-3 지표 확정 후 추가


# --- FR-06 내부 단계 ----------------------------------------------------------
def _load_image(image_bytes: bytes) -> Image.Image:
    """바이트 데이터를 PIL Image로 로드. EXIF 방향 정보 보정 포함."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img)  # 스마트폰 촬영 이미지 회전 보정
        return img.convert("RGBA")
    except Exception as e:
        logger.error(f"이미지 로드 실패: {e}")
        raise ValueError("유효하지 않은 이미지 파일입니다") from e


def _remove_background(img: Image.Image) -> Image.Image:
    """rembg를 이용한 배경 제거. 결과는 알파 채널 포함 RGBA."""
    # 세션 초기화를 rembg import 보다 먼저 수행 (내부에서 torch 선로드 → ORT 로드 순서 보장)
    session = _get_rembg_session()
    from rembg import remove

    try:
        return remove(img, session=session)
    except Exception as e:
        logger.error(f"배경 제거 실패: {e}")
        raise RuntimeError("배경 제거 처리 중 오류가 발생했습니다") from e


def _resize_with_padding(
    img: Image.Image, target_size: tuple[int, int] = DEFAULT_OUTPUT_SIZE
) -> Image.Image:
    """비율 유지 리사이즈 후 투명 배경으로 패딩하여 target_size에 맞춤.

    (제품 왜곡 방지 — 단순 stretch resize 금지)
    """
    img_copy = img.copy()
    img_copy.thumbnail(target_size, Image.LANCZOS)

    canvas = Image.new("RGBA", target_size, (0, 0, 0, 0))
    offset = (
        (target_size[0] - img_copy.width) // 2,
        (target_size[1] - img_copy.height) // 2,
    )
    canvas.paste(img_copy, offset, img_copy if img_copy.mode == "RGBA" else None)
    return canvas


def _enhance_quality(img: Image.Image) -> Image.Image:
    """품질 보정: 선명도·대비·색상 보정.

    과도한 보정은 원본 왜곡을 유발하므로 계수는 보수적으로 설정.
    알파 채널(=마스크 원천)은 보정 대상에서 제외하고 그대로 보존.
    """
    alpha = img.split()[-1] if img.mode == "RGBA" else None
    rgb_img = img.convert("RGB")

    rgb_img = ImageEnhance.Sharpness(rgb_img).enhance(1.15)
    rgb_img = ImageEnhance.Contrast(rgb_img).enhance(1.05)
    rgb_img = ImageEnhance.Color(rgb_img).enhance(1.05)

    if alpha is not None:
        rgb_img = rgb_img.convert("RGBA")
        rgb_img.putalpha(alpha)

    return rgb_img


def _extract_mask(img: Image.Image) -> Image.Image:
    """RGBA 알파 채널 → 제품/배경 분리 마스크 (제품=흰색, 배경=검정, L모드).

    FR-08 inpainting 입력용. (배경 재생성 마스크가 필요하면 소비 측에서 invert)
    """
    if img.mode != "RGBA":
        raise ValueError("마스크 추출은 RGBA 이미지에서만 가능합니다")
    return img.split()[-1]


# --- FR-06 공개 함수 ----------------------------------------------------------
def preprocess_image(
    original_image_bytes: bytes,
    target_size: tuple[int, int] = DEFAULT_OUTPUT_SIZE,
) -> bytes:
    """FR-06: 상품 이미지 전처리 파이프라인 (bytes in → PNG bytes out).

    단계:
      1. 로드 및 EXIF 보정
      2. 입력 크기 상한 적용 (과대 이미지 축소 — 처리 속도 확보)
      3. 배경 제거 (rembg)
      4. 목표 규격으로 비율 유지 리사이즈 + 투명 패딩
      5. 품질 보정 (선명도/대비/색상, 알파 보존)
    """
    img = _preprocess_to_image(original_image_bytes, target_size)

    output_buffer = io.BytesIO()
    img.save(output_buffer, format="PNG")
    return output_buffer.getvalue()


def preprocess(
    image_path: str,
    target_size: tuple[int, int] = DEFAULT_OUTPUT_SIZE,
    output_dir: Optional[str] = None,
) -> PreprocessResult:
    """FR-06: 업로드 상품 이미지 전처리 (경로 in → PreprocessResult out).

    API 계층(images 라우터)에서 사용하는 진입점.
    산출물 2종을 output_dir(기본 backend/processed/)에 저장:
      - {stem}_processed.png : 전처리 완료 이미지 (RGBA)
      - {stem}_mask.png      : 제품/배경 분리 마스크 (FR-08 inpainting 입력)
    """
    src = Path(image_path)
    if not src.is_file():
        raise FileNotFoundError(f"입력 이미지가 존재하지 않습니다: {image_path}")

    out_dir = Path(output_dir) if output_dir else PROCESSED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    img = _preprocess_to_image(src.read_bytes(), target_size)
    mask = _extract_mask(img)

    processed_path = out_dir / f"{src.stem}_processed.png"
    mask_path = out_dir / f"{src.stem}_mask.png"
    img.save(processed_path, format="PNG")
    mask.save(mask_path, format="PNG")

    logger.info(f"전처리 완료: {processed_path} (마스크: {mask_path})")
    return PreprocessResult(
        processed_image_path=str(processed_path),
        mask_path=str(mask_path),
        original_image_path=str(src),
    )


def _preprocess_to_image(
    original_image_bytes: bytes,
    target_size: tuple[int, int],
) -> Image.Image:
    """전처리 공통 파이프라인. RGBA PIL Image 반환."""
    img = _load_image(original_image_bytes)

    # 입력 크기 상한 적용 (전처리 속도 확보 목적)
    if max(img.size) > MAX_INPUT_DIMENSION:
        img.thumbnail((MAX_INPUT_DIMENSION, MAX_INPUT_DIMENSION), Image.LANCZOS)

    img = _remove_background(img)
    img = _resize_with_padding(img, target_size)
    img = _enhance_quality(img)
    return img


# --- FR-08 광고 이미지 생성 ---------------------------------------------------
_sdxl_pipeline = None


def _load_pipeline():  # noqa: ANN202
    """SDXL Inpainting 파이프라인 lazy 싱글턴 (fp16, CUDA).

    IMG-001 실측 기준 L4 안정권 (VRAM ~9GB). 요청마다 재로드 금지.
    """
    global _sdxl_pipeline
    if _sdxl_pipeline is None:
        import torch
        from diffusers import AutoPipelineForInpainting

        logger.info(f"SDXL Inpainting 파이프라인 로드 시작: {SDXL_INPAINT_MODEL}")
        _sdxl_pipeline = AutoPipelineForInpainting.from_pretrained(
            SDXL_INPAINT_MODEL,
            torch_dtype=torch.float16,
            variant="fp16",
        ).to("cuda")
        logger.info("SDXL Inpainting 파이프라인 로드 완료")
    return _sdxl_pipeline


def generate_ad_image(
    processed: PreprocessResult,
    prompt: "ImagePrompt",
    seed: Optional[int] = None,
    output_dir: Optional[str] = None,
) -> GenerateResult:
    """FR-08: 전처리 이미지 + 프롬프트 → 최종 광고 이미지.

    inpainting으로 제품 보존 + 배경 교체. seed 고정 시 재현.
    prompt 는 prompt_service.build_image_prompt() 산출물(FR-07).

    단계:
      1. 전처리 이미지(RGBA) → 흰 배경 합성 RGB (inpainting 입력)
      2. 제품 마스크(제품=흰색) invert → 배경 마스크 (inpaint 대상=흰색) + 경계 블러
      3. SDXL Inpainting 실행 (seed 고정 가능)
      4. 원본 제품 픽셀 재합성 → 제품 영역 보존 보장
      5. backend/results/ 저장
    """
    import random

    import torch
    from PIL import ImageFilter

    src = Path(processed.processed_image_path)
    if not src.is_file():
        raise FileNotFoundError(f"전처리 이미지가 없습니다: {src}")
    if not processed.mask_path or not Path(processed.mask_path).is_file():
        raise FileNotFoundError(f"마스크 파일이 없습니다: {processed.mask_path}")

    product_rgba = Image.open(src).convert("RGBA")
    product_mask = Image.open(processed.mask_path).convert("L")  # 제품=흰색

    # 1. 흰 배경 합성 (inpainting 입력은 RGB)
    base = Image.new("RGBA", product_rgba.size, (255, 255, 255, 255))
    base.alpha_composite(product_rgba)
    init_image = base.convert("RGB")

    # 2. 배경 마스크 (inpaint 대상=흰색) + 경계 블렌딩
    background_mask = ImageOps.invert(product_mask)
    if MASK_EDGE_BLUR > 0:
        background_mask = background_mask.filter(
            ImageFilter.GaussianBlur(MASK_EDGE_BLUR)
        )

    # 3. inpainting 실행
    if seed is None:
        seed = random.randint(0, 2**32 - 1)
    generator = torch.Generator(device="cuda").manual_seed(seed)

    pipe = _load_pipeline()
    started = time.perf_counter()
    result = pipe(
        prompt=prompt.positive,
        negative_prompt=prompt.negative,
        image=init_image,
        mask_image=background_mask,
        num_inference_steps=DEFAULT_STEPS,
        guidance_scale=DEFAULT_GUIDANCE,
        strength=DEFAULT_STRENGTH,
        generator=generator,
    ).images[0]
    infer_seconds = time.perf_counter() - started

    # 4. 원본 제품 픽셀 재합성 (제품 보존 보장, A-3)
    result = result.convert("RGB")
    if result.size != product_rgba.size:
        result = result.resize(product_rgba.size, Image.LANCZOS)
    result.paste(init_image, (0, 0), product_mask)

    # 5. 저장
    out_dir = Path(output_dir) if output_dir else RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    final_path = out_dir / f"{src.stem.replace('_processed', '')}_ad_{seed}.png"
    result.save(final_path, format="PNG")

    logger.info(f"광고 이미지 생성 완료: {final_path} (seed={seed}, {infer_seconds:.2f}s)")
    return GenerateResult(
        final_image_path=str(final_path),
        seed=seed,
        infer_seconds=infer_seconds,
    )


def regenerate(
    processed: PreprocessResult,
    prompt: "ImagePrompt",
    prev_seed: Optional[int] = None,
) -> GenerateResult:
    """FR-12: 동일 입력 · 새 seed 로 재생성 (이전 seed 와 중복 방지)."""
    import random

    new_seed = random.randint(0, 2**32 - 1)
    while prev_seed is not None and new_seed == prev_seed:
        new_seed = random.randint(0, 2**32 - 1)
    return generate_ad_image(processed, prompt, seed=new_seed)


if __name__ == "__main__":
    # 로컬/VM 단위 테스트용 실행 예시:
    #   python backend/app/services/image_service.py <input> <output_dir>
    import sys
    import time

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) != 3:
        print("사용법: python image_service.py <input_path> <output_dir>")
        sys.exit(1)

    started = time.perf_counter()
    result = preprocess(sys.argv[1], output_dir=sys.argv[2])
    elapsed = time.perf_counter() - started

    print(f"전처리 완료 ({elapsed:.2f}s)")
    print(f"  processed: {result.processed_image_path}")
    print(f"  mask:      {result.mask_path}")
