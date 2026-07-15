"""GPT judge LangChain batch smoke test.

목적: 생성 모델 없이 기존 이미지 2장만 GPT Vision judge 에 넣어
judge_service.pick_best() → with_structured_output + chain.batch() 경로를 검증한다.

실행 예:
  cd /home/spai0820/ai-ad-generator-AdNova
  .venv/bin/python backend/scripts/smoke_judge_batch.py \
    --original backend/uploads/golden/beef_marbled.png \
    backend/results/ai/food_realvis/beef_ba_str050.png \
    backend/results/ai/food_batch_local/poster_beef.png
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(ROOT / "backend" / ".env")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidates", nargs="+", help="candidate image paths, at least 2")
    parser.add_argument("--original", default=None, help="original reference image path")
    args = parser.parse_args()

    cands = [str(Path(p)) for p in args.candidates]
    if len(cands) < 2:
        raise SystemExit("candidate image paths are required: at least 2")
    for p in cands + ([args.original] if args.original else []):
        if p and not Path(p).is_file():
            raise SystemExit(f"file not found: {p}")

    from app.services import gpt_service, judge_service

    t0 = time.time()
    best, scores = judge_service.pick_best(cands, original_path=args.original)
    elapsed = time.time() - t0

    print(f"BEST={best}")
    print(f"SECONDS={elapsed:.2f}")
    for path, score in zip(cands, scores):
        print(
            f"SCORE {Path(path).name}: overall={score.overall}, "
            f"appeal={score.appeal}, realism={score.realism}, identity={score.identity}, "
            f"reason={score.reason}"
        )
    print("USAGE")
    print(gpt_service.usage_summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
