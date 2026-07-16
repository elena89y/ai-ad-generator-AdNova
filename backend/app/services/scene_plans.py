"""광고 장면 플랜 — 담당: 한의정. DIRECTION_v4.2 P4B-R 장면 계약.

ScenePlan = 배경 생성 프롬프트(오프라인 라이브러리 빌드용) + 합성 기하 + 카피 여백 + 광원방향.
  - light_dir 는 프롬프트에 명시해 '사전 확정' — 접지 그림자 방향을 추정할 필요가 없다.
  - 소품(prop)은 배경 프롬프트의 일부로 생성한다(런타임 소품 합성 없음).
    소품 어휘는 PROP_PHRASES 로 제한 — core_ingredients/온도효과와 매칭되는 판만 런타임에 선택
    (정직성 경계: 그 상품과 무관한 외래 소품 금지. 장식성 배경 요소(색면·린넨·마른풀)는 소품이 아님).
  - ⚠️ SDXL 도 CLIP 77토큰 한도(절대 함정 #2) — bg_prompt 는 조립 후 60단어 이하 유지.

런타임 선택 규약(결정 D-2·D-4):
  - 아키타입 로테이션: seed % len(plans) → 재생성마다 다른 구도.
  - requires_recompose=True 플랜은 음료 재연출(P5) 전용 — DRINK_RECOMPOSE=0 이면 선택에서 제외.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScenePlan:
    key: str                  # "pop/drink/diagonal_splash"
    style: str                # 6무드 키 (style_specs 무드와 동일 계열)
    domain: str               # "drink" | "object"
    archetype: str
    scene: str                # 아키타입 장면 묘사(영어, 12~20단어) — bg_prompt 조립 재료
    subject_pos: tuple        # (cx, cy) 0~1, 제품 중심
    subject_scale: float      # 제품 폭 / 캔버스 폭
    surface_y: float          # 접지선 y (0~1)
    light_dir: str            # "left" | "right" — 프롬프트와 그림자 방향의 단일 출처
    text_zone: str            # "top" | "top_left" | "top_right" — overlay 헤드라인 위치
    render_mode: str = "sdxl"  # "code" | "sdxl" — 배경 소싱 티어(D-12)
    palette: tuple[str, ...] = ()  # 코드 렌더러 입력 hex 팔레트
    view_angle: str = "eye"   # "eye" | "high" | "top" — 입력 사진과 장면의 카메라 각도 계약
    shadow_strength: float = 0.35
    reflection_strength: float = 0.0
    prop_slots: tuple = ()    # PROP_PHRASES 키 중 이 장면에 어울리는 것
    requires_recompose: bool = False  # True = P5 재연출 전용(합성 부적합 구도)


# 소품 문구 — 이 어휘 밖의 소품을 프롬프트에 넣지 말 것(정직성 게이트가 검사하는 목록)
PROP_PHRASES: dict[str, str] = {
    "beans": "a few scattered coffee beans",
    "orange": "fresh orange slices",
    "lemon": "fresh lemon slices",
    "strawberry": "a few fresh strawberries",
    "ice": "clear ice cubes and water droplets",
    "splash": "a frozen dynamic milk splash arc mid-air",
    "steam": "gentle steam wisps",
}

# core_ingredients(정규화된 영문 단어) → prop 슬롯. 정확 일치가 아니면 소품 없는 판 사용.
PROP_MAP: dict[str, str] = {
    "coffee": "beans", "espresso": "beans", "bean": "beans",
    "milk": "splash", "cream": "splash",
    "orange": "orange", "lemon": "lemon",
    "strawberry": "strawberry", "berry": "strawberry",
    "ice": "ice",
}


def build_bg_prompt(plan: ScenePlan, props: tuple = ()) -> str:
    """플랜 → SDXL 배경 프롬프트. 규칙(v4 P4-1): 광고장면 선언 + 장면 + 광원 + 빈 자리 +
    카피 여백 + 금지어. 60단어 이하 유지(CLIP 77토큰)."""
    prop_txt = ""
    if props:
        prop_txt = ", " + ", ".join(PROP_PHRASES[p] for p in props if p in PROP_PHRASES)
    pos_word = "center" if abs(plan.subject_pos[0] - 0.5) < 0.06 else (
        "right" if plan.subject_pos[0] > 0.5 else "left")
    zone = plan.text_zone.replace("_", " ")
    return (
        f"commercial advertising photography backdrop, no product, {plan.scene}{prop_txt}, "
        f"soft {plan.light_dir}-side key light, empty surface in the lower {pos_word} "
        f"for product placement, clean uncluttered {zone} area for headline, "
        f"photorealistic, no text, no letters, no people"
    )


NEGATIVE_PROMPT = (
    "text, letters, words, watermark, logo, person, hands, cup, mug, glass, "
    "bottle, can, jar, plate of food, product, cartoon, illustration, frame"
)


def _p(style, domain, archetype, scene, pos, scale, sy, light, tz,
       props=(), recompose=False, view="eye", shadow=0.35, reflection=0.0,
       render_mode="sdxl", palette=()) -> ScenePlan:
    return ScenePlan(
        key=f"{style}/{domain}/{archetype}", style=style, domain=domain,
        archetype=archetype, scene=scene, subject_pos=pos, subject_scale=scale,
        surface_y=sy, light_dir=light, text_zone=tz, view_angle=view,
        shadow_strength=shadow, reflection_strength=reflection,
        prop_slots=props, requires_recompose=recompose,
        render_mode=render_mode, palette=tuple(palette))


PLANS: list[ScenePlan] = [
    # ── pop ─────────────────────────────────────────────────────────────────
    _p("pop", "drink", "diagonal_field",
       "two diagonal color fields with one hard shadow stripe",
       (0.55, 0.60), 0.46, 0.72, "left", "top_left",
       render_mode="code", palette=("#2146C7", "#FF7A1A")),
    _p("pop", "drink", "diagonal_splash",
       "bold electric blue and orange color-block wall, glossy orange surface, "
       "dynamic diagonal composition",
       (0.55, 0.60), 0.46, 0.72, "left", "top_left", props=("splash", "ice"),
       recompose=True),
    _p("pop", "drink", "color_block_duo",
       "two flat saturated color panels, cobalt blue and tangerine, one hard sun shadow "
       "stripe across a glossy tabletop",
       (0.50, 0.62), 0.42, 0.74, "right", "top",
       render_mode="code", palette=("#2146C7", "#FF7A1A")),
    _p("pop", "object", "color_block",
       "flat vivid duotone wall in cobalt and lime green, geometric shadow shapes, "
       "glossy seamless floor",
       (0.50, 0.62), 0.42, 0.74, "left", "top",
       render_mode="code", palette=("#2146C7", "#B7E340")),
    _p("pop", "object", "concept_stage",
       "saturated coral wall and cream seamless floor with one diagonal edge accent",
       (0.58, 0.62), 0.40, 0.74, "right", "top_left",
       render_mode="code", palette=("#FF6F61", "#F5EFE6")),
    # ── editorial ───────────────────────────────────────────────────────────
    _p("editorial", "drink", "asym_negative",
       "premium magazine still-life, warm gray stone tray on pale plaster wall, "
       "generous negative space, single window light",
       (0.62, 0.64), 0.40, 0.76, "left", "top_left",
       render_mode="code", palette=("#E8E0D4", "#D8CDBC")),
    _p("editorial", "drink", "split_card",
       "two-tone seamless split with ivory upper wall and warm taupe lower band",
       (0.50, 0.66), 0.38, 0.78, "right", "top",
       render_mode="code", palette=("#F2EDE4", "#B7A48F")),
    _p("editorial", "object", "asym_negative",
       "architectural beige plaster niche, deep soft shadow, generous negative space, "
       "gallery lighting",
       (0.60, 0.64), 0.40, 0.76, "left", "top_left",
       render_mode="code", palette=("#E8E0D4", "#D8CDBC")),
    _p("editorial", "object", "seamless_min",
       "bright cement wall and clean white seamless floor with soft tonal falloff",
       (0.50, 0.60), 0.38, 0.70, "right", "top",
       render_mode="code", palette=("#EDE8DF", "#FAF8F4")),
    # ── realism ─────────────────────────────────────────────────────────────
    _p("realism", "drink", "cafe_table_window",
       "sunlit wooden cafe table by a large window, blurred cozy interior bokeh, "
       "natural morning light",
       (0.50, 0.63), 0.44, 0.78, "left", "top", props=("beans",)),
    _p("realism", "drink", "marble_daylight",
       "white marble countertop, airy bright kitchen bokeh, soft daylight",
       (0.52, 0.64), 0.44, 0.78, "right", "top", props=("lemon",)),
    _p("realism", "object", "desk_daylight",
       "light oak desk by a bright window, minimal home office bokeh, natural daylight",
       (0.50, 0.63), 0.42, 0.78, "left", "top"),
    _p("realism", "object", "linen_daylight",
       "washed pale linen cloth on a bright table, gentle fabric folds, soft daylight",
       (0.50, 0.64), 0.42, 0.78, "right", "top"),
    # ── pastel ──────────────────────────────────────────────────────────────
    _p("pastel", "drink", "soft_seamless",
       "pastel pink to lavender wall with a mint seamless floor band",
       (0.50, 0.60), 0.40, 0.70, "left", "top",
       render_mode="code", palette=("#F7D6E0", "#D9CDF2", "#CFE8DD")),
    _p("pastel", "drink", "cloud_gradient",
       "clean sky blue to blush two-tone gradient with a soft vignette",
       (0.50, 0.58), 0.42, 0.68, "right", "top",
       render_mode="code", palette=("#CDE4F7", "#F7DCE3")),
    _p("pastel", "drink", "dreamy_cloud",
       "soft cream cloud shapes, baby blue to blush pink gradient, glossy "
       "reflective floor",
       (0.50, 0.58), 0.42, 0.68, "right", "top", recompose=True,
       reflection=0.12),
    _p("pastel", "object", "soft_seamless",
       "pale mint wall with a blush seamless floor band and soft tonal falloff",
       (0.50, 0.60), 0.40, 0.70, "left", "top",
       render_mode="code", palette=("#DFF0E8", "#F3D9DF")),
    _p("pastel", "object", "lilac_seamless",
       "pastel lilac wall with a pale lavender seamless floor band",
       (0.50, 0.55), 0.36, 0.62, "right", "top",
       render_mode="code", palette=("#E4D9F2", "#F7F4FB")),
    # ── monotone (결정 D-3: 중립 판 + style_finish 듀오톤 착색) ────────────────
    _p("monotone", "drink", "tone_seamless",
       "neutral light gray wall and floor seamless with a smooth tonal falloff",
       (0.50, 0.60), 0.40, 0.70, "left", "top",
       render_mode="code", palette=("#DCDCDC", "#9A9A9A")),
    _p("monotone", "drink", "dark_mono",
       "deep charcoal studio, dramatic single rim light, dark subtly reflective surface",
       (0.50, 0.62), 0.42, 0.74, "right", "top", reflection=0.12,
       render_mode="code", palette=("#1E1E22", "#4A4A52")),
    _p("monotone", "object", "tone_seamless",
       "neutral light gray wall and floor seamless with a smooth tonal falloff",
       (0.50, 0.60), 0.40, 0.70, "left", "top",
       render_mode="code", palette=("#DCDCDC", "#9A9A9A")),
    _p("monotone", "object", "dark_mono",
       "deep charcoal studio, dramatic single rim light, dark subtly reflective surface",
       (0.50, 0.62), 0.42, 0.74, "right", "top", reflection=0.12,
       render_mode="code", palette=("#1E1E22", "#4A4A52")),
    # ── warm_vintage ────────────────────────────────────────────────────────
    _p("warm_vintage", "drink", "linen_organic",
       "beige linen tablecloth, dried grass stems in soft focus behind, warm golden "
       "afternoon light, organic textures",
       (0.52, 0.64), 0.42, 0.78, "left", "top"),
    _p("warm_vintage", "drink", "wood_morning",
       "rustic warm wood table, kraft paper texture wall, gentle morning sunbeam",
       (0.50, 0.64), 0.42, 0.78, "right", "top", props=("beans",)),
    _p("warm_vintage", "object", "linen_organic",
       "beige linen backdrop with soft folds, minimal dried botanicals aside, warm "
       "golden light",
       (0.52, 0.64), 0.42, 0.78, "left", "top"),
    _p("warm_vintage", "object", "craft_paper",
       "kraft paper backdrop in beige tones, subtle paper texture, soft warm light",
       (0.50, 0.64), 0.42, 0.78, "right", "top"),
]

_BY_KEY = {p.key: p for p in PLANS}
assert len(_BY_KEY) == len(PLANS), "ScenePlan.key 중복"
_FLAT_KEYS = {p.key.replace("/", "_") for p in PLANS}
assert len(_FLAT_KEYS) == len(PLANS), "ScenePlan 파일명용 key 충돌"


def plans_for(style: str, domain: str, allow_recompose: bool = False) -> list[ScenePlan]:
    """스타일·도메인의 사용 가능 플랜. allow_recompose=False 면 재연출 전용 플랜 제외."""
    out = [p for p in PLANS if p.style == style and p.domain == domain
           and (allow_recompose or not p.requires_recompose)]
    return out


def get_plan(style: str, domain: str, seed: int = 0,
             allow_recompose: bool = False) -> ScenePlan | None:
    """아키타입 로테이션(결정 D-2): seed % n. 해당 스타일·도메인 플랜 없으면 None."""
    cands = plans_for(style, domain, allow_recompose)
    if not cands:
        return None
    return cands[seed % len(cands)]


def map_props(core_ingredients: list[str] | None, effects: list[str]) -> set[str]:
    """정확 일치하는 재료·효과만 prop으로 허용한다. 모호한 부분문자열은 소품 없음으로 둔다."""
    allowed: set[str] = set(e for e in effects if e in PROP_PHRASES)
    for ing in (core_ingredients or []):
        slot = PROP_MAP.get(str(ing).strip().lower())
        if slot:
            allowed.add(slot)
    return allowed
