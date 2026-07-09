"""Best-of-N 생성 루프 (D3 확정: 하이브리드 사람-in-loop) — 담당: 한의정 (v2).

N개 시드로 Kontext 생성 → harness.select_best(inspect 결함탈락 + NIMA 정렬) → 상위 후보를
사람이 최종 택1. top 이 nima_floor 미달이면 명령을 강화(refine)해 1회 재생성 후 합쳐 재선정.

⚠️ 완전 자동 저지선택은 2B 신뢰불가로 폐기(P2-2 캘리브레이션) — 여기서 top 은 '권장'일 뿐,
   미세 미학 최종판정은 사람. 자동은 결함 스크리닝 + NIMA 정렬까지만.

VRAM: 생성(Kontext 13G) 후 판정(VLM 4G + NIMA/CLIP) 전에 kontext 언로드 → 순차 안전.
  refine 시 kontext 재로드(비용 감수). N 생성은 Kontext 싱글턴 재사용(로드 1회).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_REFINE_SUFFIX = (" Make it more polished, vibrant and premium, with clean professional "
                  "advertising lighting.")


def best_of_n(
    image_path: str,
    instruction: str,
    n: int = 3,
    seeds: Optional[list[int]] = None,
    output_dir: str = "backend/results/ai/bestofn",
    refine: bool = True,
    nima_floor: float = 5.0,
):
    """N 시드 Kontext 생성 → 하이브리드 선정. harness.selection.Selection 반환(top=권장, 사람 택1).

    refine=True 이고 최상위 NIMA < nima_floor 이면 명령 강화 후 N 재생성, 합쳐 재선정.
    """
    from ..harness.selection import select_best
    from . import kontext_service

    seeds = seeds or list(range(n))
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(image_path).stem

    def _gen(instr: str, tag: str, seed_list: list[int]) -> list[str]:
        paths = []
        for s in seed_list:
            out = kontext_service.edit(image_path, instr, seed=s, output_dir=output_dir)
            dst = str(out_dir / f"{stem}_{tag}{s}.png")
            if os.path.abspath(out) != os.path.abspath(dst):
                os.replace(out, dst)   # edit 은 동일 파일명 저장 → 시드별 고유명으로(덮어쓰기 방지)
            paths.append(dst)
        return paths

    paths = _gen(instruction, "s", seeds)
    kontext_service.unload()                 # 판정(VLM+NIMA) 전 VRAM 확보
    sel = select_best(paths, unload_vlm_after=True)

    top_nima = (sel.top.aesthetic or 0.0) if sel.top else 0.0
    if refine and sel.top is not None and top_nima < nima_floor:
        logger.info("best_of_n refine 발동: top NIMA %.2f < %.1f", top_nima, nima_floor)
        extra = _gen(instruction + _REFINE_SUFFIX, "r", seeds)
        kontext_service.unload()
        sel = select_best(paths + extra, unload_vlm_after=True)
    return sel
