"""레퍼런스 실험(STY-003~005)에서 검증한 도메인별 6무드 StylePlan.

무드 이름만 공유하고 실제 연출 지시는 음식·음료·사물별로 분리한다. Kontext에는
레퍼런스 이미지를 직접 넣지 않으므로 reference_ids는 추적·평가용이며, 생성 지시는
해당 레퍼런스에서 추출한 배경·조명·구도 규칙만 사용한다.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReferenceStylePlan:
    style_key: str
    domain: str
    archetype: str
    reference_ids: tuple[str, ...]
    direction: str


_STYLE_ALIASES = {
    "editorial": "editorial",
    "pop": "pop",
    "realism": "realism",
    "pastel": "pastel",
    "pastel_float": "pastel",
    "monotone": "monotone",
    "warm_organic": "warm_organic",
    "warm_vintage": "warm_organic",
}

_CLIP_STYLE_ANCHORS = {
    "editorial": "airy premium editorial, soft natural light, clean copy space",
    "pop": "bold pop advertising, saturated color-block set, crisp hard light",
    "realism": "true-to-life commercial photography, natural texture and light",
    "pastel": "soft pastel advertising set, high-key diffused light",
    "monotone": "minimal tone-on-tone campaign, graphic shadow",
    "warm_organic": "warm organic editorial, travertine, gentle golden light",
}

_IDENTITY_LOCKS = {
    "food": (
        "Edit this exact food photograph. Keep every food item, plate, sauce and garnish exactly as "
        "photographed: the same count, shape, doneness, texture, colors, camera angle, crop and arrangement. "
        "Do not add, remove, redraw, resize, move, merge or recolor any food item. Change only the background, "
        "table surface and environmental lighting. "
    ),
    "drink": (
        "Edit this exact drink photograph. Keep the drink, cup or glass, foam, ice, toppings, handle and saucer "
        "exactly as photographed: identical shapes, liquid level, colors, camera angle, crop and arrangement. "
        "Do not add, remove, redraw, move, rotate, recolor or cover the drink or its container. Change only the "
        "background, table surface and environmental lighting. "
    ),
    "object": (
        "Edit this exact product photograph. Preserve the product exactly as photographed: identical silhouette, "
        "proportions, material, surface details, seams, controls, label, logo, lettering, camera angle, crop and "
        "perspective. Do not redraw, reshape, smooth, duplicate, rotate, recolor or cover the product. Change only "
        "the background, supporting surface and environmental lighting. "
    ),
}


def _plan(style_key: str, domain: str, archetype: str,
          reference_ids: tuple[str, ...], direction: str) -> ReferenceStylePlan:
    return ReferenceStylePlan(style_key, domain, archetype, reference_ids, direction)


_PLANS: dict[tuple[str, str], ReferenceStylePlan] = {
    ("food", "editorial"): _plan(
        "editorial", "food", "asymmetric_copyspace + food_hero",
        ("01_에디토리얼__IMG_4597", "03_리얼리즘__IMG_4604", "03_리얼리즘__IMG_4675"),
        "Create a premium culinary editorial environment with a muted cream stone table and a pale warm-gray "
        "background, soft directional window light and generous quiet copy space above the plate. Restrained "
        "high-end restaurant campaign. No added cutlery, napkin, ingredients, garnish, hands or text.",
    ),
    ("food", "pop"): _plan(
        "pop", "food", "saturated_color_block + macro_texture",
        ("02_팝_pop__IMG_4606", "02_팝_pop__IMG_4608", "03_리얼리즘__IMG_4680"),
        "Create a bold contemporary food campaign with a saturated cobalt-blue background and a clean tomato-red "
        "table surface, crisp hard side light and one strong graphic diagonal shadow behind the plate. Keep the "
        "food's true appetizing colors. No extra food, props, hands, splashes, floating objects or text.",
    ),
    ("food", "realism"): _plan(
        "realism", "food", "macro_texture + food_hero",
        ("03_리얼리즘__IMG_4604", "03_리얼리즘__IMG_4675", "03_리얼리즘__IMG_4691"),
        "Create a true-to-life premium restaurant photograph with a dark charcoal stone table and a softly blurred "
        "neutral dining background. Use realistic directional light that reveals the exact natural food texture "
        "without exaggeration. No smoke, fire, utensils, ingredients, garnish, hands or text.",
    ),
    ("food", "pastel"): _plan(
        "pastel", "food", "pastel_tabletop + food_hero",
        ("04_파스텔__IMG_4674", "04_파스텔__IMG_4710", "04_파스텔__IMG_4712"),
        "Create a refined pastel culinary set with a pale blush background and a low muted lavender table plane, "
        "high-key diffused light and a very soft contact shadow. Keep all food colors fully natural, never "
        "pastel-tinted. No geometric props, flowers, extra food, hands or text.",
    ),
    ("food", "monotone"): _plan(
        "monotone", "food", "dark_color_lock + food_hero",
        ("05_모노톤__IMG_4704", "05_모노톤__IMG_4705", "03_리얼리즘__IMG_4604"),
        "Create a strict deep burgundy monochrome environment using wine-red, charcoal and black only in the "
        "background and table. Add a precise warm rim light and one bold diagonal shadow. Keep all food colors true "
        "and isolated from the monochrome surroundings. No props, extra food, hands or text.",
    ),
    ("food", "warm_organic"): _plan(
        "warm_organic", "food", "warm_tabletop + organic_material",
        ("06_웜빈티지__IMG_4667", "06_웜빈티지__IMG_4678", "03_리얼리즘__IMG_4683"),
        "Create a warm organic dining environment on a pale travertine table against a softly textured beige wall. "
        "Use gentle golden side light, tactile natural materials and an intimate premium restaurant mood. No wood "
        "grain, linen, dried plants, extra food, utensils, hands or text.",
    ),
    ("drink", "editorial"): _plan(
        "editorial", "drink", "asymmetric_copyspace + drink_hero",
        ("01_에디토리얼__IMG_4598", "01_에디토리얼__IMG_4631", "01_에디토리얼__IMG_4703"),
        "Create an airy premium cafe editorial environment with a pale cream stone table, a very light cool-gray "
        "background, soft window light and generous copy space in the upper-left. Minimal high-end magazine look. "
        "No spoon, napkin, beans, pastries, flowers, hands or text.",
    ),
    ("drink", "pop"): _plan(
        "pop", "drink", "saturated_color_block + drink_hero",
        ("02_팝_pop__IMG_4697", "02_팝_pop__IMG_4698", "02_팝_pop__IMG_4699"),
        "Create a bold contemporary beverage campaign with a saturated cobalt-blue background and a clean vivid "
        "orange table surface, crisp hard side light and one graphic shadow. No fruit, packets, beans, ice, splash, "
        "straw, hands, food or text.",
    ),
    ("drink", "realism"): _plan(
        "realism", "drink", "natural_cafe + drink_hero",
        ("03_리얼리즘__IMG_4602", "03_리얼리즘__IMG_4657", "03_리얼리즘__IMG_4683"),
        "Create a true-to-life modern cafe photograph on a clean warm-gray stone tabletop beside a softly sunlit "
        "neutral wall. Use realistic morning window light, accurate container material and natural drink texture, "
        "with restrained depth of field. No props, food, beans, hands, added steam or text.",
    ),
    ("drink", "pastel"): _plan(
        "pastel", "drink", "pastel_tabletop + drink_hero",
        ("04_파스텔__IMG_4670", "04_파스텔__IMG_4710", "04_파스텔__IMG_4712"),
        "Create a soft pastel cafe set with a pale blush background and a muted lavender table plane, ethereal "
        "high-key diffused light and soft contact shadows. Keep the drink and container grounded and true to their "
        "original colors. No shapes, flowers, props, food, hands or text.",
    ),
    ("drink", "monotone"): _plan(
        "monotone", "drink", "brand_color_lock + drink_hero",
        ("05_모노톤__IMG_4705", "05_모노톤__IMG_4713", "02_팝_pop__IMG_4698"),
        "Create a strict espresso-brown monochrome environment using coffee brown, dark cocoa and warm cream only "
        "in the background and table. Add clean even lighting and one bold diagonal shadow. Preserve the drink and "
        "container's real colors exactly. No props, beans, food, hands or text.",
    ),
    ("drink", "warm_organic"): _plan(
        "warm_organic", "drink", "warm_tabletop + organic_material",
        ("06_웜빈티지__IMG_4667", "06_웜빈티지__IMG_4678", "06_웜빈티지__IMG_4620"),
        "Create a warm organic cafe environment on a pale travertine table against a softly textured beige wall. "
        "Use gentle golden side light, tactile natural materials and a quiet premium morning atmosphere. No wood "
        "grain, linen, dried plants, spoon, beans, pastries, hands or text.",
    ),
    ("object", "editorial"): _plan(
        "editorial", "object", "asymmetric_copyspace + minimal_studio",
        ("01_에디토리얼__IMG_4632", "01_에디토리얼__IMG_4703", "IMG_4792"),
        "Create a restrained high-end product editorial environment with a cool off-white studio sweep, one thin "
        "translucent acrylic plane in the distant background, soft directional daylight and generous clean copy "
        "space in the upper-left. No accessories, hands, cables or text outside the unchanged product label.",
    ),
    ("object", "pop"): _plan(
        "pop", "object", "saturated_color_block + commercial_hero",
        ("02_팝_pop__IMG_4609", "02_팝_pop__IMG_4621", "IMG_4790"),
        "Create an energetic graphic product campaign on a saturated electric-blue surface against a vivid coral "
        "background. Add two large matte geometric blocks far behind the product and crisp hard directional shadows. "
        "No food, spheres, hands, extra products or text outside the unchanged product label.",
    ),
    ("object", "realism"): _plan(
        "realism", "object", "natural_material + commercial_hero",
        ("03_리얼리즘__IMG_4637", "IMG_4809", "IMG_4813"),
        "Create a true-to-life natural product photograph on a light gray limestone surface beside a softly sunlit "
        "neutral wall. Use realistic morning window light, accurate material texture, subtle contact shadows and "
        "restrained depth of field. No extra products, flowers, hands or text outside the unchanged product label.",
    ),
    ("object", "pastel"): _plan(
        "pastel", "object", "soft_pedestal + pastel_product_hero",
        ("04_파스텔__IMG_4670", "04_파스텔__IMG_4710", "IMG_4808"),
        "Create a soft pastel product set with a pale blush background and one low matte lavender pedestal behind "
        "the product. Use ethereal high-key diffused light and soft contact shadows. Keep the product grounded. No "
        "mist, ribbons, flowers or text outside the unchanged product label.",
    ),
    ("object", "monotone"): _plan(
        "monotone", "object", "brand_color_lock + minimal_studio",
        ("05_모노톤__IMG_4688", "05_모노톤__IMG_4713", "IMG_4793"),
        "Create a strict tone-on-tone campaign using one restrained color family only in a seamless geometric "
        "studio background, with a shallow platform, clean even lighting and one bold diagonal shadow. Preserve the "
        "product's own colors and material. No text outside the unchanged product label.",
    ),
    ("object", "warm_organic"): _plan(
        "warm_organic", "object", "neutral_stilllife + organic_material",
        ("06_웜빈티지__IMG_4618", "06_웜빈티지__IMG_4626", "IMG_4809"),
        "Create a warm organic editorial still life on a pale travertine surface with a softly textured beige wall. "
        "Add one small sculptural stone in the distant background and a subtle window shadow. Use gentle golden side "
        "light. No wood grain, plants, wrapping, flowers or text outside the unchanged product label.",
    ),
}


def normalize_style(style_key: str) -> str | None:
    """프로덕션 스타일 별칭을 실험 무드 키로 정규화한다."""
    return _STYLE_ALIASES.get((style_key or "").strip().lower())


def normalize_domain(domain: str | None) -> str:
    """분석 결과의 도메인을 StylePlan의 food/drink/object 세 축으로 정규화한다."""
    value = (domain or "food").strip().lower()
    if value in {"drink", "cafe", "beverage"}:
        return "drink"
    if value in {"object", "product", "beauty", "fashion", "general_object"}:
        return "object"
    return "food"


def get_reference_plan(style_key: str, domain: str | None) -> ReferenceStylePlan | None:
    """지원하는 6무드면 도메인별 계획을 반환하고, 특수 포맷이면 None을 반환한다."""
    style = normalize_style(style_key)
    if style is None:
        return None
    return _PLANS[(normalize_domain(domain), style)]


def build_reference_instruction(style_key: str, domain: str | None, subject_en: str) -> str | None:
    """StylePlan을 Kontext용 정체성 보존 편집 지시로 변환한다."""
    plan = get_reference_plan(style_key, domain)
    if plan is None:
        return None
    subject = (subject_en or "product").strip()
    return (
        f"The photographed subject is {subject}. "
        f"{_IDENTITY_LOCKS[plan.domain]}{plan.direction} "
        "Do not generate any new logo, label, lettering, watermark or advertising copy."
    )


def build_clip_anchor(style_key: str, domain: str | None, subject_en: str,
                      staging: str = "preserve") -> str | None:
    """CLIP 77토큰용 짧은 스타일 앵커. 전체 편집 명령은 T5 prompt_2가 담당한다.

    staging="recompose"(P5 음료 재연출): "original drink unchanged" 류 보존 문구가 재연출
    지시(앵글·구도 자유)와 CLIP 층위에서 충돌하므로 제거하고 짧은 광고 앵커만 쓴다(개정 #5).
    """
    plan = get_reference_plan(style_key, domain)
    if plan is None:
        return None
    subject = (subject_en or "product").strip()
    if staging == "recompose":
        return f"{subject} beverage advertisement, {_CLIP_STYLE_ANCHORS[plan.style_key]}, no text"
    return f"{subject}, {_CLIP_STYLE_ANCHORS[plan.style_key]}, original {plan.domain} unchanged, no text"


# 온도별 물리 효과(P5) — 그 음료에 물리적으로 참인 효과만(정직성). 이름 추정 금지, Vision이 원천.
_RECOMPOSE_EFFECTS = {
    "iced": "fresh condensation droplets on the outside of the container",
    "hot": "gentle natural steam rising from the drink",
}


def build_recompose_instruction(style_key: str, subject_en: str,
                                container_desc: str | None = None,
                                temperature: str | None = None,
                                text_zone: str | None = None) -> str | None:
    """P5 음료 재연출 지시 — 보존 편집이 아니라 같은 음료의 '새 연출'을 만든다.

    재연출 계약(원본 승계): 같은 용기 종류·색 / 같은 음료·토핑 / 앵글·구도 자유 /
    외래 재료·손·글자 금지 / text_zone 카피 여백. container_desc·temperature는
    analyze_photo(Vision) 산출값만 사용한다(개정 #2 — 이름 추정 함수 만들지 말 것).
    """
    plan = get_reference_plan(style_key, "drink")
    if plan is None:
        return None
    subject = (subject_en or "beverage").strip()
    container = (container_desc or "container").strip()
    zone = (text_zone or "top").replace("_", " ")
    effect = _RECOMPOSE_EFFECTS.get((temperature or "").strip().lower())
    effect_txt = f" You may add only {effect}." if effect else ""
    # direction 말미의 소품 금지문("No fruit, ... ice, splash ...")은 보존 편집용 —
    # 재연출 계약의 "identical ice/toppings as photographed"와 충돌한다(그 음료의 진짜 얼음까지
    # 지우라는 뜻으로 읽힘). 씬 묘사만 취하고 금지는 아래 계약 문장이 일원화해서 담당한다.
    scene_direction = ". ".join(
        s.rstrip(".") for s in plan.direction.split(". ") if not s.strip().startswith("No ")
    ) + "."
    return (
        f"Restage this {subject} into a new advertisement composition. "
        f"Keep the exact same {container} and the exact same drink inside: identical liquid color, "
        f"foam, ice and toppings as photographed. "
        "You may freely change the camera angle, composition, scale and placement for a more "
        f"dynamic advertising shot.{effect_txt} "
        f"{scene_direction} "
        f"Leave clean empty copy space in the {zone} area. "
        "Do not add any new ingredients, fruit, garnish, props, hands or people. "
        "Do not generate any new logo, label, lettering, watermark or advertising copy."
    )
