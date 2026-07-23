"""포맷 공용 스타일 팔레트 — 담당: 한의정. (DIRECTION_v6-1 F2/F3)

스타일 원장(styles/specs.yaml)의 accent 를 조판용 3색으로 파생한다:
  accent = 원색(라벨·버튼·포인트 룰)
  deep   = 진한 변형(어두운 패널 배경)
  tint   = 밝은 변형(어두운 배경 위 보조 텍스트)

배경: detail_page.py 가 이미 동일 로직을 자체 _palette 로 갖고 있으나(F1), 그건
detail_page 모듈 프라이빗이라 cardnews/banner 가 남색을 하드코딩(43,63,187 등)한 채였다.
이 공용판을 신설해 cardnews/banner 가 스타일 팔레트를 공유하게 한다(D4 해소).
detail_page._palette 는 별도 트랙(다른 세션) 소유라 지금 건드리지 않는다 — 추후 그 트랙에서
이 공용판으로 통일하고 자체 _palette 를 제거하면 중복이 사라진다.
"""
from __future__ import annotations

from ..style_specs import get_spec

RGB = tuple


def palette(style_key: str | None) -> dict:
    """스타일 키 → {accent, deep, tint} RGB 3색. 미지 키는 get_spec 이 editorial 폴백."""
    accent = tuple(get_spec(style_key or "editorial").accent)
    deep = tuple(int(c * 0.78) for c in accent)
    tint = tuple(int(c + (255 - c) * 0.78) for c in accent)
    return {"accent": accent, "deep": deep, "tint": tint}
