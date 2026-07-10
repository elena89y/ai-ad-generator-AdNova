"""스타일 디자인 토큰 (DESIGN_SYSTEM_v1 반영, 레퍼런스 1차) — 담당: 한의정.

overlay_service(타이포)·생성경로(씬 프롬프트)·저지(목표미학)가 공유하는 단일 기준.
소스: ~/ai-ad-generator-AdNova-rule/DESIGN_SYSTEM_v1.md (레퍼런스 132장 + 프롬프트 6개).

font 값은 overlay_service._font 의 kind(serif_elegant/display_heavy/condensed/…)와 일치.
production: 'hybrid'(원본 편집+PIL 타이포) | 'generative'(크리에이티브 씬 생성 비중↑).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StyleSpec:
    key: str
    mood: str
    palette: tuple[str, ...]          # 대표 hex (2~3색 중심)
    head_font: str                    # 헤드라인 폰트 kind
    sub_font: str                     # 서브/캡션 폰트 kind
    accent: tuple[int, int, int]      # 액센트 RGB
    production: str                   # hybrid | generative
    scene_prompt: str = ""            # 생성 씬 프롬프트 템플릿({subject} 치환)
    negative: str = ""


# 공통 네거티브(레퍼런스 전 스타일 공통)
_NEG = ("cluttered background, scattered crumbs, excessive props, long sentences, busy infographic, "
        "harsh shadows, watermark, logo, cropped, placeholder text, lorem ipsum")

# 사물(SKU) 전용 네거티브 — 형태·색·로고 보존 최우선(정직성 경계). 여기선 logo 를 빼지 않는다:
#   제품 로고는 원본을 보존해야 하므로 '가짜 로고 생성/왜곡'만 차단(distorted/warped/extra logo).
_OBJ_NEG = ("distorted logo, warped brand text, mirrored text, misspelled label, altered product shape, "
            "changed product color, extra duplicate products, cluttered background, long sentences, "
            "placeholder text, lorem ipsum, watermark")

STYLE_SPECS: dict[str, StyleSpec] = {
    "editorial": StyleSpec(
        key="editorial", mood="하이엔드 매거진·룩북, 프리미엄 미니멀 자연광",
        palette=("#F2ECE0", "#D8CFBB", "#3B2F2A"), head_font="serif_elegant", sub_font="gothic",
        accent=(59, 47, 42), production="hybrid",
        # ⚠️ 'magazine layout/moodboard' 어휘는 FLUX가 가짜 잡지 텍스트(gibberish)를 그림(실측 2026-07-10).
        #    단일 히어로 클린 에디토리얼로 규약 — 콜라주·텍스트 유발어 제거, 여백·자연광만.
        scene_prompt=("premium editorial hero shot of {subject} on a clean muted cream surface, "
                      "single centered subject, soft natural window light, generous empty negative space, "
                      "minimalist high-end lookbook, no props, no collage"),
        negative=_NEG),
    "pop": StyleSpec(
        key="pop", mood="하이퍼리얼 제품×음식/스포츠 크리에이티브 합성, 강한 측광 8k",
        palette=("#F2A93B", "#C42E5C", "#1E7A5A"), head_font="display_heavy", sub_font="gothic_bold",
        accent=(196, 46, 92), production="generative",
        scene_prompt=("hyper-realistic premium product photography of {subject}, creative composition "
                      "with dessert/lifestyle objects, glossy viscous highlights, intense side lighting, "
                      "shallow depth of field, 8k, vivid textures, --ar 4:5"),
        negative=_NEG + ", low saturation, dull"),
    "realism": StyleSpec(
        key="realism", mood="미니멀 럭셔리 스튜디오 푸드, 시네마틱 소프트, 선명 질감",
        palette=("#EFE7D8", "#E7C3C9", "#9FB98A"), head_font="serif_elegant", sub_font="gothic",
        accent=(120, 100, 80), production="hybrid",
        scene_prompt=("minimal luxury studio food photography of {subject}, cinematic soft lighting, "
                      "shallow depth, crisp texture, 2-3 color palette, clean gradient background, "
                      "generous negative space, 8k, --ar 4:5"),
        negative=_NEG + ", fake food texture, overcrowded ingredients"),
    "pastel_float": StyleSpec(
        key="pastel_float", mood="몽환·부유·산뜻, 소프트 물결 에테리얼 하이키",
        palette=("#F6D8E4", "#E5DCF2", "#D9F0E6"), head_font="display_round", sub_font="gothic",
        accent=(198, 150, 190), production="hybrid",
        scene_prompt=("dreamy pastel floating scene of {subject}, soft rippling water surface, "
                      "ethereal high-key light, gentle reflections, pastel pink and lavender, --ar 4:5"),
        negative=_NEG),
    "monotone": StyleSpec(
        key="monotone", mood="모노크롬 톤온톤(단일 색계열) 볼드 미니멀 임팩트",
        palette=("#C42E2E", "#E7A63A", "#C42E2E"), head_font="display_heavy", sub_font="gothic_bold",
        accent=(231, 166, 58), production="hybrid",
        scene_prompt=("monochromatic tone-on-tone product shot of {subject}, single dominant color, "
                      "bold minimal, large brand typography, clean even lighting, --ar 4:5"),
        negative=_NEG),
    "warm_vintage": StyleSpec(
        key="warm_vintage", mood="따뜻한 프리미엄 라이프스타일, 원목·골든아워·감성",
        palette=("#E8D9C0", "#C9A876", "#A97F4F"), head_font="serif_elegant", sub_font="gothic",
        accent=(169, 127, 79), production="generative",
        scene_prompt=("warm premium lifestyle still life of {subject}, wood and marble, dried wheat, "
                      "Korean bojagi wrapping, warm side lighting, elegant shadows, beige studio, --ar 4:5"),
        negative=_NEG),
    "pop_split": StyleSpec(
        key="pop_split", mood="여름음료 2패널 50:50 — 상단 매크로 / 하단 상품컷+컵뒤 블록레터",
        palette=("#EEE7D4", "#C98418", "#2E2338"), head_font="condensed", sub_font="gothic",
        accent=(201, 132, 24), production="hybrid",
        scene_prompt=("extreme macro close-up of the ice cubes and {subject} liquid surface, "
                      "filling the frame, glossy wet reflections, cold, high detail, no glass rim, "
                      "no background"),
        negative=_NEG),
    # --- C 사물(SKU) 전용 (10_사물_최신 92장 레퍼런스, 2026-07-10) ---
    # ⚠️ 사물은 SKU → 형태·색·로고 보존 최우선. 신품화(마모·먼지 제거)는 허용(형태 불변),
    #    로고 텍스트/브랜드색 왜곡은 _OBJ_NEG 로 강력 차단(정직성 경계). Kontext 로고 글자 약함 유의.
    "object_studio": StyleSpec(
        key="object_studio", mood="단일 히어로 제품 · 반사 페데스탈 · 드라마틱 림라이트 · 딥톤/제품색 배경",
        palette=("#14121A", "#C9A15A", "#F2ECE0"), head_font="display_heavy", sub_font="gothic_bold",
        accent=(201, 161, 90), production="hybrid",
        scene_prompt=("hyper-realistic premium studio product photograph of {subject}, single hero on a "
                      "reflective pedestal, dramatic rim lighting and sharp directional shadow, deep gradient "
                      "background in a color that echoes the product, glossy reflections, crisp detail, 8k, --ar 4:5"),
        negative=_OBJ_NEG),
    "object_splash": StyleSpec(
        key="object_splash", mood="부유 제품 · 성분/물 스플래시 · 제품색 모노팔레트 · 다이내믹 앵글",
        palette=("#0E2A44", "#3E7CB1", "#EAF2F8"), head_font="condensed", sub_font="gothic",
        accent=(62, 124, 177), production="hybrid",
        scene_prompt=("hyper-realistic {subject} floating mid-air in a dynamic diagonal composition, "
                      "matching-color ingredient props and splashing water droplets, monochromatic color-echo "
                      "environment tied to the product, a dramatic beam of light, glossy wet highlights, 8k, --ar 4:5"),
        negative=_OBJ_NEG),
}


def get_spec(key: str) -> StyleSpec:
    """스타일 키 → 스펙(없으면 editorial 폴백)."""
    return STYLE_SPECS.get(key, STYLE_SPECS["editorial"])
