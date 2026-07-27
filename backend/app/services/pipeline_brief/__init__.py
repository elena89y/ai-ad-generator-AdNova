"""pipeline_brief — 무-상품(텍스트 브리프) 광고팩 파이프라인 (제거 가능 모듈). 담당: 한의정.

기능 1: 상품 사진 없는 유저(행사·이벤트·서비스업)가 브리프 텍스트만으로 멀티포맷 광고팩을 얻는다.
  브리프 → plan.expand_brief(영문 씬+한글 카피+정보줄 원문발췌)
        → compliance.gate(정보 무결성=하드 / 과장표현=보조 경고·면책)
        → background.generate_background(api=gpt-image-2 | local=RealVis txt2img)
        → pipeline_v5.generate_v5(멀티포맷 조판 — 코어 재사용, 재구현 금지)

⚠️ 제거 가능 설계(copy_graph 패턴): 이 패키지 삭제 + generation_service 의 guarded import 만으로 원복.
  코어에 남는 접점은 전부 no-op — HeroAsset.info_lines/fine_print(기본 빈 값), sns/banner 의
  "정보줄 있으면" 분기(상품 경로 회귀 0, test_pipeline_v5_* 가 지킨다).
  USE_BRIEF_PIPELINE=0 으로 코드 삭제 없이 비활성화.

역할분리(함정 #1·#3): 배경=생성모델(영어 프롬프트, 글자 금지) / 타이포·정보·규정문구=코드(PIL).
정직성: 일시·장소·문의처는 브리프 원문 발췌만 조판(오탈자 0) — 상품 경로의 '없던 가니시 금지'가
무-상품 경로에선 '정보 정확성 보증'으로 치환된다.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


def enabled() -> bool:
    """기능 스위치 — USE_BRIEF_PIPELINE=0 이면 진입 차단(패키지 삭제 없이 off)."""
    return os.getenv("USE_BRIEF_PIPELINE", "1") == "1"


@dataclass
class BriefAdSet:
    """브리프(텍스트) → 멀티포맷 광고팩 산출물.

    violations 는 규정 게이트의 '보조 체크리스트'(면책) — 렌더를 막지 않고 표시만 한다.
    """
    outputs: list[str]
    headline: str
    info_lines: tuple[str, ...]
    fine_print: str
    violations: tuple[str, ...]
    purposes: list[str]


def build_hero_from_brief(
    brief: str,
    vertical: str = "event",
    engine: Optional[str] = None,
    size: str = "1024x1024",
    seed: Optional[int] = None,
    style: Optional[str] = None,
    run=None,  # noqa: ANN001 — RunLogger optional
):
    """무-상품 브리프 → (HeroAsset, GateResult). 조판은 pipeline_v5 하류가 담당."""
    if not enabled():
        raise RuntimeError("brief 파이프라인 비활성화됨 (USE_BRIEF_PIPELINE=0)")

    from ..pipeline_v5.hero import HeroAsset
    from . import background, compliance, plan as plan_mod

    plan = plan_mod.expand_brief(brief, vertical)
    gate = compliance.gate(plan.headline_ko, plan.subcopy_ko, plan.info_lines, vertical)
    bg_path = background.generate_background(
        plan.scene_en, plan.palette_hint, size=size, engine=engine, seed=seed, run=run)

    # product_name 은 배너 조판에서 키커(상단 라벨) 슬롯 — 무-상품 경로엔 상품명이 없으므로
    # 서브카피를 태운다(헤드라인 중복·커머스 placeholder 노출 방지).
    hero = HeroAsset(
        image_path=bg_path, headline=plan.headline_ko, subcopy=plan.subcopy_ko,
        subject_en=plan.scene_en, style=style, domain="event", mask_path=None,
        seed=seed or 0, product_name=plan.subcopy_ko or plan.headline_ko,
        info_lines=gate.info_lines, fine_print=gate.fine_print,
    )
    return hero, gate


def run_from_brief(
    brief: str,
    vertical: str = "event",
    purposes: Optional[list] = None,
    sizes: Optional[list[str]] = None,
    engine: Optional[str] = None,
    seed: Optional[int] = None,
    style: Optional[str] = None,
    output_dir: str = "backend/results/ai/brief",
    run=None,  # noqa: ANN001 — RunLogger optional (KPI/예산 원장)
) -> BriefAdSet:
    """텍스트 브리프만으로 멀티포맷 광고팩 생성 — 기능 1의 단일 진입점.

    purposes 기본값 = [SNS, BANNER]. sizes 는 규격 label 필터인데 label 이 purpose 별로
    서로소(SNS={square} / BANNER={commerce_*})라, **각 purpose 에는 그 purpose 가 가진
    label 만 교집합으로 넘긴다**(없으면 그 purpose 는 건너뜀). 전 purpose 에 하나도 안 맞으면
    ValueError. KPI/예산: 배경 생성이 활성 RunLogger 에 자동 합류(generate_image).
    """
    if not enabled():
        raise RuntimeError("brief 파이프라인 비활성화됨 (USE_BRIEF_PIPELINE=0)")

    from ...schemas.ads import AdPurpose
    from .. import pipeline_v5
    from ..pipeline_v5 import format_spec

    if purposes is None:
        purposes = [AdPurpose.SNS, AdPurpose.BANNER]

    hero, gate = build_hero_from_brief(
        brief, vertical=vertical, engine=engine, seed=seed, style=style, run=run)
    if gate.violations:
        logger.info("[brief 규정 경고] %s", "; ".join(gate.violations))

    outputs: list[str] = []
    rendered: list[str] = []
    for purpose in purposes:
        if sizes is not None:
            available = {s.label for s in format_spec.specs_for(purpose)}
            use_sizes = [s for s in sizes if s in available]
            if not use_sizes:  # 이 purpose 엔 요청 규격이 없음 → 크래시 대신 건너뜀
                logger.info("[brief] %s 규격 없음 → 건너뜀 (요청 sizes=%s)", purpose.value, sizes)
                continue
        else:
            use_sizes = None
        result = pipeline_v5.generate_v5(
            hero_asset=hero, purpose=purpose, sizes=use_sizes, output_dir=output_dir)
        outputs.extend(result.outputs)
        rendered.append(purpose.value)

    if sizes is not None and not rendered:
        valid = sorted({s.label for p in purposes for s in format_spec.specs_for(p)})
        raise ValueError(
            f"요청 sizes {sizes} 가 대상 purpose 어디에도 없음; 사용 가능: {', '.join(valid)}")

    return BriefAdSet(
        outputs=outputs, headline=hero.headline, info_lines=hero.info_lines,
        fine_print=hero.fine_print, violations=gate.violations,
        purposes=rendered,
    )
