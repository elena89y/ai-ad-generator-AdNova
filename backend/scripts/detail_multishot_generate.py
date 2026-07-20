"""원본 한 장에서 상세페이지 필수 구도 4종 후보를 독립 생성한다."""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import kontext_service

# 도메인별 role 프롬프트(2026-07-20, DETAIL-001): 기존 ROLE_PROMPTS는 "cup rim/vessel/handle"
#   등 음료(drink) 전용 어휘가 하드코딩돼 있어, 음식(food)·사물(object) 상품에 그대로 쓰면
#   Kontext가 편집할 대상을 못 찾아 히어로샷과 거의 동일한 결과를 내고 상세페이지 구조-유사도
#   게이트(MAX_STRUCTURE_CORRELATION)에 걸려 5장 생성 후 실패한다. 도메인별로 분리한다.
ROLE_PROMPTS_BY_DOMAIN: dict[str, dict[str, str]] = {
    "drink": {
        "top_view": "Rotate the camera to an exact 90-degree bird's-eye view directly above the product. The lens axis must be perpendicular to the tabletop. The cup rim must appear as a centered circle and the cup side wall must not be visible. Preserve the exact same product, vessel, handle, color, contents and quantity. Clean tabletop, no added props, no hands, no text, no logo, no watermark.",
        "texture_closeup": "Edit into a tight macro detail photograph of the product's real surface texture. Preserve exact ingredients, color and material. Crop close without inventing garnish or changing the vessel, no hands, no text, no logo, no watermark.",
        "side_profile": "Edit into a true eye-level side profile product photograph. Preserve the exact same vessel silhouette, handle, contents, color and proportions. Clean neutral background, no added props, no hands, no text, no logo, no watermark.",
        "lifestyle": "Edit into a restrained Korean cafe tabletop usage scene with the exact same product as the only hero. Preserve vessel, contents, color and proportions. Soft natural window light, empty copy space, no people, no hands, no packages, no text, no logo, no watermark.",
    },
    "food": {
        "top_view": "Rotate the camera to an exact 90-degree bird's-eye view directly above the food. The lens axis must be perpendicular to the tabletop. The plate or bowl must appear as a centered circle seen from directly above. Preserve the exact same food items, plate, sauce, garnish, count, shape, doneness and colors. Clean tabletop, no added props, no hands, no text, no logo, no watermark.",
        "texture_closeup": "Edit into a tight macro detail photograph of the food's real surface texture. Preserve exact ingredients, color and material. Crop close without inventing garnish or changing the plate or arrangement, no hands, no text, no logo, no watermark.",
        "side_profile": "Edit into a true eye-level side profile food photograph. Preserve the exact same plate, food items, count, shape, sauce, garnish, colors and arrangement. Clean neutral background, no added props, no hands, no text, no logo, no watermark.",
        "lifestyle": "Edit into a restrained Korean restaurant tabletop dining scene with the exact same food as the only hero. Preserve every food item, plate, sauce and garnish exactly as photographed. Soft natural window light, empty copy space, no people, no hands, no packages, no text, no logo, no watermark.",
    },
    "object": {
        "top_view": "Rotate the camera to an exact 90-degree bird's-eye view directly above the product. The lens axis must be perpendicular to the tabletop. Preserve the exact same product shape, size, color, label, material and proportions — do not distort or redesign the product. Clean tabletop, no added props, no hands, no text, no logo, no watermark.",
        "texture_closeup": "Edit into a tight macro detail photograph of the product's real surface material and texture. Preserve exact shape, color, label and material, no hands, no text, no logo, no watermark.",
        "side_profile": "Edit into a true eye-level side profile product photograph. Preserve the exact same product shape, size, color, label, material and proportions. Clean neutral background, no added props, no hands, no text, no logo, no watermark.",
        "lifestyle": "Edit into a restrained tabletop usage scene with the exact same product as the only hero. Preserve product shape, color, label and proportions exactly. Soft natural window light, empty copy space, no people, no hands, no packages, no text, no logo, no watermark.",
    },
}

# 하위 호환: 기존 호출부(및 CLI 기본값)는 drink를 기본으로 쓴다.
ROLE_PROMPTS = ROLE_PROMPTS_BY_DOMAIN["drink"]


def role_prompts_for(domain: str) -> dict[str, str]:
    """style_domain(food|drink|object)에 맞는 role 프롬프트 세트를 반환한다. 미지원 도메인은 food로 폴백."""
    return ROLE_PROMPTS_BY_DOMAIN.get(domain, ROLE_PROMPTS_BY_DOMAIN["food"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="/tmp/detail_multishot")
    parser.add_argument("--steps", type=int, default=12)
    parser.add_argument("--domain", choices=tuple(ROLE_PROMPTS_BY_DOMAIN), default="drink")
    parser.add_argument("--roles", nargs="+", choices=tuple(ROLE_PROMPTS), default=list(ROLE_PROMPTS))
    args = parser.parse_args()
    prompts = role_prompts_for(args.domain)
    output = Path(args.output); output.mkdir(parents=True, exist_ok=True)
    summary = {"input": args.input, "steps": args.steps, "domain": args.domain, "roles": {}}
    for role in args.roles:
        prompt = prompts[role]
        started = time.perf_counter()
        path = kontext_service.edit(args.input, prompt, steps=args.steps, output_dir=str(output))
        target = output / f"{role}.png"
        Path(path).replace(target)
        summary["roles"][role] = {"path": str(target), "seconds": round(time.perf_counter()-started, 2)}
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)

if __name__ == "__main__":
    main()
