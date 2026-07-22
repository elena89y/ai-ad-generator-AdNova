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
from functools import lru_cache
from dataclasses import dataclass, field
from typing import Optional

from ..schemas.ads import AdPurpose, ProductInfo, StyleCandidate, StylePreset
from . import prompt_registry as _prompts

logger = logging.getLogger(__name__)

# 프롬프트 문구 원장(T1 소프트코딩): backend/app/prompts/gpt_service.yaml
# 문구 수정은 코드가 아니라 YAML 에서 — 바이트 동일성 게이트(test_prompt_snapshots) 참조.
_NS = "gpt_service"


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
    """OpenAI 클라이언트 생성. key 는 env 에서만.

    ⚠️ langfuse.openai 의 드롭인 대체 — import만 바꾸면 모든 chat.completions.create
    호출(프롬프트·응답·지연시간·토큰·비용)이 자동으로 Langfuse 에 트레이싱된다.
    LANGFUSE_PUBLIC_KEY 미설정이면(observability.init_langfuse 참고) 트레이싱 없이
    평소와 동일하게 OpenAI 호출만 수행 — 이 함수 동작은 변하지 않는다.
    """
    try:
        from langfuse.openai import OpenAI
    except Exception:  # noqa: BLE001
        from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 미설정 (env 로드 필요)")
    return OpenAI(api_key=api_key)


# --- 스타일 → 문구 톤 매핑 (v1 잠정치, 실험 후 확정) — 문구는 YAML 원장 -------
_STYLE_TONE: dict[StylePreset, str] = {
    StylePreset(k): v for k, v in _prompts.get(_NS, "style_tone").items()}

_PURPOSE_GUIDE: dict[AdPurpose, str] = {
    AdPurpose(k): v for k, v in _prompts.get(_NS, "purpose_guide").items()}


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
    """JSON 강제 chat 호출 공통 래퍼. 토큰 사용량 기록 포함.

    호출 라벨은 usage 로그와 상위 observe span 에서 관리한다. ``name`` 은 OpenAI
    Chat Completions 표준 인자가 아니며, Langfuse 래퍼가 공식 클라이언트로 전달하면
    요청 전에 TypeError 가 발생하므로 API 호출 인자로 넘기지 않는다.
    """
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
        _prompts.fmt(_NS, "generate_copy.retry_note", feedback=feedback)
        if feedback else ""
    )
    instruction = _prompts.fmt(
        _NS, "generate_copy.instruction",
        product_context=product_context, style_tone=_STYLE_TONE[style],
        retry_note=retry_note)

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
        content = _prompts.fmt(_NS, "generate_copy.caption_line",
                               instruction=instruction, caption=caption)

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

    instruction = _prompts.fmt(
        _NS, "generate_sns_copy.instruction",
        product_context=product_context, style_tone=_STYLE_TONE[style],
        purpose_guide=_PURPOSE_GUIDE[purpose])

    result = _chat_json([{"role": "user", "content": instruction}], label="generate_sns_copy")
    caption = str(result.get("caption", "")).strip()
    if not caption:
        raise RuntimeError("SNS 문구 응답에 caption 필드가 없습니다")
    hashtags = [str(h).strip() for h in result.get("hashtags", []) if str(h).strip()]
    return SnsCopyResult(caption=caption, hashtags=hashtags)


# --- D4b 4매체 페르소나 카피 (한 번 호출 JSON + 자기보고 환각 게이트) ------------
# UI 계약(2026-07-09): 마이페이지 SNS 공유 4버튼(IG/FB/X/Threads), 카피블록 = headline+body+hashtags.
_PLATFORM_PERSONA: dict[str, str] = dict(_prompts.get(_NS, "platform_persona"))


def _platform_copy_instruction(product_context: str, style: StylePreset,
                               allowed: list[str], image_desc: str,
                               correction: Optional[list[str]]) -> str:
    persona = "\n".join(f"  - {k}: {v}" for k, v in _PLATFORM_PERSONA.items())
    honesty = _prompts.get(_NS, "platform_copy.honesty_base")
    if allowed:
        honesty += _prompts.fmt(_NS, "platform_copy.honesty_allowed",
                                allowed=", ".join(allowed))
    ground = (_prompts.fmt(_NS, "platform_copy.ground", image_desc=image_desc)
              if image_desc else "")
    fix = (_prompts.fmt(_NS, "platform_copy.fix", extra=", ".join(correction))
           if correction else "")
    return _prompts.fmt(
        _NS, "platform_copy.instruction",
        product_context=product_context, style_tone=_STYLE_TONE[style],
        honesty=honesty, ground=ground, fix=fix, persona=persona)


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


