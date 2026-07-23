"""레퍼런스 실험(STY-003~005)에서 검증한 도메인별 6무드 StylePlan.

무드 이름만 공유하고 실제 연출 지시는 음식·음료·사물별로 분리한다. Kontext에는
레퍼런스 이미지를 직접 넣지 않으므로 reference_ids는 추적·평가용이며, 생성 지시는
해당 레퍼런스에서 추출한 배경·조명·구도 규칙만 사용한다.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
import os

from . import prompt_registry as _prompts

_NS = "reference_style_plans"


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

# PALETTE-001(2026-07-20): "pop" 스타일이 상품과 무관하게 도메인당 색조합 딱 1개로 고정돼
#   있었다("항상 저 색깔로만 출력"). reference_recipe_data.PALETTE_VARIANTS에 이미 pop용
#   후보(cobalt_duo/teal_duo/coral_duo)가 있지만, 그건 "전부 후보 — 시각 몽타주 승인 전
#   조립부 사용 금지"로 명시된 미승인 레지스트리라 여기서 그대로 끌어쓰지 않는다. 대신
#   기존 색(원래 프로덕션에서 쓰던 값)을 variant 0으로 유지하고, 같은 미감을 유지하는 새
#   조합을 추가해 상품명(subject_en) 해시로 결정론적 선택한다 — 같은 상품은 항상 같은 색,
#   다른 상품은 다른 색. PALETTE-002(같은 날): pastel·monotone(food/drink)도 같은 문제라
#   같은 방식으로 확장 — object monotone은 원래 색 미지정("one restrained color family")이라
#   해당 없음.
_POP_PALETTES: dict[str, tuple[str, ...]] = {
    "food": (
        "a saturated cobalt-blue background and a clean tomato-red table surface",
        "a saturated magenta-pink background and a clean lime-green table surface",
        "a saturated golden-yellow background and a clean deep-violet table surface",
    ),
    "drink": (
        "a saturated cobalt-blue background and a clean vivid orange table surface",
        "a saturated teal background and a clean coral table surface",
        "a saturated violet background and a clean chartreuse table surface",
    ),
    "object": (
        "a saturated electric-blue surface against a vivid coral background",
        "a saturated emerald-green surface against a vivid magenta background",
        "a saturated amber-yellow surface against a vivid indigo background",
    ),
}

_PASTEL_PALETTES: dict[str, tuple[str, ...]] = {
    "food": (
        "a pale blush background and a low muted lavender table plane",
        "a pale powder-blue background and a low muted blush-pink table plane",
        "a pale mint-green background and a low muted lilac table plane",
    ),
    "drink": (
        "a pale blush background and a muted lavender table plane",
        "a pale powder-blue background and a muted blush-pink table plane",
        "a pale mint-green background and a muted lilac table plane",
    ),
    "object": (
        "a pale blush background and one low matte lavender pedestal behind the product",
        "a pale powder-blue background and one low matte blush-pink pedestal behind the product",
        "a pale mint-green background and one low matte lilac pedestal behind the product",
    ),
}

_MONOTONE_PALETTES: dict[str, tuple[str, ...]] = {
    "food": (
        "a strict deep burgundy monochrome environment using wine-red, charcoal and black only",
        "a strict pale dove-gray monochrome environment using soft gray, warm white and pale taupe only",
    ),
    "drink": (
        "a strict espresso-brown monochrome environment using coffee brown, dark cocoa and warm cream only",
        "a strict pale dove-gray monochrome environment using soft gray, warm white and pale taupe only",
    ),
}


def _palette_clause(palettes: dict[str, tuple[str, ...]], domain: str, subject_en: str) -> str:
    """상품명 기준 결정론적 팔레트 선택. 같은 상품은 재생성해도 항상 같은 색."""
    variants = palettes.get(domain, palettes.get("food", next(iter(palettes.values()))))
    digest = hashlib.sha256((subject_en or "").strip().lower().encode()).digest()
    return variants[digest[0] % len(variants)]


_STYLE_PALETTES: dict[str, dict[str, tuple[str, ...]]] = {
    "pop": _POP_PALETTES,
    "pastel": _PASTEL_PALETTES,
    "monotone": _MONOTONE_PALETTES,
}


def _style_palette_clause(style_key: str, domain: str, subject_en: str) -> str:
    palettes = _STYLE_PALETTES.get(style_key)
    if palettes is None:
        return ""
    return _palette_clause(palettes, domain, subject_en)


# CONTAINER-001(2026-07-21): food 프리앰블의 "no cup/tumbler"(BUG-KTX-001·PLATING-001 대응)와
#   (food,realism)의 "plate resting flat on dark charcoal"(BUG-KTX-001-2 대응)이 굽 유리볼
#   빙수 같은 장식 용기를 밋밋한 식당 접시로 강제 변환(운영 historyId=107). 실측 버그 대응
#   문구라 삭제 불가 — analyze_photo(Vision)가 본 용기 묘사로 분기해 장식 용기(vessel)일 때만
#   긍정 단언 프리앰블로 치환한다. 문구·분류 키워드는 prompts/reference_style_plans.yaml(T1).
def classify_container(container_desc: str | None,
                       container_opacity: str | None = None) -> str:
    """Vision 용기 묘사 → 'vessel'(내용물 보이는 유리 디저트 용기) | 'default'(접시 경로).

    실측(2026-07-21): analyze_photo가 굽·스템을 단어로 안 주고 kind는 'glass'/'plate' 수준.
    대신 opacity가 유리 용기(transparent)와 불투명 접시(opaque)를 확실히 가른다. 판정 3층위:
      1) vessel_keywords(고블릿·파르페 등 명시 형태) → opacity 무관 vessel.
      2) flat_kinds(plate·board 등) → 투명이어도 default(PLATING-001 가드).
      3) glass_vessel_kinds(glass·bowl·cup 등 깊은 용기) + opacity∈{transparent,translucent}
         → 내용물 비치는 쇼피스 vessel.
    근거 없음(None·빈값)·미분류는 전부 'default' — 컵 변환·프로핑 대응 문구 유지 안전측 폴백.
    이름 추정 금지(개정 #2): 입력은 analyze_photo 산출만.
    """
    desc = (container_desc or "").strip().lower()
    if not desc or desc == "none":
        return "default"
    if any(kw in desc for kw in _prompts.get(_NS, "container.vessel_keywords")):
        return "vessel"
    if any(fw in desc for fw in _prompts.get(_NS, "container.flat_kinds")):
        return "default"
    opacity = (container_opacity or "").strip().lower()
    if opacity in ("transparent", "translucent") and any(
            dk in desc for dk in _prompts.get(_NS, "container.glass_vessel_kinds")):
        return "vessel"
    return "default"

_IDENTITY_LOCKS = {
    "food": (
        # BUG-KTX-001-2(2026-07-20): "realism" 스타일에서 컵 변환이 재발(negative 문구만으로는
        #   불충분, 4/4는 아니지만 재현됨). 문장 맨 앞에 긍정 단언을 추가 — 부정문보다 앞쪽의
        #   긍정 진술이 모델 조건화에 더 강하게 anchor된다는 관찰에 따른 보강.
        # PLATING-001-3(2026-07-20): 두 번째 강화도 실패(프렌치토스트 재현 지속) — "propped up"
        #   부정문만으로는 못 이기는 강한 모델 편향(빵/토스트를 기대 세워 찍는 흔한 음식사진
        #   프로핑 연출)으로 판단. 긍정 단언을 이 지점에도 추가하고, 빵/토스트류를 구체적으로
        #   호명해 눕혀진 상태를 명시 — BUG-KTX-001의 "컵 아님" 성공 패턴(부정 대신 긍정 우선)을
        #   재적용.
        "This is a plated food photograph resting flat on a table, photographed from above or at a gentle angle "
        "— never a food item standing upright or propped on its edge. If the food is a slice of bread, toast, "
        "cake or similarly flat-cut item, it lies flat on its widest cut face, the same way it was photographed "
        "originally. There is no cup, mug, tumbler, lid or straw anywhere in this image. "
        "Edit this exact food photograph. Keep every food item, plate, sauce and garnish exactly as "
        "photographed: the same count, shape, doneness, texture and colors. "
        # BUG-KTX-001(2026-07-20): top-down 원형 접시 샌드위치가 4/4 시드에서 테이크아웃 컵으로
        #   정규화됨(접시의 원형·방사형 골이 컵 뚜껑 시각신호와 겹침). 객체 변환 부정문으로 차단
        #   — seed42 단독 검증에서 정체성·구도 복원 확인.
        "Never convert the food, its plate or bowl into a cup, mug, takeaway container or any different "
        "kind of object. The subject must remain a plated food item, never a beverage. "
        "Do not add, remove, redraw, resize or recolor any food item, and do not rearrange food items relative "
        "to each other. "
        # PLATING-001(2026-07-20): editorial 등 배경·구도를 새로 그리는 스타일에서 "카메라 앵글 고정"
        #   지시를 모델이 절반만 따라 배경만 바뀌고 음식은 원본 각도 그대로 남아, 새 장면(테이블·창문)
        #   위에 붕 뜨거나 단면으로 세워진 것처럼 보이는 부자연스러운 결과가 나옴(육안 확인).
        #   카메라 앵글 고정 대신 "장면에 맞는 자연스러운 접지"를 명시적으로 요구.
        # PLATING-001-2(2026-07-20): "pop" 스타일(강한 각도·다이애거널 섀도 연출)에서 재발 —
        #   프렌치토스트가 접시 위에 기대 세워진 채로 나옴. 기존 문구가 "떠있지 마라"는 다뤘지만
        #   "기대 세우는" 흔한 음식사진 프로핑 연출은 명시적으로 안 막고 있었음 — 추가.
        "You may reorient the whole plate or food as a single rigid object so it sits naturally within the new "
        "scene, but it must always rest fully and flatly on the table surface with its full base or underside in "
        "contact with the plate, casting a single realistic contact shadow, as if simply set down under normal "
        "gravity. Never leave the food floating, tilted upright, propped up, leaned back, leaning against "
        "anything, resting on a thin cut edge, or otherwise unsupported — this is a flat lay or gently-angled "
        "tabletop shot, never a propped-up or upright food-styling shot. This rule applies with no exceptions, "
        "regardless of camera angle, background color or lighting mood. "
        "Change the background, table surface, camera framing and environmental lighting to match the requested "
        "scene. "
    ),
    "drink": (
        "Edit this exact drink photograph. Preserve every source pixel belonging to the drink and its vessel. "
        "Keep the exact vessel silhouette, rim, base, wall shape, material, transparency and proportions, including "
        "whether a handle or saucer is present or absent. Keep identical foam, ice, toppings, liquid level, colors, "
        "camera angle, crop and arrangement. Do not add any vessel part absent from the source. Do not redraw, move, "
        "rotate, recolor or cover the drink or its vessel. Change only the "
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
        # CONTAINER-001: {hero}는 용기 분류에 따라 "the plate"(기본) 또는 실제 용기 묘사로
        # 치환되는 자리표시자 — build_reference_instruction()이 채운다.
        "Create a premium culinary editorial environment with a muted cream stone table and a pale warm-gray "
        "background, soft directional window light and generous quiet copy space above {hero}. Restrained "
        "high-end restaurant campaign. No added cutlery, napkin, ingredients, garnish, hands or text.",
    ),
    ("food", "pop"): _plan(
        "pop", "food", "saturated_color_block + macro_texture",
        ("02_팝_pop__IMG_4606", "02_팝_pop__IMG_4608", "03_리얼리즘__IMG_4680"),
        # PALETTE-001(2026-07-20): {palette}는 상품명(subject_en) 기준 결정론적으로 선택되는
        # 자리표시자 — build_reference_instruction()이 채운다. _POP_PALETTES 참고.
        "Create a bold contemporary food campaign with {palette}, crisp hard side light and one strong graphic "
        "diagonal shadow behind {hero}. Keep the food's true appetizing colors. No extra food, props, hands, "
        "splashes, floating objects or text.",
    ),
    ("food", "realism"): _plan(
        "realism", "food", "macro_texture + food_hero",
        ("03_리얼리즘__IMG_4604", "03_리얼리즘__IMG_4675", "03_리얼리즘__IMG_4691"),
        # BUG-KTX-001-2(2026-07-20): 이 스타일만 컵 변환이 재발했다. 다른 스타일과 달리 접시가
        #   "테이블 위에 평평히 놓임"을 명시하지 않고 흐린 배경만 지시해, 근접 제품샷(컵) 구도로
        #   미끄러지기 쉬웠던 것으로 추정 — 접시·테이블 접지를 명시적으로 보강.
        # CONTAINER-001: {container_clause}는 기본 "the plate resting flat", 장식 용기(vessel)면
        #   "the <용기> standing upright on its own base" — 굽 용기에 물리적으로 참인 접지만 지시.
        "Create a true-to-life premium restaurant photograph with {container_clause} on a dark charcoal stone "
        "table and a softly blurred neutral dining background behind it. Use realistic directional light that "
        "reveals the exact natural food texture without exaggeration. No smoke, fire, utensils, ingredients, "
        "garnish, hands or text.",
    ),
    ("food", "pastel"): _plan(
        "pastel", "food", "pastel_tabletop + food_hero",
        ("04_파스텔__IMG_4674", "04_파스텔__IMG_4710", "04_파스텔__IMG_4712"),
        "Create a refined pastel culinary set with {palette}, high-key diffused light and a very soft contact "
        "shadow. Keep all food colors fully natural, never pastel-tinted. No geometric props, flowers, extra "
        "food, hands or text.",
    ),
    ("food", "monotone"): _plan(
        "monotone", "food", "dark_color_lock + food_hero",
        ("05_모노톤__IMG_4704", "05_모노톤__IMG_4705", "03_리얼리즘__IMG_4604"),
        "Create {palette} in the background and table. Add a precise warm rim light and one bold diagonal "
        "shadow. Keep all food colors true and isolated from the monochrome surroundings. No props, extra food, "
        "hands or text.",
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
        "Create a bold contemporary beverage campaign with {palette}, crisp hard side light and one graphic "
        "shadow. No fruit, packets, beans, ice, splash, straw, hands, food or text.",
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
        ("04_파스텔__IMG_4674", "04_파스텔__IMG_4710", "04_파스텔__IMG_4712"),
        "Create a soft pastel cafe set with {palette}, ethereal high-key diffused light and soft contact "
        "shadows. Keep the drink and container grounded and true to their original colors. No shapes, flowers, "
        "props, food, hands or text.",
    ),
    ("drink", "monotone"): _plan(
        "monotone", "drink", "brand_color_lock + drink_hero",
        ("05_모노톤__IMG_4705", "05_모노톤__IMG_4713"),
        "Create {palette} in the background and table. Add clean even lighting and one bold diagonal shadow. "
        "Preserve the drink and container's real colors exactly. No props, beans, food, hands or text.",
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
        "Create an energetic graphic product campaign with {palette}. Add two large matte geometric blocks far "
        "behind the product and crisp hard directional shadows. No food, spheres, hands, extra products or text "
        "outside the unchanged product label.",
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
        ("04_파스텔__IMG_4674", "04_파스텔__IMG_4710", "IMG_4808"),
        "Create a soft pastel product set with {palette}. Use ethereal high-key diffused light and soft contact "
        "shadows. Keep the product grounded. No mist, ribbons, flowers or text outside the unchanged product "
        "label.",
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


def _validate_drink_recipe_alignment() -> None:
    """프로덕션 StylePlan이 승인 대기 recipe와 다른 레퍼런스로 회귀하지 않게 한다."""
    from .reference_recipe import canonical_reference_id
    from .reference_recipe_data import REFERENCE_RECIPES

    for (domain, style), plan in _PLANS.items():
        if domain != "drink":
            continue
        recipe = REFERENCE_RECIPES.get(f"drink/{plan.archetype.split(' + ')[0]}/{style}")
        if recipe is None:
            # 기존 plan의 표시용 archetype과 recipe key가 다른 경우 mood로 유일하게 대조한다.
            matches = [item for item in REFERENCE_RECIPES.values()
                       if item.domain == "drink" and item.mood.key == style]
            if len(matches) != 1:
                raise ValueError(f"drink recipe 누락/중복: {style}")
            recipe = matches[0]
        plan_ids = tuple(canonical_reference_id(value) for value in plan.reference_ids)
        if plan_ids != recipe.canonical_reference_ids:
            raise ValueError(
                f"drink StylePlan/reference recipe 근거 불일치: {style} "
                f"{plan_ids!r} != {recipe.canonical_reference_ids!r}")


_validate_drink_recipe_alignment()


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


def build_reference_instruction(style_key: str, domain: str | None, subject_en: str,
                                container_desc: str | None = None,
                                container_opacity: str | None = None,
                                serving_type: str | None = None,
                                palette_override: str | None = None) -> str | None:
    """StylePlan을 Kontext용 정체성 보존 편집 지시로 변환한다.

    container_desc·container_opacity(analyze_photo Vision 산출)가 유리 디저트 용기(vessel)로
    분류되면 food 프리앰블과 플랜의 용기 문구를 "원본 용기 유지+프리미엄 연출" 긍정 단언으로
    치환한다(CONTAINER-001). 미지정·접시류·분류 실패는 전부 기존 문구와 바이트 동일 —
    컵 변환(BUG-KTX-001)·프로핑(PLATING-001) 회귀 가드.

    serving_type(SRV-ROUTE-001): 제공 형태 세분 신호 배관. 현 시점 이 함수는 소비하지 않음
    — 디저트 재플레이팅 락 브랜치가 머지되면 tier-3 락 조건이 소비한다
    (설계 SRV-ROUTE-001 §4-4: serving_type in ('dessert','bakery') and not _replate_unsafe(...),
    None이면 레거시 substring — vessel 체크 선행 순서 불변).
    """
    plan = get_reference_plan(style_key, domain)
    if plan is None:
        return None
    subject = (subject_en or "product").strip()
    identity_lock = _IDENTITY_LOCKS[plan.domain]
    if plan.domain == "food" and classify_container(container_desc, container_opacity) == "vessel":
        container = container_desc.strip().lower()  # analyze_photo 계약상 ASCII 보장
        identity_lock = _prompts.fmt(_NS, "container.identity_lock_vessel",
                                     container=container).strip() + " "
        hero = f"the {container}"
        container_clause = _prompts.fmt(_NS, "container.realism_clause_vessel",
                                        container=container)
    else:
        hero = _prompts.get(_NS, "container.hero_default")
        container_clause = _prompts.get(_NS, "container.realism_clause_default")
    direction = plan.direction
    # 자리표시자는 한 번에 치환 — {palette}+{hero} 동시 보유 플랜(food pop)에서 str.format이
    # 누락 키로 KeyError를 내지 않게 한다.
    fmt_args: dict[str, str] = {}
    if "{palette}" in direction:
        # PAL-001: palette_override(제품 적응형 생성기 산출)가 오면 그것으로, 아니면 기존 고정
        #   팔레트 조회로 폴백(바이트 동일 — palette_override 미전달 시 회귀 없음).
        fmt_args["palette"] = (palette_override
                               or _style_palette_clause(plan.style_key, plan.domain, subject))
    if "{hero}" in direction:
        fmt_args["hero"] = hero
    if "{container_clause}" in direction:
        fmt_args["container_clause"] = container_clause
    if fmt_args:
        direction = direction.format(**fmt_args)
    return (
        f"The photographed subject is {subject}. "
        f"{identity_lock}{direction} "
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

# 무드별 연출 분화(PU-001 3단계) — 배경색만 다르고 앵글·크기·구도가 6무드 동일하던 문제 해결.
#   음료 재연출은 이미 앵글·스케일·배치 자유(정직성 경계는 음료·용기 종류/색/토핑 보존이 담당)라
#   여기서 "화면 내 스케일·카메라 앵글·구도"만 무드별로 규정한다. 팀장 §7 연출 프리셋 기반.
_RECOMPOSE_STAGING = {
    "editorial": ("Shoot at eye level and place the drink smaller and off to one side, leaving "
                  "generous negative space for an asymmetric high-end magazine layout."),
    "pop": ("Shoot from a bold low angle and make the drink large and dominant in frame, with a "
            "tilted dynamic diagonal composition and strong energetic movement."),
    "realism": ("Shoot at natural eye level with the drink medium-large and grounded, centered like "
                "a candid modern cafe photograph with shallow depth of field."),
    "pastel": ("Shoot from a slightly high angle with a soft, airy, balanced composition at medium "
               "size and gentle breathing space around the drink."),
    "monotone": ("Shoot from a dramatic low side angle with a strong single graphic diagonal shadow, "
                 "bold minimal composition, medium-large scale."),
    "warm_organic": ("Shoot at a relaxed three-quarter angle at medium size for a warm, inviting, "
                     "lived-in morning composition."),
}

_ANGLE_INSTRUCTIONS = {
    "eye": "eye level",
    "slightly_high": "a slightly elevated angle",
    "high": "a high angle",
    "low": "a low angle",
    "three_quarter": "a relaxed three-quarter angle",
    "top_down": "a top-down angle",
}
_PLACEMENT_INSTRUCTIONS = {
    "center": "centered",
    "left_third": "on the left third",
    "right_third": "on the right third",
    "upper_third": "on the upper third",
    "lower_third": "on the lower third",
}


def _recipe_staging(style_key: str) -> str | None:
    """승인 대기 SceneArchetype을 실험용 영문 재연출 지시로 변환한다."""
    if os.environ.get("REFERENCE_RECIPE_EXPERIMENT", "0") != "1":
        return None
    from .reference_recipe_data import get_reference_recipe

    recipe = get_reference_recipe("drink", style_key, allow_unapproved=True)
    if recipe is None:
        return None
    archetype = recipe.archetype
    angle = _ANGLE_INSTRUCTIONS[archetype.camera_angles[0]]
    placement = _PLACEMENT_INSTRUCTIONS[archetype.placements[0]]
    scale = round(sum(archetype.subject_scale) * 50)
    return (
        f"Shoot at {angle}. Place the drink {placement}, occupying about {scale}% of the "
        "canvas width. Follow the reference archetype's product scale and negative-space balance."
    )


_VESSEL_WORDS = ("cup", "glass", "mug", "saucer", "container", "bowl", "plate", "tumbler")


def build_recompose_instruction(style_key: str, subject_en: str,
                                container_desc: str | None = None,
                                temperature: str | None = None,
                                text_zone: str | None = None,
                                flexible_parts: list[str] | None = None) -> str | None:
    """P5 음료 재연출 지시 — 보존 편집이 아니라 같은 음료의 '새 연출'을 만든다.

    재연출 계약(원본 승계): 같은 음료·토핑 / 앵글·구도 자유 / 외래 재료·손·글자 금지 /
    text_zone 카피 여백. container_desc·temperature·flexible_parts는 analyze_photo(Vision)
    산출값만 사용한다(개정 #2 — 이름 추정 함수 만들지 말 것).

    제품 이해(PU-001): flexible_parts에 용기(컵·잔·받침)가 있으면 "그 용기는 상품이 아니라
    담는 그릇"이므로 색·재질을 장면 팔레트에 맞게 리스타일 허용(형태는 유지). 음료 자체와
    라떼아트·토핑은 언제나 보존. flexible이 비면 기존처럼 용기까지 그대로 승계(안전 폴백).
    """
    plan = get_reference_plan(style_key, "drink")
    if plan is None:
        return None
    subject = (subject_en or "beverage").strip()
    container = (container_desc or "container").strip()
    zone = (text_zone or "top").replace("_", " ")
    flex_text = " ".join(flexible_parts or []).lower()
    vessel_is_flexible = any(word in flex_text for word in _VESSEL_WORDS)
    if vessel_is_flexible:
        vessel_clause = (
            f"You may restyle the {container}'s color and finish to harmonize with the scene's "
            "palette, but keep its shape and proportions unchanged. Keep the drink itself exactly "
            "as photographed: identical liquid color, foam, latte art, ice and toppings. "
        )
    else:
        vessel_clause = (
            f"Keep the exact same {container} and the exact same drink inside: identical liquid "
            "color, foam, ice and toppings as photographed. "
        )
    effect = _RECOMPOSE_EFFECTS.get((temperature or "").strip().lower())
    effect_txt = f" You may add only {effect}." if effect else ""
    staging_txt = _recipe_staging(plan.style_key) or _RECOMPOSE_STAGING.get(plan.style_key, "")
    # direction 말미의 소품 금지문("No fruit, ... ice, splash ...")은 보존 편집용 —
    # 재연출 계약의 "identical ice/toppings as photographed"와 충돌한다(그 음료의 진짜 얼음까지
    # 지우라는 뜻으로 읽힘). 씬 묘사만 취하고 금지는 아래 계약 문장이 일원화해서 담당한다.
    raw_direction = plan.direction
    if "{palette}" in raw_direction:  # PALETTE-001: build_reference_instruction과 동일 치환
        raw_direction = raw_direction.format(palette=_style_palette_clause(plan.style_key, plan.domain, subject))
    scene_direction = ". ".join(
        s.rstrip(".") for s in raw_direction.split(". ") if not s.strip().startswith("No ")
    ) + "."
    return (
        f"Restage this {subject} into a new advertisement composition. "
        f"{vessel_clause}"
        "You may freely change the camera angle, composition, scale and placement for a more "
        f"dynamic advertising shot. {staging_txt}{effect_txt} "
        f"{scene_direction} "
        f"Leave clean empty copy space in the {zone} area. "
        "Do not add any new ingredients, fruit, garnish, props, hands or people. "
        "Do not generate any new logo, label, lettering, watermark or advertising copy."
    )
