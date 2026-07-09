"""runs.jsonl → markdown 집계 리포트 — 담당: 한의정.

실행: python -m app.harness.report            # experiments/report.md 생성 + 요약 출력
      python -m app.harness.report --phase P0 # 특정 Phase만

순수 파이썬(pandas 불필요) — 이식성 우선. 그룹(phase/engine/mode)별 지표 평균 + 카운트.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Optional

from .run_logger import RUNS_PATH

REPORT_PATH = RUNS_PATH.parent / "report.md"

# 리포트에 노출할 지표 컬럼(순서대로). 중첩 키는 점 표기.
_METRIC_COLS = [
    "metrics.identity_dino", "metrics.identity_lpips",
    "metrics.aesthetic.imagereward", "metrics.aesthetic.hps",
    "metrics.judge.total", "timing.load_s", "timing.infer_s",
    "timing.total_s", "vram_peak_gb",
]


def load_runs(path: Path = RUNS_PATH) -> list[dict]:
    if not path.is_file():
        return []
    runs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                runs.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return runs


def _get(d: dict, dotted: str) -> Any:
    cur: Any = d
    for k in dotted.split("."):
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return None
    return cur


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def _mean(vals: list[Any]) -> Optional[float]:
    nums = [v for v in vals if isinstance(v, (int, float))]
    return round(sum(nums) / len(nums), 3) if nums else None


def group_summary(runs: list[dict], keys: tuple[str, ...] = ("phase", "engine", "mode")) -> str:
    """그룹별 지표 평균 + 카운트 markdown 표."""
    groups: dict[tuple, list[dict]] = {}
    for r in runs:
        gk = tuple(str(r.get(k, "")) for k in keys)
        groups.setdefault(gk, []).append(r)

    def _sum(r: dict, field: str) -> float:
        return sum(u.get(field, 0) for u in r.get("llm_usage", []))

    def _models(rs: list[dict]) -> str:
        """그룹에서 쓴 모델·label 별 호출수 요약 (로컬 전환 증거)."""
        from collections import Counter

        c: Counter = Counter()
        for r in rs:
            for u in r.get("llm_usage", []):
                c[u.get("model", "?")] += 1
        return "<br>".join(f"{k}×{v}" for k, v in c.most_common()) or "—"

    short = [c.split(".")[-1] for c in _METRIC_COLS] + ["models", "tok_in", "tok_out", "$/run", "$_group"]
    header = "| " + " | ".join(keys) + " | n | " + " | ".join(short) + " |"
    sep = "|" + "|".join(["---"] * (len(keys) + 1 + len(short))) + "|"
    rows = [header, sep]
    grand = 0.0
    for gk in sorted(groups):
        rs = groups[gk]
        cells = [_fmt(_mean([_get(r, c) for r in rs])) for c in _METRIC_COLS]
        ti = _mean([_sum(r, "tok_in") for r in rs]) or 0
        to = _mean([_sum(r, "tok_out") for r in rs]) or 0
        grp_cost = sum(_sum(r, "cost_usd") for r in rs)      # 그룹 누적 비용
        per_run = _mean([_sum(r, "cost_usd") for r in rs]) or 0.0  # 실행당 평균 비용
        grand += grp_cost
        cells += [_models(rs), str(int(ti)), str(int(to)), f"${per_run:.5f}", f"${grp_cost:.5f}"]
        rows.append("| " + " | ".join(gk) + f" | {len(rs)} | " + " | ".join(cells) + " |")
    table = "\n".join(rows)
    return table + f"\n\n합계 실행 {len(runs)}건 · **누적 OpenAI 비용 ${grand:.5f}**"


def write_report(phase: Optional[str] = None, out: Path = REPORT_PATH) -> str:
    runs = load_runs()
    if phase:
        runs = [r for r in runs if r.get("phase") == phase]
    if not runs:
        msg = f"# AdNova 실험 리포트\n\n(runs.jsonl 비어있음{f' / phase={phase}' if phase else ''})\n"
        out.write_text(msg, encoding="utf-8")
        return msg
    errs = [r for r in runs if r.get("error")]
    md = (
        f"# AdNova 실험 리포트{f' — {phase}' if phase else ''}\n\n"
        f"## 그룹별 요약 (phase·engine·mode)\n\n{group_summary(runs)}\n\n"
        f"## 실패 실행 {len(errs)}건\n\n"
        + ("\n".join(f"- `{r['run_id']}` {r.get('engine')} — {r['error']}" for r in errs) or "없음")
        + "\n"
    )
    out.write_text(md, encoding="utf-8")
    return md


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default=None)
    args = ap.parse_args()
    print(write_report(args.phase))
    print(f"\n→ {REPORT_PATH}")


if __name__ == "__main__":
    main()
