"""ReferenceRecipe — 레퍼런스 조립 계약 (코덱스 재설계 순서 2, 2026-07-19).

배경: `_RECOMPOSE_STAGING[style]` 단일 규칙은 "style이 카메라앵글·소품을 소유"하는 구조라
  '웜이면 무조건 원두', '파스텔이면 무조건 로우앵글' 같은 오류를 낳았다(상품 불일치·정직성 위반).
해법: 4축을 분리해 조립한다 —
  · **MoodToken(style)**   = 분위기. 색·조명·재질·소품'밀도'만 소유. 카메라앵글·배치 소유 금지.
  · **SceneArchetype**     = 연출. 카메라앵글·스케일·배치·카피영역·호환 domain/opacity 소유.
  · **PropPolicy**         = 안전경계. 구체 소품명이 아니라 카테고리·밀도. 먹는 소품은 근거 있을 때만.
  · **ReferenceRecipe**    = 특정 (domain, archetype, mood) 조합의 조립 결과 + 대표 레퍼런스 2~3장 근거
                             + 사람(아트디렉터) 승인 게이트.

vocabulary는 전부 enum(허용 집합)으로 고정한다 — 자유 문자열이면 순서 3 데이터 적재가 사실상
  새 프롬프트 저장소가 되고, 'coffee beans'·'transparant' 같은 구체명사·오타가 침묵 통과한다(코덱스 P1).

이 파일은 **스키마만** 정의한다. 실제 인스턴스 적재는 순서 3(manifest 대표 2~3장 선정) 이후.
"""
from __future__ import annotations

from dataclasses import dataclass

# ── 고정 vocabulary (자유 문자열 금지 — 침묵 오타·구체명사 차단) ──────────────────
MOODS = ("editorial", "pop", "realism", "pastel", "monotone", "warm_organic")
DOMAINS = ("drink", "food", "object")
OPACITIES = ("opaque", "transparent", "translucent")
CAMERA_ANGLES = ("eye", "slightly_high", "high", "low", "three_quarter", "top_down")
PLACEMENTS = ("center", "left_third", "right_third", "upper_third", "lower_third")
TEXT_ZONES = ("top", "top_left", "top_right", "left", "right", "bottom", "bottom_left",
              "bottom_right")
PROP_CATEGORIES = ("tableware", "textile", "botanical", "surface", "stationery")
PROP_DENSITIES = ("none", "low", "medium", "high")
EDIBLE_MODES = ("none", "source_only")  # source_only = core_ingredients + 원본 Vision 근거 있을 때만


def _require_subset(values: tuple[str, ...], allowed: tuple[str, ...], field: str) -> None:
    bad = [v for v in values if v not in allowed]
    if bad:
        raise ValueError(f"{field}에 허용되지 않은 값: {bad} (허용: {allowed})")


@dataclass(frozen=True)
class MoodToken:
    """스타일 = 분위기. 색·조명·재질·소품 밀도만 소유한다.

    ⚠️ 카메라 앵글·제품 배치·구체 소품명을 소유하지 않는다(그건 SceneArchetype·PropPolicy 몫).
    이 경계가 '웜이면 무조건 top-down' 같은 오류를 막는다.
    """
    key: str                       # MOODS 중
    palette: tuple[str, ...]       # hex 색들 (비면 안 됨)
    lighting: str                  # 서술 (비면 안 됨)
    materials: tuple[str, ...]     # wood, linen, stone... (비면 안 됨)
    prop_density: str              # PROP_DENSITIES 중

    def __post_init__(self) -> None:
        if self.key not in MOODS:
            raise ValueError(f"mood key 잘못됨: {self.key!r} (허용: {MOODS})")
        if self.prop_density not in PROP_DENSITIES:
            raise ValueError(f"prop_density 잘못됨: {self.prop_density!r}")
        if not self.palette or not self.lighting.strip() or not self.materials:
            raise ValueError("MoodToken palette/lighting/materials는 비어있을 수 없음")


