"""ReferenceRecipe 구성요소 데이터 적재 (코덱스 재설계 순서 3, 2026-07-19).

MoodToken 6개 (palette 미소유):
  · lighting  = 기존 `reference_style_plans._CLIP_STYLE_ANCHORS` 근거 초안. manifest lighting
                라벨이 'even' 쏠림이라 실측 단독 불가 → 검증된 앵커 기반. 시각 게이트에서 조정.
  · materials = 무드 앵커의 재질 서술.
  · prop_density = manifest 91장 실측(pastel high 5/6, pop low 2/18, ...). editorial=minimal→low.

PALETTE_VARIANTS 레지스트리 (무드별 복수 후보):
  · P4BR 팔레트를 단일 승인하지 않는다(2026-07-19 지시). 같은 무드도 domain/archetype별 복수
    변형이 있어(pop drink=코발트, object=틸/코랄) **후보 레지스트리**로 정리한다.
  · 출처 = `scene_plans.py` code-render palette(P4BR 실측 검증분). ReferenceRecipe가 domain/
    archetype에 맞는 variant를 고르고, **최종 palette 승인은 recipe 시각 몽타주에서** 한다
    (여기서 approved=True 적재 없음 — 전부 후보).

SceneArchetype·ReferenceRecipe는 drink 6무드 골든패스 후보부터 적재한다. 전부 미승인이고,
실제 라떼·투명홍차 GPU 시각 게이트 전에는 조립부가 사용할 수 없다. 기존 파이프라인 미연결.
"""
from __future__ import annotations

from .reference_recipe import (
    CommercialLayout, ConditioningReferenceSet, MoodToken, PaletteVariant,
    PropPolicy, ReferenceRecipe, SceneArchetype,
)

# 무드 = 분위기만(조명·재질·소품밀도). palette·앵글·배치는 각각 PaletteVariant·SceneArchetype 몫.
MOOD_TOKENS: dict[str, MoodToken] = {
    "editorial": MoodToken("editorial", "soft natural window light, airy",
                           ("stone", "paper"), "low"),
    "pop": MoodToken("pop", "crisp hard directional light with graphic shadow",
                     ("seamless", "acrylic"), "low"),
    "realism": MoodToken("realism", "true-to-life natural directional daylight",
                         ("wood", "stone"), "medium"),
    "pastel": MoodToken("pastel", "high-key diffused soft light",
                        ("soft fabric", "matte"), "high"),
    "monotone": MoodToken("monotone", "graphic single-source light and shadow",
                          ("seamless", "matte"), "low"),
    "warm_organic": MoodToken("warm_organic", "gentle warm golden side light",
                              ("travertine", "wood", "linen"), "medium"),
}

# 무드별 palette 후보 (scene_plans P4BR code-render 실측). 전부 '후보' — recipe가 고르고
#   시각 몽타주에서 최종 승인. 단일 확정 아님.
PALETTE_VARIANTS: dict[str, tuple[PaletteVariant, ...]] = {
    "editorial": (
        PaletteVariant("airy_neutral", "editorial", ("#EDE8DF", "#FAF8F4"),
                       "P4BR editorial/seamless"),
    ),
    "pop": (
        PaletteVariant("cobalt_duo", "pop", ("#2B3FBB", "#F2ECE3"),
                       "P4BR pop/drink cobalt", ("drink",), "diagonal"),
        PaletteVariant("teal_duo", "pop", ("#2D6A6F", "#F2ECE3"),
                       "P4BR pop/object teal", ("object",)),
        PaletteVariant("coral_duo", "pop", ("#C96D5B", "#F2ECE3"),
                       "P4BR pop/object coral", ("object",)),
    ),
    "realism": (
        PaletteVariant("neutral_grey", "realism", ("#DCDCDC", "#9A9A9A"),
                       "P4BR realism/neutral-grey"),
    ),
    "pastel": (
        PaletteVariant("soft_tri", "pastel", ("#F7D6E0", "#D9CDF2", "#CFE8DD"), "P4BR pastel/tri"),
        PaletteVariant("blue_pink", "pastel", ("#CDE4F7", "#F7DCE3"), "P4BR pastel/blue-pink"),
        PaletteVariant("mint_pink", "pastel", ("#DFF0E8", "#F3D9DF"), "P4BR pastel/mint-pink"),
        PaletteVariant("lavender", "pastel", ("#E4D9F2", "#F7F4FB"), "P4BR pastel/lavender"),
    ),
    "monotone": (
        PaletteVariant("dark", "monotone", ("#1E1E22", "#4A4A52"), "P4BR monotone/dark"),
        PaletteVariant("pale", "monotone", ("#DCDCDC", "#9A9A9A"), "P4BR monotone/pale"),
    ),
    "warm_organic": (
        PaletteVariant("travertine", "warm_organic", ("#E8E0D4", "#D8CDBC"),
                       "P4BR warm/travertine"),
        PaletteVariant("wood_linen", "warm_organic", ("#F2EDE4", "#B7A48F"),
                       "P4BR warm/wood-linen"),
    ),
}

