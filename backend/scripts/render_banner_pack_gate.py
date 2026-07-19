"""기존 GPU 히어로로 v5 커머스 배너 4규격을 렌더하고 연락시트를 만든다."""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.ads import AdPurpose
from app.services.pipeline_v5 import generate_v5
from app.services.pipeline_v5.hero import hero_from_existing


CASES = (
    (
        "latte",
        "/Users/colourxswitch/Desktop/AdNova/PU005_same_domain_reference_ab_20260719/latte_a_text_only.png",
        "오늘의 시그니처 라떼",
        "부드러운 한 잔의 균형",
    ),
    (
        "tea",
        "/Users/colourxswitch/Desktop/AdNova/PU005_same_domain_reference_ab_20260719/transparent_tea_a_text_only.png",
        "한 잔의 여름",
        "과일을 담은 아이스 티",
    ),
)


def _font(size: int):
    path = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "Pretendard-Bold.otf"
    return ImageFont.truetype(str(path), size)


def _contact_sheet(paths: list[str], output: Path) -> None:
    thumbs = []
    for path in paths:
        image = Image.open(path).convert("RGB")
        image.thumbnail((540, 400), Image.LANCZOS)
        tile = Image.new("RGB", (580, 450), "white")
        tile.paste(image, ((580 - image.width) // 2, 35))
        ImageDraw.Draw(tile).text((16, 8), Path(path).stem, font=_font(17), fill=(25, 25, 25))
        thumbs.append(tile)
    sheet = Image.new("RGB", (1160, ((len(thumbs) + 1) // 2) * 450), (238, 238, 238))
    for index, tile in enumerate(thumbs):
        sheet.paste(tile, ((index % 2) * 580, (index // 2) * 450))
    sheet.save(output, quality=92)


def main() -> None:
    root = Path(__file__).resolve().parents[2] / "backend" / "results" / "ai" / "banner_pack_gate"
    root.mkdir(parents=True, exist_ok=True)
    all_outputs: list[str] = []
    for key, image_path, headline, subcopy in CASES:
        hero = hero_from_existing(
            image_path, headline=headline, subcopy=subcopy,
            subject_en=key, style="editorial", domain="cafe",
        )
        result = generate_v5(
            image_path, key, purpose=AdPurpose.BANNER, hero_asset=hero,
            output_dir=str(root / key),
        )
        all_outputs.extend(result.outputs)
    _contact_sheet(all_outputs, root / "banner_pack_latte_tea_contact_sheet.jpg")
    print(root)


if __name__ == "__main__":
    main()
