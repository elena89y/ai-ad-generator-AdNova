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
import unicodedata

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
COMMERCIAL_PATTERNS = (
    "single_hero_headline", "multi_product_lineup", "product_launch",
    "campaign_teaser", "split_campaign_collage",
)
PRODUCT_COUNT_CLASSES = ("single", "dual", "triple", "lineup_4_plus")
CONDITIONING_SUBJECTS = ("latte", "transparent_tea")
TEXT_HIERARCHIES = (
    "headline_product_brand", "campaign_item_labels", "headline_date",
    "headline_cta", "panel_headlines",
)


def _require_subset(values: tuple[str, ...], allowed: tuple[str, ...], field: str) -> None:
    bad = [v for v in values if v not in allowed]
    if bad:
        raise ValueError(f"{field}에 허용되지 않은 값: {bad} (허용: {allowed})")


def canonical_reference_id(value: str) -> str:
    """macOS 파일명(NFD)과 코드 리터럴(NFC)을 같은 manifest ID로 비교한다."""
    return unicodedata.normalize("NFC", value.strip())


@dataclass(frozen=True)
class MoodToken:
    """스타일 = 분위기. 조명·재질·소품 밀도만 소유한다.

    ⚠️ palette는 소유하지 않는다 — 같은 무드도 domain/archetype별 복수 변형이 있어(P4BR pop:
    drink=코발트, object=틸/코랄) PaletteVariant 레지스트리로 분리하고 ReferenceRecipe가 고른다.
    ⚠️ 카메라 앵글·제품 배치·구체 소품명도 소유하지 않는다(SceneArchetype·PropPolicy 몫).
    """
    key: str                       # MOODS 중
    lighting: str                  # 서술 (비면 안 됨)
    materials: tuple[str, ...]     # wood, linen, stone... (비면 안 됨)
    prop_density: str              # PROP_DENSITIES 중

    def __post_init__(self) -> None:
        if self.key not in MOODS:
            raise ValueError(f"mood key 잘못됨: {self.key!r} (허용: {MOODS})")
        if self.prop_density not in PROP_DENSITIES:
            raise ValueError(f"prop_density 잘못됨: {self.prop_density!r}")
        if not self.lighting.strip() or not self.materials:
            raise ValueError("MoodToken lighting/materials는 비어있을 수 없음")


