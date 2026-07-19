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

SceneArchetype·ReferenceRecipe 적재는 후속. 기존 파이프라인 미연결.
"""
from __future__ import annotations

from .reference_recipe import MoodToken, PaletteVariant

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
        PaletteVariant("editorial", ("#EDE8DF", "#FAF8F4"), "P4BR editorial/seamless"),
        PaletteVariant("editorial", ("#E8E0D4", "#D8CDBC"), "P4BR editorial/warm-neutral"),
    ),
    "pop": (
        PaletteVariant("pop", ("#2B3FBB", "#F2ECE3"), "P4BR pop/drink cobalt", ("drink",), "diagonal"),
        PaletteVariant("pop", ("#2D6A6F", "#F2ECE3"), "P4BR pop/object teal", ("object",)),
        PaletteVariant("pop", ("#C96D5B", "#F2ECE3"), "P4BR pop/object coral", ("object",)),
    ),
    "realism": (
        PaletteVariant("realism", ("#DCDCDC", "#9A9A9A"), "P4BR realism/neutral-grey"),
    ),
    "pastel": (
        PaletteVariant("pastel", ("#F7D6E0", "#D9CDF2", "#CFE8DD"), "P4BR pastel/tri"),
        PaletteVariant("pastel", ("#CDE4F7", "#F7DCE3"), "P4BR pastel/blue-pink"),
        PaletteVariant("pastel", ("#DFF0E8", "#F3D9DF"), "P4BR pastel/mint-pink"),
        PaletteVariant("pastel", ("#E4D9F2", "#F7F4FB"), "P4BR pastel/lavender"),
    ),
    "monotone": (
        PaletteVariant("monotone", ("#1E1E22", "#4A4A52"), "P4BR monotone/dark"),
        PaletteVariant("monotone", ("#DCDCDC", "#9A9A9A"), "P4BR monotone/pale"),
    ),
    "warm_organic": (
        PaletteVariant("warm_organic", ("#E8E0D4", "#D8CDBC"), "P4BR warm/travertine"),
        PaletteVariant("warm_organic", ("#F2EDE4", "#B7A48F"), "P4BR warm/wood-linen"),
    ),
}
