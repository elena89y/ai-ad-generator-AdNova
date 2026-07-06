"""프롬프트 구성 서비스 — 담당: 한의정.

대응 FR:
  - FR-07 광고 생성 프롬프트 구성 (상품 정보 + 이미지 + 스타일 → 이미지 프롬프트)

파이프라인 위치: 스타일 결정 → [FR-07] → 이미지 생성(FR-08).
산출물(prompt)은 image_service.generate_ad_image() 의 입력.
FR-08 은 inpainting(제품 보존 + 배경 교체) 전제 — 프롬프트는 배경·분위기 중심으로 기술.

이미지 프롬프트 전용. 문구(카피) 프롬프트는 gpt_service 쪽에서 별도 구성.
seed 고정 · positive/negative 분리는 A-4 프롬프트 실험에서 관리.
스타일 키워드는 v1 잠정치 — A-4 실험으로 확정/교체 예정.
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


# --- 공통 키워드 (스타일 무관) -------------------------------------------------
# SDXL 계열은 영어 프롬프트 기준. 상품명 등 한국어 입력은 문맥 정보로만 덧붙인다.
# ⚠️ CLIP 텍스트 인코더 한도 77토큰 — positive/negative 모두 초과분은 잘려나감.
#    (IMG-002: positive 스타일 잘림 / QUA-003: negative 84토큰 잘림 실측)
# 'sharp focus' 는 이미지에 'SHARP' 텍스트로 누출된 사례가 있어 제거 (A-4 v2 채택).
_BASE_POSITIVE = "professional product advertisement photo, high detail"

# 광고 문구는 FR-09에서 별도 생성 → 이미지 안에 글자·간판·포장 문구 금지 (A-4 v2).
# inpainting 흔한 실패 모드(손·인물 파편, 소품/음식 환각, 제품 복제)도 차단.
_BASE_NEGATIVE = (
    "text, typography, letters, watermark, logo, signage, label, "
    "packaging, price tag, brand name, "
    "human, hands, extra food, extra products, "
    "lowres, blurry, distorted, deformed, cropped product, duplicate product"
)


# --- 스타일 → 키워드 매핑 (v1 잠정치, A-4 실험으로 확정) -----------------------
_STYLE_KEYWORDS: dict[StylePreset, dict[str, str]] = {
    StylePreset.MONOTONE: {
        "positive": (
            "minimalist monochrome background, neutral gray and white tones, "
            "soft diffused studio lighting, generous negative space, modern and calm mood"
        ),
        "negative": "vivid saturated colors, cluttered background, busy patterns",
    },
    StylePreset.WARM_VINTAGE: {
        "positive": (
            "warm vintage atmosphere, cozy retro cafe mood, soft warm film grain tones, "
            "wooden table texture, golden hour window light, nostalgic feeling"
        ),
        "negative": "cold blue tones, futuristic, neon lights, sterile white background",
    },
    StylePreset.POP: {
        "positive": (
            "vibrant pop art style background, bold saturated complementary colors, "
            "playful geometric shapes, high contrast studio lighting, energetic mood"
        ),
        "negative": "dull muted colors, dark moody lighting, monochrome, plain background",
    },
}


def build_image_prompt(
    product: ProductInfo,
    style: StylePreset,
    image_caption: Optional[str] = None,
) -> ImagePrompt:
    """상품 정보 + 스타일 (+ 이미지 캡션) → 이미지 생성 프롬프트.

    구성 순서 (positive — CLIP 77토큰 한도 내 중요도순):
      1. 공통 광고 사진 키워드 (짧게)
      2. 스타일 키워드 (배경·조명·무드) — 뒤에 두면 잘려서 미반영 (IMG-002 교훈)
      3. 이미지 캡션 (B-0 저비용 경로에서 BLIP 캡션 주입. None 이면 생략)
      4. 상품 문맥 (name/description — 있는 필드만)
    negative 는 공통 금지 키워드 + 스타일별 금지 키워드.
    """
    if style not in _STYLE_KEYWORDS:
        raise ValueError(f"키워드 매핑이 없는 스타일입니다: {style}")

    style_kw = _STYLE_KEYWORDS[style]

    positive_parts = [_BASE_POSITIVE, style_kw["positive"]]

    if image_caption and image_caption.strip():
        positive_parts.append(f"scene of {image_caption.strip()}")

    product_context = ", ".join(
        part.strip()
        for part in (product.name, product.description)
        if part and part.strip()
    )
    if product_context:
        positive_parts.append(f"product: {product_context}")

    return ImagePrompt(
        positive=", ".join(positive_parts),
        negative=f"{_BASE_NEGATIVE}, {style_kw['negative']}",
    )


if __name__ == "__main__":
    # 로컬 확인용 (API 호출·비용 없음): 프리셋 3종 프롬프트 출력
    sample = ProductInfo(name="핸드드립 원두", description="산미가 적은 다크 로스트")
    for preset in StylePreset:
        p = build_image_prompt(sample, preset, image_caption="a bag of coffee beans")
        print(f"[{preset.value}]")
        print(f"  positive: {p.positive}")
        print(f"  negative: {p.negative}")
