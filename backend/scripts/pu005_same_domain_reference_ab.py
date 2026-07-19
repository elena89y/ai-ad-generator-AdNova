"""PU-005: 라떼·투명 홍차 동일도메인 conditioning A/B 게이트.

A는 원본 한 장 + 텍스트 recipe, B는 같은 원본/프롬프트/seed에 육안 승인대기인
동일 상품군 identity reference 한 장만 추가한다. 레퍼런스 효과 외 변수를 고정한다.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import torch
from PIL import Image, ImageDraw, ImageFont, ImageOps

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services import kontext_service  # noqa: E402


CASES = {
    "latte": (
        "Create one seamless square Korean cafe latte advertising photograph. Preserve image 1's "
        "exact black ceramic cup, saucer, handle, latte color, foam art and proportions. Stage one "
        "single hero on an airy warm-neutral tabletop with soft window light and generous clean "
        "copy space at upper left. Image 2, when present, is identity and material evidence only: "
        "borrow realistic milk-coffee translucency, foam texture and photographic finish, not its "
        "glass vessel, cocoa topping, napkin or table. No added ingredients, no hands, no packages, "
        "no letters, no logo, no watermark."
    ),
    "transparent_tea": (
        "Create one seamless square Korean cafe transparent iced tea advertising photograph. "
        "Preserve image 1's exact tall clear glass, amber-red liquid, ice, lemon, berries, straw and "
        "proportions. Stage one single hero on an airy warm-neutral tabletop with soft window light "
        "and generous clean copy space at upper left. Image 2, when present, is identity and material "
        "evidence only: borrow realistic transparent amber tea, ice refraction and condensation, not "
        "its mug shape, background objects or extra garnish. Do not invent, alter or duplicate any "
        "package text. No added ingredients, no hands, no new letters, no new logo, no watermark."
    ),
}


def _load_pipeline(source: Path):  # noqa: ANN202
    base = kontext_service._load_kontext()
    spec = importlib.util.spec_from_file_location("kontext_multi", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load community pipeline: {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FluxKontextPipeline(**base.components)


def _render(pipe, images: tuple[Image.Image, ...], prompt: str,
            seed: int, steps: int) -> Image.Image:
    kwargs = {
        "prompt": "commercial drink advertising photograph",
        "prompt_2": prompt,
        "guidance_scale": 2.5,
        "num_inference_steps": steps,
        "generator": torch.Generator("cuda").manual_seed(seed),
    }
    if len(images) == 1:
        kwargs["image"] = images[0]
    else:
        kwargs["multiple_images"] = images
    return pipe(**kwargs).images[0]


def _grid(target: Image.Image, reference: Image.Image,
          text_only: Image.Image, conditioned: Image.Image) -> Image.Image:
    cells = (("TARGET", target), ("IDENTITY REF", reference),
             ("A TEXT ONLY", text_only), ("B + IDENTITY REF", conditioned))
    size, label_h = 500, 42
    canvas = Image.new("RGB", (size * 2, (size + label_h) * 2), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(str(BACKEND_DIR / "assets/fonts/Pretendard-Bold.otf"), 20)
    for index, (label, image) in enumerate(cells):
        col, row = index % 2, index // 2
        cell = ImageOps.contain(image, (size - 12, size - 12), Image.Resampling.LANCZOS)
        x = col * size + (size - cell.width) // 2
        y = row * (size + label_h) + (size - cell.height) // 2
        canvas.paste(cell, (x, y))
        draw.text((col * size + 10, row * (size + label_h) + size + 8),
                  label, font=font, fill="black")
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--latte-target", required=True)
    parser.add_argument("--latte-reference", required=True)
    parser.add_argument("--tea-target", required=True)
    parser.add_argument("--tea-reference", required=True)
    parser.add_argument("--pipeline-source", required=True)
    parser.add_argument("--output", default="/tmp/pu005_same_domain_ab")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--steps", type=int, default=12)
    parser.add_argument("--case", choices=("all", "latte", "transparent_tea"), default="all")
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    pipe = _load_pipeline(Path(args.pipeline_source))
    summary = {"seed": args.seed, "steps": args.steps, "cases": {}}
    started = time.perf_counter()
    inputs = {
        "latte": (Path(args.latte_target), Path(args.latte_reference)),
        "transparent_tea": (Path(args.tea_target), Path(args.tea_reference)),
    }
    if args.case != "all":
        inputs = {args.case: inputs[args.case]}
    for index, (name, (target_path, reference_path)) in enumerate(inputs.items()):
        target = Image.open(target_path).convert("RGB")
        reference = Image.open(reference_path).convert("RGB")
        case_started = time.perf_counter()
        text_only = _render(pipe, (target,), CASES[name], args.seed + index, args.steps)
        conditioned = _render(pipe, (target, reference), CASES[name],
                              args.seed + index, args.steps)
        text_only.save(output / f"{name}_a_text_only.png")
        conditioned.save(output / f"{name}_b_identity_reference.png")
        _grid(target, reference, text_only, conditioned).save(
            output / f"{name}_ab_grid.jpg", quality=94)
        summary["cases"][name] = {
            "target": str(target_path), "reference": str(reference_path),
            "wall_seconds": round(time.perf_counter() - case_started, 2),
        }
    summary["wall_seconds"] = round(time.perf_counter() - started, 2)
    (output / "pu005_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
