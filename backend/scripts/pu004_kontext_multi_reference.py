"""PU-004: diffusers community Kontext 다중 참조 파이프라인 단일 실측."""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import torch
from PIL import Image, ImageDraw, ImageFont, ImageOps

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services import kontext_service  # noqa: E402


def _load_pipeline(source: Path):  # noqa: ANN202
    base = kontext_service._load_kontext()
    spec = importlib.util.spec_from_file_location("kontext_multi", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load community pipeline: {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FluxKontextPipeline(**base.components)


def run(target: Path, reference: Path, source: Path, output: Path,
        seed: int, steps: int, mode: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    pipe = _load_pipeline(source)
    target_image = Image.open(target).convert("RGB")
    reference_image = Image.open(reference).convert("RGB")
    editorial_prompt = (
        "Create one seamless square editorial cafe latte advertisement. Image 1 is the exact "
        "product identity source: preserve its black cup, saucer, latte art, proportions and "
        "drink faithfully. Image 2 is composition evidence only: borrow its low camera angle, "
        "airy pale-blue lighting, architectural pedestal rhythm and generous right-side copy "
        "space. Do not copy image 2's bottle, logo, text or product. No added ingredients, "
        "no hands, no letters, no watermark."
    )
    pop_prompt = (
        "Create one seamless square pop-art cafe latte advertisement. Image 1 is the exact "
        "product identity source: preserve its black cup, saucer, latte art, proportions and "
        "drink faithfully. Image 2 is composition evidence only: borrow its saturated color "
        "blocking, crisp hard shadows, asymmetric product grouping and energetic commercial "
        "rhythm. Replace its orange-yellow palette with cobalt blue and coral accents. Do not "
        "copy image 2's packages, fruit, glass, text, logos or props. No added ingredients, "
        "no hands, no letters, no watermark."
    )
    prompt = pop_prompt if mode == "pop" else editorial_prompt
    result = pipe(
        multiple_images=(target_image, reference_image),
        prompt=f"{mode} cafe latte advertising photograph",
        prompt_2=prompt,
        guidance_scale=2.5,
        num_inference_steps=steps,
        generator=torch.Generator("cuda").manual_seed(seed),
    ).images[0]
    result_path = output / "pu004_multi_reference.png"
    result.save(result_path)

    cells = [("TARGET", target_image), ("REFERENCE", reference_image),
             ("MULTI-REFERENCE", result)]
    size, label_h = 560, 42
    canvas = Image.new("RGB", (size * len(cells), size + label_h), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(str(BACKEND_DIR / "assets/fonts/Pretendard-Bold.otf"), 22)
    for index, (label, image) in enumerate(cells):
        cell = ImageOps.contain(image, (size - 12, size - 12), Image.Resampling.LANCZOS)
        canvas.paste(cell, (index * size + (size - cell.width) // 2,
                            (size - cell.height) // 2))
        draw.text((index * size + 10, size + 8), label, font=font, fill="black")
    canvas.save(output / "pu004_multi_reference_grid.jpg", quality=94)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--pipeline-source", required=True)
    parser.add_argument("--output", default="/tmp/pu004_multiref")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--steps", type=int, default=12)
    parser.add_argument("--mode", choices=("editorial", "pop"), default="editorial")
    args = parser.parse_args()
    run(Path(args.target), Path(args.reference), Path(args.pipeline_source),
        Path(args.output), args.seed, args.steps, args.mode)


if __name__ == "__main__":
    main()
