"""v5 전단지 포맷 — A4 세로 + 정보블록(메뉴·가격·매장). 담당: 한의정. (F4, 미구현)

SNS와 근본 차이: 정보 밀도가 높고 '구조화된 사업자 데이터'가 입력에 추가된다.
  - 히어로는 상단 히어로존(contain)만, 하단은 메뉴명·가격표·매장정보 블록.
  - 사진+상품명 만으로 안 됨 → 입력 스키마 확장(메뉴 리스트/가격/주소) 필요.
    이 입력 폼은 프론트(봄님 도메인) 동반 작업 → 노출 시점 조율 필수.
착수 전제: 사업자 데이터 입력 스키마 확정. 그 전까지 NotImplementedError.
"""
from __future__ import annotations

from ..format_spec import FormatSpec
from ..hero import HeroAsset


def render(hero: HeroAsset, spec: FormatSpec, output_dir: str) -> list[str]:
    raise NotImplementedError(
        "전단지(F4)는 사업자 데이터 입력 스키마(메뉴·가격·매장) 확정 후 착수. "
        "히어로존 contain 배치까지는 compose 로 가능."
    )
