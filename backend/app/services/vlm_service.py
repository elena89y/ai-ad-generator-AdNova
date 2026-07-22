"""로컬 VLM(Qwen3-VL-2B-Instruct) 판정·분석 창구 — 담당: 한의정 (v2).

⚠️ 캘리브레이션 결론(P2-2, 2026-07-09, A모드 5쌍 실측) — 역할별 신뢰도:
  ● inspect (개방형 결함/품질 서술): **신뢰 O**. "무엇이 이상한지 한 문장, 없으면 'looks clean'".
      깨끗한 건 clean, v1 수프는 "버섯 텍스처가 인공적"처럼 구체·타당. 회귀/QA 게이트로 채택.
  ● describe (카피용 묘사): **신뢰 O**. 마블링·붉은육 등 정확 서술(스모크 검증). GPT Vision 절감.
  △ score (단일 루브릭 1~10): **advisory only**. 점수 8~9 압축, v1/v2 변별 약함.
  ✗ compare (두 우수 이미지 미세 A/B 순위): **신뢰 X**. 위치편향·프롬프트 민감(양방향 강일치 20~60% 흔들림).
      CoT 로 편향은 완화되나 오라클로 못 씀. → 미세 미학 최종판정은 사람(육안)이 정본.
  cf) 값싼 자동 미학지표(LAION aesthetic)도 3/5, DINO 는 향상을 penalize — 어떤 단일 지표도
      사람 아트디렉터 판정을 재현 못 함. 자동 스택 = 총체적 실패 스크리닝 + 회귀 트립와이어 용도.

브링업 근거(ADR): FP8/bnb-4bit/ImageReward 는 이 torch2.12/cu130 스택에서 전부 실패
  (fp8 커널 빌드 부재 · transformers Qwen3VL 비전타워 4bit 통합 갭 · ImageReward 는 구 transformers
  심볼 의존). bf16 네이티브가 유일하게 확실한 경로. 2B 선택은 디스크(100G 고정, 여유 ~4G)와
  4B bf16(8.3G) 대비 안전 마진. 실측 로드 4.2s / 추론 3~7s / VRAM 4.0G.

VRAM: 4G 로 Kontext(13.2G)와 산술상 공존 가능(<20G)하나, 생성-판정은 순차 권장.
  판정 배치 전 kontext_service.unload() 후 로드하면 안전.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MODEL_REPO = "Qwen/Qwen3-VL-2B-Instruct"  # bf16 네이티브(양자화 의존성 0)
_MAX_NEW = 320

_model = None
_processor = None


# --- 루브릭 -------------------------------------------------------------------
# 각 항목 1~10 정수. artifact_free 는 "결함 없음"이 높은 점수(역방향 아님, 직관 유지).
# adherence 는 ref(원본)+instruction 이 있을 때만 유효, 없으면 null.
_DIMS = ["appetizing", "realism", "artifact_free", "composition", "adherence"]

_JUDGE_SYS = (
    "You are a strict art director reviewing AI-generated food/product advertising images. "
    "Score honestly; a mediocre image should get 5-6, not 8. Reserve 9-10 for images that "
    "could run in a real premium campaign."
)

_RUBRIC = (
    "Rate this advertising image on each axis from 1 (poor) to 10 (excellent):\n"
    "- appetizing: how appetizing / desirable the subject looks\n"
    "- realism: photographic realism (no CGI / plastic / uncanny look)\n"
    "- artifact_free: absence of AI artifacts (warped shapes, extra fingers, gibberish text, melting)\n"
    "- composition: lighting, framing and overall advertising polish\n"
    "- adherence: {adherence_hint}\n"
    "Reply with ONLY a JSON object, no prose, exactly:\n"
    '{{"appetizing":N,"realism":N,"artifact_free":N,"composition":N,'
    '"adherence":N,"overall":N,"reason":"one short sentence"}}'
)


def _load():  # noqa: ANN202
    """Qwen3-VL lazy 싱글턴 로드(bf16, cuda)."""
    global _model, _processor
    if _model is not None:
        return _model, _processor
    import torch
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

    logger.info("VLM 로드: %s (bf16)", MODEL_REPO)
    _model = Qwen3VLForConditionalGeneration.from_pretrained(
        MODEL_REPO, torch_dtype=torch.bfloat16, device_map="cuda")
    _processor = AutoProcessor.from_pretrained(MODEL_REPO)
    return _model, _processor


def unload() -> None:
    """VLM 언로드 — VRAM 확보."""
    import gc

    import torch
    global _model, _processor
    _model = None
    _processor = None
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _generate(messages: list, max_new: int = _MAX_NEW) -> str:
    """chat 메시지 → 텍스트 응답."""
    import torch
    model, proc = _load()
    inputs = proc.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True,
        return_dict=True, return_tensors="pt").to("cuda")
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_new, do_sample=False)
    return proc.batch_decode(
        out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0].strip()


def _parse_scores(text: str) -> dict:
    """응답에서 JSON 점수 추출. 실패 시 정규식 폴백, 그래도 실패면 raw 보존."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            d = json.loads(m.group(0))
            return {k: d.get(k) for k in (*_DIMS, "overall", "reason")}
        except json.JSONDecodeError:
            pass
    # 폴백: "appetizing": 8 형태를 개별 추출
    d = {}
    for k in (*_DIMS, "overall"):
        mm = re.search(rf'"{k}"\s*:\s*(\d+)', text)
        d[k] = int(mm.group(1)) if mm else None
    rm = re.search(r'"reason"\s*:\s*"([^"]*)"', text)
    d["reason"] = rm.group(1) if rm else None
    d["_raw"] = text
    return d


