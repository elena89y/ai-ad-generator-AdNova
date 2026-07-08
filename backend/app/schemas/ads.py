"""AdNova 공용 스키마.

축 분리 (2026-07-01 확정):
  - 스타일(style)  = 문구 톤 · 색상   (예: 모노톤 / 웜빈티지 / 팝)
  - 용도(purpose)  = 채널 · 목적       (예: SNS / 카드뉴스 / 배너 / 상세페이지 / 전단지)
명세서 BR-04, FR-24 의 'SNS' 중복은 이 축 분리로 해소 예정 (명세서 수정 미실행).

주의: 스타일 결정 관련은 필드 시그니처만 정의한 골격. 검증 로직 · 실제 값 enum 미확정.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# --- 광고 생성 이력 (DB 연동, 담당: 김범수) -----------------------------------
class AdvertisementCreate(BaseModel):
    user_id: int
    input_image_id: Optional[int] = None
    output_image_id: Optional[int] = None
    title: Optional[str] = None
    ad_type: str
    prompt: str
    generated_text: Optional[str] = None
    style: Optional[str] = None
    tone: Optional[str] = None
    target_audience: Optional[str] = None
    status: str = "pending"
    error_message: Optional[str] = None


class AdvertisementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    input_image_id: Optional[int] = None
    output_image_id: Optional[int] = None
    title: Optional[str] = None
    ad_type: str
    prompt: str
    generated_text: Optional[str] = None
    style: Optional[str] = None
    tone: Optional[str] = None
    target_audience: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# --- 축 정의 (스타일 결정, 담당: 한의정) --------------------------------------
class StylePreset(str, Enum):
    """스타일 = 문구 톤·색상 + 배경 무드. 6종 확정 (2026-07-03, Issue #25).

    명칭은 프론트 버튼·명세서(BR-04)와 연동 — 변경 시 팀 공유 필수.
    """
    MONOTONE = "monotone"          # 모노톤 — 미니멀 무채색
    WARM_VINTAGE = "warm_vintage"  # 웜빈티지 — 카페·원목·골든아워
    POP = "pop"                    # 팝 — 고채도 팝아트
    EDITORIAL = "editorial"        # 에디토리얼 — 단색 배경·스튜디오 럭셔리
    RETRO_PAPER = "retro_paper"    # 레트로 페이퍼 — 아이보리 종이·스크린프린트
    PASTEL_FLOAT = "pastel_float"  # 파스텔 플로팅 — 파스텔·부유 소재·몽환


class AdPurpose(str, Enum):
    """용도 = 채널·목적. FR-24 원문 대응."""
    SNS = "sns"
    CARD_NEWS = "card_news"
    BANNER = "banner"
    DETAIL_PAGE = "detail_page"
    FLYER = "flyer"


# --- 스타일 결정 2경로 (FR-05 / /ads/style) ----------------------------------
class StyleRequest(BaseModel):
    """스타일 결정 요청.

    경로1: image_id 제공 → Vision 분석 → 후보 추천
    경로2: free_text 제공  → 자유 텍스트 → 스타일 결정
    둘 중 하나만 채워지는 것을 전제. 상호배타 검증 TODO.
    """
    image_id: Optional[int] = Field(default=None, gt=0)   # 경로1
    free_text: Optional[str] = None    # 경로2
    # TODO: 상품 정보 필드 추가 여부 결정


class StyleCandidate(BaseModel):
    """추천 후보 1건 (경로1에서 3개 반환 전제)."""
    preset: StylePreset
    reason: str          # 추천 근거 (Vision 분석 요약)
    # TODO: 미리보기/썸네일 참조 필드 여부 결정


class StyleResponse(BaseModel):
    """스타일 결정 응답."""
    candidates: list[StyleCandidate]   # 경로1: 3개 / 경로2: 1개
    resolved: Optional[StylePreset] = None  # 경로2에서 즉시 확정 시


# --- 파이프라인 산출물 참조용 (골격) -----------------------------------------
class ProductInfo(BaseModel):
    """상품 정보. 필드 미확정."""
    name: Optional[str] = None
    description: Optional[str] = None
    # TODO: 명세서 FR-03(상품 정보 입력) 필드와 정합 맞추기


# --- 통합 광고 생성 (FR-06~09, /ads/generate — 프론트 app.py 연동 스펙) --------
class GenerateAdResponse(BaseModel):
    """통합 파이프라인 응답. 프론트 결과 페이지가 사용하는 필드 구성."""
    asset_id: str                    # 재생성(/ads/regenerate)에 필요한 산출물 식별자
    seed: int                        # 재현/재생성용
    style: StylePreset
    copy_text: str                   # '헤드라인\n서브카피' (FR-09)
    image_url: str                   # GET /ads/image/{filename} 상대 경로
    poster: bool                     # 타이포 오버레이 적용 여부
    generate_seconds: float
    harmonize_seconds: float


class RegenerateAdRequest(BaseModel):
    """FR-12: 동일 입력(전처리 산출물 재사용) · 새 seed 재생성."""
    asset_id: str = Field(..., min_length=12, max_length=12, pattern=r"^[a-f0-9]{12}$")
    style: StylePreset
    product_name: Optional[str] = None
    product_description: Optional[str] = None
    prev_seed: Optional[int] = None
    use_vision: bool = False
    poster: bool = False
