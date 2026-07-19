"""v5 멀티포맷 — 포맷(용도)별 캔버스 기하의 단일 진실 원천. 담당: 한의정.

설계 불변식(v5 핵심):
  히어로 생성(v4 process_ad)은 포맷을 모른다. 여기 정의한 FormatSpec 만이
  "규격 없는 히어로"를 각 채널 산출물로 굽는 기하를 소유한다.
  한 히어로로 4포맷 전부 뽑을 수 있어야 한다(재생성 비용·일관성).

신규 의존성 금지 — PIL+NumPy 만. HTTP/프론트 미노출(내부 병행 단계).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ...schemas.ads import AdPurpose

HeroFit = Literal["cover", "contain", "reflow"]
CopyDensity = Literal["minimal", "medium", "dense"]


@dataclass(frozen=True)
class FormatSpec:
    """한 산출물 면(面)의 기하 규격. slides>1 이면 시퀀스의 한 슬라이드 템플릿.

    디지털 전용(2026-07-17 인쇄 트랙 폐기 — 커머셜 집중). px 가 곧 최종.
    """
    purpose: AdPurpose
    canvas: tuple[int, int]        # (W, H) px — 최종 출력 규격
    hero_fit: HeroFit              # 히어로를 캔버스에 앉히는 방식
    copy_density: CopyDensity      # 카피 분량 정책(GPT 카피 구조·타이포 밀도)
    safe_margin: float = 0.06      # 세이프존 비율(경계 잘림 방지)
    label: str = ""                # 규격 별칭(예: "commerce_wide")
    note: str = ""                 # 채널/용도 메모(유저 노출용 라벨 후보)

    @property
    def aspect(self) -> float:
        w, h = self.canvas
        return w / h


# --- 포맷별 규격 레지스트리 -------------------------------------------------
# 한 purpose 가 복수 규격을 가질 수 있다. 리스트 = 자동 생성 팩(순서 = 대표 우선순위).
_SPECS: dict[AdPurpose, list[FormatSpec]] = {
    AdPurpose.SNS: [
        FormatSpec(AdPurpose.SNS, (1080, 1080), "cover", "medium", 0.06, "square"),
    ],
    # 배너 = 커머스/스마트스토어 디지털 전용. 자동 팩(히어로 1장 → 전 규격 동시 생성).
    AdPurpose.BANNER: [
        FormatSpec(AdPurpose.BANNER, (1080, 1080), "cover", "minimal", 0.05,
                   "commerce_square", note="스마트스토어 썸네일·피드 카드 (1:1)"),
        FormatSpec(AdPurpose.BANNER, (1920, 600), "cover", "minimal", 0.05,
                   "commerce_wide", note="웹/이벤트 상단 와이드 배너 (3.2:1)"),
        FormatSpec(AdPurpose.BANNER, (860, 860), "cover", "minimal", 0.05,
                   "smartstore_detail", note="스마트스토어 상세 상단(폭860 관례)"),
        FormatSpec(AdPurpose.BANNER, (1080, 1350), "cover", "minimal", 0.06,
                   "commerce_vertical", note="모바일 커머스 세로 프로모 (4:5)"),
    ],
    AdPurpose.CARD_NEWS: [
        # 4:5 세로. slides 는 compose 단계에서 카피 블록 수로 결정(표지+본문N+CTA).
        FormatSpec(AdPurpose.CARD_NEWS, (1080, 1350), "cover", "medium", 0.07, "cover"),
    ],
    AdPurpose.FLYER: [
        # A4 300dpi 세로. 히어로는 상단 히어로존만, 하단은 정보블록(메뉴·가격·매장).
        FormatSpec(AdPurpose.FLYER, (2480, 3508), "contain", "dense", 0.08, "A4"),
    ],
    # 상세페이지 = 커머스 핵심. 스마트스토어 폭 860 세로 롱스크롤(섹션 조판).
    # canvas H 는 섹션 수로 가변 → 여기 값은 최소 높이 힌트, 실제는 detail_page 가 결정.
    AdPurpose.DETAIL_PAGE: [
        FormatSpec(AdPurpose.DETAIL_PAGE, (860, 2600), "reflow", "dense", 0.06,
                   "smartstore", note="스마트스토어 상세 롱스크롤(폭860·섹션 가변)"),
    ],
}


def specs_for(purpose: AdPurpose) -> list[FormatSpec]:
    """용도에 해당하는 규격 목록. 미정의 시 SNS 로 폴백(무해)."""
    return _SPECS.get(purpose, _SPECS[AdPurpose.SNS])


def primary_spec(purpose: AdPurpose) -> FormatSpec:
    """용도의 대표 규격 1건."""
    return specs_for(purpose)[0]
