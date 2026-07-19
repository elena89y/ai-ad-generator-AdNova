"""ReferenceRecipe — 레퍼런스 조립 계약 (코덱스 재설계 순서 2, 2026-07-19).

배경: `_RECOMPOSE_STAGING[style]` 단일 규칙은 "style이 카메라앵글·소품을 소유"하는 구조라
  '웜이면 무조건 원두', '파스텔이면 무조건 로우앵글' 같은 오류를 낳았다(상품 불일치·정직성 위반).
해법: 4축을 분리해 조립한다 —
  · **MoodToken(style)**   = 분위기. 색·조명·재질·소품'밀도'만 소유. 카메라앵글·배치 소유 금지.
  · **SceneArchetype**     = 연출. 카메라앵글·스케일·배치·카피영역·호환 domain/opacity 소유.
  · **PropPolicy**         = 안전경계. 구체 소품명이 아니라 카테고리·밀도·재질. 먹는 소품은 근거 있을 때만.
  · **ReferenceRecipe**    = 특정 (domain, archetype, mood) 조합의 조립 결과 + 대표 레퍼런스 2~3장 근거
                             + 사람(아트디렉터) 승인 게이트.

이 파일은 **스키마만** 정의한다. 실제 MoodToken/SceneArchetype 인스턴스 적재는 순서 3
  (manifest에서 domain+archetype+mood 조합별 대표 2~3장 선정) 이후. 기존 파이프라인 미연결.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_PROP_DENSITIES = ("none", "low", "medium", "high")
_EDIBLE_MODES = ("none", "source_only")  # source_only = core_ingredients + 원본 Vision 근거 있을 때만
_CAMERA_ANGLES = ("eye", "slightly_high", "high", "low", "three_quarter", "top_down")


@dataclass(frozen=True)
class MoodToken:
    """스타일 = 분위기. 색·조명·재질·소품 밀도만 소유한다.

    ⚠️ 카메라 앵글·제품 배치·구체 소품명을 소유하지 않는다(그건 SceneArchetype·PropPolicy 몫).
    이 경계가 '웜이면 무조건 top-down' 같은 오류를 막는다.
    """
    key: str                       # editorial|pop|realism|pastel|monotone|warm_organic
    palette: tuple[str, ...]       # hex 색들
    lighting: str                  # 서술: "warm directional daylight" 등
    materials: tuple[str, ...]     # wood, linen, stone, travertine...
    prop_density: str              # none|low|medium|high

    def __post_init__(self) -> None:
        if self.prop_density not in _PROP_DENSITIES:
            raise ValueError(f"prop_density 잘못됨: {self.prop_density!r}")
        if not self.key:
            raise ValueError("MoodToken.key 비어있음")


@dataclass(frozen=True)
class SceneArchetype:
    """연출 = 구도. 카메라 앵글·스케일·배치·카피영역, 그리고 호환 domain/opacity를 소유한다.

    상품과 맞지 않는 아키타입은 is_compatible로 처음부터 제외한다(투명 아이스 음료에 pedestal 등).
    """
    key: str                              # tabletop_lifestyle, soft_pedestal, minimal_studio...
    domains: frozenset[str]               # {"drink","object","food"}
    allowed_opacity: frozenset[str]       # {"opaque","transparent","translucent"}
    camera_angles: tuple[str, ...]        # _CAMERA_ANGLES 중
    subject_scale: tuple[float, float]    # (min, max) 제품 폭/캔버스 폭
    placements: tuple[str, ...]           # center, right_third, left_third...
    text_zones: tuple[str, ...]           # top, top_left, left...

    def __post_init__(self) -> None:
        lo, hi = self.subject_scale
        if not (0.0 < lo <= hi <= 1.0):
            raise ValueError(f"subject_scale 범위 오류: {self.subject_scale}")
        for a in self.camera_angles:
            if a not in _CAMERA_ANGLES:
                raise ValueError(f"camera_angle 잘못됨: {a!r}")
        if not self.domains or not self.allowed_opacity:
            raise ValueError("domains/allowed_opacity 비어있음")


@dataclass(frozen=True)
class PropPolicy:
    """소품 안전경계. 구체 명사가 아니라 카테고리·밀도·재질로 표현한다.

    먹는 소품(과일·원두 등)은 edible='source_only'일 때만, 그것도 core_ingredients + 원본 Vision
    근거가 있을 때만 조립부가 허용한다(커피=원두 OK, 홍차=찻잎 확인시만, 불명확=비식용만).
    로고 SKU는 avoid_overlap로 제품을 가리는/반사하는 소품을 금지한다.
    """
    categories: tuple[str, ...]           # tableware, textile, botanical, surface...
    edible: str = "none"                  # none|source_only
    max_count: int = 2
    avoid_overlap_with_product: bool = True

    def __post_init__(self) -> None:
        if self.edible not in _EDIBLE_MODES:
            raise ValueError(f"edible 잘못됨: {self.edible!r}")
        if self.max_count < 0:
            raise ValueError("max_count 음수")


@dataclass(frozen=True)
class ReferenceRecipe:
    """특정 (domain, archetype, mood) 조합의 조립 계약.

    대표 레퍼런스 2~3장의 공통 특징에서 추출하고, **사람(아트디렉터) 승인 전에는 approved=False**라
    조립부가 사용하지 않는다(오늘 교훈: 머릿속 staging 금지 → 실측 + 사람 승인).
    """
    domain: str
    archetype: SceneArchetype
    mood: MoodToken
    prop_policy: PropPolicy
    reference_ids: tuple[str, ...]        # 근거 대표 2~3장 (manifest id)
    composition_note: str                 # 공통 구도 요약 (사람이 읽고 승인)
    approved_by: str = ""                 # 승인 아트디렉터
    approved: bool = False                # 사람 승인 게이트

    def __post_init__(self) -> None:
        if self.domain not in self.archetype.domains:
            raise ValueError(f"domain {self.domain!r}가 아키타입 {self.archetype.key} 호환 밖")
        if not (2 <= len(self.reference_ids) <= 3):
            raise ValueError("reference_ids는 대표 2~3장이어야 함(스타일 평균 금지)")
        if self.approved and not self.approved_by:
            raise ValueError("approved=True인데 approved_by 비어있음")

    def is_compatible(self, domain: str, opacity: str) -> bool:
        """상품 traits와 호환되는지 — 조립부가 후보에서 부적합 아키타입을 처음부터 제외한다."""
        return (domain in self.archetype.domains
                and opacity in self.archetype.allowed_opacity)

    def usable(self) -> bool:
        """조립부가 실제로 쓸 수 있는가 = 사람 승인 통과. 미승인은 탐색 상태로만 존재."""
        return self.approved
