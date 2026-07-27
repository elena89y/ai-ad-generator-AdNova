"""스타일 씬 생성 경로 (레퍼런스 StylePlan + 특수 포맷) — 담당: 한의정.

6개 무드는 reference_style_plans의 도메인별 규칙을, 특수 포맷은 style_specs.scene_prompt를 사용한다.
  - food/drink/object별로 pop·editorial·realism·pastel·monotone·warm organic 연출을 분리.
  - 하이브리드 스타일은 kontext_service 의 A/B 템플릿(정체성 보존 편집)이 이미 담당.
  - 타이포는 이 단계 이후 overlay_service(PIL)로 별도 조판(역할분리).

⚠️ 정직성: 제품 형태·색은 보존절로 지킴. Kontext 로 안 되는 대규모 크리에이티브 합성
  (예: 화장품×크렘브륄레)은 풀생성 프롬프트(외부/추후) 몫 — scene_prompt 는 그 규약도 겸함.
"""
from __future__ import annotations

import os
from typing import Optional


def generate_scene(image_path: str, style_key: str, subject_en: str,
                   output_dir: str = "backend/results/ai/style",
                   seed: int = 42, steps: Optional[int] = None,
                   domain: Optional[str] = None,
                   staging: str = "preserve",
                   container_desc: Optional[str] = None,
                   container_opacity: Optional[str] = None,
                   temperature: Optional[str] = None,
                   text_zone: Optional[str] = None,
                   flexible_parts: Optional[list[str]] = None,
                   finish_profile: Optional[str] = None,
                   serving_type: Optional[str] = None,
                   core_ingredients: Optional[list[str]] = None,
                   extra_style_en: str = "") -> str:
    """도메인별 StylePlan 또는 특수 포맷 지시로 Kontext 편집 후 경로를 반환한다.

    staging="recompose"(P5 음료 재연출): 보존 편집 대신 같은 음료의 새 연출을 지시한다.
    container_desc/temperature/text_zone은 호출부가 analyze_photo 결과에서 넘긴다 —
    재연출 계약을 지원하지 않는 스타일이면 preserve로 자연 폴백.
    finish_profile(REAL-001): "photographic" 등 사진적 사실감 finish 절을 지시에 주입한다.
    None(기본)이면 build_*_instruction 이 plan 기본값("none")을 써 절 무주입 → 바이트 동일
    (REAL A/B 대조군). 실험 arm이 "photographic"을 넘겨 처리군을 만든다.
    extra_style_en: 사용자 자유서술 무드(영문, 직접 입력 탭). 값 있으면 프리셋의 verbose 씬 문단
      '대신' 사용자 서술을 연출 지시로 넣는다(맞교환). ⚠️ append 금지 — Kontext T5 512토큰 예산
      초과 시 뒤(가드·씬)부터 조용히 잘림([[kontext-t5-token-budget]]). 짧은 보존 템플릿에 사용자
      절만 실어 지시문을 짧게 유지(락·구성유지·no-text 보존, 영문 강제=함정#1). 빈값이면 회귀 0.
      (상위 process_ad 가 직접입력을 gpt-image edit 로 라우팅하고 이 로컬 경로는 폴백.)
    """
    from . import kontext_service
    from .style_specs import get_spec

    # P5 재연출 경로 — drink 전용 계약. 지시 생성 실패(미지원 스타일)면 아래 preserve로 폴백.
    if staging == "recompose":
        from .reference_style_plans import build_clip_anchor, build_recompose_instruction
        recompose_instr = build_recompose_instruction(
            style_key, subject_en, container_desc=container_desc,
            temperature=temperature, text_zone=text_zone,
            flexible_parts=flexible_parts, finish_profile=finish_profile,
        )
        if recompose_instr:
            kw = {} if steps is None else {"steps": steps}
            return kontext_service.edit(
                image_path, recompose_instr, seed=seed, output_dir=output_dir,
                clip_prompt=build_clip_anchor(style_key, "drink", subject_en,
                                              staging="recompose"),
                **kw,
            )

    sp = get_spec(style_key)
    scene = sp.scene_prompt.format(subject=subject_en or "product")

    # STY-003~005: 범용 프롬프트 한 개로는 6무드가 비슷해지고 도메인에 맞지 않는 소품이 생겼다.
    # 레퍼런스에서 추출한 무드 규칙을 food/drink/object별로 분리하고, 원본 정체성 잠금을 앞에 둔다.
    # CONTAINER-001: container_desc는 보존 경로에서도 쓴다 — 장식 용기(굽 유리볼 등)면
    # food 프리앰블·용기 문구를 원본 용기 유지 긍정 단언으로 치환. None이면 기존 문구 그대로.
    from .reference_style_plans import (build_clip_anchor, build_reference_instruction,
                                        normalize_style)
    clip_prompt = build_clip_anchor(style_key, domain, subject_en)
    #   재구성이 목적인 포맷(cross_section 단면·object_* 사물·pop_split 매크로)은 제외.
    _RECOMPOSE_OK = {"cross_section", "object_studio", "object_splash", "pop_split"}

    # 직접 입력(자유서술): 프리셋 verbose 씬 '대신' 사용자 절을 연출 지시로(맞교환, T5 예산 안전).
    #   상위 process_ad 는 직접입력을 gpt-image edit 로 라우팅하고, 이 로컬 경로는 폴백.
    if extra_style_en:
        if style_key not in _RECOMPOSE_OK:
            instr = (f"Edit this exact photo into an ad for the {subject_en or 'dish'}. Keep that food "
                     "faithful — the same pieces, the same real ingredients and its own sauce; do not "
                     "add, multiply or invent any food, ingredient, garnish or prop. Focus on it only: "
                     "you may crop out other unrelated foods or items in the original that are not part "
                     "of it. You may re-plate on a premium dish, restage it attractively and make it "
                     f"look freshly made and appetizing. Apply: {extra_style_en}. Keep colors natural "
                     "and true. No text.")
        else:
            instr = (f"Restyle the background, lighting and mood: {extra_style_en}. "
                     "Keep the product's shape, proportions and true colors faithful; "
                     "do not distort or recolor the product. No text.")
        kw = {} if steps is None else {"steps": steps}
        return kontext_service.edit(
            image_path, instr, seed=seed, output_dir=output_dir,
            clip_prompt=clip_prompt, **kw,
        )

    # PAL-001→003: 배경 팔레트를 제품 적응형 생성기로 도출(미지원 스타일=None → 기존 문구 바이트 동일).
    #   PAL_ADAPTIVE=0 이면 고정 팔레트 폴백(A/B 대조군·킬스위치).
    palette_override = None
    if os.environ.get("PAL_ADAPTIVE", "1") != "0":
        from . import palette_gen
        palette_override = palette_gen.style_palette_clause(
            normalize_style(style_key) or "", subject_en, domain, image_path, seed,
            serving_type=serving_type)
    # 구성(composition) 유지 절 — 무드 프리셋 씬 전용 (2026-07-11 콜드런 실측). ⚠️ 절 순서 결정적.
    reference_instr = build_reference_instruction(style_key, domain, subject_en,
                                                  container_desc=container_desc,
                                                  container_opacity=container_opacity,
                                                  palette_override=palette_override,
                                                  finish_profile=finish_profile,
                                                  serving_type=serving_type,
                                                  scene_seed=seed,
                                                  core_ingredients=core_ingredients)
    if reference_instr:
        instr = reference_instr
    elif style_key not in _RECOMPOSE_OK:
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
    return kontext_service.edit(
        image_path, instr, seed=seed, output_dir=output_dir,
        clip_prompt=clip_prompt, **kw,
    )
