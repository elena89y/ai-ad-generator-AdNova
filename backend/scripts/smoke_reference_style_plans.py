"""레퍼런스 StylePlan 배포 전 비GPU smoke."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services.reference_style_plans import (
    build_clip_anchor,
    build_reference_instruction,
    get_reference_plan,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input")
    parser.add_argument("--output", default="/tmp/reference_style_smoke")
    parser.add_argument("--style", default="pop")
    parser.add_argument("--domain", default="drink")
    parser.add_argument("--subject", default="cafe latte")
    parser.add_argument("--steps", type=int, default=12)
    args = parser.parse_args()

    for domain in ("food", "drink", "object"):
        for style in ("editorial", "pop", "realism", "pastel_float", "monotone", "warm_vintage"):
            plan = get_reference_plan(style, domain)
            assert plan is not None, (domain, style)
            instruction = build_reference_instruction(style, domain, "smoke subject")
            assert instruction and "Change only" in instruction, (domain, style)
            clip_anchor = build_clip_anchor(style, domain, "smoke subject")
            assert clip_anchor and len(clip_anchor.split()) < 30, (domain, style)

    assert get_reference_plan("cross_section", "food") is None
    print("REFERENCE_STYLE_PLAN_SMOKE_OK plans=18 special_format_fallback=1")

    if args.input:
        from app.services.style_gen import generate_scene

        result = generate_scene(
            args.input,
            args.style,
            args.subject,
            output_dir=args.output,
            seed=42,
            steps=args.steps,
            domain=args.domain,
        )
        print(f"REFERENCE_STYLE_GENERATION_OK output={result}")


if __name__ == "__main__":
    main()
