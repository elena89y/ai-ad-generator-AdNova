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
    scene = sp.scene_prompt.format(subject=subject_en or "product")

    # 구성(composition) 유지 절 — 무드 씬 전용 (2026-07-11 콜드런 실측: editorial 이 브런치
    #   4조각+치즈소스+음료를 1개 단품으로 재구성 → 메뉴 시그니처 소실 = 정직성 경계 위반).
    #   재구성이 목적인 포맷(cross_section 단면·object_* 사물·pop_split 매크로)은 제외.
    #   ⚠️ 절 순서가 결정적: 구성 유지를 '맨 앞'에 둬야 씬의 스타일 언어(싱글히어로·여백)에 안 밀림.
    _RECOMPOSE_OK = {"cross_section", "object_studio", "object_splash", "pop_split"}
    if style_key not in _RECOMPOSE_OK:
        instr = ("Edit this exact photo. Keep every food item exactly as photographed: the same "
                 "number of pieces, the same sauces and garnishes, the same plating and arrangement "
                 "— do not remove, add, merge or simplify anything on the plate. "
                 f"Restyle ONLY the background, surface, lighting and mood as follows: {scene} "
                 "Keep the food's true colors. No text.")
    else:
        instr = (scene + " Keep the product's shape, proportions and true colors faithful; "
                 "do not distort or recolor the product. No text.")

    # cross_section 정직성 게이트: 그 케이크의 '실재하는' 레이어만 GPT 레시피 검증으로 주입
    #   (통 케이크 단면 생성 시 허위 레이어 방지 — 09_기타/케익클로즈업 워크플로).
    if style_key == "cross_section":
        from . import gpt_service
        rec = gpt_service.build_cake_layers("", subject_en=subject_en)
        if rec.get("layers"):
            layers = " ".join(rec["layers"])
            top = f" Top decoration: {rec['top']}." if rec.get("top") else ""
            instr += (f" Cross section layers arranged from bottom to top: {layers}.{top} "
                      "Render exactly these layers, do not invent other ingredients.")

    kw = {} if steps is None else {"steps": steps}
    return kontext_service.edit(image_path, instr, seed=seed, output_dir=output_dir, **kw)
