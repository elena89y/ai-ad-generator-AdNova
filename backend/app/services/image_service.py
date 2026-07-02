"""이미지 서비스 — 담당: 한의정.

대응 FR:
  - FR-06 상품 이미지 전처리 (배경 제거/마스킹 · 크기 조정 · 품질 보정) ← 구현 완료
  - FR-08 상품 이미지 기반 광고 생성 (제품 보존 + 배경 교체 inpainting) ← 미구현
  - FR-12 재생성 (동일 입력 · seed 변경) ← 미구현

파이프라인 위치 (4단계 확정):
  전처리(FR-06) → 스타일 결정(2경로) → [이미지 생성 FR-08] → 문구 생성(FR-09)

마스킹(A-2) 확정: rembg(u2net, ONNX). GPU 환경(onnxruntime-gpu)에서 가속,
  미지원 환경에서는 onnxruntime(CPU)로 자동 폴백.
모델 결정(A-1) 미확정:
  후보 = SDXL Inpainting(1순위) / FLUX.1 Fill(2순위, offload) / SD1.5(속도 비교군).
  실측(IMG-001~) 전까지 로더 구현 보류. VRAM · 추론시간 실측 후 확정.

실행 환경: 전처리(FR-06)는 CPU에서도 동작(느림). FR-08은 GPU 필요(GCP L4).
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image, ImageEnhance, ImageOps

logger = logging.getLogger(__name__)

# 광고 이미지 표준 규격 (FR-18의 비율 옵션 중 기본값 1:1 기준, 추후 옵션화)
DEFAULT_OUTPUT_SIZE: tuple[int, int] = (1024, 1024)
MAX_INPUT_DIMENSION = 2048  # 과도하게 큰 업로드 이미지에 대한 리사이즈 상한

# 전처리 산출물 저장 위치: backend/processed/
PROCESSED_DIR = Path(__file__).resolve().parents[2] / "processed"

# rembg 세션은 최초 사용 시 1회만 생성 (요청마다 재생성하면 GPU 초기화 비용 발생).
# 모듈 import 시점에 만들지 않는 이유: rembg 미설치 환경(로컬 CPU 개발 등)에서도
# 본 모듈을 import 하는 서버 기동 자체는 가능해야 함.
_rembg_session = None


def _get_rembg_session():  # noqa: ANN202
    """u2net 세션 lazy 초기화. 범용 배경 제거 모델, L4 24GB 환경에서 VRAM 여유."""
    global _rembg_session
    if _rembg_session is None:
        # onnxruntime-gpu 가 pip 으로 설치된 NVIDIA 라이브러리(nvidia-cublas-cu12 등)를
        # 찾으려면 세션 생성 전에 preload 가 필요 (없으면 CPU 로 조용히 폴백됨).
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
    from rembg import remove

    try:
        return remove(img, session=_get_rembg_session())
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


# --- FR-08 / FR-12 (미구현 — A-1 모델 확정 후) --------------------------------
def generate_ad_image(
    processed: PreprocessResult,
    prompt: str,
    seed: Optional[int] = None,
) -> GenerateResult:
    """FR-08: 전처리 이미지 + 프롬프트 → 최종 광고 이미지.

    inpainting으로 제품 보존 + 배경 교체. seed 고정 시 재현.
    prompt 는 prompt_service.build_image_prompt() 산출물(FR-07) 전제.
    마스크는 processed.mask_path 사용 (제품=흰색 → 배경 재생성 시 invert).
    """
    raise NotImplementedError("FR-08 이미지 생성 미구현 — 모델(A-1) 확정 후")


def regenerate(
    processed: PreprocessResult,
    prompt: str,
    prev_seed: Optional[int] = None,
) -> GenerateResult:
    """FR-12: 동일 입력 · 새 seed 로 재생성."""
    raise NotImplementedError("FR-12 재생성 미구현")


def _load_pipeline():  # noqa: ANN202
    """diffusers inpainting 파이프라인 로드.

    후보: diffusers/stable-diffusion-xl-1.0-inpainting-0.1
    VRAM/추론시간 실측(IMG-001) 후 모델 string · dtype · offload 확정.
    """
    raise NotImplementedError("A-1 모델 미확정")


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
