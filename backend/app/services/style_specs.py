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
        key="realism", mood="사진 사실감 우선 스튜디오 푸드 — 실제 질감·자연광, 매크로 디테일",
        palette=("#EFE7D8", "#E7C3C9", "#9FB98A"), head_font="serif_elegant", sub_font="gothic",
        accent=(120, 100, 80), production="hybrid",
        # ⚠️ 실측(2026-07-10): 과한 스타일화로 고기가 CGI/장난감처럼 뭉갬 → 사진 사실감을 최우선 앵커.
        #   고기류는 비계(흰 지방)와 붉은 살결의 대비·마블링이 실제처럼 선명해야 함.
        scene_prompt=("photorealistic premium studio food photograph of {subject}, true-to-life natural "
                      "surface texture and moisture, sharp macro detail, for meat keep the white fat marbling "
                      "and deep red lean clearly distinct, cinematic soft natural light, shallow depth, "
                      "clean gradient background, generous negative space, --ar 4:5"),
        negative=_NEG + ", CGI, 3d render, plastic, toy, wax figure, cartoon, smoothed over, "
                        "overly glossy, fake food texture, uniform color, overcrowded ingredients"),
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
        key="warm_vintage", mood="따뜻한 프리미엄 라이프스타일, 원목·골든아워·감성 (제품색 보존)",
        palette=("#E8D9C0", "#C9A876", "#A97F4F"), head_font="serif_elegant", sub_font="gothic",
        accent=(169, 127, 79), production="hybrid",
        # ⚠️ 실측(2026-07-10): 'bojagi wrapping'이 없던 비닐봉투를 만들어 제품을 가리고,
        #   'beige studio'+generative가 음식 실제색(말차 초록·라즈베리 빨강)을 오렌지 모노톤으로 뭉갬.
        #   → 포장어휘 제거, 제품을 명시적 히어로로, 실제색 유지, 소품은 배경으로만.
        scene_prompt=("warm premium lifestyle photograph of {subject} as the clear hero in sharp focus, "
                      "a wooden surface with dried wheat and soft cafe props blurred in the background, "
                      "gentle golden-hour side light, elegant soft shadows, keep the food's real vivid colors "
                      "and appetizing texture, no packaging, no plastic bag, --ar 4:5"),
        negative=_NEG + ", plastic bag, wrapping, packaging, washed-out monochrome, orange color cast, dull food"),
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
        # ⚠️ 배경교체 프레이밍(2026-07-10): 'photograph of {subject}'는 제품 전체 재생성을 유도해
        #   애매한 형태(예: 문어 괄사)가 매끈한 구로 붕괴. Kontext=편집모델 → '제품은 그대로, 배경만' 지시.
        scene_prompt=("Keep the {subject} exactly as it is: identical shape, outline, proportions, color, "
                      "material and every surface detail — do NOT redraw, reshape, smooth, round or restyle "
                      "the object itself. Change ONLY the surroundings: replace the background with a deep dark "
                      "studio gradient, add dramatic rim lighting and a subtle glossy floor reflection beneath it."),
        negative=_OBJ_NEG),
    "object_splash": StyleSpec(
        key="object_splash", mood="부유 제품 · 성분/물 스플래시 · 제품색 모노팔레트 · 다이내믹 앵글",
        palette=("#0E2A44", "#3E7CB1", "#EAF2F8"), head_font="condensed", sub_font="gothic",
        accent=(62, 124, 177), production="hybrid",
        scene_prompt=("hyper-realistic {subject} floating mid-air in a dynamic diagonal composition, "
                      "matching-color ingredient props and splashing water droplets, monochromatic color-echo "
                      "environment tied to the product, a dramatic beam of light, glossy wet highlights, 8k, --ar 4:5"),
        negative=_OBJ_NEG),
    # --- 디저트 단면 매크로 (09_기타/클로즈업 케익 크로스섹션, 2026-07-10) ---
    # ⚠️ 생성비중↑ — 업로드된 통 케이크의 '단면'을 새로 만든다(원본에 단면이 없음). 정직성 게이트:
    #    레이어는 그 케이크의 실제 재료여야(gpt_service 레시피 검증 후 layers 주입) — 허위 레이어 금지.
    "cross_section": StyleSpec(
        key="cross_section", mood="프리미엄 파티세리 단면 매크로 — 레이어별 물성, 프레임 꽉 참, 여백 0",
        palette=("#F4EDE1", "#C25B4E", "#7A5A3A"), head_font="serif_elegant", sub_font="gothic",
        accent=(122, 90, 58), production="generative",
        scene_prompt=("extreme macro front-facing cross-section of {subject}, camera at exact eye-level 0-degree, "
                      "all layers sheared flat on one continuous vertical plane, hyper-real per-layer texture "
                      "(moisture, gloss, air pockets, crumb), focus stacked no bokeh, premium patisserie campaign, "
                      "the sliced cross-section fills the entire frame, zero negative space, not a whole cake, "
                      "not angled, not isometric, --ar 4:5"),
        negative=_NEG + ", whole cake, three-quarter view, angled view, isometric, cake top visible"),
}


def get_spec(key: str) -> StyleSpec:
    """스타일 키 → 스펙(없으면 editorial 폴백)."""
    return STYLE_SPECS.get(key, STYLE_SPECS["editorial"])


# 프론트 6버튼(무드) → style_spec 키 매핑 (2026-07-10, 봄·한의정 조율안).
#   나머지 4종(object_studio/object_splash/pop_split/cross_section)은 '포맷'이라 버튼이 아니라
#   라우터가 콘텐츠(사물/여름음료/케이크단면)로 자동 선택 — 무드 버튼과 직교.
#   키는 한글 라벨·영문 별칭·기존 StylePreset 값을 모두 수용(프론트 최종 명칭과 무관하게 동작).
BUTTON_STYLE_MAP: dict[str, str] = {
    # 무드 6버튼
    "비비드": "pop", "vivid": "pop", "pop": "pop",
    "미니멀": "monotone", "minimal": "monotone", "monotone": "monotone",
    "럭셔리": "editorial", "luxury": "editorial", "editorial": "editorial",
    "내추럴": "realism", "natural": "realism", "realism": "realism",
    "감성": "warm_vintage", "emotional": "warm_vintage", "warm_vintage": "warm_vintage",
    "파스텔": "pastel_float", "pastel": "pastel_float", "pastel_float": "pastel_float",
    # 폐기된 구 프리셋 폴백(레트로→파스텔 재카테고리화)
    "레트로": "pastel_float", "retro": "pastel_float", "retro_paper": "pastel_float",
}


def resolve_style(button: str) -> str:
    """프론트 버튼/프리셋명 → style_spec 키. 미지값은 editorial 폴백. ads.py 가 process_ad(style=) 로 전달."""
    return BUTTON_STYLE_MAP.get((button or "").strip().lower(), "editorial")