# --- 공개 API -----------------------------------------------------------------
# 개방형 결함 QA — 신뢰 역할. 체크리스트를 주면 2B 가 항목을 복창하므로 반드시 개방형.
_INSPECT_Q = (
    "Look closely at this food photo as a picky customer. In ONE sentence, describe anything "
    "that actually looks wrong, fake, distorted, or unappetizing in THIS specific image. "
    "If nothing looks wrong and it looks like a clean, appetizing real photo, reply exactly "
    "'looks clean'. Do not invent problems.")


def inspect(image_path: str) -> dict:
    """개방형 결함/품질 검사(신뢰 역할·QA 게이트). dict{clean:bool, note:str} 반환.

    체크리스트가 아니라 개방형으로 물어 2B 의 복창(parroting)을 회피. clean 판정은
    'looks clean' 정확일치로만. 회귀 스크리닝·총체적 실패(왜곡/맨손/CGI) 검출에 사용.
    """
    messages = [{"role": "user", "content": [
        {"type": "image", "image": str(image_path)},
        {"type": "text", "text": _INSPECT_Q}]}]
    note = _generate(messages, max_new=90).strip()
    clean = note.lower().strip().strip(".'\"") == "looks clean"
    return {"clean": clean, "note": note}


def judge(image_path: str, instruction: Optional[str] = None,
          ref_path: Optional[str] = None) -> dict:
    """생성 이미지 1장을 루브릭으로 채점. dict(점수 + overall + reason) 반환.

    instruction+ref_path 를 주면 adherence(원본 정체성 보존 + 명령 이행)를 판정,
    없으면 adherence 는 무의미하므로 힌트를 완화한다.
    """
    if ref_path and instruction:
        hint = (f'how well it followed the edit "{instruction}" while keeping the '
                "original subject's identity (first image = original, second = result)")
        content = [
            {"type": "image", "image": str(ref_path)},
            {"type": "image", "image": str(image_path)},
            {"type": "text", "text": _RUBRIC.format(adherence_hint=hint)},
        ]
    else:
        hint = "leave 5 if not applicable"
        content = [
            {"type": "image", "image": str(image_path)},
            {"type": "text", "text": _RUBRIC.format(adherence_hint=hint)},
        ]
    messages = [
        {"role": "system", "content": [{"type": "text", "text": _JUDGE_SYS}]},
        {"role": "user", "content": content},
    ]
    return _parse_scores(_generate(messages))


