"""원본 한 장에서 상세페이지 필수 구도 4종 후보를 독립 생성한다."""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import kontext_service

ROLE_PROMPTS = {
    "top_view": "Rotate the camera to an exact 90-degree bird's-eye view directly above the product. The lens axis must be perpendicular to the tabletop. The cup rim must appear as a centered circle and the cup side wall must not be visible. Preserve the exact same product, vessel, handle, color, contents and quantity. Clean tabletop, no added props, no hands, no text, no logo, no watermark.",
    "texture_closeup": "Edit into a tight macro detail photograph of the product's real surface texture. Preserve exact ingredients, color and material. Crop close without inventing garnish or changing the vessel, no hands, no text, no logo, no watermark.",
    "side_profile": "Edit into a true eye-level side profile product photograph. Preserve the exact same vessel silhouette, handle, contents, color and proportions. Clean neutral background, no added props, no hands, no text, no logo, no watermark.",
    "lifestyle": "Edit into a restrained Korean cafe tabletop usage scene with the exact same product as the only hero. Preserve vessel, contents, color and proportions. Soft natural window light, empty copy space, no people, no hands, no packages, no text, no logo, no watermark.",
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="/tmp/detail_multishot")
    parser.add_argument("--steps", type=int, default=12)
    parser.add_argument("--roles", nargs="+", choices=tuple(ROLE_PROMPTS), default=list(ROLE_PROMPTS))
    args = parser.parse_args()
    output = Path(args.output); output.mkdir(parents=True, exist_ok=True)
    summary = {"input": args.input, "steps": args.steps, "roles": {}}
    for role in args.roles:
        prompt = ROLE_PROMPTS[role]
        started = time.perf_counter()
        path = kontext_service.edit(args.input, prompt, steps=args.steps, output_dir=str(output))
        target = output / f"{role}.png"
        Path(path).replace(target)
        summary["roles"][role] = {"path": str(target), "seconds": round(time.perf_counter()-started, 2)}
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)

if __name__ == "__main__":
    main()
