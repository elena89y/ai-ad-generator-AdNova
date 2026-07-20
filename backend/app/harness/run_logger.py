"""RunLogger — 실행 계측 원장 (모든 생성의 필수 게이트) — 담당: 한의정.

사용:
    with RunLogger(phase="P1", mode="A", engine="kontext-nf4",
                   input="golden/꽃등심.png", seed=42,
                   params={"instruction": "...", "steps": 28}) as run:
        pipe = load_model(); run.mark_load_done()      # load_s 마감
        out = generate(...);  run.set_output(out_path) # infer_s 마감
        run.add_metrics({"identity_dino": 0.91})
        run.add_llm_usage(model="qwen3-vl-4b", tok_in=120, tok_out=40)
        run.set_verdict("kontext win")
    # __exit__: timing/vram_peak 계산 후 runs.jsonl 1행 append (예외 시 error 필드 포함)

원장 스키마는 DIRECTION_v2 §4 와 1:1. 시간/VRAM 은 자동, 지표/usage 는 호출자가 채운다.
"""
from __future__ import annotations

import json
import logging
import subprocess
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# 원장 위치: backend/experiments/runs.jsonl (repo 상대). 이미지 산출물과 분리.
_HARNESS_DIR = Path(__file__).resolve().parents[2] / "experiments"
RUNS_PATH = _HARNESS_DIR / "runs.jsonl"


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(Path(__file__).resolve().parents[3]), stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return ""


def _vram_peak_gb() -> float:
    try:
        import torch

        if torch.cuda.is_available():
            return round(torch.cuda.max_memory_allocated() / 1024**3, 2)
    except Exception:
        pass
    return 0.0


def _vram_reset() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except Exception:
        pass


def _vram_free_gb() -> float:
    """현재 GPU 여유(GB). mem_get_info 는 PyTorch 밖 점유(onnxruntime 등)까지 반영."""
    try:
        import torch

        if torch.cuda.is_available():
            free, _ = torch.cuda.mem_get_info()
            return round(free / 1024**3, 2)
    except Exception:
        pass
    return 0.0


def _vram_stats() -> dict:
    """OOM 진단용 VRAM 스냅샷(연정 PDF #7). allocated 만 보면 PyTorch 밖 점유를 놓친다
    — 예: rembg onnxruntime 아레나. free(=total-전체점유)와 대조해야 원인이 보인다."""
    out = {"peak_allocated_gb": 0.0, "peak_reserved_gb": 0.0,
           "free_after_gb": 0.0, "total_gb": 0.0}
    try:
        import torch

        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            out.update(
                peak_allocated_gb=round(torch.cuda.max_memory_allocated() / 1024**3, 2),
                peak_reserved_gb=round(torch.cuda.max_memory_reserved() / 1024**3, 2),
                free_after_gb=round(free / 1024**3, 2),
                total_gb=round(total / 1024**3, 2),
            )
    except Exception:
        pass
    return out


