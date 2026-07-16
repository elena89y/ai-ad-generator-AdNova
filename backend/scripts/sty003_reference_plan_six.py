"""STY-003: 재분류 레퍼런스 기반 사물 SKU 6무드 비교 — 담당: 한의정.

동일한 향수 원본, seed, steps를 고정하고 무드와 사물 연출 아키타입만 바꾼다.
프로덕션 라우터를 바꾸기 전 스타일 분리도와 SKU 정체성 보존을 확인하는 실험 하네스다.

실행:
  .venv/bin/python backend/scripts/sty003_reference_plan_six.py --input /tmp/perfume.jpg
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services import kontext_service


@dataclass(frozen=True)
class ExperimentPlan:
    mood: str
    archetype: str
    reference_ids: tuple[str, ...]
    direction: str


_PERFUME_IDENTITY_LOCK = (
    "Edit this exact product photograph. Preserve the perfume bottle and separate clear cap exactly as "
    "photographed: identical shape, proportions, frosted glass, liquid level, silver atomizer, label, logo, "
    "lettering, positions, camera angle, crop and spacing. Do not redraw, duplicate, move, rotate, recolor or "
    "cover either object. Change only the background, supporting surface and environmental lighting. "
)


PLANS = (
    ExperimentPlan(
        mood="editorial",
        archetype="asymmetric_copyspace + minimal_studio",
        reference_ids=("01_에디토리얼__IMG_4632", "01_에디토리얼__IMG_4703", "IMG_4792"),
        direction=(
            "Create a high-end editorial beauty campaign using an airy pearl-white and very pale blue studio "
            "environment. Add one restrained transparent acrylic plane behind the product, soft diffused side "
            "light and a precise faint shadow. Keep generous clean copy space in the upper-right. Quiet, modern, "
            "luxurious, photographic, with no decorative props. No text outside the unchanged product label."
        ),
    ),
    ExperimentPlan(
        mood="pop",
        archetype="material_metaphor + saturated_color_block",
        reference_ids=("02_팝_pop__IMG_4609", "02_팝_pop__IMG_4621", "IMG_4790"),
        direction=(
            "Create a vivid conceptual beauty campaign on a saturated coral-pink color-block set. Place three "
            "large translucent pearl-like glass spheres only in the background, echoing the pearly perfume, with "
            "crisp hard side light and playful graphic shadows. Premium hyper-real studio photography, energetic "
            "but uncluttered. No food, no splash, no hands, no text outside the unchanged product label."
        ),
    ),
    ExperimentPlan(
        mood="realism",
        archetype="natural_material + minimal_studio",
        reference_ids=("03_리얼리즘__IMG_4637", "IMG_4809", "IMG_4813"),
        direction=(
            "Create a true-to-life natural product photograph on a light gray limestone surface beside a softly "
            "sunlit neutral wall. Use realistic morning window light, accurate transparent and frosted glass, "
            "subtle contact shadows and restrained depth of field. No dramatic effects, no extra products, no "
            "flowers, no hands, no text outside the unchanged product label."
        ),
    ),
    ExperimentPlan(
        mood="pastel",
        archetype="soft_pedestal + pastel_product_hero",
        reference_ids=("04_파스텔__IMG_4670", "04_파스텔__IMG_4710", "IMG_4808"),
        direction=(
            "Create a soft pastel beauty set with a pale blush-pink background, one low matte lavender pedestal "
            "behind the product and two broad translucent circular shapes far in the background. Ethereal high-key "
            "diffused light, soft shadows and gentle reflections. Keep the product grounded, not floating. No mist, "
            "ribbons, flowers or text outside the unchanged product label."
        ),
    ),
    ExperimentPlan(
        mood="monotone",
        archetype="pale_color_lock",
        reference_ids=("05_모노톤__IMG_4688", "05_모노톤__IMG_4713", "IMG_4793"),
        direction=(
            "Create a strict tone-on-tone champagne monochrome product campaign. Use one pale champagne color "
            "family across a seamless geometric studio background, with a single shallow circular platform, clean "
            "even lighting and one bold diagonal shadow. Minimal, graphic and precise. Preserve natural glass "
            "transparency. No typography or text outside the unchanged product label."
        ),
    ),
    ExperimentPlan(
        mood="warm_organic",
        archetype="neutral_stilllife + organic_material",
        reference_ids=("06_웜빈티지__IMG_4618", "06_웜빈티지__IMG_4626", "IMG_4809"),
        direction=(
            "Create a warm organic editorial still life on a pale travertine surface with a softly textured warm "
            "beige wall. Add one small sculptural stone in the distant background and a subtle dried grass shadow, "
            "not the grass itself. Gentle golden side light, tactile natural materials, quiet premium atmosphere. "
            "No wood table, gift wrapping, flowers or text outside the unchanged product label."
        ),
    ),
)

_MOUSE_IDENTITY_LOCK = (
    "Edit this exact product photograph. Preserve the computer mouse exactly as photographed: identical "
    "asymmetric oval silhouette, width-to-length ratio, metallic gray outer shell, black center panel, left and "
    "right button seams, central black scroll wheel, narrow center split, PHILIPS logo, camera angle, crop and "
    "perspective. Do not redraw, reshape, smooth, duplicate, rotate, recolor or cover the mouse. Change only the "
    "background, supporting surface and environmental lighting. "
)

MOUSE_PLANS = (
    ExperimentPlan(
        mood="editorial",
        archetype="asymmetric_copyspace + minimal_studio",
        reference_ids=("01_에디토리얼__IMG_4601", "01_에디토리얼__IMG_4703", "IMG_4792"),
        direction=(
            "Create a restrained high-end technology editorial environment with a cool off-white studio sweep, "
            "one thin translucent acrylic plane in the distant background, soft directional daylight and generous "
            "clean copy space in the upper-left. Quiet premium catalog photography. No desk accessories, hands, "
            "cables or text outside the unchanged product logo."
        ),
    ),
    ExperimentPlan(
        mood="pop",
        archetype="sports_concept + saturated_color_block",
        reference_ids=("02_팝_pop__IMG_4614", "02_팝_pop__IMG_4615", "02_팝_pop__IMG_4621"),
        direction=(
            "Create an energetic graphic technology campaign on a saturated electric-blue surface against a vivid "
            "lime background. Add two large matte geometric blocks far behind the mouse and crisp hard directional "
            "shadows suggesting speed. Clean color-block composition, no sports equipment, no spheres, no hands, no "
            "extra devices and no text outside the unchanged product logo."
        ),
    ),
    ExperimentPlan(
        mood="realism",
        archetype="natural_material + lifestyle_editorial",
        reference_ids=("03_리얼리즘__IMG_4637", "IMG_4735", "IMG_4813"),
        direction=(
            "Create a true-to-life natural product photograph on a clean light-gray woven desk mat beside a softly "
            "sunlit neutral wall. Use realistic morning window light, accurate matte metal and plastic textures, a "
            "subtle contact shadow and restrained depth of field. No keyboard, hands, plants, cups, cables or text "
            "outside the unchanged product logo."
        ),
    ),
    ExperimentPlan(
        mood="pastel",
        archetype="soft_pedestal + pastel_product_hero",
        reference_ids=("04_파스텔__IMG_4670", "04_파스텔__IMG_4710", "04_파스텔__IMG_4712"),
        direction=(
            "Create a soft pastel technology set with a pale lavender background and one low matte mint pedestal "
            "behind the mouse. Add two broad flat pastel geometric shapes far in the background, ethereal high-key "
            "diffused light and soft contact shadows. Keep the mouse grounded, not floating. No spheres, flowers, "
            "hands, cables or text outside the unchanged product logo."
        ),
    ),
    ExperimentPlan(
        mood="monotone",
        archetype="dark_color_lock",
        reference_ids=("05_모노톤__IMG_4704", "05_모노톤__IMG_4705", "IMG_4808"),
        direction=(
            "Create a strict graphite monochrome campaign using charcoal, black and gunmetal only. Place the mouse "
            "on a seamless dark geometric studio surface with one shallow platform behind it, a precise silver rim "
            "light and one bold diagonal shadow. Minimal, graphic and premium. No extra objects or text outside the "
            "unchanged product logo."
        ),
    ),
    ExperimentPlan(
        mood="warm_organic",
        archetype="neutral_stilllife + organic_material",
        reference_ids=("06_웜빈티지__IMG_4618", "06_웜빈티지__IMG_4626", "IMG_4809"),
        direction=(
            "Create a warm organic workspace still life on a pale travertine surface with a softly textured beige "
            "wall. Add one small rounded stone far in the background and a subtle window shadow. Gentle warm side "
            "light, tactile natural materials and a quiet premium atmosphere. No wood grain, plants, stationery, "
            "hands, cables or text outside the unchanged product logo."
        ),
    ),
)

_STEAK_IDENTITY_LOCK = (
    "Edit this exact food photograph. Keep the steak, white plate and rosemary exactly as photographed: the same "
    "single steak cut, thickness, seared crust, pink medium-rare interior, herb and garlic coating, juices, plate "
    "rim, rosemary sprigs, camera angle, crop and arrangement. Do not add, remove, redraw, resize, move, recolor or "
    "change the doneness of any food item. Change only the background, table surface and environmental lighting. "
)

STEAK_PLANS = (
    ExperimentPlan(
        mood="editorial", archetype="asymmetric_copyspace + food_hero",
        reference_ids=("01_에디토리얼__IMG_4597", "03_리얼리즘__IMG_4604", "03_리얼리즘__IMG_4675"),
        direction=(
            "Create a premium culinary editorial environment with a muted cream stone table and a pale warm-gray "
            "background, soft directional window light and generous quiet copy space above the plate. Restrained "
            "high-end restaurant campaign, no added cutlery, napkin, ingredients, garnish, hands or text."
        ),
    ),
    ExperimentPlan(
        mood="pop", archetype="saturated_color_block + macro_texture",
        reference_ids=("02_팝_pop__IMG_4606", "02_팝_pop__IMG_4608", "03_리얼리즘__IMG_4680"),
        direction=(
            "Create a bold contemporary food campaign with a saturated cobalt-blue background and a clean tomato-red "
            "table surface, crisp hard side light and one strong graphic diagonal shadow behind the plate. Energetic "
            "color-block composition while keeping the steak's true appetizing colors. No extra food, props, hands, "
            "splashes, floating objects or text."
        ),
    ),
    ExperimentPlan(
        mood="realism", archetype="macro_texture + food_hero",
        reference_ids=("03_리얼리즘__IMG_4604", "03_리얼리즘__IMG_4675", "03_리얼리즘__IMG_4691"),
        direction=(
            "Create a true-to-life premium steakhouse photograph with a dark charcoal stone table and a softly "
            "blurred neutral restaurant background. Use realistic directional light that reveals the exact seared "
            "crust, moist pink interior and herbs without exaggeration. No added smoke, fire, utensils, ingredients, "
            "garnish, hands or text."
        ),
    ),
    ExperimentPlan(
        mood="pastel", archetype="soft_pedestal + pastel_product_hero",
        reference_ids=("04_파스텔__IMG_4674", "04_파스텔__IMG_4710", "04_파스텔__IMG_4712"),
        direction=(
            "Create a refined pastel culinary set with a pale blush background and a low muted lavender table plane, "
            "high-key diffused light and a very soft contact shadow. Keep the steak's true brown, pink and green food "
            "colors fully natural, not pastel-tinted. No geometric props, flowers, extra food, hands or text."
        ),
    ),
    ExperimentPlan(
        mood="monotone", archetype="dark_color_lock + food_hero",
        reference_ids=("05_모노톤__IMG_4704", "05_모노톤__IMG_4705", "03_리얼리즘__IMG_4604"),
        direction=(
            "Create a strict dark burgundy monochrome environment using deep wine-red, charcoal and black only in "
            "the background and table. Add a precise warm rim light and one bold diagonal shadow. Keep all food colors "
            "true and isolated from the monochrome surroundings. No props, extra food, hands or text."
        ),
    ),
    ExperimentPlan(
        mood="warm_organic", archetype="warm_tabletop + organic_material",
        reference_ids=("06_웜빈티지__IMG_4667", "06_웜빈티지__IMG_4678", "03_리얼리즘__IMG_4683"),
        direction=(
            "Create a warm organic dining environment on a pale travertine table against a softly textured beige "
            "wall. Gentle golden side light, tactile natural materials and an intimate premium restaurant mood. No "
            "wood grain, linen, dried plants, extra food, utensils, hands or text."
        ),
    ),
)

_LATTE_IDENTITY_LOCK = (
    "Edit this exact drink photograph. Keep the black ceramic cup and saucer and the cafe latte exactly as "
    "photographed: identical cup shape, right-side handle, saucer, liquid level, brown coffee tone, white leaf-shaped "
    "latte art, every orange zest speck, camera angle, crop and arrangement. Do not add, remove, redraw, move, rotate, "
    "recolor or cover the cup, saucer, foam or toppings. Change only the background, table surface and environmental "
    "lighting. "
)

LATTE_PLANS = (
    ExperimentPlan(
        mood="editorial", archetype="asymmetric_copyspace + drink_hero",
        reference_ids=("01_에디토리얼__IMG_4598", "01_에디토리얼__IMG_4631", "01_에디토리얼__IMG_4703"),
        direction=(
            "Create an airy premium cafe editorial environment with a pale cream stone table, a very light cool-gray "
            "background, soft window light and generous copy space in the upper-left. Minimal high-end magazine look. "
            "No added spoon, napkin, beans, pastries, flowers, hands or text."
        ),
    ),
    ExperimentPlan(
        mood="pop", archetype="saturated_color_block + drink_hero",
        reference_ids=("02_팝_pop__IMG_4697", "02_팝_pop__IMG_4698", "02_팝_pop__IMG_4699"),
        direction=(
            "Create a bold contemporary beverage campaign with a saturated cobalt-blue background and a clean vivid "
            "orange table surface that echoes the existing zest. Use crisp hard side light and a single graphic shadow. "
            "No added fruit, packets, beans, ice, splash, straw, hands, food or text."
        ),
    ),
    ExperimentPlan(
        mood="realism", archetype="natural_cafe + drink_hero",
        reference_ids=("03_리얼리즘__IMG_4602", "03_리얼리즘__IMG_4657", "03_리얼리즘__IMG_4683"),
        direction=(
            "Create a true-to-life modern cafe photograph on a clean warm-gray stone tabletop beside a softly sunlit "
            "neutral wall. Use realistic morning window light, accurate glossy black ceramic and natural latte foam, "
            "with restrained depth of field. No props, food, beans, hands, steam or text."
        ),
    ),
    ExperimentPlan(
        mood="pastel", archetype="soft_pedestal + pastel_product_hero",
        reference_ids=("04_파스텔__IMG_4670", "04_파스텔__IMG_4710", "04_파스텔__IMG_4712"),
        direction=(
            "Create a soft pastel cafe set with a pale blush background and a muted lavender table plane, ethereal "
            "high-key diffused light and soft contact shadows. Keep the cup grounded and the coffee, foam and zest true "
            "to their original colors, not pastel-tinted. No shapes, flowers, props, food, hands or text."
        ),
    ),
    ExperimentPlan(
        mood="monotone", archetype="brand_color_lock + drink_hero",
        reference_ids=("05_모노톤__IMG_4705", "05_모노톤__IMG_4713", "02_팝_pop__IMG_4698"),
        direction=(
            "Create a strict espresso-brown monochrome environment using coffee brown, dark cocoa and warm cream only "
            "in the background and table. Add clean even lighting and one bold diagonal shadow. Preserve the black cup "
            "and the latte's real colors exactly. No props, beans, food, hands or text."
        ),
    ),
    ExperimentPlan(
        mood="warm_organic", archetype="warm_tabletop + organic_material",
        reference_ids=("06_웜빈티지__IMG_4667", "06_웜빈티지__IMG_4678", "06_웜빈티지__IMG_4620"),
        direction=(
            "Create a warm organic cafe environment on a pale travertine table against a softly textured beige wall. "
            "Gentle golden side light, tactile natural materials and a quiet premium morning atmosphere. No wood grain, "
            "linen, dried plants, spoon, beans, pastries, hands or text."
        ),
    ),
)

PROFILES = {
    "perfume": (_PERFUME_IDENTITY_LOCK, PLANS),
    "mouse": (_MOUSE_IDENTITY_LOCK, MOUSE_PLANS),
    "steak": (_STEAK_IDENTITY_LOCK, STEAK_PLANS),
    "latte": (_LATTE_IDENTITY_LOCK, LATTE_PLANS),
}

EXPERIMENT_IDS = {
    "perfume": "STY-003",
    "mouse": "STY-004",
    "steak": "STY-005",
    "latte": "STY-005",
}


def _comparison(input_path: Path, outputs: list[tuple[str, Path]], destination: Path) -> None:
    """원본과 6개 결과를 한 장의 4x2 비교 시트로 저장한다."""
    cells = [("ORIGINAL", input_path), *[(name.upper(), path) for name, path in outputs]]
    cell_w, image_h, label_h = 480, 480, 38
    canvas = Image.new("RGB", (cell_w * 4, (image_h + label_h) * 2), "white")
    draw = ImageDraw.Draw(canvas)
    for index, (label, image_path) in enumerate(cells):
        col, row = index % 4, index // 4
        image = Image.open(image_path).convert("RGB")
        fitted = ImageOps.contain(image, (cell_w - 12, image_h - 12), Image.Resampling.LANCZOS)
        x = col * cell_w + (cell_w - fitted.width) // 2
        y = row * (image_h + label_h) + (image_h - fitted.height) // 2
        canvas.paste(fitted, (x, y))
        draw.text((col * cell_w + 12, row * (image_h + label_h) + image_h + 10), label, fill="black")
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, quality=94)


def run_profile(input_path: Path, output_root: Path, profile: str,
                seed: int = 42, steps: int = 12) -> dict:
    """한 상품 프로필의 6개 무드를 생성하고 비교 시트와 요약을 반환한다."""
    output_root.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    generated: list[tuple[str, Path]] = []
    identity_lock, plans = PROFILES[profile]
    experiment_id = EXPERIMENT_IDS[profile]

    for plan in plans:
        print(f"[{experiment_id}] {plan.mood}: {plan.archetype}", flush=True)
        started = time.perf_counter()
        result = Path(kontext_service.edit(
            str(input_path),
            identity_lock + plan.direction,
            seed=seed,
            steps=steps,
            output_dir=str(output_root / plan.mood),
        ))
        elapsed = time.perf_counter() - started
        final_path = output_root / f"{plan.mood}.png"
        result.replace(final_path)
        generated.append((plan.mood, final_path))
        results.append({**asdict(plan), "output": str(final_path), "seconds": round(elapsed, 2)})
        print(f"[{experiment_id}] {plan.mood} 완료: {elapsed:.1f}s -> {final_path}", flush=True)

    file_prefix = experiment_id.lower().replace("-", "")
    comparison_path = output_root / f"{file_prefix}_comparison.jpg"
    _comparison(input_path, generated, comparison_path)
    summary = {
        "input": str(input_path),
        "experiment_id": experiment_id,
        "profile": profile,
        "seed": seed,
        "steps": steps,
        "total_seconds": round(sum(row["seconds"] for row in results), 2),
        "comparison": str(comparison_path),
        "plans": results,
    }
    (output_root / f"{file_prefix}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="/tmp/sty003_reference_plan")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="perfume")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--steps", type=int, default=12)
    args = parser.parse_args()
    run_profile(Path(args.input), Path(args.output), args.profile, args.seed, args.steps)


if __name__ == "__main__":
    main()
