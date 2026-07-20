"""광고 생성 오케스트레이션 그래프 (LangGraph) — 담당: 한의정. (DIRECTION_v6 T2)

analyze → route(engine) → generate(local|api) → gate → (실패 시 반대 엔진 폴백 1회) 를
LangGraph StateGraph 로 명시한다. copy_graph 패턴 계승:
  - USE_PIPELINE_GRAPH=0 기본 off — 기존 run_generation/process_ad 계약 불변, HTTP 노출은 팀 조율 후.
  - langgraph 미설치 시 동일 노드를 순차 실행(무해 폴백).

ENGINE_POLICY (env, T3 하이브리드 실측의 강등 스위치 — GCP 종료 시 api 로 전환):
  local  = 기존 GPU 파이프라인만
  api    = gpt-image edit 만 (GPU 불필요 — 생존 경로)
  hybrid = 라우팅 가설(T3 HYB-001 검증 대상): 정체성 민감(사물 SKU·texture_hero) → api,
           그 외 연출 중심 → local. 근거: 2026-07-17 실측 — gpt-image-2 가 로고·투명유리·
           3D 형상 보존에서 우수, 로컬 FLUX/RealVis 는 씬 연출 자유도·고정비 활용에서 우위.

각 실행은 RunLogger 1행(engine="graph:{엔진}") — KPI 3축(T0)이 자동 파생된다.
"""
from __future__ import annotations

import logging
import os
from typing import Optional, TypedDict

logger = logging.getLogger(__name__)


class PipelineState(TypedDict, total=False):
    image_path: str
    name: str
    style: Optional[str]
    policy: str            # local | api | hybrid
    engine: str            # 이번 시도 엔진: local | api
    subject_en: str
    domain: str            # food | object
    texture_hero: bool
    identity_parts: list
    flexible_parts: list
    out_path: Optional[str]
    gate_passed: Optional[bool]
    attempts: int
    error: Optional[str]


def enabled() -> bool:
    """USE_PIPELINE_GRAPH=1 일 때만 활성 (기본 off — 기존 계약 불변)."""
    return os.environ.get("USE_PIPELINE_GRAPH", "0") == "1"


def engine_policy() -> str:
    value = os.environ.get("ENGINE_POLICY", "local").strip().lower()
    return value if value in ("local", "api", "hybrid") else "local"


# --- 노드 구현 (테스트에서 monkeypatch 하는 단위) -----------------------------------
def _do_analyze(state: PipelineState) -> PipelineState:
    """사진+이름 통합 분석 → 라우팅 근거 필드. 실패 시 이름 기반 폴백(기존 계약)."""
    from . import gpt_service

    analysis = gpt_service.analyze_photo(state["image_path"], state["name"])
    if analysis is None:
        menu = gpt_service.analyze_menu(state["name"])
        state.update(subject_en=menu.subject_en, domain=menu.domain,
                     texture_hero=menu.texture_hero, identity_parts=[], flexible_parts=[])
    else:
        state.update(subject_en=analysis.subject_en, domain=analysis.domain,
                     texture_hero=analysis.texture_hero,
                     identity_parts=list(analysis.identity_parts),
                     flexible_parts=list(analysis.flexible_parts))
    return state


def _route_engine(state: PipelineState) -> PipelineState:
    policy = state.get("policy") or engine_policy()
    if policy == "hybrid":
        sensitive = state.get("domain") == "object" or bool(state.get("texture_hero"))
        engine = "api" if sensitive else "local"
    else:
        engine = policy
    state["policy"] = policy
    state["engine"] = engine
    return state


def _do_generate_api(state: PipelineState) -> str:
    from . import api_image_service
    from .style_specs import get_spec

    style_hint = get_spec(state.get("style") or "editorial").mood if state.get("style") else ""
    instruction = api_image_service.build_edit_instruction(
        subject_en=state.get("subject_en", ""),
        style_hint=style_hint,
        identity_parts=state.get("identity_parts") or None,
        flexible_parts=state.get("flexible_parts") or None,
        is_object=state.get("domain") == "object")
    return api_image_service.edit_image(state["image_path"], instruction)


def _do_generate_local(state: PipelineState) -> str:
    from . import generation_service

    result = generation_service.process_ad(
        state["image_path"], state["name"], style=state.get("style"),
        poster=False, log=False)
    return result.final_image_path