class RunLogger:
    """1 실행 = 1 원장 행. 컨텍스트 매니저로 시간·VRAM 자동 계측."""

    def __init__(
        self,
        phase: str,
        mode: str,
        engine: str,
        input: str,
        seed: Optional[int] = None,
        params: Optional[dict] = None,
        runs_path: Path = RUNS_PATH,
        auto_llm: bool = True,
    ) -> None:
        self.record: dict[str, Any] = {
            "run_id": datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4],
            "git_sha": _git_sha(),
            "phase": phase,
            "mode": mode,
            "engine": engine,
            "input": input,
            "seed": seed,
            "params": params or {},
            "metrics": {"openai_calls": 0, "openai_tokens": 0, "openai_cost_usd": 0.0},
            "stages": {},
            "timing": {"load_s": None, "infer_s": None, "total_s": None},
            "vram_peak_gb": 0.0,      # = vram.peak_allocated_gb (하위호환)
            "vram": {},               # allocated/reserved/free/total (OOM 진단, 연정 PDF #7)
            "llm_usage": [],
            "image_api": [],          # 이미지 생성/편집 API 호출 (v6 T0: 하이브리드 비용축)
            "gpu_used": None,         # False=API 경로 등 GPU 미사용 명시(GPU 호스트 오계상 방지)
            "kpi": None,              # __exit__ 에서 파생되는 비용/시간/품질 3축 요약
            "output": None,
            "verdict": "",
            "notes": "",
            "error": None,
        }
        self._runs_path = runs_path
        self._auto_llm = auto_llm
        self._usage_start: Optional[int] = None
        self._t0 = 0.0
        self._t_load: Optional[float] = None
        self._free_before = 0.0

    # --- 컨텍스트 ---
    def __enter__(self) -> "RunLogger":
        _vram_reset()
        self._free_before = _vram_free_gb()
        if self._auto_llm:
            try:
                from ..services import gpt_service

                self._usage_start = len(gpt_service.API_USAGE_LOG)
            except Exception:
                self._usage_start = None
        self._t0 = time.perf_counter()
        return self

    def _capture_llm(self) -> None:
        """블록 동안 gpt_service 에 쌓인 OpenAI usage 를 전부 자동 기록(비용 환산 포함).

        analyze_menu·detect_material·generate_copy 등 어떤 호출이든 놓치지 않는다.
        """
        if self._usage_start is None:
            return
        try:
            from ..services import gpt_service

            from .pricing import cost_of

            for u in gpt_service.API_USAGE_LOG[self._usage_start:]:
                model = getattr(gpt_service, "GPT_MODEL", "gpt-5.4-mini")
                ti, to = u.prompt_tokens, u.completion_tokens
                self.record["llm_usage"].append(
                    {"model": model, "label": u.label, "tok_in": ti, "tok_out": to,
                     "cost_usd": cost_of(model, ti, to)}
                )
            usage = self.record["llm_usage"]
            self.record["metrics"].update(
                openai_calls=len(usage),
                openai_tokens=sum(item["tok_in"] + item["tok_out"] for item in usage),
                openai_cost_usd=round(sum(item["cost_usd"] for item in usage), 8),
            )
        except Exception:
            pass

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        total = time.perf_counter() - self._t0
        self.record["timing"]["total_s"] = round(total, 2)
        if self.record["timing"]["infer_s"] is None:
            # set_output 을 안 불렀으면 infer_s = 로드 이후 전체
            load = self.record["timing"]["load_s"] or 0.0
            self.record["timing"]["infer_s"] = round(total - load, 2)
        stats = _vram_stats()
        stats["free_before_gb"] = self._free_before
        self.record["vram"] = stats
        self.record["vram_peak_gb"] = stats["peak_allocated_gb"]
        self._capture_llm()
        self.record["kpi"] = self._build_kpi()
        if exc is not None:
            self.record["error"] = f"{exc_type.__name__}: {exc}"
        self._append()
        self._push_kpi_scores()
        return False  # 예외 재전파(기록만 하고 삼키지 않음)

    def _build_kpi(self) -> dict:
        """원장 행에서 비용/시간/품질 3축을 파생한다 (v6 T0 — 서비스 핵심 KPI).

        - 비용: OpenAI 텍스트(자동 캡처) + 이미지 API(장당) + GPU 점유 환산.
          GPU 초는 "요청이 GPU 호스트를 점유한 벽시계 시간" 근사 = total_s (CUDA 가용 시).
          단일 워커가 요청을 직렬 처리하는 현 구조(GPU busy 락)에서는 벽시계=점유로 타당.
        - 품질: inline_gate 통과여부 + 심미/판정 점수 — 채워진 것만, 없으면 None 유지
          (null도 정보다: 어떤 축이 미계측인지 집계에서 드러나야 한다).
        """
        from .pricing import gpu_cost_of

        m = self.record["metrics"]
        t = self.record["timing"]
        gpu_s = 0.0
        try:
            import torch

            # gpu_used=False 명시(API 경로 등)면 GPU 호스트여도 점유 0 — 하이브리드 A/B 공정성.
            if torch.cuda.is_available() and self.record.get("gpu_used") is not False:
                gpu_s = float(t["total_s"] or 0.0)
        except Exception:  # noqa: BLE001 — torch 미설치(로컬 CPU 테스트)면 GPU 비용 0
            pass
        openai_usd = float(m.get("openai_cost_usd", 0.0))
        image_usd = round(sum(i.get("cost_usd", 0.0) for i in self.record["image_api"]), 6)
        gpu_usd = gpu_cost_of(gpu_s)
        gate = m.get("gate")
        gate_passed = gate.get("pass") if isinstance(gate, dict) else None
        return {
            "cost": {
                "openai_usd": openai_usd,
                "image_api_usd": image_usd,
                "gpu_s": round(gpu_s, 2),
                "gpu_usd_est": gpu_usd,
                "total_usd": round(openai_usd + image_usd + gpu_usd, 6),
            },
            "time": {"total_s": t["total_s"], "load_s": t["load_s"], "infer_s": t["infer_s"]},
            "quality": {
                "gate_passed": gate_passed,
                "aesthetic": m.get("aesthetic"),
                "judge_score": m.get("judge_score"),
                "identity": m.get("identity_dino"),
            },
        }

    def _push_kpi_scores(self) -> None:
        """KPI 3축을 현재 Langfuse 트레이스 score 로 push — 실패해도 원장은 이미 저장됨."""
        try:
            from ..core.observability import push_kpi_scores

            push_kpi_scores(self.record["run_id"], self.record["kpi"])
        except Exception:  # noqa: BLE001 — 트레이싱 장애가 생성 응답을 실패시키면 안 됨
            logging.getLogger(__name__).debug("KPI score push 실패(무해)", exc_info=True)

    # --- 계측 마커 ---
    def mark_load_done(self) -> None:
        """모델 로드 완료 시점 — load_s 마감, 이후는 추론 구간."""
        self._t_load = time.perf_counter()
        self.record["timing"]["load_s"] = round(self._t_load - self._t0, 2)

    def set_output(self, path: str) -> None:
        """결과 이미지 경로 + infer_s 마감."""
        self.record["output"] = str(path)
        end = time.perf_counter()
        base = self._t_load if self._t_load is not None else self._t0
        self.record["timing"]["infer_s"] = round(end - base, 2)

    def set_meta(self, **kw: Any) -> None:
        """생성 도중 확정되는 mode/engine/seed 등을 원장에 반영한다."""
        for key, value in kw.items():
            if key not in ("ts", "timing"):
                self.record[key] = value

    @contextmanager
    def stage(self, name: str):  # noqa: ANN201
        """한 생성 안의 단계별 누적 소요시간을 기록한다."""
        started = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - started
            previous = self.record["stages"].get(name, 0.0)
            self.record["stages"][name] = round(previous + elapsed, 2)

    # --- 채우기 ---
    def add_metric(self, key: str, value: Any) -> None:
        self.record["metrics"][key] = value

    def add_metrics(self, d: dict) -> None:
        self.record["metrics"].update(d)

    def add_llm_usage(self, model: str, tok_in: int = 0, tok_out: int = 0,
                      cost_usd: Optional[float] = None) -> None:
        """LLM 호출 1건 기록. cost_usd 미지정 시 pricing 으로 토큰→비용 자동 환산."""
        if cost_usd is None:
            from .pricing import cost_of

            cost_usd = cost_of(model, tok_in, tok_out)
        self.record["llm_usage"].append(
            {"model": model, "tok_in": tok_in, "tok_out": tok_out, "cost_usd": cost_usd}
        )

    def add_image_api_usage(self, model: str, n: int = 1,
                            cost_usd: Optional[float] = None) -> None:
        """이미지 생성/편집 API 호출 기록 (v6 T0). cost 미지정 시 장당 단가표로 환산."""
        if cost_usd is None:
            from .pricing import image_cost_of

            cost_usd = image_cost_of(model, n)
        self.record["image_api"].append({"model": model, "n": n, "cost_usd": cost_usd})

    def set_verdict(self, verdict: str) -> None:
        self.record["verdict"] = verdict

    def note(self, text: str) -> None:
        self.record["notes"] = (self.record["notes"] + " " + text).strip()

    # --- 저장 ---
    def _append(self) -> None:
        try:
            self._runs_path.parent.mkdir(parents=True, exist_ok=True)
            with self._runs_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(self.record, ensure_ascii=False) + "\n")
        except OSError as exc:
            # 계측 저장 장애가 이미 완성된 광고 응답을 실패시키면 안 된다.
            logging.getLogger(__name__).warning("RunLogger 원장 저장 실패: %s", exc)
