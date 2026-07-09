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
    ⚠️ v2에서 Qwen3-VL로 대체 예정(deprecated) — 캐시 없거나 로드 실패 시 "" 폴백(비차단).
    """
    global _blip
    import torch
    from PIL import Image

    try:
        if _blip is None:
            from transformers import BlipForConditionalGeneration, BlipProcessor

            # CPU 고정: L4 에서 SDXL 2종+rembg 와 동시 상주 시 OOM (서비스 실측).
            # BLIP-base 는 CPU 추론 ~2s 로 지연 예산 내 — VRAM 1GB+ 절약이 이득.
            device = "cpu"
            processor = BlipProcessor.from_pretrained(
                "Salesforce/blip-image-captioning-base", local_files_only=True)
            model = BlipForConditionalGeneration.from_pretrained(
                "Salesforce/blip-image-captioning-base", local_files_only=True).to(device)
            _blip = (processor, model, device)

        processor, model, device = _blip
        img = Image.open(image_path).convert("RGB")
        inputs = processor(img, return_tensors="pt").to(device)
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=40)
        return processor.decode(out[0], skip_special_tokens=True)
    except Exception as e:  # 캐시 제거(v2 디스크 확보) 등 → 캡션 없이 진행
        logger.warning(f"BLIP 캡션 불가 → 빈 캡션 폴백: {e}")
        return ""


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


# --- D4b 4매체 페르소나 카피 (한 번 호출 JSON + 자기보고 환각 게이트) ------------
# UI 계약(2026-07-09): 마이페이지 SNS 공유 4버튼(IG/FB/X/Threads), 카피블록 = headline+body+hashtags.
_PLATFORM_PERSONA: dict[str, str] = {
    "instagram": "비주얼·감성 중심. 첫 줄 강한 후킹, 이모지 적절히, 해시태그 6~10개. body 2~3문장.",
    "facebook": "정보·친근형. 혜택과 CTA 명확, body 2~4문장으로 조금 길게, 해시태그 2~4개.",
    "x": "짧고 위트있게. 트렌디한 한두 문장, body 1~2문장, 해시태그 1~3개.",
    "threads": "대화체·솔직담백. 친구에게 말하듯 캐주얼, body 1~3문장, 해시태그 0~3개.",
}


def _platform_copy_instruction(product_context: str, style: StylePreset,
                               allowed: list[str], image_desc: str,
                               correction: Optional[list[str]]) -> str:
    persona = "\n".join(f"  - {k}: {v}" for k, v in _PLATFORM_PERSONA.items())
    honesty = ("정직성(중요): 이미지·상품에 실제로 있는 것만 표현해. 없는 재료·효능·수상·원산지·"
               "할인·최상급 표현을 지어내지 마.")
    if allowed:
        honesty += f" 재료·맛 관련 표현은 다음 실제 구성만 근거로 삼아: {', '.join(allowed)}."
    ground = f"\n- 이미지 실제 묘사(사실 근거): {image_desc}" if image_desc else ""
    fix = (f"\n- ⚠️ 직전 시도가 실제에 없는 재료를 지어냈어: {', '.join(correction)}. "
           "이 표현들을 빼고 다시 써." if correction else "")
    return (
        "아래 상품으로 4개 SNS 매체별 광고 카피를 한국어로 작성해줘.\n"
        f"- 상품: {product_context}\n"
        f"- 문구 톤: {_STYLE_TONE[style]}\n"
        f"- {honesty}{ground}{fix}\n"
        "- 모든 카피는 자연스러운 한국어로 써. 위 영문 재료명·이미지 묘사는 내용 참고용일 뿐이니 "
        "영어 단어를 그대로 노출하지 말고 한국어로 자연스럽게 옮겨(예: tapioca pearls→타피오카 펄).\n"
        "매체별 페르소나:\n" + persona + "\n"
        "각 매체는 headline(임팩트 있는 1줄), body(페르소나에 맞는 문장), "
        "hashtags(# 포함 문자열 배열)로.\n"
        "또한 카피에서 네가 언급한 구체적 재료를 claimed_ingredients(영문 소문자 배열)로 함께 "
        "보고해(환각 검증용, 언급 없으면 []).\n"
        '반드시 JSON 으로만 응답: {"instagram":{"headline":"","body":"","hashtags":["#..."]},'
        '"facebook":{"headline":"","body":"","hashtags":[]},"x":{...},"threads":{...},'
        '"claimed_ingredients":["..."]}'
    )


def generate_platform_copy(
    product: ProductInfo,
    style: StylePreset,
    core_ingredients: Optional[list[str]] = None,
    image_desc: str = "",
) -> dict[str, dict]:
    """4매체(instagram/facebook/x/threads) 카피를 한 번 호출로 생성 (D4b, FR-23 확장).

    반환: {platform: {"headline","body","hashtags":[...]}}  — UI 공유 4버튼에 직결.
    환각 차단: 모델이 자기보고한 claimed_ingredients 가 core_ingredients 부분집합인지 검증,
      초과(지어낸 재료)면 그 항목을 빼라고 1회 교정 재생성. image_desc(로컬 vlm_service.describe)
      를 주면 실제 이미지에 그라운딩해 환각을 더 줄인다.
    """
    product_context = " — ".join(
        p.strip() for p in (product.name, product.description) if p and p.strip()
    ) or "(상품 정보 없음)"
    allowed = [str(i).strip().lower() for i in (core_ingredients or []) if str(i).strip()]

    correction: Optional[list[str]] = None
    result: dict = {}
    for attempt in range(2):  # 최초 + 환각 시 교정 1회
        instruction = _platform_copy_instruction(
            product_context, style, allowed, image_desc, correction)
        result = _chat_json([{"role": "user", "content": instruction}], label="platform_copy")
        claimed = [str(c).strip().lower() for c in (result.get("claimed_ingredients") or [])]
        # allowed 가 있을 때만 게이트 발동(없으면 재료 검증 불가 → 통과)
        extra = [c for c in claimed
                 if c and allowed and not any(c in a or a in c for a in allowed)]
        if not extra:
            break
        logger.warning("platform_copy 환각 의심 재료 %s → 교정 재생성(%d)", extra, attempt)
        correction = extra

    out: dict[str, dict] = {}
    for plat in _PLATFORM_PERSONA:
        blk = result.get(plat) or {}
        out[plat] = {
            "headline": str(blk.get("headline", "")).strip(),
            "body": str(blk.get("body", "")).strip(),
            "hashtags": [str(h).strip() for h in (blk.get("hashtags") or []) if str(h).strip()],
        }
    return out


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


@dataclass
class MenuAnalysis:
    """상품명 → 라우팅 정보 (A 음식 / C 사물 공통).

    domain: 'food'(음식) | 'object'(하드굿즈 사물). 최상위 분기.
    display_name: 입력 원문(포스터 헤드라인용, 언어 보존).
    subject_en: 이미지 모델용 영어 설명(CLIP 한글 오염 방지 — 항상 영어).
    category: 음식이면 fried|soup|bakery|grill|beef|pork|default,
              사물이면 material 값을 반영(matte|reflective|transparent|default).
    core_ingredients: (음식) 진짜 구성 재료 — 생성 허용 경계(외래 데코와 구분).
    texture_hero: (음식) 텍스처가 상품인가 → True 면 보존 그레이드.
    material: (사물) matte|reflective|transparent|default — 클린 보정 강도.
    lang: ko|en (원문 언어).
    """
    domain: str
    display_name: str
    subject_en: str
    category: str
    core_ingredients: list[str]
    texture_hero: bool
    material: str
    food_mode: str    # (food) 'dish'=음식점 접시(A, in-place) | 'cafe'=카페 이산제품(B, 누끼+씬)
    lang: str

    # 하위호환: 기존 코드가 쓰던 food_en 별칭
    @property
    def food_en(self) -> str:
        return self.subject_en


_MENU_CATEGORIES = "fried, soup, bakery, grill, beef, pork, default"
_MATERIALS = ("matte", "reflective", "transparent", "default")


def analyze_menu(name: str) -> MenuAnalysis:
    """상품명(한/영) → 라우팅 정보. 사용자는 이름만 입력, 나머지는 GPT 매핑.

    최상위로 domain(food/object) 을 판정 — 음식이면 category·재료·texture_hero,
    사물이면 material 을 뽑는다. display_name 은 원문 보존(헤드라인용).
    """
    display_name = (name or "").strip()
    instruction = (
        "너는 소상공인 광고 파이프라인의 상품 분석기야. 아래 '상품명'을 분석해 JSON 으로만 응답해.\n"
        f"- 상품명: {display_name or '(빈 입력)'}\n"
        "규칙:\n"
        "1. domain: 먹는 음식이면 'food', 사물·제품(전자기기·주방용품·뷰티툴·잡화 등)이면 'object'.\n"
        f"2. category(food 일 때만 의미): [{_MENU_CATEGORIES}] 중 하나. "
        "생소고기=beef, 생돼지고기=pork, 국·탕·찌개=soup, 튀김=fried, 빵·디저트=bakery, "
        "구이=grill, 그 외=default. object 면 'default'.\n"
        "3. subject_en: 이미지용 영어 설명(2~6단어, 항상 영어. 한글이면 번역). "
        "브랜드명·과장 금지, 실제 상품만.\n"
        "4. core_ingredients: (food) 원래 들어가는 핵심 재료 영어 배열(최대 4개). object 면 [].\n"
        "5. texture_hero: (food) 미세 텍스처가 상품의 핵심이면 true "
        "(마블링 생소고기·눈꽃치즈 파우더·회 등). 그 외 false. object 면 false.\n"
        "6. material: (object) 'reflective'(금속·거울·유광), 'transparent'(유리·투명), "
        "'matte'(무광 플라스틱·세라믹·천), 애매하면 'default'. food 면 'default'.\n"
        "7. food_mode: (food) 그릇·용기에 담겨 나오는 음식점 요리(국·탕·밥·구이·정식·치킨 등)="
        "'dish', 카페의 이산 제품(음료·커피·케이크·베이커리·디저트·마들렌 등)='cafe'. object 면 'dish'.\n"
        "8. lang: 상품명이 한글이면 'ko', 영어면 'en'.\n"
        '반드시 JSON: {"domain":"object","category":"default","subject_en":"wireless computer mouse",'
        '"core_ingredients":[],"texture_hero":false,"material":"reflective","food_mode":"dish","lang":"ko"}'
    )
    result = _chat_json([{"role": "user", "content": instruction}], label="analyze_menu")
    low = {str(k).lower(): v for k, v in result.items()} if isinstance(result, dict) else {}
    domain = "object" if str(low.get("domain", "food")).lower().startswith("obj") else "food"
    category = str(low.get("category", "default")).strip().lower()
    if category not in ("fried", "soup", "bakery", "grill", "beef", "pork", "default"):
        category = "default"
    material = str(low.get("material", "default")).strip().lower()
    if material not in _MATERIALS:
        material = "default"
    ings = low.get("core_ingredients") or []
    if not isinstance(ings, list):
        ings = []
    return MenuAnalysis(
        domain=domain,
        display_name=display_name,
        subject_en=str(low.get("subject_en") or low.get("food_en", "")).strip() or "product",
        category=category,
        core_ingredients=[str(x).strip() for x in ings][:4] if domain == "food" else [],
        texture_hero=bool(low.get("texture_hero", False)) and domain == "food",
        material=material,
        food_mode="cafe" if str(low.get("food_mode", "dish")).lower() == "cafe" else "dish",
        lang="en" if str(low.get("lang", "")).lower().startswith("en") else "ko",
    )


def detect_material(image_path: str) -> str:
    """사물 사진 → 표면 재질 판정 (Vision). ⚠️ 이름만으론 유광/무광/투명 구분 불가 →
    실제 사진을 보고 판정. 반환: matte|reflective|transparent|default. (Vision 비용 1회)"""
    client = _get_client()
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")
    media_type, _ = mimetypes.guess_type(image_path)
    if media_type is None or not media_type.startswith("image/"):
        media_type = "image/jpeg"
    prompt = (
        "이 사진 속 주된 사물의 표면 재질을 판정해 JSON 으로만 응답해.\n"
        "- reflective: 금속·거울·유광 플라스틱 등 반사 강한 표면\n"
        "- transparent: 유리·투명/반투명 재질\n"
        "- matte: 무광 플라스틱·세라믹·천·나무 등\n"
        "- default: 애매하거나 혼합\n"
        '반드시 JSON: {"material": "reflective"}'
    )
    response = client.chat.completions.create(
        model=GPT_MODEL,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_b64}"}},
        ]}],
        response_format={"type": "json_object"},
    )
    _record_usage("detect_material", response)
    try:
        result = json.loads(response.choices[0].message.content)
    except Exception:
        return "default"
    m = str(result.get("material", "default")).strip().lower()
    return m if m in _MATERIALS else "default"


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