# --- v6-1 F1: 상세페이지 섹션별 카피 (한 번 호출 JSON + 환각 게이트) ------------
@dataclass
class DetailCopy:
    """상세페이지 섹션별 전용 카피 (DIRECTION_v6-1 F1 P1).

    같은 headline 이 3개 섹션에 복붙되던 문제(D1)와 하드코딩 섹션 문구(D2),
    스토리 본문·혜택 불릿 부재(D3)를 한 번 호출로 해소한다.
    """
    intro_headline: str          # 히어로 오버레이 (기존 headline 과 다른 후킹)
    story_title: str             # PRODUCT STORY 제목
    story_body: str              # PRODUCT STORY 본문 2~3문장
    benefit_bullets: list[str]   # 혜택/특징 불릿 최대 3개 (없으면 섹션 생략)
    top_view_label: str          # 01 탑뷰 라벨
    closeup_caption: str         # 02 클로즈업 캡션
    profile_title: str           # 03 스플릿 제목 (최대 2줄, \n 구분)
    profile_caption: str         # 03 스플릿 보조 문장
    lifestyle_line: str          # 04 MOMENT 한 줄
    cta_title: str
    cta_label: str


def _detail_copy_instruction(product_context: str, style_tone: str, headline: str,
                             subcopy: str, allowed: list[str], image_desc: str,
                             correction: Optional[list[str]]) -> str:
    """상세 카피 프롬프트 조립 — 정직성·그라운딩·교정 조각은 platform_copy(D4b) 원장 재사용."""
    honesty = _prompts.get(_NS, "platform_copy.honesty_base")
    if allowed:
        honesty += _prompts.fmt(_NS, "platform_copy.honesty_allowed",
                                allowed=", ".join(allowed))
    ground = (_prompts.fmt(_NS, "platform_copy.ground", image_desc=image_desc)
              if image_desc else "")
    fix = (_prompts.fmt(_NS, "platform_copy.fix", extra=", ".join(correction))
           if correction else "")
    return _prompts.fmt(
        _NS, "detail_copy.instruction",
        product_context=product_context, style_tone=style_tone,
        headline=headline or "(없음)", subcopy=subcopy or "(없음)",
        honesty=honesty, ground=ground, fix=fix)


def _detail_copy_tone(style_key: str) -> str:
    """스타일 키 → 문구 톤. 튜닝된 style_tone 원장 우선, 없는 키(realism 등)는
    styles/specs.yaml 의 mood 로 폴백 — 스타일이 다르면 상세 카피 톤도 달라진다."""
    tone = dict(_prompts.get(_NS, "style_tone")).get((style_key or "").strip())
    if tone:
        return tone
    from .style_specs import get_spec
    return get_spec(style_key or "editorial").mood