@dataclass(frozen=True)
class PaletteVariant:
    """무드별 palette 후보 하나. 같은 무드도 domain/archetype별로 여러 variant가 있다.

    ReferenceRecipe가 domain/archetype에 맞는 variant를 고르고, 최종 palette 승인은 recipe
    시각 몽타주에서 사람이 한다(여기서 approved=True 적재 금지 — 후보일 뿐).
    """
    key: str                           # 무드 내 안정 식별자 (예: cobalt_duo)
    mood: str                          # MOODS 중
    palette: tuple[str, ...]           # hex (비면 안 됨, 각 #RRGGBB)
    source: str                        # 출처 (예: "P4BR pop/drink", "style_specs editorial")
    domain_scope: tuple[str, ...] = () # 이 variant가 유래·적합한 domain (비면 = 무드 공통)
    archetype_hint: str = ""           # 유래 아키타입(선택 힌트)

    def __post_init__(self) -> None:
        if not self.key.strip() or "/" in self.key:
            raise ValueError(f"PaletteVariant.key 형식 오류: {self.key!r}")
        if self.mood not in MOODS:
            raise ValueError(f"palette variant mood 잘못됨: {self.mood!r}")
        if not self.palette:
            raise ValueError("PaletteVariant.palette 비어있음")
        for hx in self.palette:
            if not (isinstance(hx, str) and hx.startswith("#") and len(hx) == 7):
                raise ValueError(f"palette hex 형식 오류: {hx!r}")
        if self.domain_scope:
            _require_subset(self.domain_scope, DOMAINS, "domain_scope")
        if not self.source.strip():
            raise ValueError("PaletteVariant.source 비어있음(출처 필수)")

    @property
    def variant_id(self) -> str:
        """원장·selector에서 사용하는 안정 식별자."""
        return f"{self.mood}/{self.key}"


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
class CommercialLayout:
    """국내 광고의 상품 수·카피 위계 계약.

    SceneArchetype은 이미지 장면의 카메라·배치만 소유하고, 이 축은 최종 광고 조판에서
    단일 히어로/제품군 라인업/티저 같은 상업 레이아웃을 소유한다. 국내 카페 광고 20장
    실측(PU-DATA-004)에서 4종 이상 라인업 10/20, 상단 카피 17/20이 확인돼 분리했다.
    """
    key: str
    pattern: str
    product_count: str
    text_hierarchy: str
    text_zones: tuple[str, ...]
    reference_ids: tuple[str, ...]
    label_each_product: bool = False
    cta_zone: str = ""

    def __post_init__(self) -> None:
        if not self.key.strip() or "/" in self.key:
            raise ValueError(f"CommercialLayout.key 형식 오류: {self.key!r}")
        if self.pattern not in COMMERCIAL_PATTERNS:
            raise ValueError(f"commercial pattern 잘못됨: {self.pattern!r}")
        if self.product_count not in PRODUCT_COUNT_CLASSES:
            raise ValueError(f"product_count 잘못됨: {self.product_count!r}")
        if self.text_hierarchy not in TEXT_HIERARCHIES:
            raise ValueError(f"text_hierarchy 잘못됨: {self.text_hierarchy!r}")
        _require_subset(self.text_zones, TEXT_ZONES, "commercial text_zones")
        if not self.text_zones:
            raise ValueError("CommercialLayout.text_zones 비어있음")
        if not (2 <= len(self.reference_ids) <= 3):
            raise ValueError("CommercialLayout.reference_ids는 대표 2~3장이어야 함")
        if len(set(self.reference_ids)) != len(self.reference_ids):
            raise ValueError(f"CommercialLayout.reference_ids 중복: {self.reference_ids}")
        if self.cta_zone and self.cta_zone not in TEXT_ZONES:
            raise ValueError(f"cta_zone 잘못됨: {self.cta_zone!r}")
        is_lineup = self.product_count in ("dual", "triple", "lineup_4_plus")
        if self.label_each_product and not is_lineup:
            raise ValueError("단일 상품 layout은 label_each_product=True일 수 없음")
        if self.pattern == "multi_product_lineup" and not is_lineup:
            raise ValueError("multi_product_lineup은 2개 이상 product_count가 필요")


@dataclass(frozen=True)
class ConditioningReferenceSet:
    """모델 입력용 동일 상품군 레퍼런스 계약.

    ``ReferenceRecipe.reference_ids``는 장면·구도 근거이고, 이 레지스트리는 모델에 실제로
    넣어도 되는 정체성/질감 근거만 소유한다. 구도만 좋은 사진을 조건 이미지로 오인하지 않도록
    두 근거를 의도적으로 분리한다.
    """
    key: str
    subject: str
    domain: str
    opacity: str
    identity_reference_ids: tuple[str, ...]
    composition_reference_ids: tuple[str, ...] = ()
    approved_by: str = ""
    approved: bool = False

    def __post_init__(self) -> None:
        if not self.key.strip() or "/" in self.key:
            raise ValueError(f"ConditioningReferenceSet.key 형식 오류: {self.key!r}")
        if self.subject not in CONDITIONING_SUBJECTS:
            raise ValueError(f"conditioning subject 잘못됨: {self.subject!r}")
        if self.domain not in DOMAINS:
            raise ValueError(f"conditioning domain 잘못됨: {self.domain!r}")
        if self.opacity not in OPACITIES:
            raise ValueError(f"conditioning opacity 잘못됨: {self.opacity!r}")
        if not (1 <= len(self.identity_reference_ids) <= 2):
            raise ValueError("identity_reference_ids는 직접 조건용 1~2장이어야 함")
        if len(set(self.identity_reference_ids)) != len(self.identity_reference_ids):
            raise ValueError("identity_reference_ids 중복")
        if len(self.composition_reference_ids) > 3:
            raise ValueError("composition_reference_ids는 최대 3장")
        if len(set(self.composition_reference_ids)) != len(self.composition_reference_ids):
            raise ValueError("composition_reference_ids 중복")
        overlap = set(self.identity_reference_ids) & set(self.composition_reference_ids)
        if overlap:
            raise ValueError(f"identity/composition 근거 역할 중복: {sorted(overlap)}")
        if bool(self.approved) != bool(self.approved_by):
            raise ValueError("approved와 approved_by는 함께 설정되어야 함(대칭)")

    def usable(self) -> bool:
        return self.approved


