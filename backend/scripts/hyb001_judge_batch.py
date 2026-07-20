"""HYB-001 품질축(judge) 배치 — 담당: 한의정. (DIRECTION_v6 T3, 게이트 G3 마무리)

3암 최신 결과(암·입력별 last-wins, error 제외)를 GPT Vision judge_ad 로 원본 대조 채점한다.
비용: 36건 × Vision ≈ $0.4 내외 — API_BUDGET_USD 가드는 이미지 편집 전용이라 별도로,
호출 수 자체가 고정(36)이라 상한이 명확하다. usage 는 기존 $30 장부에 합산.

산출: experiments/hyb001_judge.jsonl (행별) + stdout 에 암별 평균표.
실행(VM): cd backend && ../.venv/bin/python scripts/hyb001_judge_batch.py --inputs-dir ~/HYB001_inputs
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import sys

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_BACKEND / ".env")

RUNS = _BACKEND / "experiments" / "runs.jsonl"
ARMS = ("local", "api", "hybrid")


def _latest_rows(phase: str) -> dict[tuple[str, str], dict]:
    """(암, 입력) → 최신 유효 행. 러너 summary 와 동일한 last-wins·error 제외 규칙."""
    latest: dict[tuple[str, str], dict] = {}
    for line in RUNS.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("phase") != phase or not rec.get("kpi"):
            continue
        arm = rec.get("params", {}).get("arm")
        if arm in ARMS:
            latest[(arm, rec.get("input", ""))] = rec
    return {k: r for k, r in latest.items() if not r.get("error") and r.get("output")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs-dir", required=True)
    parser.add_argument("--phase", default="HYB-001",
                        help="채점 대상 phase (예: HOLDOUT-001)")
    args = parser.parse_args()
    inputs_dir = Path(args.inputs_dir).expanduser()
    out_path = _BACKEND / "experiments" / (
        args.phase.lower().replace("-", "") + "_judge.jsonl")

    from app.services import gpt_service

    rows = _latest_rows(args.phase)
    print(f"채점 대상 {len(rows)}건 (예상 Vision 호출 {len(rows)}회)")
    per_arm: dict[str, list[float]] = {a: [] for a in ARMS}
    with out_path.open("a", encoding="utf-8") as f:
        for (arm, name), rec in sorted(rows.items()):
            original = inputs_dir / name
            if not original.exists():
                print(f"skip(원본 없음): {arm}/{name}")
                continue
            try:
                scores = gpt_service.judge_ad(
                    rec["output"],
                    instruction="re-stage as a professional advertisement while preserving identity",
                    ref_path=str(original))
            except Exception as exc:  # noqa: BLE001 — 1건 실패가 배치를 죽이면 안 됨
                print(f"fail: {arm}/{name}: {exc}")
                continue
            row = {"run_id": rec["run_id"], "arm": arm, "input": name, **scores}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            if isinstance(scores.get("overall"), (int, float)):
                per_arm[arm].append(float(scores["overall"]))
            print(f"{arm:6s} {name:24s} overall={scores.get('overall')} "
                  f"identity-adherence={scores.get('adherence')}")

    print("\n| 암 | n | judge overall (mean) | p50 |")
    print("|---|---|---|---|")
    for arm in ARMS:
        vals = per_arm[arm]
        if vals:
            print(f"| {arm} | {len(vals)} | {sum(vals)/len(vals):.2f} "
                  f"| {statistics.median(vals):.1f} |")
    print(f"\n→ 행별 기록: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
