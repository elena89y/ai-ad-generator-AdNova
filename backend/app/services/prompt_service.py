"""프롬프트 구성 서비스 (스캐폴드) — 담당: 한의정.

대응 FR:
  - FR-07 광고 생성 프롬프트 구성 (상품 정보 + 이미지 + 스타일 → 이미지 프롬프트)

파이프라인 위치: 스타일 결정 → [FR-07] → 이미지 생성(FR-08).
산출물(prompt)은 image_service.generate_ad_image() 의 입력.

이미지 프롬프트 전용. 문구(카피) 프롬프트는 gpt_service 쪽에서 별도 구성.
seed 고정 · positive/negative 분리는 A-4 프롬프트 실험에서 관리.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..schemas.ads import ProductInfo, StylePreset


@dataclass
class ImagePrompt:
    """FR-07 산출물. image_service 로 전달."""
    positive: str
    negative: str
    # TODO: A-4 실험 파라미터(steps/guidance/seed) 동반 여부 결정


def build_image_prompt(
    product: ProductInfo,
    style: StylePreset,
    image_caption: Optional[str] = None,
) -> ImagePrompt:
    """상품 정보 + 스타일 (+ 이미지 캡션) → 이미지 생성 프롬프트.

    image_caption: 저비용 경로에서 BLIP 캡션 주입(B-0). None이면 미사용.
    스타일 → 톤·색상 키워드 매핑 테이블 미확정.
    """
    raise NotImplementedError("FR-07 프롬프트 구성 미구현 — A-4 실험 후")


# --- 스타일 → 키워드 매핑 (골격) ---------------------------------------------
_STYLE_KEYWORDS: dict[StylePreset, dict[str, str]] = {
    # TODO: A-4 실험으로 positive/negative 키워드 확정
    StylePreset.MONOTONE: {"positive": "", "negative": ""},
    StylePreset.WARM_VINTAGE: {"positive": "", "negative": ""},
    StylePreset.POP: {"positive": "", "negative": ""},
}