PALETTE_VARIANTS_BY_ID: dict[str, PaletteVariant] = {
    variant.variant_id: variant
    for variants in PALETTE_VARIANTS.values()
    for variant in variants
}

if len(PALETTE_VARIANTS_BY_ID) != sum(map(len, PALETTE_VARIANTS.values())):
    raise ValueError("PaletteVariant.variant_id 중복")


SCENE_ARCHETYPES: dict[str, SceneArchetype] = {
    "asymmetric_copyspace": SceneArchetype(
        "asymmetric_copyspace", frozenset({"drink", "food", "object"}),
        frozenset({"opaque", "transparent", "translucent"}),
        ("eye", "slightly_high"), (0.38, 0.58), ("right_third", "center"),
        ("top_left", "left"),
    ),
    "saturated_color_block": SceneArchetype(
        "saturated_color_block", frozenset({"drink", "food", "object"}),
        frozenset({"opaque", "transparent", "translucent"}),
        ("eye", "slightly_high"), (0.42, 0.64), ("center", "left_third", "right_third"),
        ("top", "bottom"),
    ),
    "natural_tabletop": SceneArchetype(
        "natural_tabletop", frozenset({"drink", "food", "object"}),
        frozenset({"opaque", "transparent", "translucent"}),
        ("eye", "slightly_high", "three_quarter"), (0.38, 0.62),
        ("center", "right_third"), ("top_left", "left"),
    ),
    "soft_pastel_set": SceneArchetype(
        "soft_pastel_set", frozenset({"drink", "object"}),
        frozenset({"opaque", "transparent", "translucent"}),
        ("eye", "slightly_high"), (0.40, 0.60), ("center", "right_third"),
        ("top_left", "left"),
    ),
    "tone_on_tone": SceneArchetype(
        "tone_on_tone", frozenset({"drink", "food", "object"}),
        frozenset({"opaque", "transparent", "translucent"}),
        ("eye", "slightly_high", "top_down"), (0.40, 0.62),
        ("center", "right_third"), ("top_left", "left", "bottom"),
    ),
    "warm_tabletop": SceneArchetype(
        "warm_tabletop", frozenset({"drink", "food", "object"}),
        frozenset({"opaque", "transparent", "translucent"}),
        ("slightly_high", "three_quarter", "top_down"), (0.38, 0.62),
        ("center", "right_third"), ("top_left", "left"),
    ),
}

