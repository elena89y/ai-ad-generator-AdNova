"""PU-002: 승인 대기 ReferenceRecipe 기반 라떼 6무드 GPU 시각 게이트."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services import style_gen  # noqa: E402
from app.services.reference_recipe_data import get_reference_recipe  # noqa: E402

MOODS = ("editorial", "pop", "realism", "pastel", "monotone", "warm_organic")


def _comparison(input_path: Path, outputs: list[tuple[str, Path]], destination: Path) -> None:
    cells = [("ORIGINAL", input_path), *[(mood.upper(), path) for mood, path in outputs]]
    cell_w, image_h, label_h, cols = 500, 500, 40, 4
    rows = (len(cells) + cols - 1) // cols
    canvas = Image.new("RGB", (cell_w * cols, (image_h + label_h) * rows), "white")
    draw = ImageDraw.Draw(canvas)
    font_path = BACKEND_DIR / "assets/fonts/Pretendard-Bold.otf"
    font = ImageFont.truetype(str(font_path), 22)
    for index, (label, image_path) in enumerate(cells):
        col, row = index % cols, index // cols
        image = Image.open(image_path).convert("RGB")
        fitted = ImageOps.contain(image, (cell_w - 12, image_h - 12), Image.Resampling.LANCZOS)
        x = col * cell_w + (cell_w - fitted.width) // 2
        y = row * (image_h + label_h) + (image_h - fitted.height) // 2
        canvas.paste(fitted, (x, y))
        draw.text((col * cell_w + 12, row * (image_h + label_h) + image_h + 8),
                  label, font=font, fill="black")
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, quality=94)


def run(input_path: Path, output_dir: Path, seed: int, steps: int,
        container: str, temperature: str, flexible_parts: list[str]) -> None:
    os.environ["REFERENCE_RECIPE_EXPERIMENT"] = "1"
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[tuple[str, Path]] = []
    summary = {
        "input": str(input_path), "seed": seed, "steps": steps,
        "analysis": {
            "container": container,
            "temperature": temperature,
            "flexible_parts": flexible_parts,
        },
        "results": [],
    }
    for mood in MOODS:
        recipe = get_reference_recipe("drink", mood, allow_unapproved=True)
        if recipe is None:
            raise RuntimeError(f"recipe 없음: drink/{mood}")
        result = style_gen.generate_scene(
            str(input_path), mood, "cafe latte", output_dir=str(output_dir / mood),
            seed=seed, steps=steps, domain="drink", staging="recompose",
            container_desc=container,
            temperature=temperature,
            text_zone=recipe.archetype.text_zones[0],
            flexible_parts=flexible_parts,
        )
        destination = output_dir / f"latte_{mood}.png"
        Image.open(result).save(destination)
        outputs.append((mood, destination))
        summary["results"].append({
            "mood": mood,
            "recipe_id": recipe.recipe_id,
            "palette_variant": recipe.palette_variant.variant_id,
            "references": recipe.reference_ids,
            "output": str(destination),
        })
        print(json.dumps(summary["results"][-1], ensure_ascii=False), flush=True)
    comparison = output_dir / "pu002_recipe_staging_grid.jpg"
    _comparison(input_path, outputs, comparison)
    summary["comparison"] = str(comparison)
    (output_dir / "pu002_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"GRID {comparison}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="/tmp/pu002_recipe_staging")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--steps", type=int, default=12)
    parser.add_argument("--container", default="black ceramic cup")
    parser.add_argument("--temperature", choices=("hot", "iced", "unknown"), default="hot")
    parser.add_argument("--flexible-part", action="append", default=["cup"])
    args = parser.parse_args()
    run(Path(args.input), Path(args.output), args.seed, args.steps,
        args.container, args.temperature, args.flexible_part)


if __name__ == "__main__":
    main()