@dataclass(frozen=True)
class SceneArchetype:
    """연출 = 구도. 카메라 앵글·스케일·배치·카피영역, 그리고 호환 domain/opacity를 소유한다.

    상품과 맞지 않는 아키타입은 is_compatible로 처음부터 제외한다(투명 아이스 음료에 pedestal 등).
    """
    key: str                              # tabletop_lifestyle, soft_pedestal, minimal_studio...
    domains: frozenset[str]               # DOMAINS 부분집합
    allowed_opacity: frozenset[str]       # OPACITIES 부분집합
    camera_angles: tuple[str, ...]        # CAMERA_ANGLES 부분집합
    subject_scale: tuple[float, float]    # (min, max) 제품 폭/캔버스 폭
    placements: tuple[str, ...]           # PLACEMENTS 부분집합
    text_zones: tuple[str, ...]           # TEXT_ZONES 부분집합

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("SceneArchetype.key 비어있음")
        lo, hi = self.subject_scale
        if not (0.0 < lo <= hi <= 1.0):
            raise ValueError(f"subject_scale 범위 오류: {self.subject_scale}")
        if not self.domains or not self.allowed_opacity:
            raise ValueError("domains/allowed_opacity 비어있음")
        _require_subset(tuple(self.domains), DOMAINS, "domains")
        _require_subset(tuple(self.allowed_opacity), OPACITIES, "allowed_opacity")
        _require_subset(self.camera_angles, CAMERA_ANGLES, "camera_angles")
        _require_subset(self.placements, PLACEMENTS, "placements")
        _require_subset(self.text_zones, TEXT_ZONES, "text_zones")
        if not self.camera_angles or not self.placements or not self.text_zones:
            raise ValueError("camera_angles/placements/text_zones는 비어있을 수 없음")


@dataclass(frozen=True)
class PropPolicy:
    """소품 안전경계. 구체 명사가 아니라 category(고정 enum)·밀도로 표현한다.

    'coffee beans'·'salt shaker' 같은 구체명사는 category enum이 아니므로 스키마에서 거부된다(P1).
    먹는 소품은 edible='source_only'일 때만, 그것도 core_ingredients + 원본 Vision 근거가 있을 때만
    조립부가 허용한다. 로고 SKU는 avoid_overlap으로 제품을 가리는/반사하는 소품을 금지한다.
    """
    categories: tuple[str, ...]           # PROP_CATEGORIES 부분집합
    edible: str = "none"                  # EDIBLE_MODES 중
    max_count: int = 2
    avoid_overlap_with_product: bool = True

    def __post_init__(self) -> None:
        if self.edible not in EDIBLE_MODES:
            raise ValueError(f"edible 잘못됨: {self.edible!r}")
        if self.max_count < 0:
            raise ValueError("max_count 음수")
        _require_subset(self.categories, PROP_CATEGORIES, "categories")
        if self.max_count > 0 and not self.categories:
            raise ValueError("max_count>0인데 허용 category가 비어있음(모순)")


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
    reference_ids: tuple[str, ...]        # 근거 대표 2~3장 (manifest id, 중복 불가)
    composition_note: str                 # 공통 구도 요약 (사람이 읽고 승인, 비면 안 됨)
    approved_by: str = ""                 # 승인 아트디렉터
    approved: bool = False                # 사람 승인 게이트

    def __post_init__(self) -> None:
        if self.domain not in DOMAINS:
            raise ValueError(f"domain 잘못됨: {self.domain!r}")
        if self.domain not in self.archetype.domains:
            raise ValueError(f"domain {self.domain!r}가 아키타입 {self.archetype.key} 호환 밖")
        if not (2 <= len(self.reference_ids) <= 3):
            raise ValueError("reference_ids는 대표 2~3장이어야 함(스타일 평균 금지)")
        if len(set(self.reference_ids)) != len(self.reference_ids):
            raise ValueError(f"reference_ids 중복: {self.reference_ids}")
        if not self.composition_note.strip():
            raise ValueError("composition_note 비어있음")
        if bool(self.approved) != bool(self.approved_by):
            raise ValueError("approved와 approved_by는 함께 설정되어야 함(대칭)")

    @property
    def recipe_id(self) -> str:
        """selector·원장용 안정적 식별자. 동일 조합이면 동일 id."""
        return f"{self.domain}/{self.archetype.key}/{self.mood.key}"

    def is_compatible(self, domain: str, opacity: str) -> bool:
        """상품 traits와 호환되는지 — 조립부가 후보에서 부적합 아키타입을 처음부터 제외한다."""
        return (domain in self.archetype.domains
                and opacity in self.archetype.allowed_opacity)

    def usable(self) -> bool:
        """조립부가 실제로 쓸 수 있는가 = 사람 승인 통과. 미승인은 탐색 상태로만 존재."""
        return self.approved