# 국내 카페 광고 20장(PU-DATA-004)에서 실측한 상업 조판 후보. 이미지 생성 장면과 분리하며,
# 타이포 ON/OFF 시각 게이트 전에는 ReferenceRecipe에 강제 적용하지 않는다.
COMMERCIAL_LAYOUTS: dict[str, CommercialLayout] = {
    "kr_single_hero": CommercialLayout(
        "kr_single_hero", "single_hero_headline", "single",
        "headline_product_brand", ("top", "bottom"),
        ("KR-AD-001", "KR-AD-011"), cta_zone="bottom_right",
    ),
    "kr_multi_product_lineup": CommercialLayout(
        "kr_multi_product_lineup", "multi_product_lineup", "lineup_4_plus",
        "campaign_item_labels", ("top", "bottom"),
        ("KR-AD-002", "KR-AD-009", "KR-AD-016"), label_each_product=True,
    ),
}

# 직접 모델 입력과 구도 참고를 분리한 상품군별 근거. 2026-07-19 육안 감사 결과:
# · 라떼 002/014는 제품·질감이 일치해 identity 조건 허용. 005는 흑백 종이컵이라 구도만 사용.
# · 홍차 004만 깨끗한 투명 음료 조건으로 허용. 003의 파란 빨대와 011의 꽃은 구도만 사용.
# 전부 review_pending 출처이므로 GPU A/B와 사람 판정 전에는 usable=False다.
CONDITIONING_REFERENCE_SETS: dict[str, ConditioningReferenceSet] = {
    "latte_clean": ConditioningReferenceSet(
        "latte_clean", "latte", "drink", "opaque",
        ("EXT-DRINK-002", "EXT-DRINK-014"),
        ("EXT-DRINK-005",),
    ),
    "transparent_tea_clean": ConditioningReferenceSet(
        "transparent_tea_clean", "transparent_tea", "drink", "transparent",
        ("EXT-DRINK-004",),
        ("EXT-DRINK-003", "EXT-DRINK-011"),
    ),
}


def get_conditioning_reference_set(
        subject: str, allow_unapproved: bool = False) -> ConditioningReferenceSet | None:
    """상품군 conditioning 선택.

    PU-005에서 동일도메인 참조도 홍차 가짜 문자를 만들고 라떼 미감 이득이 없었다. 따라서
    사람 승인 전에는 운영 호출에 절대 노출하지 않으며, 명시적 GPU 실험만 후보를 조회한다.
    """
    matches = [refs for refs in CONDITIONING_REFERENCE_SETS.values()
               if refs.subject == subject]
    if len(matches) > 1:
        raise ValueError(f"ConditioningReferenceSet 후보 중복: {subject}")
    if not matches:
        return None
    refs = matches[0]
    return refs if allow_unapproved or refs.usable() else None


def _palette(variant_id: str) -> PaletteVariant:
    try:
        return PALETTE_VARIANTS_BY_ID[variant_id]
    except KeyError as exc:
        raise ValueError(f"등록되지 않은 palette variant: {variant_id}") from exc


_NO_PROPS = PropPolicy(categories=(), max_count=0)
_TABLETOP_PROPS = PropPolicy(categories=("tableware", "textile"), max_count=2)

# drink 직접 레퍼런스가 없는 무드는 cross-domain bootstrap이다. palette/props는 전이 근거에서
# 가져오지 않고 별도 후보·PropPolicy로 결정하며, 실제 라떼/투명홍차 결과 승인 전 usable=False다.
REFERENCE_RECIPES: dict[str, ReferenceRecipe] = {}


def _register(recipe: ReferenceRecipe) -> None:
    if recipe.recipe_id in REFERENCE_RECIPES:
        raise ValueError(f"ReferenceRecipe.recipe_id 중복: {recipe.recipe_id}")
    if recipe.palette_variant.variant_id not in PALETTE_VARIANTS_BY_ID:
        raise ValueError(f"registry 밖 palette variant: {recipe.palette_variant.variant_id}")
    REFERENCE_RECIPES[recipe.recipe_id] = recipe