def generate_detail_copy(product_name: str, subject_en: str, domain: str,
                         headline: str, subcopy: str = "",
                         core_ingredients: Optional[list[str]] = None,
                         style_key: str = "", image_desc: str = "") -> DetailCopy:
    """상세페이지 섹션 카피 전체를 한 번 호출 JSON 으로 생성한다 (v6-1 F1 P1).

    환각 차단은 generate_platform_copy(D4b)와 동일 패턴 — 자기보고
    claimed_ingredients ⊂ core_ingredients 검증, 초과 시 1회 교정 재생성.
    본문이 길어질수록 허위 서술 위험이 커지는 포맷이라 게이트 최우선 적용 대상.
    core_ingredients 가 비면 재료 검증 불가 → 게이트 통과(관대, D4b 동일).
    실패는 예외로 던진다 — 호출부(commercial_copy.detail_copy_for)가 기존 문구로 폴백.
    """
    product_context = " — ".join(
        p.strip() for p in (product_name, subject_en) if p and p.strip()
    ) or "(상품 정보 없음)"
    allowed = [str(i).strip().lower() for i in (core_ingredients or []) if str(i).strip()]
    style_tone = _detail_copy_tone(style_key)

    correction: Optional[list[str]] = None
    result: dict = {}
    for attempt in range(2):  # 최초 + 환각 시 교정 1회 (D4b 패턴)
        instruction = _detail_copy_instruction(
            product_context, style_tone, headline, subcopy, allowed, image_desc, correction)
        result = _chat_json([{"role": "user", "content": instruction}], label="detail_copy")
        claimed = [str(c).strip().lower() for c in (result.get("claimed_ingredients") or [])]
        extra = [c for c in claimed
                 if c and allowed and not any(c in a or a in c for a in allowed)]
        if not extra:
            break
        logger.warning("detail_copy 환각 의심 재료 %s → 교정 재생성(%d)", extra, attempt)
        correction = extra

    lowered = {str(k).lower(): v for k, v in result.items()} if isinstance(result, dict) else {}

    def _s(key: str) -> str:
        return str(lowered.get(key, "")).strip()

    bullets = [str(b).strip() for b in (lowered.get("benefit_bullets") or [])
               if str(b).strip()][:3]
    copy = DetailCopy(
        intro_headline=_s("intro_headline"), story_title=_s("story_title"),
        story_body=_s("story_body"), benefit_bullets=bullets,
        top_view_label=_s("top_view_label"), closeup_caption=_s("closeup_caption"),
        profile_title=_s("profile_title"), profile_caption=_s("profile_caption"),
        lifestyle_line=_s("lifestyle_line"), cta_title=_s("cta_title"),
        cta_label=_s("cta_label"))
    required = (copy.intro_headline, copy.story_title, copy.story_body,
                copy.top_view_label, copy.closeup_caption, copy.profile_title,
                copy.lifestyle_line, copy.cta_title, copy.cta_label)
    if not all(required):
        raise RuntimeError(f"상세 카피 응답 필드 누락 (원문: {result!r:.200})")
    return copy


# --- 품질 저지 (GPT Vision — 골든셋 평가·캘리브레이션용, 실시간 아님) -----------
# 역할분리: 실시간 결함검사는 로컬 vlm_service.inspect(빠르고 무료), 정밀 미세 순위는
#   여기 GPT Vision(신뢰·저비용, 평가 호출량 적음). 2B 의 위치편향/점수압축 한계 극복(P2-2 재설계).
_JUDGE_SYS = _prompts.get(_NS, "judge_sys")


def _vision_part(image_path: str) -> dict:
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    mt, _ = mimetypes.guess_type(image_path)
    if not mt or not mt.startswith("image/"):
        mt = "image/png"
    return {"type": "image_url", "image_url": {"url": f"data:{mt};base64,{b64}"}}


def judge_ad(image_path: str, instruction: str = "", ref_path: Optional[str] = None) -> dict:
    """GPT Vision 광고 품질 저지 — 루브릭 1~10 채점. 골든셋 평가/캘리브레이션 전용.

    ref_path(원본)+instruction 주면 정체성 보존·명령 이행까지 평가.
    반환: {appetizing, realism, artifact_free, composition, adherence, overall, reason}.
    """
    ident = (_prompts.fmt(_NS, "judge_ad.ident", instruction=instruction)
             if ref_path and instruction else "")
    rubric = _prompts.fmt(_NS, "judge_ad.rubric", ident=ident)
    content: list = [{"type": "text", "text": rubric}]
    if ref_path and instruction:
        content.append(_vision_part(ref_path))
    content.append(_vision_part(image_path))
    r = _chat_json([{"role": "system", "content": _JUDGE_SYS},
                    {"role": "user", "content": content}], label="judge_ad/vision")
    keys = ["appetizing", "realism", "artifact_free", "composition", "adherence", "overall"]
    out = {k: r.get(k) for k in keys}
    out["reason"] = str(r.get("reason", ""))[:200]
    return out


