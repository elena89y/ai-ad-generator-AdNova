"""LangGraph 챗봇 답변 품질 게이트 (제거 가능 모듈) — 담당: 한의정.

copy_graph 와 같은 설계 철학: 순환(생성→판정→재생성)이 실제로 필요한 지점에만
LangGraph 를 쓰고, 나머지는 순수 Python 유지.

흐름: generate → validate → (조건부 엣지) regenerate | END
판정 규칙 (validate_answer, 순수 함수):
  - 길이 상한 (ANSWER_MAX_CHARS)
  - 근거 인용 필수 — "[근거: faq-...]" 가 검색된 FAQ id 중 하나와 일치해야 함
  - 프롬프트 유출 마커 금지 ("system prompt", "시스템 프롬프트" 등이 답변에 등장 금지)

⚠️ 제거 가능 설계: 이 파일 + chat_service 의 guarded import 만으로 원복.
  langgraph 미설치 / USE_CHAT_GATE=0 → chat_service 가 generate_answer 직접 호출.
"""
from __future__ import annotations

import logging
from typing import Optional, Sequence, TypedDict

from .retrieval import RetrievalHit

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2  # 생성 최대 횟수 (초과 시 마지막 답변을 그대로 반환 → 상위에서 무근거면 에스컬레이션)
_LEAK_MARKERS = ("system prompt", "시스템 프롬프트", "[faq 근거]")


def validate_answer(answer: str, allowed_ids: Sequence[str], max_chars: int) -> list[str]:
    """답변 규칙 위반 목록 (빈 리스트 = 통과). 그래프 밖에서도 재사용하는 순수 함수."""
    violations: list[str] = []
    if not answer.strip():
        violations.append("답변이 비어있음")
    if len(answer) > max_chars:
        violations.append(f"답변이 {max_chars}자 초과 ({len(answer)}자)")
    if not any(fid in answer for fid in allowed_ids):
        violations.append("근거 FAQ 인용([근거: faq-...])이 없음")
    lowered = answer.lower()
    if any(m in lowered for m in _LEAK_MARKERS):
        violations.append("내부 프롬프트 유출 의심 표현 포함")
    return violations


class ChatState(TypedDict):
    """그래프 상태 — 질문·근거는 불변, answer/violations/attempts 만 갱신."""

    question: str
    hits: list  # list[RetrievalHit] — langgraph 직렬화 제약으로 느슨하게 유지
    attempts: int
    answer: str
    violations: list[str]


def _build_graph():  # noqa: ANN202
    from langgraph.graph import END, StateGraph  # noqa: PLC0415 — guarded import

    from . import chat_service  # noqa: PLC0415 — 순환 임포트 방지 (함수 시점 로드)

    def generate(state: ChatState) -> dict:
        retry_note = ""
        if state["violations"]:
            retry_note = "\n\n(이전 답변이 규칙 위반으로 반려됨: " + "; ".join(state["violations"]) + \
                         " — 규칙을 지켜 다시 답하세요.)"
        answer = chat_service.generate_answer(state["question"] + retry_note, state["hits"])
        return {"answer": answer, "attempts": state["attempts"] + 1}

    def validate(state: ChatState) -> dict:
        allowed = [h.faq.id for h in state["hits"]]
        return {"violations": validate_answer(state["answer"], allowed, chat_service.ANSWER_MAX_CHARS)}

    def route(state: ChatState) -> str:
        if state["violations"] and state["attempts"] < MAX_ATTEMPTS:
            logger.info("chat_graph: 위반 %s → 재생성 (%d/%d)",
                        state["violations"], state["attempts"], MAX_ATTEMPTS)
            return "generate"
        return END

    g = StateGraph(ChatState)
    g.add_node("generate", generate)
    g.add_node("validate", validate)
    g.set_entry_point("generate")
    g.add_edge("generate", "validate")
    g.add_conditional_edges("validate", route)
    return g.compile()


_compiled = None


def run_gated_generation(question: str, hits: Sequence[RetrievalHit]) -> str:
    """게이트 루프를 통과한 답변 반환. 재시도 소진 시 마지막 답변 그대로 반환."""
    global _compiled  # noqa: PLW0603
    if _compiled is None:
        _compiled = _build_graph()
    final = _compiled.invoke(
        {"question": question, "hits": list(hits), "attempts": 0, "answer": "", "violations": []}
    )
    return final["answer"]
