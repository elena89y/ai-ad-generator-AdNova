"""상품명 → 도메인 라우팅 (A 음식 / C 사물) 통합 진입점 — 담당: 한의정.

analyze_menu 로 domain·food_mode 판정 후:
  - food + dish → kontext_service.edit (A: Kontext 명령편집, texture_hero 로 A-hero/A-dish)
  - food + cafe → kontext_service.edit (B: Kontext B-scene 배경교체 — P3-1 결정, v1 누끼+FLUX 대체)
  - object      → object_service.generate_object_ad (C: 누끼 + 클린 보정 + 스튜디오)

A·B 모두 Kontext 로 통일 → 카페 누끼(rembg)·FLUX Fill 인페인트 경로 은퇴(운영 단순화·OOM 회피).
knob(0~1)은 A/B steps(8~20)·C 강도에 매핑.
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
                  output_dir: str = "backend/results/ai/route",
                  analysis=None) -> RouteResult:  # noqa: ANN001
    """사진 + 상품명 → 자동 라우팅 광고 리터치. 사용자는 이름만 입력."""
    from . import gpt_service

    a = analysis or gpt_service.analyze_menu(name)

    # C 사물: 누끼 + 클린보정 + 스튜디오
    if a.domain == "object":
        from . import object_service
        # 재질은 이름이 아니라 사진(Vision)으로 판정 — 이름만으론 유광/무광/투명 구분 불가.
        material = (
            getattr(a, "material", "default")
            if analysis is not None else gpt_service.detect_material(image_path)
        )
        intensity = 1.0 if knob is None else max(0.0, min(1.5, knob * 1.5))
        r = object_service.generate_object_ad(
            image_path, material=material, intensity=intensity, output_dir=output_dir)
        return RouteResult(r.output_path, "object", f"objectcut:{material}", a.subject_en, r.seconds)

    # B 카페(이산 제품): Kontext 배경교체 단발 (P3-1 결정 — v1 누끼+RealVis+FLUX 대체)
    #   투명 유리잔(누끼 최난이도)을 누끼 없이 정체성보존(DINO 0.94)+씬연출, 4/4 결함0, 운영 견고
    #   (v1 은 rembg onnxruntime 아레나+FLUX OOM/박스마비 실증 — ERROR_LOG ERR-008/010).
    #   cafe_service 는 폴백으로 잔존. knob→steps(A 와 동일 매핑).
    if a.food_mode == "cafe":
        import time

        from . import kontext_service
        instr = kontext_service.build_instruction("B-scene", a.subject_en)
        steps = (kontext_service.DEFAULT_STEPS if knob is None
                 else int(round(8 + max(0.0, min(1.0, knob)) * 12)))
        t0 = time.time()
        out = kontext_service.edit(image_path, instr, steps=steps, output_dir=output_dir)
        return RouteResult(out, "cafe", "kontext:B-scene", a.subject_en, round(time.time() - t0, 2))

    # A 음식점(접시): Kontext 명령기반 편집 (grade/generative 대체 — P1 대결 5/5 승).
    #   texture_hero(마블링·파우더)=보존 최우선 A-hero / 그 외 A-dish. Kontext가 보존+연출 동시.
    #   knob 은 현재 미사용(guidance 2.5 고정) — 필요 시 guidance 매핑. food_service 는 폴백으로 잔존.
    import time

    from . import kontext_service
    template = "A-hero" if a.texture_hero else "A-dish"
    instr = kontext_service.build_instruction(template, a.subject_en, a.core_ingredients)
    # knob → steps(품질/속도): 0=빠름(8) ~ 1=고품질(20), 기본 12. P1-speed 실측 범위.
    steps = (kontext_service.DEFAULT_STEPS if knob is None
             else int(round(8 + max(0.0, min(1.0, knob)) * 12)))
    t0 = time.time()
    out = kontext_service.edit(image_path, instr, steps=steps, output_dir=output_dir)
    return RouteResult(out, "food", f"kontext:{template}", a.subject_en, round(time.time() - t0, 2))
