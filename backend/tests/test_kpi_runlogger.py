"""v6 T0 KPI 3축 회귀 — 담당: 한의정. RunLogger 파생 kpi 블록·단가 환산·score push 무해성 검증.

G0 게이트: CPU 로컬에서 생성 1건 → 원장 행의 kpi.cost/time/quality 전부 채워짐.
"""
from __future__ import annotations

import json

from app.harness import pricing
from app.harness.run_logger import RunLogger
from app.services import gpt_service


def _run_one(tmp_path, *, with_gate=True, with_image_api=False, fake_llm=True):
    """RunLogger 1회 실행 후 원장 마지막 행(dict) 반환."""
    runs_path = tmp_path / "runs.jsonl"
    with RunLogger(phase="TEST", mode="A", engine="test", input="x.png",
                   runs_path=runs_path) as run:
        if fake_llm:
            # 블록 중 쌓인 OpenAI usage 를 auto_llm 이 캡처하는 경로 그대로 검증
            gpt_service.API_USAGE_LOG.append(
                gpt_service.ApiUsage(label="test", prompt_tokens=1000,
                                     completion_tokens=100, total_tokens=1100)
            )
        if with_gate:
            run.add_metric("gate", {"pass": True, "failures": [], "mode": "audit"})
        run.add_metric("aesthetic", 7.5)
        if with_image_api:
            run.add_image_api_usage("gpt-image-2", n=2)
        run.set_output(str(tmp_path / "out.png"))
    lines = runs_path.read_text(encoding="utf-8").strip().splitlines()
    return json.loads(lines[-1])


# --- G0: 3축 전부 non-null ---------------------------------------------------------
def test_kpi_three_axes_filled(tmp_path):
    rec = _run_one(tmp_path)
    kpi = rec["kpi"]
    # 비용축: 가짜 usage 1000in/100out → gpt-5.4-mini 단가 환산으로 0 초과
    assert kpi["cost"]["openai_usd"] > 0
    assert kpi["cost"]["total_usd"] >= kpi["cost"]["openai_usd"]
    # 시간축
    assert kpi["time"]["total_s"] is not None
    # 품질축
    assert kpi["quality"]["gate_passed"] is True
    assert kpi["quality"]["aesthetic"] == 7.5


def test_kpi_cpu_gpu_cost_zero(tmp_path):
    """로컬 Mac(CUDA 없음)에서는 GPU 환산 비용이 0이어야 한다."""
    rec = _run_one(tmp_path)
    assert rec["kpi"]["cost"]["gpu_s"] == 0.0
    assert rec["kpi"]["cost"]["gpu_usd_est"] == 0.0


def test_kpi_quality_null_kept_when_unmeasured(tmp_path):
    """미계측 축은 None 으로 남아야 한다 — 어떤 축이 빠졌는지 집계에서 보이도록."""
    rec = _run_one(tmp_path, with_gate=False)
    assert rec["kpi"]["quality"]["gate_passed"] is None
    assert rec["kpi"]["quality"]["judge_score"] is None


# --- 이미지 API 비용축 -------------------------------------------------------------
def test_image_api_usage_counted(tmp_path):
    rec = _run_one(tmp_path, with_image_api=True)
    assert rec["image_api"] == [
        {"model": "gpt-image-2", "n": 2, "cost_usd": pricing.image_cost_of("gpt-image-2", 2)}
    ]
    kpi = rec["kpi"]
    assert kpi["cost"]["image_api_usd"] == pricing.image_cost_of("gpt-image-2", 2)
    assert kpi["cost"]["total_usd"] == round(
        kpi["cost"]["openai_usd"] + kpi["cost"]["image_api_usd"] + kpi["cost"]["gpu_usd_est"], 6
    )


