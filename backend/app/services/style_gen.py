"""스타일 씬 생성 경로 (레퍼런스 StylePlan + 특수 포맷) — 담당: 한의정.

6개 무드는 reference_style_plans의 도메인별 규칙을, 특수 포맷은 style_specs.scene_prompt를 사용한다.
  - food/drink/object별로 pop·editorial·realism·pastel·monotone·warm organic 연출을 분리.
  - 하이브리드 스타일은 kontext_service 의 A/B 템플릿(정체성 보존 편집)이 이미 담당.
  - 타이포는 이 단계 이후 overlay_service(PIL)로 별도 조판(역할분리).

⚠️ 정직성: 제품 형태·색은 보존절로 지킴. Kontext 로 안 되는 대규모 크리에이티브 합성
  (예: 화장품×크렘브륄레)은 풀생성 프롬프트(외부/추후) 몫 — scene_prompt 는 그 규약도 겸함.
"""
from __future__ import annotations

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
                   extra_style_en: str = "") -> str:
    """도메인별 StylePlan 또는 특수 포맷 지시로 Kontext 편집 후 경로를 반환한다.

    staging="recompose"(P5 음료 재연출): 보존 편집 대신 같은 음료의 새 연출을 지시한다.
    container_desc/temperature/text_zone은 호출부가 analyze_photo 결과에서 넘긴다 —
    재연출 계약을 지원하지 않는 스타일이면 preserve로 자연 폴백.
    extra_style_en: 사용자 자유서술 무드(영문, 직접 입력 탭). 값 있으면 프리셋의 verbose 씬 문단
      '대신' 사용자 서술을 연출 지시로 넣는다(맞교환). ⚠️ append 금지 — Kontext T5 512토큰 예산
      초과 시 뒤(가드·씬)부터 조용히 잘리고 현행 배포본도 이미 초과 수준이라, 붙이면 사용자 절이
      제일 먼저 유실된다([[kontext-t5-token-budget]]). 그래서 짧은 보존 템플릿에 사용자 절만 실어
      지시문을 짧게 유지한다(락·구성유지·no-text 보존, 영문 강제=함정#1). 빈값이면 회귀 0.
      (recompose 경로는 실험 게이트 off 기본이라 자유서술 미적용.)
    """
    from . import kontext_service
    from .style_specs import get_spec

    # P5 재연출 경로 — drink 전용 계약. 지시 생성 실패(미지원 스타일)면 아래 preserve로 폴백.
    if staging == "recompose":
        from .reference_style_plans import build_clip_anchor, build_recompose_instruction
        recompose_instr = build_recompose_instruction(
            style_key, subject_en, container_desc=container_desc,
            temperature=temperature, text_zone=text_zone,
            flexible_parts=flexible_parts,
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
    from .reference_style_plans import build_clip_anchor, build_reference_instruction
    clip_prompt = build_clip_anchor(style_key, domain, subject_en)

    #   재구성이 목적인 포맷(cross_section 단면·object_* 사물·pop_split 매크로)은 제외.
    _RECOMPOSE_OK = {"cross_section", "object_studio", "object_splash", "pop_split"}

    if extra_style_en:
        # 직접 입력(자유서술): 프리셋 verbose 씬 '대신' 사용자 절을 연출 지시로(맞교환, T5 예산 안전).
        #   짧은 보존 템플릿으로 감싸 정체성·구성·no-text 유지. 락은 앞, 사용자 절은 씬 자리.
        if style_key not in _RECOMPOSE_OK:
            instr = ("Edit this exact photo. Keep every item exactly as photographed: the same "
                     "number of pieces, the same sauces, garnishes, plating and arrangement — do "
                     "not remove, add, merge or simplify anything. "
                     f"Restyle ONLY the background, surface, lighting and mood as follows: {extra_style_en}. "
                     "Keep the true colors. No text.")
        else:
            instr = (f"Restyle the background, lighting and mood: {extra_style_en}. "
                     "Keep the product's shape, proportions and true colors faithful; "
                     "do not distort or recolor the product. No text.")
        kw = {} if steps is None else {"steps": steps}
        return kontext_service.edit(
            image_path, instr, seed=seed, output_dir=output_dir,
            clip_prompt=clip_prompt, **kw,
        )

    # 구성(composition) 유지 절 — 무드 프리셋 씬 전용 (2026-07-11 콜드런 실측: editorial 이 브런치
    #   4조각+치즈소스+음료를 1개 단품으로 재구성 → 메뉴 시그니처 소실 = 정직성 경계 위반).
    #   ⚠️ 절 순서가 결정적: 구성 유지를 '맨 앞'에 둬야 씬의 스타일 언어(싱글히어로·여백)에 안 밀림.
    reference_instr = build_reference_instruction(style_key, domain, subject_en,
                                                  container_desc=container_desc,
                                                  container_opacity=container_opacity)
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