@dataclass(frozen=True)
class ReferenceRecipe:
    """특정 (domain, archetype, mood) 조합의 조립 계약.

    대표 레퍼런스 2~3장의 공통 특징에서 추출하고, **사람(아트디렉터) 승인 전에는 approved=False**라
    조립부가 사용하지 않는다(오늘 교훈: 머릿속 staging 금지 → 실측 + 사람 승인).
    """
    domain: str                          # target domain (이 recipe가 적용될 상품 도메인)
    archetype: SceneArchetype
    mood: MoodToken
    palette_variant: PaletteVariant      # recipe가 고른 palette 후보 (최종 승인은 시각 몽타주)
    prop_policy: PropPolicy
    reference_ids: tuple[str, ...]        # 근거 대표 2~3장 (manifest id, 중복 불가)
    composition_note: str                 # 공통 구도 요약 (사람이 읽고 승인, 비면 안 됨)
    commercial_layout: CommercialLayout | None = None  # 광고 조판 선택. 이미지 생성 전용이면 None
    approved_by: str = ""                 # 승인 아트디렉터
    approved: bool = False                # 사람 승인 게이트
    # cross-domain 부트스트랩(결정 B, B-1 제한적 허용): drink 코퍼스가 빈약(4장)해
    #   food/object 근거로 연출을 빌릴 때만 사용. 전면 domain-agnostic 금지 — 반드시 아래 메타
    #   기록 + approved=False로 생성하고, 라떼·투명홍차 시각 게이트 통과분만 사람이 승인한다.
    source_domains: tuple[str, ...] = ()  # 근거 출처 도메인들(target과 달라야). 비면 = 동일도메인 recipe
    transfer_reason: str = ""             # 전이 사유 (예: "카메라·구도는 도메인 불변")
    evidence_scope: str = ""              # 근거 범위 (예: "camera+composition only, NOT palette/props")

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
        if self.palette_variant.mood != self.mood.key:
            raise ValueError(
                f"palette_variant mood({self.palette_variant.mood})가 recipe mood({self.mood.key})와 불일치")
        if (self.palette_variant.domain_scope
                and self.domain not in self.palette_variant.domain_scope):
            raise ValueError(
                f"palette_variant {self.palette_variant.variant_id}가 domain {self.domain!r} 범위 밖")
        if bool(self.approved) != bool(self.approved_by):
            raise ValueError("approved와 approved_by는 함께 설정되어야 함(대칭)")
        if self.source_domains:
            _require_subset(self.source_domains, DOMAINS, "source_domains")
            cross_domain = any(source != self.domain for source in self.source_domains)
            if cross_domain and (not self.transfer_reason.strip() or not self.evidence_scope.strip()):
                raise ValueError("cross-domain recipe는 transfer_reason·evidence_scope 필수")
            if not cross_domain and (self.transfer_reason.strip() or self.evidence_scope.strip()):
                raise ValueError("동일 domain recipe에 cross-domain 전이 메타가 설정됨")

    @property
    def recipe_id(self) -> str:
        """selector·원장용 안정적 식별자. 동일 조합이면 동일 id."""
        return f"{self.domain}/{self.archetype.key}/{self.mood.key}"

    @property
    def is_cross_domain(self) -> bool:
        """근거를 다른 도메인에서 빌린 부트스트랩 recipe인가(결정 B). 시각 게이트 통과 전엔 미승인 상태여야."""
        return any(source != self.domain for source in self.source_domains)

    @property
    def canonical_reference_ids(self) -> tuple[str, ...]:
        """manifest/file-system 대조용 NFC ID."""
        return tuple(canonical_reference_id(value) for value in self.reference_ids)

    def is_compatible(self, domain: str, opacity: str) -> bool:
        """상품 traits와 호환되는지 — 조립부가 후보에서 부적합 아키타입을 처음부터 제외한다."""
        return (domain in self.archetype.domains
                and opacity in self.archetype.allowed_opacity)

    def usable(self) -> bool:
        """조립부가 실제로 쓸 수 있는가 = 사람 승인 통과. 미승인은 탐색 상태로만 존재."""
        return self.approved