def compare_ads(image_a: str, image_b: str, ref_path: Optional[str] = None,
                debias: bool = True) -> dict:
    """두 광고 중 더 나은 쪽 — GPT Vision. debias=True 면 순서 뒤집어 2회, 일치해야 확정(위치편향 제거).

    반환: {winner: 'A'|'B'|'tie', reason}. A=image_a, B=image_b.
    """
    q = _prompts.get(_NS, "compare_ads.question")
    lead = (_prompts.get(_NS, "compare_ads.lead_ref") if ref_path else "")

    def _one(x: str, y: str) -> tuple:
        content: list = [{"type": "text", "text": lead + q}]
        if ref_path:
            content.append(_vision_part(ref_path))
        content += [_vision_part(x), _vision_part(y)]
        r = _chat_json([{"role": "system", "content": _JUDGE_SYS},
                        {"role": "user", "content": content}], label="compare_ads/vision")
        w = str(r.get("winner", "")).lower()
        return ("x" if "first" in w else "y" if "second" in w else "tie"), str(r.get("reason", ""))[:160]

    w1, why1 = _one(image_a, image_b)          # x=A, y=B
    if not debias:
        return {"winner": "A" if w1 == "x" else "B" if w1 == "y" else "tie", "reason": why1}
    w2, _why2 = _one(image_b, image_a)          # x=B, y=A → x 는 image_b
    a_wins = (w1 == "x") and (w2 == "y")
    b_wins = (w1 == "y") and (w2 == "x")
    winner = "A" if a_wins else "B" if b_wins else "tie"
    return {"winner": winner, "reason": why1, "debias_consistent": winner != "tie"}


def judge_ad_calibrated(image_path: str, style_key: str,
                        ref_image_paths: list[str], extra: str = "") -> dict:
    """레퍼런스-캘리브레이션 저지 — 목표 미학 예시(ref) 대비 후보를 채점.

    P2-2 결론: 미세 A/B 는 오라클 없음(GPT-4V 도) → "무엇이 좋은가"를 레퍼런스로 정의해야 판단이 의미.
    ref_image_paths 앞 2~3장을 목표 미학 예시로, 마지막에 후보를 붙여 GPT Vision 이 목표 대비 채점.
    반환: {style_match, execution, identity, overall, improve}.
    """
    from .style_specs import get_spec
    sp = get_spec(style_key)
    refs = ref_image_paths[:3]
    intro = _prompts.fmt(
        _NS, "judge_calibrated.intro", n_refs=len(refs), style_key=style_key,
        mood=sp.mood, extra_part=(extra + " " if extra else ""))
    content: list = [{"type": "text", "text": intro}]
    for p in refs:
        content.append(_vision_part(p))
    content.append(_vision_part(image_path))
    r = _chat_json([{"role": "system", "content": _JUDGE_SYS},
                    {"role": "user", "content": content}], label="judge_calibrated")
    out = {k: r.get(k) for k in ["style_match", "execution", "identity", "overall"]}
    out["improve"] = str(r.get("improve", ""))[:200]
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

    # A(구조화 출력): LangChain with_structured_output 으로 키 변형(트랩 #6) 원천 차단.
    #   langchain 미설치/키 없음/파싱 실패 → 아래 기존 raw JSON 경로로 폴백(무해).
    try:
        from . import judge_service
        return judge_service.structured_labels(product_context)
    except Exception as e:  # noqa: BLE001
        logger.info(f"구조화 라벨 폴백 → raw JSON 경로: {e}")

    instruction = _prompts.fmt(_NS, "english_labels.instruction",
                               product_context=product_context)
    result = _chat_json([{"role": "user", "content": instruction}], label="english_labels")
    # 키 표기 변형(NAME/Name 등) 방어
    lowered = {str(k).lower(): v for k, v in result.items()} if isinstance(result, dict) else {}
    name = str(lowered.get("name", "")).strip().upper()
    phrase = str(lowered.get("phrase", "")).strip().upper()
    if not name:
        raise RuntimeError(f"영문 라벨 응답에 name 이 없습니다 (원문: {result!r:.200})")
    return name, (phrase or name)


@dataclass
class SectionLabels:
    """v5 카드뉴스/상세페이지 섹션 라벨 (ROUTING-002)."""
    top_view_label: str
    detail_title: str
    cta_title: str
    cta_label: str


