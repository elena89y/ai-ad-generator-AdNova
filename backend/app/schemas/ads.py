"""AdNova 공용 스키마 (스캐폴드).

축 분리 (2026-07-01 확정):
  - 스타일(style)  = 문구 톤 · 색상   (예: 모노톤 / 웜빈티지 / 팝)
  - 용도(purpose)  = 채널 · 목적       (예: SNS / 카드뉴스 / 배너 / 상세페이지 / 전단지)
명세서 BR-04, FR-24 의 'SNS' 중복은 이 축 분리로 해소 예정 (명세서 수정 미실행).

주의: 아래는 필드 시그니처만 정의한 골격. 검증 로직 · 실제 값 enum 미확정.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


# --- 축 정의 -----------------------------------------------------------------
class StylePreset(str, Enum):
    """스타일 = 문구 톤·색상. 값은 잠정, 실험(STY-001/002) 후 확정."""
    MONOTONE = "monotone"        # 모노톤
    WARM_VINTAGE = "warm_vintage"  # 웜빈티지
    POP = "pop"                  # 팝
    # TODO: 실험 결과로 프리셋 확정/추가


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

    경로1: image_path 제공 → Vision 분석 → 후보 추천
    경로2: free_text 제공  → 자유 텍스트 → 스타일 결정
    둘 중 하나만 채워지는 것을 전제. 상호배타 검증 TODO.
    """
    image_path: Optional[str] = None   # 경로1
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
