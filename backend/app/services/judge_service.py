"""LangChain 구조화 저지 + 배치 채점 (제거 가능 모듈) — 담당: 한의정.

목적 ①(선별기 실험): Best-of-N 후보 N장을 '동시에' 채점해 최선을 고른다.
  - BON-002 기각(2026-07-13): NIMA(값싼 심미 지표)는 이미-좋은 이미지(5~6점대)를 변별 못 해
    Best-of-N 이 무효였다. 사람 선호에 더 가까운 GPT Vision 저지를 선별기로 검증하는 트랙.
  - 배치(chain.batch): N개 독립 채점을 한 번에 스케줄 → 순차 invoke N회 대비 벽시계 = 합→최댓값
    (강좌 1일차 4.1 '실행 메서드' 교훈을 실제 비용 구간에 적용).

목적 ②(구조화 출력, A 시범): with_structured_output(Pydantic) 로 응답 스키마를 강제 →
  gpt_service 의 json_object+json.loads+try/except 폴백 취약점(트랩 #6) 제거. 라벨 생성에 우선 적용.

설계: requirements 에 있으나 死코드였던 langchain-openai 를 처음으로 실사용.
⚠️ 제거 가능: 이 파일 + 호출부(guarded import)만으로 원복.
  langchain 미설치 / OPENAI_API_KEY 없음 / 런타임 오류 → 상위에서 NIMA·raw 경로로 폴백.

비용: 후보 1장당 Vision 1회. Best-of-N(N=4)이면 생성당 +4 Vision 호출 → 팀 예산($30) 유의.
"""
from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

JUDGE_MODEL = "gpt-5.4-mini"  # gpt_service.GPT_MODEL 과 일치 유지
JUDGE_LOG_DIR = Path(__file__).resolve().parents[2] / "results" / "ai" / "judge_logs"


# ── 구조화 스키마 ────────────────────────────────────────────────────────────
class AdScore(BaseModel):
    """광고 후보 한 장의 채점 (1=나쁨 ~ 10=최고). 선별기용."""
    appeal: int = Field(description="식욕·구매욕 유발 (appetite/purchase desire), 1-10")
    realism: int = Field(description="사진 사실감 — CGI/플라스틱 아님, 1-10")
    identity: int = Field(description="원본 상품의 형태·색·구성 보존 충실도, 1-10")
    overall: int = Field(description="광고로서 종합 점수, 1-10")
    reason: str = Field(description="한 문장 근거")


class AdLabels(BaseModel):
    """포스터용 영문 라벨 (구조화 출력 — 키 표기 변형 방어 불필요)."""
    name: str = Field(description="메뉴명 영문 대문자 2~4단어 (브랜드명·과장 금지)")
    phrase: str = Field(description="분위기 문구 영문 대문자 3~6단어")


# ── LangChain plumbing (lazy) ────────────────────────────────────────────────
def _llm():
    """ChatOpenAI lazy 생성. langchain 미설치/키 없음 → 예외 (상위 폴백)."""
    from langchain_openai import ChatOpenAI

    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY 미설정")
    return ChatOpenAI(model=JUDGE_MODEL, temperature=0)


def _langfuse_callbacks() -> list:
    """Langfuse CallbackHandler — LangChain 호출(ChatOpenAI.batch/invoke)을 트레이싱.

    gpt_service 는 langfuse.openai 드롭인으로 자동 트레이싱되지만, 여기(judge_service)는
    LangChain 을 통하므로 별도 핸들러가 필요(공식 LangChain 연동 방식).
    LANGFUSE_PUBLIC_KEY 미설정/langfuse 미설치 시 빈 리스트 반환 → 트레이싱 없이 정상 동작(무해 폴백,
    이 파일 전체의 "제거 가능" 설계 원칙과 동일).
    """
    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return []
    try:
        from langfuse.langchain import CallbackHandler
        return [CallbackHandler()]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Langfuse LangChain 핸들러 생성 실패(무해): {e}")
        return []


def _record_usage(label: str, raw) -> None:  # noqa: ANN001
    """LangChain 응답(raw AIMessage)의 usage → gpt_service.API_USAGE_LOG (예산 추적 유지)."""
    try:
        from . import gpt_service
        um = getattr(raw, "usage_metadata", None) or {}
        gpt_service.API_USAGE_LOG.append(gpt_service.ApiUsage(
            label=label,
            prompt_tokens=int(um.get("input_tokens", 0) or 0),
            completion_tokens=int(um.get("output_tokens", 0) or 0),
            total_tokens=int(um.get("total_tokens", 0) or 0),
        ))
    except Exception as e:  # 로깅 실패는 무해 — 채점 결과엔 영향 없음
        logger.warning(f"judge usage 기록 실패(무해): {e}")


def _usage_dict(raw) -> dict[str, int]:  # noqa: ANN001
    """LangChain raw AIMessage usage 를 JSONL 저장용 dict 로 정규화."""
    um = getattr(raw, "usage_metadata", None) or {}
    return {
        "prompt_tokens": int(um.get("input_tokens", 0) or 0),
        "completion_tokens": int(um.get("output_tokens", 0) or 0),
        "total_tokens": int(um.get("total_tokens", 0) or 0),
    }