def generate_section_labels(product_name: str, subject_en: str, domain: str,
                            headline: str) -> SectionLabels:
    """카드뉴스/상세페이지 섹션·CTA 라벨을 상품에 맞게 생성한다.

    도메인 고정 문구("한 잔의 디테일" 등)가 모든 상품에 똑같이 나가던 문제(ROUTING-001)의
    후속 — 실패하면 예외를 그대로 던진다. 호출부(commercial_copy.py)가 고정 문구로 폴백한다.
    cta_title/cta_label은 2026-07-20 추가(CTA-001) — "지금 만나보세요"/"자세히 보기"가
    section 라벨과 별개로 여전히 모듈 상수로 하드코딩돼 있던 걸 같은 호출에 얹어 해결.
    """
    instruction = _prompts.fmt(
        _NS, "section_labels.instruction",
        product_name=product_name or subject_en, subject_en=subject_en,
        domain=domain, headline=headline)
    result = _chat_json([{"role": "user", "content": instruction}], label="section_labels")
    lowered = {str(k).lower(): v for k, v in result.items()} if isinstance(result, dict) else {}
    top_view_label = str(lowered.get("top_view_label", "")).strip()
    detail_title = str(lowered.get("detail_title", "")).strip()
    cta_title = str(lowered.get("cta_title", "")).strip()
    cta_label = str(lowered.get("cta_label", "")).strip()
    if not top_view_label or not detail_title or not cta_title or not cta_label:
        raise RuntimeError(f"섹션 라벨 응답이 비어 있습니다 (원문: {result!r:.200})")
    return SectionLabels(top_view_label=top_view_label, detail_title=detail_title,
                         cta_title=cta_title, cta_label=cta_label)


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


@dataclass
class PhotoAnalysis:
    """사진+상품명 통합 분석. 입력 게이트·라우팅·장면 연출이 Vision 1회 결과를 공유한다."""

    match: bool
    seen: str
    domain: str
    display_name: str
    subject_en: str
    category: str
    core_ingredients: list[str]
    texture_hero: bool
    material: str
    food_mode: str
    lang: str
    container_kind: str
    container_color: str
    container_opacity: str
    temperature: str
    view_angle: str
    visible_text: str
    # 제품 이해(2026-07-17): 파트별 보존 등급 — 미적 재연출과 정직성을 양립시킨다.
    #   identity_parts = 상품 정체성이라 반드시 보존(상품 본체·로고·라벨). 라떼면 coffee·latte art.
    #   flexible_parts = 상품이 아니라 담는 용기·그릇 → 무드에 맞게 색·재질 리컬러 허용. 라떼면 cup·saucer.
    #   하위호환: default 빈 리스트라 기존 호출부·캐시 무해. 비면 "전체 보존"으로 안전 폴백.
    identity_parts: list[str] = field(default_factory=list)
    flexible_parts: list[str] = field(default_factory=list)

    @property
    def food_en(self) -> str:
        """MenuAnalysis의 기존 별칭과 동일한 하위호환 계약."""
        return self.subject_en

    def __post_init__(self) -> None:
        """캐시를 포함해 프롬프트로 흐르는 필드의 enum·영문 계약을 검증한다."""
        if not isinstance(self.match, bool) or not isinstance(self.texture_hero, bool):
            raise ValueError("PhotoAnalysis boolean 필드 형식 오류")
        enum_fields = {
            "domain": (self.domain, ("food", "object")),
            "category": (self.category, tuple(_MENU_CATEGORIES.split(", "))),
            "material": (self.material, _MATERIALS),
            "food_mode": (self.food_mode, ("dish", "cafe")),
            "lang": (self.lang, ("ko", "en")),
            "container_opacity": (self.container_opacity, _CONTAINER_OPACITIES),
            "temperature": (self.temperature, _TEMPERATURES),
            "view_angle": (self.view_angle, _VIEW_ANGLES),
        }
        for field, (value, allowed) in enum_fields.items():
            if value not in allowed:
                raise ValueError(f"잘못된 {field}: {value!r}")
        if not isinstance(self.core_ingredients, list):
            raise ValueError("core_ingredients가 배열이 아님")
        _require_ascii_prompt_text(self.subject_en, "subject_en")
        _require_ascii_prompt_text(self.container_kind, "container_kind")
        _require_ascii_prompt_text(self.container_color, "container_color")
        for ingredient in self.core_ingredients:
            _require_ascii_prompt_text(ingredient, "core_ingredients")
        for part in self.identity_parts:
            _require_ascii_prompt_text(part, "identity_parts")
        for part in self.flexible_parts:
            _require_ascii_prompt_text(part, "flexible_parts")


