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
import subprocess
import time
import uuid
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
            "metrics": {},
            "timing": {"load_s": None, "infer_s": None, "total_s": None},
            "vram_peak_gb": 0.0,
            "llm_usage": [],
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

    # --- 컨텍스트 ---
    def __enter__(self) -> "RunLogger":
        _vram_reset()
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
        except Exception:
            pass

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        total = time.perf_counter() - self._t0
        self.record["timing"]["total_s"] = round(total, 2)
        if self.record["timing"]["infer_s"] is None:
            # set_output 을 안 불렀으면 infer_s = 로드 이후 전체
            load = self.record["timing"]["load_s"] or 0.0
            self.record["timing"]["infer_s"] = round(total - load, 2)
        self.record["vram_peak_gb"] = _vram_peak_gb()
        self._capture_llm()
        if exc is not None:
            self.record["error"] = f"{exc_type.__name__}: {exc}"
        self._append()
        return False  # 예외 재전파(기록만 하고 삼키지 않음)

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

    def set_verdict(self, verdict: str) -> None:
        self.record["verdict"] = verdict

    def note(self, text: str) -> None:
        self.record["notes"] = (self.record["notes"] + " " + text).strip()

    # --- 저장 ---
    def _append(self) -> None:
        self._runs_path.parent.mkdir(parents=True, exist_ok=True)
        with self._runs_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(self.record, ensure_ascii=False) + "\n")