def _append_judge_log(original_path: Optional[str],
                      candidate_paths: list[str],
                      scores: list[AdScore],
                      raws: list,  # noqa: ANN001
                      best_path: str) -> None:
    """후보별 GPT judge 결과를 JSONL 로 저장.

    judge 는 비용이 드는 평가 호출이라, smoke/운영 선택 결과를 나중에 발표·실험 리포트·
    셀렉터 캘리브레이션에 재사용할 수 있게 원장을 남긴다. 저장 실패는 선별 결과를 막지 않는다.
    """
    try:
        now = datetime.now(timezone.utc)
        JUDGE_LOG_DIR.mkdir(parents=True, exist_ok=True)
        out = JUDGE_LOG_DIR / f"{now:%Y%m%d}.jsonl"
        usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        candidates = []
        for path, score, raw in zip(candidate_paths, scores, raws):
            usage = _usage_dict(raw) if raw is not None else {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
            for k in usage_total:
                usage_total[k] += usage[k]
            candidates.append({
                "path": path,
                "score": score.model_dump(),
                "usage": usage,
                "selected": path == best_path,
            })
        row = {
            "run_id": uuid.uuid4().hex[:12],
            "created_at": now.isoformat(),
            "model": JUDGE_MODEL,
            "selector": "gpt",
            "original_path": original_path,
            "best_path": best_path,
            "candidates": candidates,
            "usage_total": usage_total,
        }
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"judge 결과 저장 실패(무해): {e}")


def _data_url(image_path: str) -> str:
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    mt, _ = mimetypes.guess_type(image_path)
    if not mt or not mt.startswith("image/"):
        mt = "image/png"
    return f"data:{mt};base64,{b64}"


_RUBRIC = (
    "You are a strict food/product advertising art director. The FIRST image is the ORIGINAL "
    "product photo (identity reference); the SECOND image is a generated AD candidate. Score the "
    "candidate 1(poor) to 10(excellent). Richer color/gloss/lighting is GOOD as long as it still "
    "looks like a real photo and the product stays faithful; penalize only genuine flaws (warping, "
    "CGI/plastic look, fake blur, missing/extra parts, gibberish text)."
)


def _score_msg(candidate_path: str, original_path: Optional[str]):
    from langchain_core.messages import HumanMessage
    content: list = [{"type": "text", "text": _RUBRIC}]
    if original_path:
        content.append({"type": "image_url", "image_url": {"url": _data_url(original_path)}})
    content.append({"type": "image_url", "image_url": {"url": _data_url(candidate_path)}})
    return [HumanMessage(content=content)]


# ── 선별기: 배치 채점 (C + B) ────────────────────────────────────────────────
def score_batch(candidate_paths: list[str],
                original_path: Optional[str] = None) -> list[AdScore]:
    """후보 N장을 한 번의 chain.batch 로 동시 채점. 반환: 입력 순서대로 AdScore.

    파싱 실패한 후보는 중립 점수(5)로 폴백 — 배치 전체를 죽이지 않는다.
    호출 실패(키 없음·langchain 미설치·네트워크) 는 예외 전파 → 상위(_select_best)가 NIMA 폴백.
    """
    chain = _llm().with_structured_output(AdScore, include_raw=True)
    inputs = [_score_msg(p, original_path) for p in candidate_paths]
    results = chain.batch(
        inputs, config={"callbacks": _langfuse_callbacks(), "run_name": "judge_batch/score"}
    )  # [{raw, parsed, parsing_error}, ...] 순서 보존
    scores: list[AdScore] = []
    raws: list = []
    for r in results:
        raw = r.get("raw") if isinstance(r, dict) else None
        parsed = r.get("parsed") if isinstance(r, dict) else None
        if raw is not None:
            _record_usage("judge_batch/vision", raw)
        if parsed is None:
            parsed = AdScore(appeal=5, realism=5, identity=5, overall=5, reason="parse_fallback")
        scores.append(parsed)
        raws.append(raw)
    best_i = max(range(len(candidate_paths)), key=lambda i: scores[i].overall)
    _append_judge_log(original_path, candidate_paths, scores, raws, candidate_paths[best_i])
    return scores


def pick_best(candidate_paths: list[str],
              original_path: Optional[str] = None) -> tuple[str, list[AdScore]]:
    """배치 채점 후 overall 최고 후보 경로 + 전체 점수 반환. (동점 시 앞선 후보)"""
    scores = score_batch(candidate_paths, original_path)
    best_i = max(range(len(candidate_paths)), key=lambda i: scores[i].overall)
    return candidate_paths[best_i], scores


# ── 구조화 라벨 (A 시범) ─────────────────────────────────────────────────────
def structured_labels(product_context: str) -> tuple[str, str]:
    """상품 컨텍스트 → (name, phrase) 영문 라벨. 구조화 출력이라 키 변형 방어 불필요.

    실패 시 예외 전파 → 호출부(generate_english_labels)가 기존 raw 경로로 폴백.
    """
    from langchain_core.messages import HumanMessage
    chain = _llm().with_structured_output(AdLabels, include_raw=True)
    instruction = (
        "Create two English poster labels for this product.\n"
        f"- Product: {product_context}\n"
        "name = the product's real menu name in UPPERCASE 2-4 words (no brand names, no hype). "
        "phrase = a mood line in UPPERCASE 3-6 words. Letters, spaces and & only."
    )
    r = chain.invoke(
        [HumanMessage(content=instruction)],
        config={"callbacks": _langfuse_callbacks(), "run_name": "english_labels/structured"},
    )
    raw = r.get("raw") if isinstance(r, dict) else None
    parsed: Optional[AdLabels] = r.get("parsed") if isinstance(r, dict) else None
    if raw is not None:
        _record_usage("english_labels/structured", raw)
    if parsed is None or not parsed.name.strip():
        raise RuntimeError(f"구조화 라벨 파싱 실패: {r!r:.200}")
    name = parsed.name.strip().upper()
    phrase = parsed.phrase.strip().upper()
    return name, (phrase or name)