_MENU_CATEGORIES = "fried, soup, bakery, grill, beef, pork, default"
_MATERIALS = ("matte", "reflective", "transparent", "default")
_CONTAINER_OPACITIES = ("opaque", "transparent", "translucent")
_TEMPERATURES = ("hot", "iced", "ambient")
_VIEW_ANGLES = ("eye", "high", "top")


def _require_ascii_prompt_text(value, field: str) -> str:  # noqa: ANN001
    """이미지 프롬프트 후보값은 비어 있지 않은 ASCII 문자열만 허용한다."""
    text = str(value).strip()
    if not text or not text.isascii():
        raise ValueError(f"영문 프롬프트 계약 위반 {field}: {value!r}")
    return text


def _json_bool(value, field: str) -> bool:  # noqa: ANN001
    """JSON boolean과 문자열 true/false만 허용한다. 애매한 값은 통합 분석 전체를 폴백한다."""
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in ("true", "false"):
        return normalized == "true"
    raise ValueError(f"잘못된 {field}: {value!r}")


def build_cake_layers(name: str, subject_en: str = "", image_desc: str = "") -> dict:
    """케이크 이름(+선택 이미지 묘사) → '호텔 파티쉐' 레시피 검증 후 영문 단면 레이어.

    cross_section 스타일의 정직성 게이트: 통 케이크 단면을 생성할 때 '그 케이크에 실재하는'
    레이어만 쓰도록 GPT가 실제 조리 가능한 레시피로 검증(레퍼런스 워크플로 09_기타/케익클로즈업).
    반환: {"layers":[Bottom→Top 물성 묘사...], "top":"상단 데코 묘사", "plausible":bool}.
    실패/비케이크면 layers 빈 리스트 → 호출부가 일반 매크로로 폴백.
    """
    display = (name or "").strip()
    hint = (_prompts.fmt(_NS, "cake_recipe.hint", image_desc=image_desc)
            if image_desc else "")
    instruction = _prompts.fmt(
        _NS, "cake_recipe.instruction",
        display=display or "(빈 입력)", subject_en=subject_en or "cake", hint=hint)
    try:
        r = _chat_json([{"role": "user", "content": instruction}], label="cake_recipe")
        layers = [str(x) for x in (r.get("layers") or [])] if r.get("plausible") else []
        return {"layers": layers, "top": str(r.get("top") or ""), "plausible": bool(r.get("plausible"))}
    except Exception:
        return {"layers": [], "top": "", "plausible": False}


@lru_cache(maxsize=256)
def analyze_menu(name: str) -> MenuAnalysis:
    """상품명(한/영) → 라우팅 정보. 사용자는 이름만 입력, 나머지는 GPT 매핑.

    최상위로 domain(food/object) 을 판정 — 음식이면 category·재료·texture_hero,
    사물이면 material 을 뽑는다. display_name 은 원문 보존(헤드라인용).
    """
    # 이름 기반 분석은 결정적이며 같은 생성에서 라우팅·플랫폼 카피가 중복 호출한다.
    # 예외는 lru_cache에 저장되지 않으므로 일시적인 API 실패도 고착되지 않는다.
    display_name = (name or "").strip()
    instruction = _prompts.fmt(
        _NS, "analyze_menu.instruction",
        display_name=display_name or "(빈 입력)", menu_categories=_MENU_CATEGORIES)
    result = _chat_json([{"role": "user", "content": instruction}], label="analyze_menu")
    return menu_from_result(result, display_name)


def build_menu_instruction(name: str) -> str:
    """analyze_menu 라우팅 프롬프트 조립(원장 YAML). VLM-001 로컬 라우팅이 재사용."""
    display_name = (name or "").strip()
    return _prompts.fmt(_NS, "analyze_menu.instruction",
                        display_name=display_name or "(빈 입력)", menu_categories=_MENU_CATEGORIES)


