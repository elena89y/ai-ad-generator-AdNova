"""이미지 서비스 (스캐폴드) — 담당: 한의정.

대응 FR:
  - FR-06 상품 이미지 전처리 (배경 제거/마스킹 · 크기 조정 · 품질 보정)
  - FR-08 상품 이미지 기반 광고 생성 (제품 보존 + 배경 교체 inpainting)
  - FR-12 재생성 (동일 입력 · seed 변경)

파이프라인 위치 (4단계 확정):
  전처리(FR-06) → 스타일 결정(2경로) → [이미지 생성 FR-08] → 문구 생성(FR-09)

모델 결정(A-1) 미확정:
  후보 = SDXL Inpainting(1순위) / FLUX.1 Fill(2순위, offload) / SD1.5(속도 비교군).
  실측(IMG-001~) 전까지 로더 구현 보류. VRAM · 추론시간 실측 후 확정.
마스킹(A-2) 미확정: SAM vs rembg. 검증 전까지 인터페이스만.

실행 환경: GPU 필요(Colab L4 / GCP L4). 로컬 CPU에서는 미동작 전제.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


# --- 데이터 컨테이너 ----------------------------------------------------------
@dataclass
class PreprocessResult:
    """FR-06 산출물."""
    processed_image_path: str
    mask_path: Optional[str] = None   # 마스킹 사용 시 제품/배경 분리 마스크
    # TODO: A-3 픽셀 보존율 측정을 위해 원본 참조 경로 보관 여부 결정


@dataclass
class GenerateResult:
    """FR-08 산출물."""
    final_image_path: str
    seed: int
    infer_seconds: float          # A-1 추론시간 실측 기록용
    # TODO: 제품 보존율(SSIM/L1) 필드 — A-3 지표 확정 후 추가


# --- 마스킹 추상화 (A-2 검증 전 인터페이스만) --------------------------------
class Masker(Protocol):
    """SAM / rembg 공통 인터페이스. 구현체는 실측 후 결정."""
    def make_mask(self, image_path: str) -> str:
        """제품/배경 분리 마스크 생성 → 마스크 경로 반환."""
        ...


# --- 공개 함수 (골격) ---------------------------------------------------------
def preprocess(image_path: str, masker: Optional[Masker] = None) -> PreprocessResult:
    """FR-06: 업로드 상품 이미지 전처리.

    단계(예정): 로드 → (masker) 배경/제품 분리 → 크기 조정 → 품질 보정.
    """
    raise NotImplementedError("FR-06 전처리 미구현 — 마스킹(A-2) 확정 후")


def generate_ad_image(
    processed: PreprocessResult,
    prompt: str,
    seed: Optional[int] = None,
) -> GenerateResult:
    """FR-08: 전처리 이미지 + 프롬프트 → 최종 광고 이미지.

    inpainting으로 제품 보존 + 배경 교체. seed 고정 시 재현.
    prompt 는 prompt_service.build_image_prompt() 산출물(FR-07) 전제.
    """
    raise NotImplementedError("FR-08 이미지 생성 미구현 — 모델(A-1) 확정 후")


def regenerate(
    processed: PreprocessResult,
    prompt: str,
    prev_seed: Optional[int] = None,
) -> GenerateResult:
    """FR-12: 동일 입력 · 새 seed 로 재생성."""
    raise NotImplementedError("FR-12 재생성 미구현")


# --- 모델 로더 (A-1 실측 전 보류) --------------------------------------------
def _load_pipeline():  # noqa: ANN202
    """diffusers inpainting 파이프라인 로드.

    후보: diffusers/stable-diffusion-xl-1.0-inpainting-0.1
    VRAM/추론시간 실측(IMG-001) 후 모델 string · dtype · offload 확정.
    """
    raise NotImplementedError("A-1 모델 미확정")
