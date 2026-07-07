"""LangGraph 문구 품질 게이트 루프 (제거 가능 모듈) — 담당: 한의정.

강사 권고(LangGraph 적극 사용)에 대응하는 유일한 정당화 지점:
  문구 생성 → 규칙 자동판정 → 미준수 시 재생성 (순환·조건분기·상태유지).
  나머지 파이프라인은 순차라 순수 Python 유지 (억지 래핑 안 함).

⚠️ 제거 가능 설계: 이 파일 하나 + generation_service 의 guarded import 만으로 원복.
  langgraph 미설치/USE_COPY_GATE=0 → generation_service 가 gpt_service.generate_copy 직접 호출로 폴백.

흐름: generate → validate → (조건부 엣지) regenerate | END
상태(CopyState): 이미지·상품·스타일 + 시도횟수 + 위반목록 + 문구.
"""
from __future__ import annotations

import logging
from typing import Optional, TypedDict

from ..schemas.ads import ProductInfo, StylePreset
from . import gpt_service

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
HEADLINE_MAX = 40      # 헤드라인 글자수 상한
SUBCOPY_MAX = 120      # 서브카피 글자수 상한
_BANNED = ("최고", "1위", "100%", "무조건")  # 과장·허위 광고 소지 표현 (B-4 Layer1 예시)


# --- 규칙 판정 (B-4 Layer 1 체크리스트) ---------------------------------------
def validate_copy(copy_text: str) -> list[str]:
    """문구 규칙 위반 목록 반환 (빈 리스트 = 통과). 순수 함수 — 그래프 밖에서도 재사용."""
    violations: list[str] = []
    parts = copy_text.split("\n", 1)
    headline = parts[0].strip() if parts else ""
    subcopy = parts[1].strip() if len(parts) > 1 else ""

    if not headline:
        violations.append("헤드라인이 비어있음")
    if not subcopy:
        violations.append("서브카피(2번째 줄)가 없음 — 반드시 '헤드라인\\n서브카피' 형식")
    if len(headline) > HEADLINE_MAX:
        violations.append(f"헤드라인이 너무 김({len(headline)}자, {HEADLINE_MAX}자 이내로)")
    if len(subcopy) > SUBCOPY_MAX:
        violations.append(f"서브카피가 너무 김({len(subcopy)}자, {SUBCOPY_MAX}자 이내로)")
    hit = [w for w in _BANNED if w in copy_text]
    if hit:
        violations.append(f"과장·허위 소지 표현 사용: {', '.join(hit)}")
    return violations


# --- LangGraph 상태·노드 -------------------------------------------------------
class CopyState(TypedDict):
    final_image_path: str
    product: ProductInfo
    style: StylePreset
    use_vision: bool
    copy_text: str
    attempt: int
    violations: list[str]


def _generate_node(state: CopyState) -> dict:
    feedback = "; ".join(state.get("violations", []))
    result = gpt_service.generate_copy(
        state["final_image_path"], state["product"], state["style"],
        use_vision=state["use_vision"], feedback=feedback,
    )
    return {"copy_text": result.copy_text, "attempt": state["attempt"] + 1}


def _validate_node(state: CopyState) -> dict:
    v = validate_copy(state["copy_text"])
    if v:
        logger.info(f"[copy-gate] 시도 {state['attempt']} 위반: {v}")
    return {"violations": v}


def _route(state: CopyState) -> str:
    """통과했거나 시도 소진 → END, 아니면 재생성."""
    if not state["violations"] or state["attempt"] >= MAX_ATTEMPTS:
        return "end"
    return "regenerate"


_compiled = None


def _get_graph():  # noqa: ANN202
    """StateGraph lazy 컴파일. langgraph 미설치면 ImportError → 상위에서 폴백."""
    global _compiled
    if _compiled is None:
        from langgraph.graph import END, StateGraph

        g = StateGraph(CopyState)
        g.add_node("generate", _generate_node)
        g.add_node("validate", _validate_node)
        g.set_entry_point("generate")
        g.add_edge("generate", "validate")
        g.add_conditional_edges("validate", _route, {"regenerate": "generate", "end": END})
        _compiled = g.compile()
    return _compiled


# --- 공개 API ------------------------------------------------------------------
def generate_copy_with_gate(
    final_image_path: str,
    product: ProductInfo,
    style: StylePreset,
    use_vision: bool = False,
) -> gpt_service.CopyResult:
    """품질 게이트 루프로 문구 생성. 규칙 통과 문구 반환 (소진 시 마지막 시도)."""
    graph = _get_graph()
    final = graph.invoke({
        "final_image_path": final_image_path, "product": product, "style": style,
        "use_vision": use_vision, "copy_text": "", "attempt": 0, "violations": [],
    })
    logger.info(f"[copy-gate] 완료 (시도 {final['attempt']}회, 최종 위반 {final['violations']})")
    return gpt_service.CopyResult(copy_text=final["copy_text"])
