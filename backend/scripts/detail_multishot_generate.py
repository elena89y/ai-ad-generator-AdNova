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

# TOPVIEW-001(2026-07-20): 원본 사진이 이미 위에서 내려다본 각도로 찍힌 경우(예: 책상 위
#   마우스), "정확히 90도"만 요구하면 원본과 거의 같은 결과가 나와 상세페이지 구조-유사도
#   게이트(hero, top_view)에 걸려 5장 생성 후 실패한다(사물 도메인에서 실측). 90도 고정 대신
#   15도씩 낮춰가며(90→75→60→45) 재시도해 원본과 확실히 다른 앵글을 찾는다.
TOP_VIEW_ANGLES: tuple[int, ...] = (90, 75, 60, 45)

_TOP_VIEW_PRESERVE = {
    "drink": "Preserve the exact same product, vessel, handle, color, contents and quantity.",
    "food": "Preserve the exact same food items, plate, sauce, garnish, count, shape, doneness and colors.",
    "object": ("Preserve the exact same product shape, size, color, label, material and proportions — "
               "do not distort or redesign the product."),
}


def top_view_prompt(domain: str, angle: int = 90) -> str:
    """도메인 + 카메라 각도(수직 기준 90=정탑뷰)로 top_view 프롬프트를 만든다."""
    preserve = _TOP_VIEW_PRESERVE.get(domain, _TOP_VIEW_PRESERVE["food"])
    if angle >= 85:
        angle_clause = (
            "Rotate the camera to an exact 90-degree bird's-eye view directly above the product. "
            "The lens axis must be perpendicular to the tabletop."
        )
    else:
        angle_clause = (
            f"Rotate the camera to a steep downward angle, tilted about {angle} degrees from directly "
            "overhead, clearly different from a straight-on side view."
        )
    # FMT-BG(2026-07-22): 섹션별 배경 변주 — 육안 정본이 "4컷 배경 동일"을 포착(corr이 못 잡는 축).
    #   top_view는 위에서 본 '부드러운 매트 표면 + 은은한 그림자'로, side_profile(그라디언트)·
    #   texture(무배경)·lifestyle(실장면)과 시각적으로 구분. 소품 추가는 금지(함정 #7 환각 방지).
    return (
        f"{angle_clause} {preserve} Shot from above on a smooth matte surface with a soft directional "
        "shadow, no added props, no hands, no text, no logo, no watermark."
    )


# LIFESTYLE-001(2026-07-20): top_view와 같은 문제가 lifestyle에서도 재현됨(사물 도메인 실측,
#   마우스 사진) — 원본이 이미 단순한 구도인 상품은 기본(눈높이) lifestyle도 히어로와 구조적으로
#   겹칠 수 있다. 0(눈높이)→30→50→70도로 카메라를 내려다보는 각도를 올려가며 재시도.
LIFESTYLE_ANGLES: tuple[int, ...] = (0, 30, 50, 70)

_LIFESTYLE_SCENE = {
    "drink": "Korean cafe tabletop usage scene",
    "food": "Korean restaurant tabletop dining scene",
    "object": "tabletop usage scene",
}
_LIFESTYLE_PRESERVE = {
    "drink": "Preserve vessel, contents, color and proportions.",
    "food": "Preserve every food item, plate, sauce and garnish exactly as photographed.",
    "object": "Preserve product shape, color, label and proportions exactly.",
}


def lifestyle_prompt(domain: str, angle: int = 0) -> str:
    """도메인 + 카메라 각도(0=눈높이, 클수록 위에서 내려다보는 각도)로 lifestyle 프롬프트를 만든다."""
    scene = _LIFESTYLE_SCENE.get(domain, _LIFESTYLE_SCENE["food"])
    preserve = _LIFESTYLE_PRESERVE.get(domain, _LIFESTYLE_PRESERVE["food"])
    if angle <= 5:
        angle_clause = (
            f"Edit into a restrained {scene} at natural eye level with the exact same product as the only hero."
        )
    else:
        angle_clause = (
            f"Edit into a restrained {scene}, camera tilted about {angle} degrees downward from eye level "
            "with more surrounding tabletop visible, with the exact same product as the only hero."
        )
    return (
        f"{angle_clause} {preserve} Soft natural window light, empty copy space, no people, no hands, "
        "no packages, no text, no logo, no watermark."
    )


