"""Best-of-N 하이브리드 선택 (D3 확정 2026-07-09, 사람-in-loop) — 담당: 한의정.

완전 자동 저지선택은 캘리브레이션(P2-2)상 신뢰 불가(2B 위치편향·점수압축) →
자동은 **스크리닝 + 정렬**에만 쓰고 미세 미학 최종판정은 사람:
  (a) vlm_service.inspect 로 결함본(clean=False) 자동 탈락
  (b) 생존자 metrics.aesthetic(LAION) 내림차순 정렬
  (c) 상위 후보를 사람이 최종 택1 (top 은 권장값일 뿐, 사람이 바꿀 수 있음)
전원 결함 탈락 시 aesthetic 최상위 1개를 폴백으로 노출(빈손 방지).

VRAM: inspect(VLM 4G)와 aesthetic(CLIP)은 순차 로드. 생성엔진(Kontext 13G)은
  select_best 진입 전 unload 권장(호출측 책임). 기본 unload_vlm_after=True.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Candidate:
    path: str
    clean: bool                 # inspect 결함 없음
    note: str                   # inspect 서술('looks clean' 또는 결함 문장)
    aesthetic: Optional[float]  # 심미(NIMA 우선/LAION 폴백, 높을수록 좋음), 실패 시 None


@dataclass
class Selection:
    ranked: list[Candidate]     # 사람에게 보여줄 순서(권장 상위부터)
    dropped: list[Candidate]    # 결함으로 탈락한 후보
    top: Optional[Candidate]    # 권장 1순위(사람이 최종 변경 가능)
    fallback_used: bool         # 전원 결함 → 폴백 노출 여부


def _aes_key(c: Candidate):  # None 은 최하위
    return c.aesthetic if c.aesthetic is not None else float("-inf")


def select_best(image_paths: list[str], unload_vlm_after: bool = True) -> Selection:
    """N개 후보 → 결함 스크리닝 + 심미 정렬. 사람 최종택1용 Selection 반환."""
    from app.harness import metrics
    from app.services import vlm_service

    cands: list[Candidate] = []
    for p in image_paths:
        insp = vlm_service.inspect(p)
        aes = metrics.aesthetic_primary(p)   # NIMA 우선, LAION 폴백
        cands.append(Candidate(str(p), bool(insp["clean"]), insp["note"], aes))
    if unload_vlm_after:
        vlm_service.unload()

    clean = [c for c in cands if c.clean]
    if clean:
        ranked = sorted(clean, key=_aes_key, reverse=True)
        dropped = [c for c in cands if not c.clean]
        fallback = False
    else:
        # 전원 결함 → 빈손 방지: aesthetic 최상위 1개만 폴백 노출
        ranked = sorted(cands, key=_aes_key, reverse=True)[:1]
        dropped = [c for c in cands if c not in ranked]
        fallback = True

    return Selection(ranked, dropped, ranked[0] if ranked else None, fallback)
