"""같은 입력의 6무드 생성 결과에 Phase 3 색 마감을 적용해 비교표를 만든다."""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.services import style_finish

STYLES = ("editorial", "pop", "realism", "pastel", "monotone", "warm_organic")
FINISH_KEYS = {
    "editorial": "editorial",
    "pop": "pop",
    "realism": "realism",
    "pastel": "pastel_float",
    "monotone": "monotone",
    "warm_organic": "warm_vintage",
}


def _contact_sheet(paths: list[Path], output: Path) -> None:
    thumbs = []
    for path in paths:
        image = Image.open(path).convert("RGB")
        image.thumbnail((420, 525), Image.Resampling.LANCZOS)
        thumbs.append((path.stem.replace("_finish", ""), image.copy()))

    cell_w, cell_h = 440, 575
    sheet = Image.new("RGB", (cell_w * 3, cell_h * 2), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, (label, image) in enumerate(thumbs):
        x = (index % 3) * cell_w + (cell_w - image.width) // 2
        y = (index // 3) * cell_h + 38
        sheet.paste(image, (x, y))
        draw.text(((index % 3) * cell_w + 12, (index // 3) * cell_h + 10),
                  label, fill="black", font=font)
    sheet.save(output, quality=94)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--strength", type=float, default=0.6)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    finished_paths = []
    report = {"strength": args.strength, "styles": {}}
    for style in STYLES:
        source = args.input_dir / f"{style}.png"
        if not source.exists():
            raise FileNotFoundError(source)
        staged = args.output_dir / f"{style}.png"
        shutil.copy2(source, staged)
        started = time.perf_counter()
        finished = Path(style_finish.apply(
            str(staged), FINISH_KEYS[style], strength=args.strength,
        ))
        duration_ms = (time.perf_counter() - started) * 1000.0
        before_pixels = np.asarray(Image.open(staged).convert("RGB"), dtype=np.float32) / 255.0
        after_pixels = np.asarray(Image.open(finished).convert("RGB"), dtype=np.float32) / 255.0
        delta = np.abs(after_pixels - before_pixels).mean(axis=2)
        height, width = delta.shape
        center = delta[int(height * 0.28):int(height * 0.72),
                       int(width * 0.25):int(width * 0.75)]
        border = np.concatenate((
            delta[:int(height * 0.18)].ravel(),
            delta[-int(height * 0.18):].ravel(),
            delta[:, :int(width * 0.15)].ravel(),
            delta[:, -int(width * 0.15):].ravel(),
        ))
        finished_paths.append(finished)
        report["styles"][style] = {
            "duration_ms": round(duration_ms, 2),
            "center_delta": round(float(center.mean()), 5),
            "background_delta": round(float(border.mean()), 5),
            "before": style_finish.style_stats(str(staged), background_only=True),
            "after": style_finish.style_stats(str(finished), background_only=True),
        }

    _contact_sheet(finished_paths, args.output_dir / "v3p3_finish_comparison.jpg")
    (args.output_dir / "v3p3_finish_stats.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )


if __name__ == "__main__":
    main()