def menu_from_result(result: dict, display_name: str) -> MenuAnalysis:
    """라우팅 JSON → MenuAnalysis (GPT·로컬 VLM 공용 파서, VLM-001). 화이트리스트 클램프로
    로컬 2B의 자유형 출력도 안전 범위로 강제한다."""
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


def analyze_photo(image_path: str, name: str) -> Optional[PhotoAnalysis]:
    """사진+상품명 → 게이트·라우팅·연출 통합 분석. 실패하면 기존 경로용 ``None`` 반환.

    MenuAnalysis의 모든 필드와 사진 근거 필드를 한 번의 Vision 호출로 받는다. 응답 키는
    소문자 snake_case로 고정하며 core_ingredients와 이미지 프롬프트용 값은 영어를 강제한다.
    """
    display_name = (name or "").strip()
    instruction = _prompts.fmt(
        _NS, "analyze_photo.instruction",
        display_name=display_name or "(빈 입력)", menu_categories=_MENU_CATEGORIES)
    try:
        content = [
            {"type": "text", "text": instruction},
            _vision_part(image_path),
        ]
        result = _chat_json([{"role": "user", "content": content}], label="analyze_photo")
        if not isinstance(result, dict):
            raise TypeError("analyze_photo 응답이 JSON 객체가 아님")

        domain = "object" if str(result["domain"]).strip().lower() == "object" else "food"
        category = str(result["category"]).strip().lower()
        if category not in ("fried", "soup", "bakery", "grill", "beef", "pork", "default"):
            category = "default"
        material = str(result["material"]).strip().lower()
        if material not in _MATERIALS:
            material = "default"
        ingredients = result["core_ingredients"]
        if not isinstance(ingredients, list):
            raise TypeError("core_ingredients가 배열이 아님")
        opacity = str(result["container_opacity"]).strip().lower()
        temperature = str(result["temperature"]).strip().lower()
        view_angle = str(result["view_angle"]).strip().lower()
        if opacity not in _CONTAINER_OPACITIES:
            raise ValueError(f"잘못된 container_opacity: {opacity}")
        if temperature not in _TEMPERATURES:
            raise ValueError(f"잘못된 temperature: {temperature}")
        if view_angle not in _VIEW_ANGLES:
            raise ValueError(f"잘못된 view_angle: {view_angle}")

        subject_en = _require_ascii_prompt_text(result["subject_en"], "subject_en")
        container_kind = _require_ascii_prompt_text(
            result["container_kind"], "container_kind",
        ).lower()
        container_color = _require_ascii_prompt_text(
            result["container_color"], "container_color",
        ).lower()
        normalized_ingredients = [
            _require_ascii_prompt_text(item, "core_ingredients").lower()
            for item in ingredients
            if str(item).strip()
        ][:4]

        def _part_list(key: str) -> list[str]:
            """파트 등급은 개선 정보라 관대하게 — 비ASCII·비배열은 조용히 버리고 빈 리스트 폴백."""
            raw = result.get(key)
            if not isinstance(raw, list):
                return []
            parts: list[str] = []
            for item in raw:
                text = str(item).strip()
                if text and text.isascii():
                    parts.append(text.lower())
            return parts[:5]

        flexible = _part_list("flexible_parts") if domain == "food" else []
        # 투명/반투명 용기는 리컬러 시 유리를 색칠해 붕괴 위험 → 용기 본체만 flexible 제외.
        #   받침류(saucer·coaster·plate)는 불투명이라 유지(홍차 콜드런 발견, 2026-07-19).
        if opacity != "opaque":
            _vessel_body = ("cup", "glass", "mug", "tumbler", "bottle", "jar", "container", "bowl")
            flexible = [p for p in flexible if not any(w in p for w in _vessel_body)]

        return PhotoAnalysis(
            match=_json_bool(result["match"], "match"),
            seen=str(result.get("seen", ""))[:80],
            domain=domain,
            display_name=display_name,
            subject_en=subject_en,
            category=category,
            core_ingredients=(
                normalized_ingredients
                if domain == "food" else []
            ),
            texture_hero=_json_bool(result["texture_hero"], "texture_hero") and domain == "food",
            material=material,
            food_mode="cafe" if str(result["food_mode"]).strip().lower() == "cafe" else "dish",
            lang="en" if str(result["lang"]).strip().lower() == "en" else "ko",
            container_kind=container_kind,
            container_color=container_color,
            container_opacity=opacity,
            temperature=temperature,
            view_angle=view_angle,
            visible_text=str(result.get("visible_text", ""))[:200],
            # 사물(로고 SKU)은 flexible을 무시하고 전체 보존 — object 정직성 경계(형태·색 왜곡 금지).
            identity_parts=_part_list("identity_parts"),
            flexible_parts=flexible,
        )
    except Exception as exc:  # 기존 verify_photo_subject+analyze_menu 경로로 폴백
        logger.warning("analyze_photo 실패 → 기존 분석 경로 폴백: %s", exc)
        return None


