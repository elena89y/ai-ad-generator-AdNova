"""OpenAI 호출 래퍼 (스캐폴드) — 담당: 한의정.

역할: OpenAI API(문구 생성 · Vision 분석) 단일 진입 지점.
  - FR-09 광고 문구 생성 (생성 이미지 기반 — 파이프라인 확정안)
  - FR-23 SNS 공유 문구 생성 (플랫폼별 캡션·해시태그)
  - 스타일 경로1용 Vision 이미지 분석 (style_service 가 호출)

⚠️ 명세서 불일치(미해소):
  FR-09 원문 입력 = "상품 정보 + 스타일".
  확정 파이프라인   = "생성 이미지 기반" 문구 생성(4단계).
  → 골격은 확정안(이미지 기반)을 따름. 명세서 FR-09 수정은 미실행 To-do.

⚠️ 비용/보안:
  - 팀 OpenAI 한도 $30. 초과 시 key disabled. B-0 단계분리(BLIP↔Vision)로 방어.
  - API key 는 env 로드. 코드/깃/로그에 노출 금지. .gitignore 확인 필수.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from ..schemas.ads import AdPurpose, ProductInfo, StyleCandidate, StylePreset


# --- 산출물 ------------------------------------------------------------------
@dataclass
class CopyResult:
    """FR-09 산출물."""
    copy_text: str


@dataclass
class SnsCopyResult:
    """FR-23 산출물."""
    caption: str
    hashtags: list[str]


# --- 클라이언트 (골격) --------------------------------------------------------
def _get_client():  # noqa: ANN202
    """OpenAI 클라이언트 생성. key 는 env 에서만."""
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 미설정 (env 로드 필요)")
    return OpenAI(api_key=api_key)
    # TODO: 모델 string 확정(GPT-5.4 Nano/Mini/일반). 비용 기준 Mini 검토 중.

# --- FR-09 광고 문구 생성 -----------------------------------------------------
def generate_copy(
    final_image_path: str,
    product: ProductInfo,
    style: StylePreset,
) -> CopyResult:
    """생성된 광고 이미지 기반 광고 문구 생성 (확정 파이프라인).

    개발 단계: BLIP 캡션 → 텍스트 API (저비용).
    검증/데모: Vision API 직접 입력 (정합성 입증 시에만, B-0).
    """
    raise NotImplementedError("FR-09 문구 생성 미구현")


# --- FR-23 SNS 문구 생성 ------------------------------------------------------
def generate_sns_copy(
    product: ProductInfo,
    style: StylePreset,
    purpose: AdPurpose,
) -> SnsCopyResult:
    """플랫폼(purpose)별 캡션 + 해시태그 생성."""
    raise NotImplementedError("FR-23 SNS 문구 미구현")


# --- 스타일 경로1: Vision 분석 -----------------------------------------------
def analyze_image_for_style(image_path: str) -> list[StyleCandidate]:
    """이미지 Vision 분석 → 스타일 후보 3개 반환 (style_service 경로1).

    ⚠️ Vision 호출 = 비용 발생. 개발 중 반복 호출 금지.
    """
    client = _get_client()

    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    preset_values = [p.value for p in StylePreset]

    prompt = (
        "이 상품 이미지를 보고 어울리는 광고 스타일(문구 톤·색상) 후보 3개를 추천해줘. "
        f"각 후보는 다음 중 하나여야 해: {preset_values}. "
        "각 후보에 대해 왜 이 이미지에 어울리는지 간단한 이유도 함께 작성해줘. "
        '반드시 아래 JSON 형식으로만 응답해: '
        '{"candidates": [{"preset": "monotone", "reason": "..."}, '
        '{"preset": "warm_vintage", "reason": "..."}, '
        '{"preset": "pop", "reason": "..."}]}'
    )

    response = client.chat.completions.create(
        model="gpt-5.4-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            }
        ],
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)
    candidates = [
        StyleCandidate(preset=StylePreset(c["preset"]), reason=c["reason"])
        for c in result["candidates"]
    ]
    return candidates
