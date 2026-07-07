"""상품명 → 도메인 라우팅 (A 음식 / C 사물) 통합 진입점 — 담당: 한의정.

analyze_menu 로 domain 판정 후:
  - food   → food_service.retouch (보존 그레이드 / 생성 리터치, texture_hero 로 재분기)
  - object → object_service.generate_object_ad (누끼 + 클린 보정 + 스튜디오 배경)

knob(0~1 공통 슬라이더)은 각 엔진의 강도로 매핑된다. B(카페) 모드는 추후 추가.
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
        from . import cafe_service
        strength = 0.4 if knob is None else max(0.2, min(0.65, knob))
        r = cafe_service.generate_cafe_ad(
            image_path, subject_en=a.subject_en, retouch_strength=strength, output_dir=output_dir)
        return RouteResult(r.output_path, "cafe", "cutout+flux", a.subject_en, r.seconds)

    # A 음식점(접시): in-place 리터치 (그레이드/생성)
    from . import food_service
    r = food_service.retouch(image_path, a, knob=knob, output_dir=output_dir)
    engine = "grade" if a.texture_hero else "generative"
    return RouteResult(r.output_path, "food", engine, a.subject_en, r.seconds)