def test_gpu_used_false_zeroes_gpu_cost_on_gpu_host(tmp_path, monkeypatch):
    """API 경로(gpu_used=False)는 GPU 호스트(CUDA 가용)에서도 GPU 비용 0 — 3암 A/B 공정성."""
    import time

    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    runs_path = tmp_path / "runs.jsonl"
    for gpu_used, expect_zero in ((False, True), (None, False)):
        with RunLogger(phase="TEST", mode="A", engine="graph:api", input="x.png",
                       runs_path=runs_path, auto_llm=False) as run:
            time.sleep(0.02)  # total_s 가 0.00 으로 반올림되지 않도록
            if gpu_used is not None:
                run.set_meta(gpu_used=gpu_used)
    rows = [json.loads(l) for l in runs_path.read_text().strip().splitlines()]
    assert rows[0]["kpi"]["cost"]["gpu_s"] == 0.0            # gpu_used=False
    assert rows[1]["kpi"]["cost"]["gpu_s"] > 0.0             # 미지정(기존 로컬 경로) = 점유 계상


# --- 단가 환산 ---------------------------------------------------------------------
def test_gpu_cost_env_override(monkeypatch):
    monkeypatch.setenv("GPU_USD_PER_HOUR", "1.80")
    assert pricing.gpu_cost_of(3600) == 1.80
    monkeypatch.setenv("GPU_USD_PER_HOUR", "not-a-number")
    assert pricing.gpu_cost_of(3600) == pricing.GPU_USD_PER_HOUR_DEFAULT


def test_image_cost_unknown_model_is_zero():
    assert pricing.image_cost_of("some-local-model", 3) == 0.0


# --- run 1건 = Langfuse 트레이스 1건 (APIQ-001 'no active span' 갭의 근본 수정) --------
def test_run_span_wraps_scores_with_fake_langfuse(tmp_path, monkeypatch):
    """스팬 열림 → score push → 스팬 닫힘 순서 보장. 러너 직행 경로에서도 트레이스가 남는다."""
    import sys
    import types

    calls: list = []

    class _Span:
        def __enter__(self):
            calls.append("span_enter")
            return self

        def __exit__(self, *a):  # noqa: ANN002
            calls.append("span_exit")
            return False

    class _Client:
        def start_as_current_observation(self, name, as_type="span"):  # noqa: ANN001
            calls.append(("span_name", name))
            assert as_type == "span"
            return _Span()

        def update_current_trace(self, **kw):  # noqa: ANN003
            calls.append(("trace_meta", kw.get("metadata", {}).get("engine")))

        def score_current_trace(self, name, value, comment=None):  # noqa: ANN001
            calls.append(("score", name, value))

    fake = types.ModuleType("langfuse")
    fake.get_client = lambda: _Client()
    monkeypatch.setitem(sys.modules, "langfuse", fake)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")

    with RunLogger(phase="LF-TEST", mode="A", engine="graph:api", input="x.png",
                   runs_path=tmp_path / "runs.jsonl", auto_llm=False) as run:
        run.add_metric("gate", {"pass": True, "failures": [], "mode": "audit"})
        run.set_output(str(tmp_path / "out.png"))

    enter_i, exit_i = calls.index("span_enter"), calls.index("span_exit")
    score_is = [i for i, c in enumerate(calls)
                if isinstance(c, tuple) and c[0] == "score"]
    assert score_is, "KPI score 가 하나도 push 되지 않음"
    assert all(enter_i < i < exit_i for i in score_is), "score 가 스팬 밖에서 push 됨"
    assert ("span_name", "run:LF-TEST:x.png") in calls
    score_names = {c[1] for c in calls if isinstance(c, tuple) and c[0] == "score"}
    assert {"kpi.cost_total_usd", "kpi.time_total_s", "kpi.quality_gate_passed"} <= score_names


# --- score push 무해성 -------------------------------------------------------------
def test_push_kpi_scores_noop_without_key(tmp_path, monkeypatch):
    """LANGFUSE_PUBLIC_KEY 없으면 push 는 조용히 no-op — 예외/네트워크 호출 없어야 한다."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    from app.core.observability import push_kpi_scores

    rec = _run_one(tmp_path)          # __exit__ 경로에서 이미 1회 통과했음
    push_kpi_scores(rec["run_id"], rec["kpi"])  # 직접 호출도 무해
    push_kpi_scores(rec["run_id"], None)        # kpi 미생성(구버전 행)도 무해
