"""STY-005: 스테이크와 카페라떼의 레퍼런스 StylePlan 6무드 연속 생성.

두 도메인을 한 프로세스에서 실행해 Kontext 모델 로드를 한 번만 부담한다.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sty003_reference_plan_six import run_profile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steak", required=True)
    parser.add_argument("--latte", required=True)
    parser.add_argument("--output", default="/tmp/sty005_food_drink")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--steps", type=int, default=12)
    args = parser.parse_args()

    output_root = Path(args.output)
    started = time.perf_counter()
    summaries = [
        run_profile(Path(args.steak), output_root / "steak", "steak", args.seed, args.steps),
        run_profile(Path(args.latte), output_root / "latte", "latte", args.seed, args.steps),
    ]
    batch_summary = {
        "seed": args.seed,
        "steps": args.steps,
        "wall_seconds": round(time.perf_counter() - started, 2),
        "jobs": summaries,
    }
    (output_root / "sty005_batch_summary.json").write_text(
        json.dumps(batch_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(batch_summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
