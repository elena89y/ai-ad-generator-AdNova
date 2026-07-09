"""상품명 → 도메인 라우팅 (A 음식 / C 사물) 통합 진입점 — 담당: 한의정.

analyze_menu 로 domain·food_mode 판정 후:
  - food + dish → kontext_service.edit (A: Kontext 명령편집, texture_hero 로 A-hero/A-dish)
  - food + cafe → cafe_service.generate_cafe_ad (B: 누끼 + 리터치 + FLUX 씬)
  - object      → object_service.generate_object_ad (C: 누끼 + 클린 보정 + 스튜디오)

⚠️ VRAM: A(Kontext)와 B(FLUX Fill)는 동시상주 불가 — 각 진입 시 상대 언로드.
knob(0~1)은 C/B 강도에 매핑. A(Kontext)는 현재 guidance 고정.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class RouteResult:
    output_path: str
    domain: str          # food | object
    engine: str          # grade | generative | objectcut
    subject_en: str
    seconds: float


def process_input(image_path: str, name: str, knob: Optional[float] = None,
                  output_dir: str = "backend/results/ai/route") -> RouteResult:
    """사진 + 상품명 → 자동 라우팅 광고 리터치. 사용자는 이름만 입력."""
    from . import gpt_service

    a = gpt_service.analyze_menu(name)

    # C 사물: 누끼 + 클린보정 + 스튜디오
    if a.domain == "object":
        from . import object_service
        # 재질은 이름이 아니라 사진(Vision)으로 판정 — 이름만으론 유광/무광/투명 구분 불가.
        material = gpt_service.detect_material(image_path)
        intensity = 1.0 if knob is None else max(0.0, min(1.5, knob * 1.5))
        r = object_service.generate_object_ad(
            image_path, material=material, intensity=intensity, output_dir=output_dir)
        return RouteResult(r.output_path, "object", f"objectcut:{material}", a.subject_en, r.seconds)

    # B 카페(이산 제품): 누끼 + 생성리터치 + FLUX 씬
    if a.food_mode == "cafe":
        from . import cafe_service, kontext_service
        kontext_service.unload()   # A(Kontext) 상주 시 해제 → Fill 공간 확보(동시상주 OOM)
        strength = 0.4 if knob is None else max(0.2, min(0.65, knob))
        r = cafe_service.generate_cafe_ad(
            image_path, subject_en=a.subject_en, retouch_strength=strength, output_dir=output_dir)
        return RouteResult(r.output_path, "cafe", "cutout+flux", a.subject_en, r.seconds)

    # A 음식점(접시): Kontext 명령기반 편집 (grade/generative 대체 — P1 대결 5/5 승).
    #   texture_hero(마블링·파우더)=보존 최우선 A-hero / 그 외 A-dish. Kontext가 보존+연출 동시.
    #   knob 은 현재 미사용(guidance 2.5 고정) — 필요 시 guidance 매핑. food_service 는 폴백으로 잔존.
    import time

    from . import kontext_service
    template = "A-hero" if a.texture_hero else "A-dish"
    instr = kontext_service.build_instruction(template, a.subject_en, a.core_ingredients)
    t0 = time.time()
    out = kontext_service.edit(image_path, instr, output_dir=output_dir)
    return RouteResult(out, "food", f"kontext:{template}", a.subject_en, round(time.time() - t0, 2))
