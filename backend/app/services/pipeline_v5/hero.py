"""v5 — v4 합성엔진을 '함수 호출로만' 소비해 규격 없는 히어로를 얻는다. 담당: 한의정.

⚠️ v4(generation_service/overlay_service)는 동결 대상. 여기서 import 해 호출만 한다.
process_ad(poster=False) → 타이포 없는 리터치 히어로 + copy_text(헤드라인\n서브카피).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class DetailCutRole(str, Enum):
    HERO = "hero"
    TOP_VIEW = "top_view"
    TEXTURE_CLOSEUP = "texture_closeup"
    SIDE_PROFILE = "side_profile"
    LIFESTYLE = "lifestyle"


@dataclass(frozen=True)
class DetailCut:
    image_path: str
    role: DetailCutRole


@dataclass
class HeroAsset:
    """포맷 무관 히어로 소스. compose 가 이걸 각 FormatSpec 캔버스에 앉힌다."""
    image_path: str            # 타이포 없는 리터치 결과(규격 미확정)
    headline: str
    subcopy: str
    subject_en: str
    style: Optional[str]
    domain: str                # food | cafe | object
    mask_path: Optional[str]   # 누끼 마스크(B/C 모드만 존재, A 음식 in-place=None)
    seed: int
    product_name: str = ""
    detail_image_paths: tuple[str, ...] = ()  # 상세페이지용 추가 구도(메인 제외)
    detail_cuts: tuple[DetailCut, ...] = ()


def build_hero(
    image_path: str,
    name: str,
    knob: Optional[float] = None,
    style: Optional[str] = None,
    use_vision: bool = False,
    seed: Optional[int] = None,
    output_dir: str = "backend/results/ai/v5_hero",
) -> HeroAsset:
    """v4 process_ad 로 히어로만 생성(poster=False). GPU 필요.

    포스터(타이포)는 v5 compose 가 포맷별로 얹으므로 여기선 끈다.
    """
    from .. import generation_service  # v4 — 호출 전용
    from .. import image_service       # 누끼 마스크 경로 조회용

    processed = generation_service.process_ad(
        image_path=image_path,
        name=name,
        knob=knob,
        poster=False,          # ← 핵심: 타이포 없는 순수 히어로
        style=style,
        use_vision=use_vision,
        output_dir=output_dir,
        seed=seed,
        log=False,
    )

    headline, _, subcopy = processed.copy_text.partition("\n")
    headline, subcopy = headline.strip() or name, subcopy.strip()

    # 누끼 마스크는 B/C 모드에서만 생성됨(A 음식 in-place 는 없음).
    mask_path: Optional[str] = None
    try:
        cand = Path(image_service.PROCESSED_DIR) / f"{_asset_stem(processed.final_image_path)}_mask.png"
        if cand.is_file():
            mask_path = str(cand)
    except Exception:
        mask_path = None

    return HeroAsset(
        image_path=processed.final_image_path,
        headline=headline,
        subcopy=subcopy,
        subject_en=processed.subject_en,
        style=processed.style,
        domain=processed.domain,
        mask_path=mask_path,
        seed=processed.seed, product_name=name,
    )


def hero_from_existing(
    image_path: str,
    headline: str = "",
    subcopy: str = "",
    subject_en: str = "",
    style: Optional[str] = None,
    domain: str = "food",
    mask_path: Optional[str] = None,
    detail_image_paths: tuple[str, ...] = (),
    detail_cuts: tuple[DetailCut, ...] = (),
    product_name: str = "",
) -> HeroAsset:
    """GPU 없이 기존 이미지로 HeroAsset 구성 — 로컬 compose 검증용(테스트 진입점)."""
    return HeroAsset(
        image_path=image_path, headline=headline, subcopy=subcopy,
        subject_en=subject_en, style=style, domain=domain,
        mask_path=mask_path, seed=0, product_name=product_name,
        detail_image_paths=detail_image_paths,
        detail_cuts=detail_cuts,
    )


def _asset_stem(path: str) -> str:
    """결과 파일명에서 asset_id 추정(마스크 경로 매칭용, 실패해도 무해)."""
    return Path(path).stem.split("_")[0]
