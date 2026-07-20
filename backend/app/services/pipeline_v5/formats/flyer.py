"""v5 전단지 포맷 — A4 세로 + 정보블록(메뉴·가격·매장). 담당: 한의정. (F4, **범위 제외**)

⚠️ 2026-07-21 결정: 전단지는 v6 범위 제외 — 온라인 포맷(sns·banner·cardnews·detail_page) 위주.
  이유: 인쇄물 + '구조화된 사업자 데이터'(메뉴 리스트/가격/주소) 입력 스키마·프론트 폼 의존이라
  비용 대비 후순위 (DIRECTION_v6 §개요 범위 제외). 템플릿 원장(templates.yaml)에서도 제거됨.
모듈·AdPurpose.FLYER enum은 API 계약 불변 원칙으로 유지 — 호출되면 아래 가드가 막는다.
(재개 시 참고) SNS와 근본 차이: 정보 밀도 — 상단 히어로존(contain) + 하단 메뉴·가격·매장 블록.
"""
from __future__ import annotations

from ..format_spec import FormatSpec
from ..hero import HeroAsset


def render(hero: HeroAsset, spec: FormatSpec, output_dir: str) -> list[str]:
    raise NotImplementedError(
        "전단지(flyer)는 v6 범위 제외(2026-07-21, 온라인 포맷 위주). "
        "재개 시 사업자 데이터 입력 스키마(메뉴·가격·매장) 확정이 선행 조건."
    )