_COMPARE_Q = (
    "Image 1 and Image 2 are two edited versions of the same food photo for an advertisement. "
    "First, in one short sentence, state the single most important visual difference between them. "
    "Then decide which one is the better ADVERTISEMENT. For an ad, richer color, glossy sheen, "
    "clearer detail and appetizing enhancement are GOOD, as long as the food still looks like a "
    "real photograph of real food. Penalize ONLY genuine flaws: warped/melted shapes, plastic or "
    "CGI look, fake-looking blur, or unnatural artifacts. Think about the difference before deciding. "
    'Reply with ONLY compact JSON, no markdown: {"difference":"max 10 words","winner":1 or 2}')


def compare(image_a: str, image_b: str) -> dict:
    """두 결과 중 더 나은 광고 선택 — **advisory only**(캘리브레이션상 미세 A/B 순위 신뢰 X).

    CoT(차이 먼저 서술 후 판정)로 위치편향을 완화하나 오라클로 쓰지 말 것. 위치편향
    제거하려면 image_a/image_b 를 뒤바꿔 두 번 호출해 일치할 때만 신뢰. dict{winner,difference}.
    """
    q = _COMPARE_Q  # 2장만(원본 3장은 2B 혼동), 광고 프레이밍 + 짧은 차이 강제(truncation 방지)
    messages = [{"role": "user", "content": [
        {"type": "image", "image": str(image_a)},
        {"type": "image", "image": str(image_b)},
        {"type": "text", "text": q}]}]
    text = _generate(messages, max_new=256)
    wm = re.search(r'"winner"\s*:\s*(\d)', text)
    dm = re.search(r'"difference"\s*:\s*"([^"]*)"', text)
    winner = {"1": "A", "2": "B"}.get(wm.group(1), "tie") if wm else "tie"
    return {"winner": winner, "difference": dm.group(1) if dm else text[:120]}


def describe(image_path: str, prompt: Optional[str] = None) -> str:
    """광고 카피용 이미지 묘사(영문 1~2문장). GPT Vision 절감."""
    q = prompt or ("Describe this food/product for an advertising copywriter in one or two "
                   "vivid sentences: the subject, its most appetizing/desirable visual "
                   "qualities, and mood. No preamble.")
    messages = [{"role": "user", "content": [
        {"type": "image", "image": str(image_path)},
        {"type": "text", "text": q}]}]
    return _generate(messages, max_new=160)


# 광고 디자인 토큰 오토캡션 — 개방형 지각(2B 강점)만 요구, 엄격 분류 회피(2B 약점).
#   lighting 은 '실제 그림자/하이라이트로 판단' 강제(AUTOCAP-002: 60%가 soft로 쏠려 오판 → 관찰 유도).
_CAPTION_Q = (
    "You are labeling a reference advertising image to build a design dataset. Look ONLY at what "
    "you can visually see and reply in JSON. Do NOT guess brand or category names.\n"
    '{"subject":"physical description of the main product/food, e.g. a glossy amber serum bottle",'
    '"lighting":"Judge ONLY from the visible shadows and highlights. Hard-edged shadows, a bright rim/'
    'back glow, a spotlight, or high contrast => dramatic (say the direction: side/back/top). Only call '
    'it soft/even when shadows are genuinely faint and low-contrast. Do NOT default to soft.",'
    '"composition":"subject position + framing, e.g. single hero on pedestal, low angle",'
    '"text_space":"where the largest empty area for text is: top | bottom | left | right | none",'
    '"style_tokens":["3-5 mood words SPECIFIC to THIS image (its color feel, energy, era, finish), '
    'avoid generic filler",'
    '"colors":["2-3 dominant colors"]}')


def auto_caption(image_path: str) -> dict:
    """레퍼런스 이미지 → 광고 디자인 토큰 JSON(자동 라벨링, Self-distill/harvest 코퍼스용).

    subject·lighting·composition·text_space(여백 위치)·style_tokens·colors 를 추출.
    2B 의 강점(개방형 describe)만 쓰고 브랜드/카테고리 분류는 요구하지 않는다(약점 회피).
    """
    messages = [{"role": "user", "content": [
        {"type": "image", "image": str(image_path)},
        {"type": "text", "text": _CAPTION_Q}]}]
    raw = _generate(messages, max_new=256)
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            d = json.loads(m.group(0))
            d["_ok"] = True
            return d
        except json.JSONDecodeError:
            pass
    return {"_ok": False, "_raw": raw}


