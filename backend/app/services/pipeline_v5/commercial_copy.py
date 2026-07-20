"""포맷 조판용 구조화 카피. 제공되지 않은 판매 사실은 만들지 않는다."""
from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass
from functools import lru_cache

from .hero import HeroAsset

logger = logging.getLogger(__name__)

# 도메인별 폴백 섹션 라벨(ROUTING-001) — GPT 호출 실패 시에만 쓰는 안전망.
_TOP_VIEW_FALLBACK = {
    "food": "위에서 보는 플레이팅",
    "drink": "위에서 만나는 한 잔",
    "object": "위에서 보는 디테일",
}
_DETAIL_TITLE_FALLBACK = {
    "food": "맛까지\n또렷하게",
    "drink": "한 잔의\n디테일",
    "object": "디테일까지\n또렷하게",
}


@dataclass(frozen=True)
class CommercialCopy:
    product_name: str
    headline: str
    subcopy: str = ""
    brand_name: str = ""
    campaign_label: str = ""
    cta: str = "자세히 보기"
    top_view_label: str = ""
    detail_title: str = ""


def copy_for(hero: HeroAsset) -> CommercialCopy:
    """HeroAsset의 검증된 문자열만 구조화한다. GPT 호출 없음(배너 등 모든 포맷이 씀)."""
    product_name = _clean(hero.product_name)
    headline = _clean(hero.headline) or product_name or "상품 이야기"
    return CommercialCopy(
        product_name=product_name,
        headline=headline,
        subcopy=_clean(hero.subcopy),
    )


def section_copy_for(hero: HeroAsset) -> CommercialCopy:
    """copy_for + 카드뉴스/상세페이지 전용 섹션 라벨(ROUTING-002).

    상품마다 다른 짧은 라벨을 GPT로 생성 — 도메인 고정 문구가 모든 상품에 똑같이 나가던
    문제 해결. 같은 (상품명, 영문키워드, 도메인, 헤드라인) 조합은 프로세스 내에서 캐싱되어
    한 번의 렌더(카드뉴스 4슬라이드 등)에서 여러 번 호출돼도 GPT는 한 번만 부른다.
    실패하면 도메인별 고정 문구로 폴백 — 화면에 빈 문구가 나가는 것보다 낫다.
    """
    base = copy_for(hero)
    top_view_label, detail_title = _section_labels(base.product_name, hero.subject_en, hero.domain, base.headline)
    return dataclasses.replace(base, top_view_label=top_view_label, detail_title=detail_title)


@lru_cache(maxsize=256)
def _section_labels(product_name: str, subject_en: str, domain: str, headline: str) -> tuple[str, str]:
    try:
        from .. import gpt_service
        labels = gpt_service.generate_section_labels(
            product_name=product_name, subject_en=subject_en, domain=domain, headline=headline,
        )
        return labels.top_view_label, labels.detail_title
    except Exception as e:  # noqa: BLE001
        logger.info(f"섹션 라벨 GPT 생성 실패 → 도메인 고정 문구 폴백: {e}")
        key = domain if domain in _TOP_VIEW_FALLBACK else "food"
        return _TOP_VIEW_FALLBACK[key], _DETAIL_TITLE_FALLBACK[key]


def _clean(value: str) -> str:
    return " ".join((value or "").split())
