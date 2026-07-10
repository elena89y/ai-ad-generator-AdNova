"""스타일 씬 생성 경로 (DESIGN_SYSTEM 생성비중 스타일) — 담당: 한의정.

style_specs.scene_prompt 를 Kontext 명령으로 적용해 스타일 씬을 생성한다.
  - 생성비중 스타일(pop 제품합성 · editorial 무드보드 · warm_vintage 소품씬)의 배경/연출 생성.
  - 하이브리드 스타일은 kontext_service 의 A/B 템플릿(정체성 보존 편집)이 이미 담당.
  - 타이포는 이 단계 이후 overlay_service(PIL)로 별도 조판(역할분리).

⚠️ 정직성: 제품 형태·색은 보존절로 지킴. Kontext 로 안 되는 대규모 크리에이티브 합성
  (예: 화장품×크렘브륄레)은 풀생성 프롬프트(외부/추후) 몫 — scene_prompt 는 그 규약도 겸함.
"""
from __future__ import annotations

from typing import Optional


def generate_scene(image_path: str, style_key: str, subject_en: str,
                   output_dir: str = "backend/results/ai/style",
                   seed: int = 42, steps: Optional[int] = None) -> str:
    """스타일 씬 생성. style_specs.scene_prompt({subject}) + 보존절 → Kontext 편집. 경로 반환."""
    from . import kontext_service
    from .style_specs import get_spec

    sp = get_spec(style_key)
    instr = (sp.scene_prompt.format(subject=subject_en or "product")
             + " Keep the product's shape, proportions and true colors faithful; do not distort "
               "or recolor the product. No text.")
    kw = {} if steps is None else {"steps": steps}
    return kontext_service.edit(image_path, instr, seed=seed, output_dir=output_dir, **kw)