def verify_photo_subject(image_path: str, name: str) -> dict:
    """입력 게이트: 사진의 주 피사체가 상품명과 같은 종류인지 Vision 으로 의미 판단 (OCR 아님).

    콜드런 배치(n=50) 실측: 무관 사진(다람쥐+팬케이크, 경주트랙+와플)이 들어오면 이름 기반으로
    없는 제품을 날조 → 허위광고 최고 위험. 생성 전에 차단한다.
    **관대한 게이트**: 유저 사진은 지저분하므로(흐림·복수 피사체·애매한 각도) 명백한 불일치만
    거부, 애매하면 통과. 반환: {"match": bool, "seen": "사진 내용 한 줄"}. 실패 시 통과(무해).
    (Vision 비용 1회. 추후 OpenAI 생성모델 전환 시 사진→상품명 자동추출로 대체 예정)
    """
    content = [{"type": "text", "text": _prompts.fmt(
        _NS, "verify_photo_subject.instruction", name=(name or "").strip(),
    )}, _vision_part(image_path)]
    try:
        r = _chat_json([{"role": "user", "content": content}], label="verify_photo_subject")
        return {"match": bool(r.get("match", True)), "seen": str(r.get("seen", ""))[:80]}
    except Exception:
        return {"match": True, "seen": ""}  # 판정 실패 시 통과(가용성 우선)


def detect_material(image_path: str) -> str:
    """사물 사진 → 표면 재질 판정 (Vision). ⚠️ 이름만으론 유광/무광/투명 구분 불가 →
    실제 사진을 보고 판정. 반환: matte|reflective|transparent|default. (Vision 비용 1회)"""
    client = _get_client()
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")
    media_type, _ = mimetypes.guess_type(image_path)
    if media_type is None or not media_type.startswith("image/"):
        media_type = "image/jpeg"
    prompt = _prompts.get(_NS, "detect_material.prompt")
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


def detect_ingredients(image_path: str, n: int = 3) -> list[dict]:
    """음식 사진 → 명확히 구분되는 재료 n개 + 표면 위 상대좌표 (Vision).

    재료 콜아웃(부분클로즈업) 파이프라인용. 접시·도구·배경은 제외, 음식 재료만.
    반환: [{"name":"연어","name_en":"salmon","x":0.35,"y":0.45}, ...] (x,y=0~1 재료 표면 위 점).
    (Vision 비용 1회)
    """
    content = [{"type": "text", "text": _prompts.fmt(
        _NS, "detect_ingredients.instruction", n=n,
    )}, _vision_part(image_path)]
    try:
        r = _chat_json([{"role": "user", "content": content}], label="detect_ingredients")
        out = []
        for it in (r.get("items") or [])[:n]:
            try:
                out.append({"name": str(it.get("name", "")).strip(),
                            "name_en": str(it.get("name_en", "")).strip(),
                            "x": min(max(float(it.get("x", 0.5)), 0.05), 0.95),
                            "y": min(max(float(it.get("y", 0.5)), 0.05), 0.95)})
            except (TypeError, ValueError):
                continue
        return out
    except Exception:
        return []


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

    prompt = _prompts.fmt(_NS, "analyze_image_for_style.prompt",
                          preset_values=preset_values)

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