def _generate(state: PipelineState) -> PipelineState:
    state["attempts"] = state.get("attempts", 0) + 1
    try:
        if state["engine"] == "api":
            state["out_path"] = _do_generate_api(state)
        else:
            state["out_path"] = _do_generate_local(state)
        state["error"] = None
    except Exception as exc:  # noqa: BLE001 — 폴백 라우팅이 처리
        logger.warning("pipeline_graph generate(%s) 실패: %s", state.get("engine"), exc)
        state["error"] = f"{type(exc).__name__}: {exc}"
        state["out_path"] = None
    return state


def _gate(state: PipelineState) -> PipelineState:
    if not state.get("out_path"):
        state["gate_passed"] = False
        return state
    from . import inline_gate

    verdict = inline_gate.evaluate(state["out_path"], state.get("style"))
    state["gate_passed"] = bool(verdict.get("pass"))
    return state


def _after_gate(state: PipelineState) -> str:
    """게이트 후 분기: 통과·재시도 소진 → end / 실패 1회차 → 반대 엔진 폴백."""
    if state.get("gate_passed") or state.get("attempts", 0) >= 2:
        return "end"
    return "fallback"


def _fallback_engine(state: PipelineState) -> PipelineState:
    """hybrid 만 반대 엔진으로 교차 폴백. 단일 정책(local|api)은 같은 엔진 재시도 1회 —
    T3 3암 A/B 의 암 순수성(로컬암에 API 결과 혼입 금지) 보장."""
    if state.get("policy") == "hybrid":
        state["engine"] = "local" if state["engine"] == "api" else "api"
        logger.info("pipeline_graph 폴백: 엔진 전환 → %s", state["engine"])
    else:
        logger.info("pipeline_graph 폴백: 같은 엔진(%s) 재시도", state["engine"])
    return state


# --- 그래프 조립·실행 ---------------------------------------------------------------
def _build_graph():  # noqa: ANN202 — langgraph CompiledGraph
    from langgraph.graph import END, StateGraph

    g = StateGraph(PipelineState)
    g.add_node("analyze", _do_analyze)
    g.add_node("route", _route_engine)
    g.add_node("generate", _generate)
    g.add_node("gate", _gate)
    g.add_node("fallback", _fallback_engine)
    g.set_entry_point("analyze")
    g.add_edge("analyze", "route")
    g.add_edge("route", "generate")
    g.add_edge("generate", "gate")
    g.add_conditional_edges("gate", _after_gate, {"end": END, "fallback": "fallback"})
    g.add_edge("fallback", "generate")
    return g.compile()


def _run_sequential(state: PipelineState) -> PipelineState:
    """langgraph 미설치 폴백 — 동일 노드를 같은 순서로 실행(추가 생성 ≤1 동일)."""
    state = _do_analyze(state)
    state = _route_engine(state)
    state = _generate(state)
    state = _gate(state)
    while _after_gate(state) == "fallback":
        state = _fallback_engine(state)
        state = _generate(state)
        state = _gate(state)
    return state


from ..core.observability import observe


@observe(name="pipeline.run_graph")
def run_pipeline(image_path: str, name: str, style: Optional[str] = None,
                 policy: Optional[str] = None) -> PipelineState:
    """그래프 실행 1회 = KPI 원장 1행. 반환 state 에 out_path/gate_passed/attempts/error.

    @observe 스팬 안에서 RunLogger 가 닫히므로 KPI score 가 이 트레이스에 붙는다(T0 계약).
    """
    from ..harness.run_logger import RunLogger

    initial: PipelineState = {
        "image_path": image_path, "name": name, "style": style,
        "policy": (policy or engine_policy()), "attempts": 0,
    }
    with RunLogger(phase="V6T2", mode="pending", engine="graph:pending",
                   input=image_path, params={"name": name, "style": style,
                                             "policy": initial["policy"]}) as run:
        try:
            graph = _build_graph()
            final = graph.invoke(initial)
        except ImportError:
            logger.info("langgraph 미설치 → 순차 폴백 실행")
            final = _run_sequential(initial)
        run.set_meta(mode=final.get("domain", "pending"),
                     engine=f"graph:{final.get('engine', 'unknown')}",
                     gpu_used=(final.get("engine") == "local"))
        if final.get("out_path"):
            run.set_output(final["out_path"])
        run.add_metric("gate", {"pass": bool(final.get("gate_passed")),
                                "failures": [], "mode": "graph"})
        run.add_metric("attempts", final.get("attempts", 0))
        return final