# --- VLM-001 ① 로컬 라우팅 (analyze_menu 무-API 대체) ------------------------------
def analyze_menu_local(name: str):
    """Qwen3-VL 로컬 라우팅 — gpt_service.analyze_menu 의 무-OpenAI 대체(VLM-001 ①).

    같은 원장 프롬프트(build_menu_instruction)로 Qwen 텍스트 생성 → JSON 추출 →
    공용 파서(gpt_service.menu_from_result)로 MenuAnalysis 반환. 2B 자유형 출력은
    화이트리스트 클램프가 안전 범위로 강제. gpt_service 는 vlm_service.describe 를
    참조하므로 순환 회피 위해 함수 내부 import.
    """
    from . import gpt_service
    instr = gpt_service.build_menu_instruction(name)
    messages = [{"role": "user", "content": [{"type": "text", "text": instr}]}]
    raw = _generate(messages, max_new=256)
    result: dict = {}
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            result = json.loads(m.group(0))
        except json.JSONDecodeError:
            result = {}
    ma = gpt_service.menu_from_result(result, (name or "").strip())
    logger.info("[VLM-001 route] %s → domain=%s food_mode=%s subject=%s (raw_ok=%s)",
                name, ma.domain, ma.food_mode, ma.subject_en, bool(m))
    return ma


# --- VLM-001 ② 로컬 광고 카피 (완성 광고 이미지 → 어울리는 한국어 문구) ---------------
#   VLM 본연의 목적: 완성된 광고 이미지를 '보고' 어울리는 카피를 붙인다(이미지 그라운딩).
#   describe/inspect 가 캘리브레이션서 신뢰 O였던 개방형 지각 강점을 카피에 사용. 무-API.
_COPY_Q = (
    "너는 감각적인 한국 광고 카피라이터다. 아래 '완성된 광고 이미지'를 자세히 보고, 이 이미지에 "
    "가장 어울리는 한국어 광고 문구를 지어라. 이미지의 분위기·색감·질감·연출과 제품을 반영해라. "
    "제품명: {name}.\n"
    "규칙: 헤드라인은 짧고 임팩트 있게(공백 포함 {hmax}자 이내), 서브카피는 헤드라인을 받쳐주는 "
    "한 문장({smax}자 이내). 과장·허위 표현(최고·1위·100%·무조건) 금지. 이미지에 없는 사실 지어내지 말 것.\n"
    'JSON 하나만 출력: {{"headline":"...", "subcopy":"..."}}'
)


def generate_copy_local(image_path: str, product_name: str) -> dict:
    """Qwen3-VL 로컬 이미지 그라운딩 광고 카피(VLM-001 ②) — gpt_service.generate_copy 무-API 대체.

    완성 광고 이미지 + 제품명 → 한국어 {headline, subcopy}. 기존 규칙 게이트(copy_graph.
    validate_copy: 길이·과장어)를 그대로 태워 품질 하한 강제. 위반은 반환에 실어 육안 판정에 노출.
    """
    from .copy_graph import HEADLINE_MAX, SUBCOPY_MAX, validate_copy
    q = _COPY_Q.format(name=(product_name or "상품").strip(), hmax=HEADLINE_MAX, smax=SUBCOPY_MAX)
    messages = [{"role": "user", "content": [
        {"type": "image", "image": str(image_path)},
        {"type": "text", "text": q}]}]
    raw = _generate(messages, max_new=220)
    headline, subcopy = "", ""
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            d = json.loads(m.group(0))
            headline = str(d.get("headline", "")).strip()
            subcopy = str(d.get("subcopy", "")).strip()
        except json.JSONDecodeError:
            pass
    violations = validate_copy(f"{headline}\n{subcopy}") if headline else ["헤드라인 파싱 실패"]
    logger.info("[VLM-001 copy] %s → '%s' / '%s' (위반 %d)",
                product_name, headline, subcopy, len(violations))
    return {"headline": headline, "subcopy": subcopy, "violations": violations, "raw": raw}
