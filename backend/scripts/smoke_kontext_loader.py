"""Kontext loader smoke test for shared HF cache / Fill-component refactor.

목적:
  - HF_HOME/HF_HUB_CACHE 공용 캐시가 적용됐는지 확인
  - kontext_service._load_kontext() 가 FLUX Fill 파이프라인 전체가 아니라
    Fill 서브컴포넌트(T5/CLIP/VAE/tokenizer) + Kontext GGUF 로 로드되는지 확인

실행 예:
  cd /home/spai0820/ai-ad-generator-AdNova
  PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    .venv/bin/python backend/scripts/smoke_kontext_loader.py

생성까지 확인:
  PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    .venv/bin/python backend/scripts/smoke_kontext_loader.py \
      --image backend/uploads/golden/beef_marbled.png \
      --subject "marbled beef" \
      --steps 4
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(ROOT / "backend" / ".env")


def _cuda_summary() -> str:
    try:
        import torch
        if not torch.cuda.is_available():
            return "cuda=unavailable"
        free, total = torch.cuda.mem_get_info()
        return f"cuda=ok free={free / 1024**3:.1f}GB total={total / 1024**3:.1f}GB"
    except Exception as e:  # noqa: BLE001
        return f"cuda=error {type(e).__name__}: {e}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=None, help="optional image path for a tiny edit run")
    parser.add_argument("--subject", default="food", help="English subject for optional edit")
    parser.add_argument("--steps", type=int, default=4, help="steps for optional edit")
    args = parser.parse_args()

    print(f"HF_HOME={os.environ.get('HF_HOME', '')}")
    print(f"HF_HUB_CACHE={os.environ.get('HF_HUB_CACHE', '')}")
    print(_cuda_summary())

    from app.services import kontext_service

    t0 = time.time()
    pipe = kontext_service._load_kontext()  # noqa: SLF001 - smoke test for loader internals
    print(f"LOAD_SECONDS={time.time() - t0:.2f}")
    print(f"PIPELINE={pipe.__class__.__name__}")
    print(_cuda_summary())

    if args.image:
        image = Path(args.image)
        if not image.is_file():
            raise SystemExit(f"file not found: {image}")
        instr = kontext_service.build_instruction("A-hero", args.subject)
        t0 = time.time()
        out = kontext_service.edit(str(image), instr, steps=args.steps)
        print(f"EDIT_SECONDS={time.time() - t0:.2f}")
        print(f"OUTPUT={out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
