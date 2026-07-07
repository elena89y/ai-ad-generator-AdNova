"""OpenAI 호출 래퍼 — 담당: 한의정.

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

import base64
import json
import logging
import mimetypes
import os
from dataclasses import dataclass
from typing import Optional

from ..schemas.ads import AdPurpose, ProductInfo, StyleCandidate, StylePreset

logger = logging.getLogger(__name__)


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


@dataclass
class ApiUsage:
    """OpenAI 호출 1건의 토큰 사용량. $30 한도 관리용 — 모든 호출에서 기록."""
    label: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


# 프로세스 내 누적 사용량. 실험 스크립트가 결과 md 에 함께 저장한다.
API_USAGE_LOG: list[ApiUsage] = []


def _record_usage(label: str, response) -> None:  # noqa: ANN001
    """응답의 usage 를 로그·누적 기록. usage 미제공 시 경고만."""
    usage = getattr(response, "usage", None)
    if usage is None:
        logger.warning(f"[OpenAI usage] {label}: usage 정보 없음")
        return
    entry = ApiUsage(
        label=label,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
    )
    API_USAGE_LOG.append(entry)
    logger.info(
        f"[OpenAI usage] {label}: prompt={entry.prompt_tokens}, "
        f"completion={entry.completion_tokens}, total={entry.total_tokens}"
    )


def usage_summary() -> str:
    """누적 사용량 요약 문자열 (실험 결과 md 저장용)."""
    if not API_USAGE_LOG:
        return "OpenAI 호출 없음"
    lines = [
        f"- {u.label}: prompt {u.prompt_tokens} + completion {u.completion_tokens} = {u.total_tokens} tokens"
        for u in API_USAGE_LOG
    ]
    total = sum(u.total_tokens for u in API_USAGE_LOG)
    lines.append(f"- **합계: {len(API_USAGE_LOG)}회 호출, {total} tokens ({GPT_MODEL})**")
    return "\n".join(lines)


# --- 클라이언트 ----------------------------------------------------------------
GPT_MODEL = "gpt-5.4-mini"  # STY-001 검증 완료. Nano 다운그레이드는 비용/품질 실험 후


def _get_client():  # noqa: ANN202
    """OpenAI 클라이언트 생성. key 는 env 에서만."""
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 미설정 (env 로드 필요)")
    return OpenAI(api_key=api_key)


# --- 스타일 → 문구 톤 매핑 (v1 잠정치, 실험 후 확정) ---------------------------
_STYLE_TONE: dict[StylePreset, str] = {
    StylePreset.MONOTONE: "절제되고 미니멀한 톤. 짧고 세련된 표현, 불필요한 수식어 배제",
    StylePreset.WARM_VINTAGE: "따뜻하고 감성적인 톤. 포근한 정서와 추억을 자극하는 표현",
    StylePreset.POP: "발랄하고 에너지 넘치는 톤. 리듬감 있는 표현과 감탄사 활용 가능",
    StylePreset.EDITORIAL: "고급스럽고 정제된 톤. 프리미엄 매거진 헤드라인처럼 짧고 단정한 단문",
    StylePreset.RETRO_PAPER: "복고풍의 정겨운 톤. 오래된 간판·손글씨 광고 같은 친근하고 담백한 표현",
    StylePreset.PASTEL_FLOAT: "가볍고 산뜻한 톤. 부드럽고 몽글몽글한 표현, 상큼함과 설렘 강조",
}

_PURPOSE_GUIDE: dict[AdPurpose, str] = {
    AdPurpose.SNS: "인스타그램 피드 게시물. 첫 줄에 후킹, 이모지 적절히 활용, 해시태그 5~8개",
    AdPurpose.CARD_NEWS: "카드뉴스 표지. 호기심을 유발하는 한 줄, 해시태그 3~5개",
    AdPurpose.BANNER: "웹 배너. 매우 짧고 강한 한 줄, 해시태그 최소",
    AdPurpose.DETAIL_PAGE: "상세페이지 도입부. 신뢰감 있는 설명형, 해시태그 불필요 시 빈 배열",
    AdPurpose.FLYER: "오프라인 전단지. 직관적 혜택 강조, 해시태그 불필요 시 빈 배열",
}


# --- 이미지 캡셔닝 (B-0 저비용 경로, 로컬 BLIP) --------------------------------
_blip = None  # (processor, model, device) 튜플 lazy 싱글턴


def _caption_image(image_path: str) -> str:
    """BLIP 로컬 캡셔닝 — API 비용 없음. GPU 있으면 사용, 없으면 CPU.

    생성 이미지의 장면 묘사(영어)를 반환. generate_copy 저비용 경로 입력.
    """
    global _blip
    import torch
    from PIL import Image

    if _blip is None:
        from transformers import BlipForConditionalGeneration, BlipProcessor

        # CPU 고정: L4 에서 SDXL 2종+rembg 와 동시 상주 시 OOM (서비스 실측).
        # BLIP-base 는 CPU 추론 ~2s 로 지연 예산 내 — VRAM 1GB+ 절약이 이득.
        device = "cpu"
        processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
        model = BlipForConditionalGeneration.from_pretrained(
            "Salesforce/blip-image-captioning-base"
        ).to(device)
        _blip = (processor, model, device)

    processor, model, device = _blip
    img = Image.open(image_path).convert("RGB")
    inputs = processor(img, return_tensors="pt").to(device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=40)
    return processor.decode(out[0], skip_special_tokens=True)


def _chat_json(messages: list, label: str) -> dict:
    """JSON 강제 chat 호출 공통 래퍼. 토큰 사용량 기록 포함."""
    client = _get_client()
    response = client.chat.completions.create(
        model=GPT_MODEL,
        messages=messages,
        response_format={"type": "json_object"},
    )
    _record_usage(label, response)
    return json.loads(response.choices[0].message.content)


# --- FR-09 광고 문구 생성 -----------------------------------------------------
def generate_copy(
    final_image_path: str,
    product: ProductInfo,
    style: StylePreset,
    use_vision: bool = False,
    feedback: str = "",
) -> CopyResult:
    """생성된 광고 이미지 기반 광고 문구 생성 (확정 파이프라인).

    use_vision=False (기본, 개발): BLIP 캡션 → 텍스트 API (저비용, B-0)
    use_vision=True  (검증/데모): 이미지를 Vision 으로 직접 입력 (비용 ↑, 호출 최소화)
    feedback: 재시도 시 직전 위반 사항을 주입 (LangGraph 품질 게이트 루프용, 하위호환).
    """
    product_context = " — ".join(
        p.strip() for p in (product.name, product.description) if p and p.strip()
    ) or "(상품 정보 없음)"

    retry_note = (
        f"\n- ⚠️ 직전 시도가 규칙을 어겼어. 다음을 반드시 고쳐서 다시 써: {feedback}"
        if feedback else ""
    )
    instruction = (
        "아래 광고 이미지와 상품 정보를 바탕으로 한국어 광고 카피를 작성해줘.\n"
        f"- 상품: {product_context}\n"
        f"- 문구 톤: {_STYLE_TONE[style]}\n"
        "요구사항: 헤드라인 1줄 + 서브카피 1문장. 이미지에 실제로 보이는 분위기·소품과 "
        "어울려야 하고, 이미지에 없는 요소를 지어내지 마."
        f"{retry_note}\n"
        '반드시 JSON 으로만 응답: {"copy": "헤드라인\\n서브카피"}'
    )

    if use_vision:
        with open(final_image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
        media_type, _ = mimetypes.guess_type(final_image_path)
        if media_type is None or not media_type.startswith("image/"):
            media_type = "image/png"
        content = [
            {"type": "text", "text": instruction},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{image_b64}"},
            },
        ]
    else:
        caption = _caption_image(final_image_path)
        content = f"{instruction}\n- 이미지 장면 묘사(캡션): {caption}"

    label = f"generate_copy/{'vision' if use_vision else 'blip'}"
    result = _chat_json([{"role": "user", "content": content}], label=label)
    copy_text = str(result.get("copy", "")).strip()
    if not copy_text:
        raise RuntimeError("문구 생성 응답에 copy 필드가 없습니다")
    return CopyResult(copy_text=copy_text)


# --- FR-23 SNS 문구 생성 ------------------------------------------------------
def generate_sns_copy(
    product: ProductInfo,
    style: StylePreset,
    purpose: AdPurpose,
) -> SnsCopyResult:
    """용도(purpose)별 캡션 + 해시태그 생성 (텍스트 API, 저비용)."""
    product_context = " — ".join(
        p.strip() for p in (product.name, product.description) if p and p.strip()
    ) or "(상품 정보 없음)"

    instruction = (
        "아래 상품의 홍보 문구를 한국어로 작성해줘.\n"
        f"- 상품: {product_context}\n"
        f"- 문구 톤: {_STYLE_TONE[style]}\n"
        f"- 용도: {_PURPOSE_GUIDE[purpose]}\n"
        "해시태그는 # 포함 문자열 배열로. "
        '반드시 JSON 으로만 응답: {"caption": "...", "hashtags": ["#...", "#..."]}'
    )

    result = _chat_json([{"role": "user", "content": instruction}], label="generate_sns_copy")
    caption = str(result.get("caption", "")).strip()
    if not caption:
        raise RuntimeError("SNS 문구 응답에 caption 필드가 없습니다")
    hashtags = [str(h).strip() for h in result.get("hashtags", []) if str(h).strip()]
    return SnsCopyResult(caption=caption, hashtags=hashtags)


# --- 포스터용 영문 라벨 (층2 오버레이 — editorial/retro 헤드라인) ---------------
def generate_english_labels(product: ProductInfo) -> tuple[str, str]:
    """상품 정보 → 포스터용 영문 라벨 (레퍼런스: 영문 대문자 메뉴명 헤드라인).

    반환: (name, phrase)
      - name  : 메뉴명, UPPERCASE 2~4 단어 (예: STRAWBERRY ADE)
      - phrase: 분위기 문구, UPPERCASE 3~6 단어 (에디토리얼 링용, 예: FRESH BERRY REFRESHMENT)
    """
    product_context = " — ".join(
        p.strip() for p in (product.name, product.description) if p and p.strip()
    ) or "(상품 정보 없음)"

    instruction = (
        "아래 상품의 광고 포스터용 영문 라벨 2개를 만들어줘.\n"
        f"- 상품: {product_context}\n"
        "규칙: name 은 상품의 실제 메뉴명을 영문 대문자 2~4단어로 (브랜드명·과장 금지), "
        "phrase 는 상품 분위기를 담은 영문 대문자 3~6단어. 둘 다 영문자·공백·&만 사용.\n"
        '반드시 JSON 으로만 응답: {"name": "STRAWBERRY ADE", "phrase": "FRESH BERRY REFRESHMENT"}'
    )
    result = _chat_json([{"role": "user", "content": instruction}], label="english_labels")
    # 키 표기 변형(NAME/Name 등) 방어
    lowered = {str(k).lower(): v for k, v in result.items()} if isinstance(result, dict) else {}
    name = str(lowered.get("name", "")).strip().upper()
    phrase = str(lowered.get("phrase", "")).strip().upper()
    if not name:
        raise RuntimeError(f"영문 라벨 응답에 name 이 없습니다 (원문: {result!r:.200})")
    return name, (phrase or name)


# --- 스타일 경로1: Vision 분석 -----------------------------------------------
def analyze_image_for_style(image_path: str) -> list[StyleCandidate]:
    """이미지 Vision 분석 → 스타일 후보 3개 반환 (style_service 경로1).

    ⚠️ Vision 호출 = 비용 발생. 개발 중 반복 호출 금지.
    """
    client = _get_client()

    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    media_type, _ = mimetypes.guess_type(image_path)
    if media_type is None or not media_type.startswith("image/"):
        media_type = "image/jpeg"

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
        model=GPT_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{image_b64}"},
                    },
                ],
            }
        ],
        response_format={"type": "json_object"},
    )
    _record_usage("analyze_image_for_style/vision", response)

    try:
        result = json.loads(response.choices[0].message.content)
        candidates = [
            StyleCandidate(preset=StylePreset(c["preset"]), reason=c["reason"])
            for c in result["candidates"]
        ]
    except (KeyError, ValueError, TypeError) as e:
        raise RuntimeError(f"Vision 응답 파싱 실패: {e}") from e

    if not candidates:
        raise RuntimeError("Vision 응답에 스타일 후보가 없습니다")
    return candidates
