"""v5 멀티포맷 파이프라인 — v4 히어로 엔진을 소비하는 상부구조. 담당: 한의정.

내부 병행 단계: HTTP/프론트 미노출. 환경변수 ADNOVA_PIPELINE=v5 또는 purpose!=SNS 로만 스위치.
기본값 v4 → 기존 SNS 계약 완전 보존(아무것도 안 바뀜).

    from app.services import pipeline_v5
    result = pipeline_v5.generate_v5(photo, name, purpose=AdPurpose.BANNER)

v4(generation_service/overlay_service)는 동결 — 여기서 호출만 한다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from ...schemas.ads import AdPurpose
from . import compose, format_spec, hero
from .hero import HeroAsset


@dataclass
class ProcessedAdSet:
    """v5 산출물 묶음. 단면 포맷=1장, 카드뉴스=N장."""
    purpose: AdPurpose
    outputs: list[str]                 # 최종 이미지 경로(들)
    hero: HeroAsset
    specs: list[format_spec.FormatSpec] = field(default_factory=list)


def use_v5(purpose: AdPurpose = AdPurpose.SNS) -> bool:
    """이 요청을 v5로 처리할지. 기본 v4, 스위치로만 v5 노출."""
    if os.getenv("ADNOVA_PIPELINE", "v4").lower() == "v5":
        return True
    return purpose != AdPurpose.SNS


def generate_v5(
    image_path: str,
    name: str,
    purpose: AdPurpose = AdPurpose.SNS,
    knob: Optional[float] = None,
    style: Optional[str] = None,
    use_vision: bool = False,
    seed: Optional[int] = None,
    output_dir: str = "backend/results/ai/v5",
    hero_asset: Optional[HeroAsset] = None,
    sizes: Optional[list[str]] = None,
    detail_image_paths: Optional[list[str]] = None,
) -> ProcessedAdSet:
    """사진+상품명+용도 → 포맷별 산출물. 히어로 1회 생성 후 규격별 조판.

    sizes: 규격 label 필터(예 ["commerce_wide"]). None 이면 팩 전체 자동 생성(기본 정책).
           → '유저 1개 선택'과 '팩 자동'을 한 함수로 지원(정책은 호출부 결정).
    hero_asset 을 주면 v4 재생성을 건너뛴다(멀티포맷 배치·로컬 테스트용).
    """
    # SNS 단독(override 없음)은 v4 process_ad(poster=True)를 그대로 태운다 — 완전 무손실.
    if purpose == AdPurpose.SNS and hero_asset is None:
        from .. import generation_service  # v4 — 호출 전용
        r = generation_service.process_ad(
            image_path=image_path, name=name, knob=knob, poster=True,
            style=style, use_vision=use_vision, output_dir=output_dir,
            seed=seed, log=False,
        )
        head, _, sub = r.copy_text.partition("\n")
        h = HeroAsset(
            image_path=r.final_image_path, headline=head.strip() or name,
            subcopy=sub.strip(), subject_en=r.subject_en, style=r.style,
            domain=r.domain, mask_path=None, seed=r.seed,
        )
        return ProcessedAdSet(
            purpose=purpose, outputs=[r.final_image_path], hero=h,
            specs=format_spec.specs_for(purpose),
        )

    h = hero_asset or hero.build_hero(
        image_path=image_path, name=name, knob=knob,
        style=style, use_vision=use_vision, seed=seed,
    )
    if detail_image_paths:
        h.detail_image_paths = tuple(detail_image_paths)

    specs = format_spec.specs_for(purpose)
    if sizes:
        wanted = set(sizes)
        available = {s.label for s in specs}
        unknown = wanted - available
        if unknown:
            raise ValueError(
                f"지원하지 않는 규격: {', '.join(sorted(unknown))}; "
                f"사용 가능: {', '.join(sorted(available))}"
            )
        specs = [s for s in specs if s.label in wanted]
    outputs: list[str] = []
    for spec in specs:
        outputs.extend(compose.render(h, spec, output_dir))

    return ProcessedAdSet(purpose=purpose, outputs=outputs, hero=h, specs=specs)