_register(ReferenceRecipe(
    "drink", SCENE_ARCHETYPES["asymmetric_copyspace"], MOOD_TOKENS["editorial"],
    _palette("editorial/airy_neutral"), _NO_PROPS,
    ("01_에디토리얼__IMG_4598", "01_에디토리얼__IMG_4631", "01_에디토리얼__IMG_4703"),
    "비대칭 단일 히어로와 좌측 카피 여백, 밝고 절제된 스튜디오",
    source_domains=("object",), transfer_reason="상품 종류와 무관한 카피 여백·히어로 배치 전이",
    evidence_scope="camera+composition only, not palette/props",
))
_register(ReferenceRecipe(
    "drink", SCENE_ARCHETYPES["saturated_color_block"], MOOD_TOKENS["pop"],
    _palette("pop/cobalt_duo"), _NO_PROPS,
    ("02_팝_pop__IMG_4697", "02_팝_pop__IMG_4698", "02_팝_pop__IMG_4699"),
    "고채도 색면 위 중앙 음료 히어로와 선명한 그래픽 그림자",
    source_domains=("drink",),
))
_register(ReferenceRecipe(
    "drink", SCENE_ARCHETYPES["natural_tabletop"], MOOD_TOKENS["realism"],
    _palette("realism/neutral_grey"), _TABLETOP_PROPS,
    ("03_리얼리즘__IMG_4602", "03_리얼리즘__IMG_4657", "03_리얼리즘__IMG_4683"),
    "자연광 테이블 위 실제 촬영 같은 깊이와 절제된 주변 맥락",
    source_domains=("food",), transfer_reason="자연광·테이블 깊이·카메라 높이 전이",
    evidence_scope="camera+lighting+composition only, not edible props",
))
_register(ReferenceRecipe(
    "drink", SCENE_ARCHETYPES["soft_pastel_set"], MOOD_TOKENS["pastel"],
    _palette("pastel/soft_tri"), _NO_PROPS,
    ("04_파스텔__IMG_4674", "04_파스텔__IMG_4710", "04_파스텔__IMG_4712"),
    "부드러운 파스텔 면과 낮은 받침, 중앙 히어로와 확산광",
    source_domains=("object",), transfer_reason="제품 히어로의 낮은 받침·확산광 구도 전이",
    evidence_scope="camera+composition only, not product count/props",
))
_register(ReferenceRecipe(
    "drink", SCENE_ARCHETYPES["tone_on_tone"], MOOD_TOKENS["monotone"],
    _palette("monotone/pale"), _NO_PROPS,
    ("05_모노톤__IMG_4705", "05_모노톤__IMG_4713"),
    "단일 색군 배경과 제품 고유색을 분리한 간결한 히어로",
    source_domains=("drink", "object"), transfer_reason="직접 음료 근거를 제품 색면 구도로 보강",
    evidence_scope="color-field+composition only, not object identity/props",
))
_register(ReferenceRecipe(
    "drink", SCENE_ARCHETYPES["warm_tabletop"], MOOD_TOKENS["warm_organic"],
    _palette("warm_organic/travertine"), _TABLETOP_PROPS,
    ("06_웜빈티지__IMG_4667", "06_웜빈티지__IMG_4678", "06_웜빈티지__IMG_4620"),
    "따뜻한 자연 재질 테이블과 측면광, 중앙 상품 주변의 낮은 밀도 맥락",
    source_domains=("food", "object"), transfer_reason="자연 재질·측면광·정물 깊이 전이",
    evidence_scope="materials+lighting+composition only, not edible props",
))


def get_reference_recipe(domain: str, mood: str,
                         allow_unapproved: bool = False) -> ReferenceRecipe | None:
    """도메인·무드 recipe 선택. 미승인 후보는 명시적인 실험에서만 반환한다."""
    matches = [recipe for recipe in REFERENCE_RECIPES.values()
               if recipe.domain == domain and recipe.mood.key == mood]
    if len(matches) > 1:
        raise ValueError(f"ReferenceRecipe 후보 중복: {domain}/{mood}")
    if not matches:
        return None
    recipe = matches[0]
    return recipe if allow_unapproved or recipe.usable() else None
