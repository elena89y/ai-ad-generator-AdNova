"""이미지 서비스 — 담당: 한의정.

대응 FR:
  - FR-06 상품 이미지 전처리 (배경 제거/마스킹 · 크기 조정 · 품질 보정) ← 구현 완료
  - FR-08 상품 이미지 기반 광고 생성 (제품 보존 + 배경 교체 inpainting) ← 구현 완료
  - FR-12 재생성 (동일 입력 · seed 변경) ← 구현 완료

파이프라인 위치 (4단계 확정):
  전처리(FR-06) → 스타일 결정(2경로) → [이미지 생성 FR-08] → 문구 생성(FR-09)

마스킹(A-2): BiRefNet (rembg birefnet-general) — QUA-001 에서 u2net 대비
  다중 객체·프레임 잘림 입력 커버리지 압승 (쿠키2: 0.2%→95.3%). GPU 가속, CPU 폴백.
모델(A-1): SDXL Inpainting (IMG-001/002: 추론 ~11.5s, VRAM 8.95GB — L4 안정권).

제품 보존 + 품질 전략 (QUA-003, 실험로그 v4):
  1. inpainting 후 원본 제품 픽셀 재합성(post-composite)
  2. 접촉 그림자 합성 → 조화 패스(SDXL base img2img, strength 0.25)
  3. 코어 보호 재합성(마스크 침식+페더) — 제품 내부는 원본, 경계 링만 조화 픽셀
  → 코어 SSIM 0.97+ 유지하면서 '붙여넣은 티' 제거.
  ⚠️ L4 22GB 에서 inpaint+img2img 동시 상주 시 OOM 실측 → 조화 파이프라인은 cpu offload.

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
# 히어로 비율: 제품 bbox 가 캔버스에서 차지하는 목표 비율 (레퍼런스 포스터 60~80%)
FILL_FRACTION = 0.62
FILL_MAX_UPSCALE = 2.0   # 과도 업스케일 화질 저하 방지
FILL_CENTER_Y = 0.56     # 제품 수직 중심 (약간 아래 — 상단 헤드라인 여백 확보)

# 전처리 산출물 저장 위치: backend/processed/ · AI 생성 결과물: backend/results/ai/ (gitignore)
PROCESSED_DIR = Path(__file__).resolve().parents[2] / "processed"
RESULTS_DIR = Path(__file__).resolve().parents[2] / "results" / "ai"

# FR-08 생성 파라미터 (IMG-002/LAT-001/QUA-003 실측 기반)
SDXL_INPAINT_MODEL = "diffusers/stable-diffusion-xl-1.0-inpainting-0.1"
REMBG_MODEL = "birefnet-general"  # QUA-001 채택 (u2net 은 다중 객체·잘림 입력에서 누락)
DEFAULT_STEPS = 30  # 25로 낮추면 -3.4s 가능하나 품질 우선 결정 (2026-07-03)
DEFAULT_GUIDANCE = 7.5
# ⚠️ strength < 1.0 이면 init(흰 배경) 잔재로 배경 생성이 붕괴됨 (IMG-002 실측: 0.99 → 흰 배경)
DEFAULT_STRENGTH = 1.0
MASK_EDGE_BLUR = 4  # 배경/제품 경계 블렌딩용 (0 = 미사용)

# 조화(harmonization) 패스 파라미터 (QUA-002/003 확정)
SDXL_BASE_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"
HARMONIZE_STRENGTH = 0.25
HARMONIZE_GUIDANCE = 5.0
# A모드 음식 리터치 전용 포토리얼 체크포인트 — SDXL base 는 img2img 에서 스타일화
#   편향으로 사진 붕괴(육개장·꽃등심 실측). RealVis 는 사실감 특화라 구조·질감 보존.
FOOD_IMG2IMG_MODEL = "SG161222/RealVisXL_V5.0"
SHADOW_OFFSET = (10, 14)   # 접촉 그림자 오프셋 (x, y)
SHADOW_BLUR = 18
SHADOW_OPACITY = 0.35
CORE_ERODE_PX = 6          # 코어 보호: 마스크 침식/페더 (제품 내부 원본 보존)
CORE_FEATHER_PX = 6

# rembg 세션은 최초 사용 시 1회만 생성 (요청마다 재생성하면 GPU 초기화 비용 발생).
# 모듈 import 시점에 만들지 않는 이유: rembg 미설치 환경(로컬 CPU 개발 등)에서도
# 본 모듈을 import 하는 서버 기동 자체는 가능해야 함.
_rembg_session = None


def _get_rembg_session():  # noqa: ANN202
    """마스킹 세션 lazy 초기화 (REMBG_MODEL, QUA-001 채택 모델)."""
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

        _rembg_session = new_session(REMBG_MODEL)
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
    infer_seconds: float          # 배경 생성(inpainting) 시간
    harmonize_seconds: float = 0.0  # 조화 패스 시간 (미실행 시 0)
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


def _fit_product(
    img: Image.Image,
    fill_frac: float = FILL_FRACTION,
    target_size: Optional[tuple[int, int]] = None,
) -> Image.Image:
    """제품(알파 bbox)을 캔버스의 히어로 비율로 확대/축소 후 재배치.

    포스터 체감 품질의 최대 요인 — 제품이 작으면 어떤 배경·오버레이도 허전함.
    """
    import numpy as np

    alpha = np.array(img.split()[-1])
    ys, xs = np.nonzero(alpha >= 16)
    if len(xs) == 0:
        return img

    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    bw, bh = int(x1 - x0 + 1), int(y1 - y0 + 1)
    w, h = target_size if target_size else img.size
    scale = min(fill_frac * w / bw, fill_frac * h / bh, FILL_MAX_UPSCALE)
    nw, nh = max(1, int(bw * scale)), max(1, int(bh * scale))

    crop = img.crop((int(x0), int(y0), int(x1 + 1), int(y1 + 1))).resize(
        (nw, nh), Image.LANCZOS
    )
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = (w - nw) // 2
    py = min(max(int(h * FILL_CENTER_Y) - nh // 2, 0), h - nh)
    canvas.paste(crop, (px, py), crop)
    return canvas


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
    img = _fit_product(img)   # 히어로 비율 재배치 (FILL_FRACTION)
    img = _enhance_quality(img)
    return img


# --- 조화(harmonization) 패스 — QUA-002/003 ------------------------------------
_harmonize_pipeline = None


def _load_harmonize_pipeline():  # noqa: ANN202
    """SDXL base img2img lazy 싱글턴 — inpaint 파이프라인과 컴포넌트 공유.

    L4 22GB 제약: 두 파이프라인을 통째로 올리면 OOM (QUA-003 실측),
    cpu offload 는 스텝마다 가중치 전송으로 12배 느림 (4.2s → 49.5s 실측).
    → text encoder ×2 / VAE / tokenizer 를 inpaint 와 공유하고 UNet 만 추가 상주
      (약 +5GB) 시켜 둘 다 GPU 에 유지한다.
    """
    global _harmonize_pipeline
    if _harmonize_pipeline is None:
        import torch
        from diffusers import StableDiffusionXLImg2ImgPipeline

        inpaint = _load_pipeline()
        logger.info(f"조화 파이프라인 로드 시작 (컴포넌트 공유): {SDXL_BASE_MODEL}")
        _harmonize_pipeline = StableDiffusionXLImg2ImgPipeline.from_pretrained(
            SDXL_BASE_MODEL,
            torch_dtype=torch.float16,
            variant="fp16",
            text_encoder=inpaint.text_encoder,
            text_encoder_2=inpaint.text_encoder_2,
            tokenizer=inpaint.tokenizer,
            tokenizer_2=inpaint.tokenizer_2,
            vae=inpaint.vae,
        ).to("cuda")
        _harmonize_pipeline.enable_vae_slicing()
        logger.info("조화 파이프라인 로드 완료 (GPU 상주, UNet 만 추가)")
    return _harmonize_pipeline


def _add_contact_shadow(img: Image.Image, product_mask: Image.Image) -> Image.Image:
    """제품 마스크 기반 접촉 그림자: 오프셋+블러 후 배경 영역만 어둡게."""
    import numpy as np
    from PIL import ImageFilter

    mask = np.array(product_mask, dtype=np.float64) / 255.0
    shadow = np.zeros_like(mask)
    dx, dy = SHADOW_OFFSET
    shadow[dy:, dx:] = mask[:-dy, :-dx]
    shadow = np.array(
        Image.fromarray((shadow * 255).astype(np.uint8)).filter(
            ImageFilter.GaussianBlur(SHADOW_BLUR)
        ),
        dtype=np.float64,
    ) / 255.0
    shadow *= 1.0 - mask  # 제품 위에는 그림자 없음

    arr = np.array(img, dtype=np.float64)
    darken = 1.0 - SHADOW_OPACITY * shadow[..., None]
    return Image.fromarray((arr * darken).clip(0, 255).astype(np.uint8))


def _protect_core(
    harmonized: Image.Image, composite: Image.Image, product_mask: Image.Image
) -> Image.Image:
    """코어 보호 재합성: 제품 내부=원본 합성본, 경계 링=조화 픽셀 (침식+페더 블렌딩)."""
    import numpy as np
    from PIL import ImageFilter

    binary = (np.array(product_mask) >= 128).astype(np.uint8)
    inv = 1 - binary
    for _ in range(CORE_ERODE_PX):
        stacked = [inv]
        for sy in (-1, 0, 1):
            for sx in (-1, 0, 1):
                if sy or sx:
                    stacked.append(np.roll(np.roll(inv, sy, axis=0), sx, axis=1))
        inv = np.max(np.stack(stacked), axis=0)
    eroded = 1 - inv

    feather = np.array(
        Image.fromarray((eroded * 255).astype(np.uint8)).filter(
            ImageFilter.GaussianBlur(CORE_FEATHER_PX)
        ),
        dtype=np.float64,
    ) / 255.0
    h = np.array(harmonized, dtype=np.float64)
    c = np.array(composite, dtype=np.float64)
    out = h * (1 - feather[..., None]) + c * feather[..., None]
    return Image.fromarray(out.clip(0, 255).astype(np.uint8))


def _harmonize(
    composite: Image.Image,
    product_mask: Image.Image,
    prompt: "ImagePrompt",
    seed: int,
) -> Image.Image:
    """그림자 → 저강도 img2img → 코어 보호. 실패 시 합성본 그대로 반환 (품질 패스는 best-effort)."""
    import torch

    try:
        shadowed = _add_contact_shadow(composite, product_mask)
        pipe = _load_harmonize_pipeline()
        harmonized = pipe(
            prompt=prompt.positive,
            negative_prompt=prompt.negative,
            image=shadowed,
            strength=HARMONIZE_STRENGTH,
            guidance_scale=HARMONIZE_GUIDANCE,
            num_inference_steps=DEFAULT_STEPS,
            generator=torch.Generator("cuda").manual_seed(seed),
        ).images[0]
        if harmonized.size != composite.size:
            harmonized = harmonized.resize(composite.size, Image.LANCZOS)
        return _protect_core(harmonized, composite, product_mask)
    except Exception as e:
        logger.error(f"조화 패스 실패 — 합성본으로 폴백: {e}")
        return composite


_food_pipeline = None


def _load_food_pipeline():  # noqa: ANN202
    """A모드 음식 리터치용 RealVisXL img2img lazy 싱글턴 (독립 로드).

    B모드 조화(SDXL base)와 분리 — 서로 다른 체크포인트라 컴포넌트 공유 불가.
    A·B 파이프라인 동시 상주 대비 cpu offload (음식 요청은 대개 단독이라 부담 적음).
    """
    global _food_pipeline
    if _food_pipeline is None:
        import torch
        from diffusers import StableDiffusionXLImg2ImgPipeline

        logger.info(f"음식 img2img 파이프라인 로드 시작: {FOOD_IMG2IMG_MODEL}")
        try:
            _food_pipeline = StableDiffusionXLImg2ImgPipeline.from_pretrained(
                FOOD_IMG2IMG_MODEL, torch_dtype=torch.float16, variant="fp16",
            )
        except Exception:  # fp16 variant 없으면 기본 가중치로 (다운캐스트)
            _food_pipeline = StableDiffusionXLImg2ImgPipeline.from_pretrained(
                FOOD_IMG2IMG_MODEL, torch_dtype=torch.float16,
            )
        _food_pipeline.enable_model_cpu_offload()
        _food_pipeline.enable_vae_slicing()
        logger.info("음식 img2img 파이프라인 로드 완료 (RealVisXL, cpu offload)")
    return _food_pipeline


def img2img(
    image: Image.Image,
    positive: str,
    negative: str,
    strength: float,
    seed: int = 7,
    guidance: float = 6.5,
    steps: int = 32,
    photoreal: bool = False,
) -> Image.Image:
    """SDXL img2img — GPU 파이프라인 단독 소유 지점.

    photoreal=False: 조화 파이프라인(SDXL base) 재사용 (B모드 등).
    photoreal=True : RealVisXL 전용 파이프라인 (A모드 음식 리터치 — 사실감 보존).
    strength 로 변형 강도 조절 (0.3 안전 ~ 0.65 글램).
    """
    import torch

    pipe = _load_food_pipeline() if photoreal else _load_harmonize_pipeline()
    return pipe(
        prompt=positive,
        negative_prompt=negative,
        image=image,
        strength=strength,
        guidance_scale=guidance,
        num_inference_steps=steps,
        generator=torch.Generator("cuda").manual_seed(seed),
    ).images[0]


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
        _sdxl_pipeline.enable_vae_slicing()  # 1024² decode 피크 VRAM 절감 (속도 영향 미미)
        logger.info("SDXL Inpainting 파이프라인 로드 완료")
    return _sdxl_pipeline


def unload_pipelines(keep: tuple = ()) -> None:
    """VRAM 확보 — 지정(keep) 외 SDXL/RealVis 파이프라인 언로드. 대형 모델(FLUX) 로드 전 호출.

    keep: {"sdxl","harmonize","food"} 부분집합. B모드는 리터치(food) 후 전부 비우고 FLUX 로드.
    """
    import gc

    import torch

    global _sdxl_pipeline, _harmonize_pipeline, _food_pipeline
    if "sdxl" not in keep:
        _sdxl_pipeline = None
    if "harmonize" not in keep:
        _harmonize_pipeline = None
    if "food" not in keep:
        _food_pipeline = None
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    logger.info(f"파이프라인 언로드 (keep={keep}) — VRAM 확보")


def _flat_color_background(
    product_rgba: Image.Image, product_mask: Image.Image, mode: str = "editorial"
) -> Image.Image:
    """평면 배경 합성 (SDXL 미사용, 결정적 렌더링). 비용·지연 0.

    mode:
      - editorial: 제품 주도색 딥톤 + 수직 그라데이션 (SDXL 회색조 회귀 우회, QUA-007)
      - retro    : 크림 아이보리 + 미세 종이 그레인 (레퍼런스 배경 — SDXL 로 만들면
                   소품·색 편차가 생김, 포스터 v3 피드백)
    """
    import colorsys
    import io as _io

    import numpy as np

    from .overlay_service import extract_signature_color

    # 주도색 추출을 위해 임시로 제품 합성본 사용
    buf = _io.BytesIO()
    product_rgba.convert("RGB").save(buf, format="PNG")
    tmp = RESULTS_DIR / "_sig_tmp.png"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(buf.getvalue())
    mask_tmp = RESULTS_DIR / "_sig_mask_tmp.png"
    product_mask.save(mask_tmp)
    sig = extract_signature_color(str(tmp), str(mask_tmp))
    tmp.unlink(missing_ok=True)
    mask_tmp.unlink(missing_ok=True)

    w, h = product_rgba.size
    if mode == "pastel":
        # 파스텔 그라데이션 + 보케 방울 (SDXL 지브리시·소품 환각 원천 차단)
        from PIL import ImageDraw, ImageFilter

        top = np.array([255.0, 226.0, 212.0])     # 피치
        bot = np.array([246.0, 197.0, 208.0])     # 핑크
        t = np.linspace(0, 1, h)[:, None, None]
        bg = (top[None, None, :] * (1 - t) + bot[None, None, :] * t)
        canvas = Image.fromarray(np.tile(bg, (1, w, 1)).astype(np.uint8))

        # 보케 방울: 반투명 원 + 상단 하이라이트, 제품 뒤 레이어
        bubbles = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bubbles)
        rng = np.random.default_rng(5)
        for _ in range(46):
            r = int(rng.uniform(7, 34))
            x, y = int(rng.uniform(0, w)), int(rng.uniform(0, h))
            alpha = int(rng.uniform(50, 120))
            bd.ellipse([x - r, y - r, x + r, y + r],
                       fill=(255, 255, 255, alpha),
                       outline=(255, 255, 255, min(alpha + 60, 255)), width=2)
            hr = max(2, r // 3)
            bd.ellipse([x - r // 2 - hr, y - r // 2 - hr, x - r // 2 + hr, y - r // 2 + hr],
                       fill=(255, 255, 255, min(alpha + 90, 255)))
        bubbles = bubbles.filter(ImageFilter.GaussianBlur(1.2))
        canvas.paste(bubbles, (0, 0), bubbles)

        canvas.paste(product_rgba, (0, 0), product_rgba)
        return _add_contact_shadow(canvas, product_mask)

    if mode == "studio":
        # 클린 스튜디오 스윕 (C모드 사물 제품컷): 중립 밝은 그라데이션 + 중앙 소프트광.
        #   음식·카페와 달리 사물은 '먹음직'이 아니라 '정확·깔끔'이 목표 → 무채색 배경.
        top = np.array([248.0, 248.0, 249.0])
        bot = np.array([225.0, 223.0, 222.0])
        t = np.linspace(0, 1, h)[:, None, None]
        canvas = np.tile(top[None, None, :] * (1 - t) + bot[None, None, :] * t, (1, w, 1))
        yy, xx = np.mgrid[0:h, 0:w]
        r = np.sqrt(((xx - w * 0.5) / (w * 0.5)) ** 2 + ((yy - h * 0.42) / (h * 0.55)) ** 2)
        canvas = np.clip(canvas + np.clip(1 - r, 0, 1)[..., None] * 12.0, 0, 255)
        canvas = Image.fromarray(canvas.astype(np.uint8))
        canvas.paste(product_rgba, (0, 0), product_rgba)
        return _add_contact_shadow(canvas, product_mask)

    if mode == "retro":
        # 크림 아이보리 + 종이 그레인 (레퍼런스: softly aged cream paper)
        base = np.full((h, w, 3), (246.0, 238.0, 219.0), dtype=np.float64)
        rng = np.random.default_rng(3)
        grain = rng.normal(0, 4.5, (h, w, 1))
        canvas = Image.fromarray((base + grain).clip(0, 255).astype(np.uint8))
    else:
        # 배경용 딥톤 (아이보리 타이포 대비 확보)
        hh, ss, vv = colorsys.rgb_to_hsv(*(c / 255.0 for c in sig))
        ss = min(max(ss, 0.42), 0.75)
        vv = min(max(vv * 0.85, 0.34), 0.60)
        r, g, b = (int(c * 255) for c in colorsys.hsv_to_rgb(hh, ss, vv))
        # 수직 그라데이션 (상단 +8% 밝게 → 하단 -8%) 로 평면감 완화
        grad = np.linspace(1.08, 0.92, h)[:, None, None]
        bg = (np.array([r, g, b], dtype=np.float64)[None, None, :] * grad).clip(0, 255)
        canvas = Image.fromarray(np.tile(bg, (1, w, 1)).astype(np.uint8))

    canvas.paste(product_rgba, (0, 0), product_rgba)
    return _add_contact_shadow(canvas, product_mask)


def generate_ad_image(
    processed: PreprocessResult,
    prompt: "ImagePrompt",
    seed: Optional[int] = None,
    output_dir: Optional[str] = None,
    harmonize: bool = True,
    flat_background: Optional[str] = None,  # "editorial" | "retro" | "pastel" | None(생성)
    product_tilt: float = 0.0,  # 2.5D 연출: 제품 기울임 각도 (레퍼런스 플로팅 룩 ~ -12°)
) -> GenerateResult:
    """FR-08: 전처리 이미지 + 프롬프트 → 최종 광고 이미지.

    inpainting으로 제품 보존 + 배경 교체. seed 고정 시 재현.
    prompt 는 prompt_service.build_image_prompt() 산출물(FR-07).

    단계:
      1. 전처리 이미지(RGBA) → 흰 배경 합성 RGB (inpainting 입력)
      2. 제품 마스크(제품=흰색) invert → 배경 마스크 (inpaint 대상=흰색) + 경계 블러
      3. SDXL Inpainting 실행 (seed 고정 가능)
      4. 원본 제품 픽셀 재합성 → 제품 영역 보존 보장
      5. 조화 패스 (그림자 + img2img + 코어 보호) — harmonize=False 로 생략 가능
      6. backend/results/ai/ 저장
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

    # 2.5D 기울임: 회전 후 히어로 비율로 재배치 (마스크는 알파에서 재유도)
    if product_tilt:
        rotated = product_rgba.rotate(product_tilt, expand=True, resample=Image.BICUBIC)
        product_rgba = _fit_product(rotated, target_size=product_mask.size)
        product_mask = product_rgba.split()[-1]

    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    # 평면 배경 경로 (editorial/retro): SDXL·조화 생략 — 코드 렌더링
    if flat_background:
        started = time.perf_counter()
        result = _flat_color_background(product_rgba, product_mask, mode=flat_background)
        infer_seconds = time.perf_counter() - started

        out_dir = Path(output_dir) if output_dir else RESULTS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        final_path = out_dir / f"{src.stem.replace('_processed', '')}_ad_{seed}.png"
        result.convert("RGB").save(final_path, format="PNG")
        logger.info(f"광고 이미지 생성 완료 (평면 배경 {flat_background}): {final_path}")
        return GenerateResult(
            final_image_path=str(final_path), seed=seed,
            infer_seconds=infer_seconds, harmonize_seconds=0.0,
        )

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

    # 5. 조화 패스 (QUA-003: 코어 SSIM 0.97+ 유지, '붙여넣은 티' 제거)
    harmonize_seconds = 0.0
    if harmonize:
        started = time.perf_counter()
        result = _harmonize(result, product_mask, prompt, seed)
        harmonize_seconds = time.perf_counter() - started

    # 연속 요청 시 단편화 누적으로 OOM 발생 (서비스 실측) → 요청마다 캐시 정리
    torch.cuda.empty_cache()

    # 6. 저장
    out_dir = Path(output_dir) if output_dir else RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    final_path = out_dir / f"{src.stem.replace('_processed', '')}_ad_{seed}.png"
    result.save(final_path, format="PNG")

    logger.info(
        f"광고 이미지 생성 완료: {final_path} "
        f"(seed={seed}, 생성 {infer_seconds:.2f}s + 조화 {harmonize_seconds:.2f}s)"
    )
    return GenerateResult(
        final_image_path=str(final_path),
        seed=seed,
        infer_seconds=infer_seconds,
        harmonize_seconds=harmonize_seconds,
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
