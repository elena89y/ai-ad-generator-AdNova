"""포맷 조판용 구조화 카피. 제공되지 않은 판매 사실은 만들지 않는다."""
from __future__ import annotations

from dataclasses import dataclass

from .hero import HeroAsset


@dataclass(frozen=True)
class CommercialCopy:
    product_name: str
    headline: str
    subcopy: str = ""
    brand_name: str = ""
    campaign_label: str = ""
    cta: str = "자세히 보기"


def copy_for(hero: HeroAsset) -> CommercialCopy:
    """HeroAsset의 검증된 문자열만 구조화한다."""
    product_name = _clean(hero.product_name)
    headline = _clean(hero.headline) or product_name or "상품 이야기"
    return CommercialCopy(
        product_name=product_name,
        headline=headline,
        subcopy=_clean(hero.subcopy),
    )


def _clean(value: str) -> str:
    return " ".join((value or "").split())