# GATE-001(2026-07-20, 임시방편): top_view·lifestyle에 각도 재시도를 넣고 나니, 다른 사진
#   (문어모양 괄사)에서는 hero/texture_closeup 쌍이 걸렸다 — 즉 마우스만의 특수 케이스가
#   아니라, 상세페이지 구조-유사도 게이트(32x32 흑백 상관계수, 임계값 0.84)가 사물 도메인
#   전반에서 예측 불가능하게 어느 구도든 걸 수 있다는 뜻이다. 역할 하나씩 예외 처리하는
#   방식은 두더지잡기라 4개 구도(top_view/texture_closeup/side_profile/lifestyle) 전부를
#   같은 재시도 패턴으로 통일한다.
#   ⚠️ 이건 차선책이다 — 각 구도는 여전히 "히어로와만" 비교해서 다른 변형을 찾고, 구도끼리
#   (예: top_view vs lifestyle) 서로 겹치는 경우는 못 막는다(실측: 마우스 사진에서 재현).
#   더 나은 해법 후보(미착수): (1) 새로 만든 컷을 히어로뿐 아니라 "지금까지 확정된 모든 컷"과
#   비교, (2) 32x32 흑백 상관계수 대신 임베딩 기반 유사도로 교체, (3) 애초에 이 게이트가
#   맞는 방식인지(진짜 문제=편집이 하나도 안 먹힌 경우) 재검토.
TEXTURE_CLOSEUP_VARIANTS: tuple[int, ...] = (0, 1, 2)

_TEXTURE_PRESERVE = {
    "drink": "Preserve exact ingredients, color and material.",
    "food": "Preserve exact ingredients, color and material.",
    "object": "Preserve exact shape, color, label and material.",
}
# FMT-BG(2026-07-22): texture는 '프레임을 꽉 채운 무배경 매크로'로 강제 — 배경이 아예 없어
#   다른 섹션(표면/그라디언트/실장면)과 최대로 구분되고, 원본 배경이 딸려오는 문제도 차단.
_TEXTURE_CLOSEUP_FRAMINGS: tuple[str, ...] = (
    "a tight macro detail crop of the product's real surface texture that fills the entire frame "
    "with no visible background",
    "an extremely tight macro crop filling the whole frame with no visible background, offset to a "
    "different part of the product than a straight front view",
    "a medium macro close-up filling the frame with no visible background, from a slightly different "
    "angle than a straight front view, with more surrounding surface visible",
)


def texture_closeup_prompt(domain: str, variant: int = 0) -> str:
    """도메인 + 프레이밍 변형(0=기본 매크로, 클수록 더 다른 크롭/각도)으로 texture_closeup 프롬프트를 만든다."""
    preserve = _TEXTURE_PRESERVE.get(domain, _TEXTURE_PRESERVE["food"])
    framing = _TEXTURE_CLOSEUP_FRAMINGS[min(variant, len(_TEXTURE_CLOSEUP_FRAMINGS) - 1)]
    return f"Edit into {framing}. {preserve} No hands, no text, no logo, no watermark."


SIDE_PROFILE_ANGLES: tuple[int, ...] = (90, 45, 135, 180)

_SIDE_PROFILE_PRESERVE = {
    "drink": "Preserve the exact same vessel silhouette, handle, contents, color and proportions.",
    "food": "Preserve the exact same plate, food items, count, shape, sauce, garnish, colors and arrangement.",
    "object": "Preserve the exact same product shape, size, color, label, material and proportions.",
}


def side_profile_prompt(domain: str, angle: int = 90) -> str:
    """도메인 + 수직축 회전각(90=정측면)으로 side_profile 프롬프트를 만든다."""
    preserve = _SIDE_PROFILE_PRESERVE.get(domain, _SIDE_PROFILE_PRESERVE["food"])
    angle_clause = (
        f"Rotate the camera {angle} degrees around the product's vertical axis relative to the original "
        "framing, still at eye level, clearly different from the original angle."
    )
    # FMT-BG(2026-07-22): '무배경/평면' 대신 부드러운 스튜디오 그라디언트 배경 — top_view(표면)·
    #   texture(무배경)·lifestyle(실장면)과 배경축에서 구분. 소품 추가 없이 배경 톤만 변주(환각 방지).
    return (
        f"{angle_clause} {preserve} Set against a soft seamless studio gradient backdrop (not a plain "
        "flat wall), no added props, no hands, no text, no logo, no watermark."
    )


def role_prompts_for(domain: str) -> dict[str, str]:
    """style_domain(food|drink|object)에 맞는 role 프롬프트 세트를 반환한다. 미지원 도메인은 food로 폴백.

    4개 구도 모두 기본값 하나씩(90도 탑뷰 / 0번 매크로 프레이밍 / 90도 정측면 / 0도 눈높이) —
    앵글 재시도가 필요한 호출부(generation_app.py)는 각 *_prompt(domain, variant)를 직접 써서 덮어쓴다.
    """
    domain_prompts = ROLE_PROMPTS_BY_DOMAIN.get(domain, ROLE_PROMPTS_BY_DOMAIN["food"])
    return {
        **domain_prompts,
        "top_view": top_view_prompt(domain, 90),
        "texture_closeup": texture_closeup_prompt(domain, 0),
        "side_profile": side_profile_prompt(domain, 90),
        "lifestyle": lifestyle_prompt(domain, 0),
    }


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
