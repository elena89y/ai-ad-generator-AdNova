"""생성 파이프라인 순수 로직 (DB·auth 없음) — 담당: 한의정.

역할: 전처리 → 배경 생성+조화 → 문구 → (포스터 오버레이) 를 한 함수로.
  API·DB 와 분리 — GPU VM 의 독립 생성 서비스(generation_app.py)와
  모놀리식 ads.py 가 공유하는 단일 진입점.

배포 구조(B): 이 파이프라인은 GPU 필요 → GPU VM 에서 실행.
  웹 백엔드(Docker, CPU)는 generation_client 로 HTTP 호출.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# asset_id 형식: preprocess 가 uuid4().hex[:12] 로 생성 → 12자리 hex 만 허용.
# 경로 탈출(../, /, \) 차단 (백엔드 리뷰 5번).
_ASSET_ID_RE = re.compile(r"^[a-f0-9]{12}$")


def is_valid_asset_id(asset_id: str) -> bool:
    return bool(_ASSET_ID_RE.match(asset_id or ""))

from ..schemas.ads import ProductInfo, StylePreset
from . import gpt_service, image_service
from .prompt_service import build_image_prompt

# 스타일 → 평면배경 모드 (SDXL 회색조 회귀·소품 잔재 우회, IMG-002/QUA-007)
_FLAT_BG = {"editorial": "editorial", "retro_paper": "retro", "pastel_float": "pastel"}


def _generate_copy(final_image_path, product, style, use_vision):  # noqa: ANN001
    """문구 생성. USE_COPY_GATE + langgraph 있으면 품질 게이트 루프, 아니면 직접 호출.

    제거 가능 설계: copy_graph 없거나 플래그 off 면 조용히 gpt_service 로 폴백.
    """
    from ..core.config import settings

    if settings.USE_COPY_GATE:
        try:
            from .copy_graph import generate_copy_with_gate

            return generate_copy_with_gate(final_image_path, product, style, use_vision)
        except ImportError:
            pass  # langgraph 미설치 → 폴백
    return gpt_service.generate_copy(final_image_path, product, style, use_vision=use_vision)


@dataclass
class GenerationOutput:
    """순수 생성 결과 (DB·URL 성형 이전)."""
    final_image_path: str
    asset_id: str
    seed: int
    style: StylePreset
    copy_text: str            # '헤드라인\n서브카피' (FR-09)
    platform_copies: dict[str, dict]
    poster: bool
    generate_seconds: float
    harmonize_seconds: float


def run_generation(
    processed: image_service.PreprocessResult,
    product: ProductInfo,
    style: StylePreset,
    seed: Optional[int] = None,
    use_vision: bool = False,
    poster: bool = False,
) -> GenerationOutput:
    """전처리 산출물 → 최종 광고 이미지 + 문구. GPU 필요.

    generate/regenerate 공통 구간. ads.py 와 generation_app.py 가 공유.
    """
    prompt = build_image_prompt(product, style)
    gen = image_service.generate_ad_image(
        processed, prompt, seed=seed,
        flat_background=_FLAT_BG.get(style.value),
        product_tilt=(-12.0 if style == StylePreset.PASTEL_FLOAT else 0.0),
    )

    copy = _generate_copy(gen.final_image_path, product, style, use_vision)
    try:
        platform_copies = gpt_service.generate_platform_copy(product, style)
    except Exception:
        platform_copies = {}

    final_path = gen.final_image_path
    if poster:
        from .overlay_service import apply_overlay

        headline, _, subcopy = copy.copy_text.partition("\n")
        headline, subcopy = headline.strip(), subcopy.strip() or (product.name or "")
        # editorial/retro 헤드라인은 영문 대문자 (레퍼런스 룩, GPT 변환 1회)
        if style in (StylePreset.EDITORIAL, StylePreset.RETRO_PAPER):
            en_name, en_phrase = gpt_service.generate_english_labels(product)
            headline = en_name
            if style == StylePreset.EDITORIAL:
                subcopy = en_phrase
        final_path = apply_overlay(
            gen.final_image_path, style, headline, subcopy, processed.mask_path,
            text_only=(style in (StylePreset.EDITORIAL, StylePreset.RETRO_PAPER)),
        )

    asset_id = Path(processed.processed_image_path).stem.replace("_processed", "")
    return GenerationOutput(
        final_image_path=final_path,
        asset_id=asset_id,
        seed=gen.seed,
        style=style,
        copy_text=copy.copy_text,
        platform_copies=platform_copies,
        poster=poster,
        generate_seconds=round(gen.infer_seconds, 2),
        harmonize_seconds=round(gen.harmonize_seconds, 2),
    )


def run_from_upload(
    image_path: str,
    product: ProductInfo,
    style: StylePreset,
    seed: Optional[int] = None,
    use_vision: bool = False,
    poster: bool = False,
) -> GenerationOutput:
    """업로드 이미지 경로 → 전처리 포함 전체 생성. 생성 서비스 진입점."""
    processed = image_service.preprocess(image_path)
    return run_generation(processed, product, style, seed, use_vision, poster)


def rerun(
    asset_id: str,
    product: ProductInfo,
    style: StylePreset,
    prev_seed: Optional[int] = None,
    use_vision: bool = False,
    poster: bool = False,
) -> GenerationOutput:
    """FR-12: 기존 전처리 산출물 재사용 + 새 seed. 전처리 생략(빠름)."""
    if not is_valid_asset_id(asset_id):
        raise ValueError(f"잘못된 asset_id 형식: {asset_id!r}")
    processed_path = image_service.PROCESSED_DIR / f"{asset_id}_processed.png"
    mask_path = image_service.PROCESSED_DIR / f"{asset_id}_mask.png"
    if not processed_path.is_file() or not mask_path.is_file():
        raise FileNotFoundError(f"산출물 없음: asset_id={asset_id}")

    processed = image_service.PreprocessResult(
        processed_image_path=str(processed_path), mask_path=str(mask_path)
    )
    new_seed = random.randint(0, 2**32 - 1)
    while prev_seed is not None and new_seed == prev_seed:
        new_seed = random.randint(0, 2**32 - 1)
    return run_generation(processed, product, style, new_seed, use_vision, poster)


# =============================================================================
# 통합 엔트리 (신규 흐름) — 이름 기반 자동 모드 라우팅. 기존 run_generation 과 병행.
#   사진 + 상품명 → router(A/B/C 자동) → 문구 → 포스터. StylePreset 불필요.
#   HTTP API 계약 확정·이관은 팀 공유 후(PR 직전).
# =============================================================================
@dataclass
class ProcessedAd:
    final_image_path: str
    domain: str               # food | cafe | object
    engine: str               # grade | generative | cutout+flux | objectcut:<mat>
    subject_en: str
    copy_text: str            # '헤드라인\n서브카피' (FR-09)
    poster: bool
    seconds: float


def process_ad(
    image_path: str,
    name: str,
    knob: Optional[float] = None,
    poster: bool = True,
    layout: str = "overlay",
    use_vision: bool = False,
    output_dir: str = "backend/results/ai/route",
) -> ProcessedAd:
    """사진 + 상품명 → 자동 라우팅 리터치 + 문구 + 포스터. 사용자는 이름만 입력.

    knob(0~1): 공통 강도 슬라이더. layout: overlay|panel(포스터). GPU 필요.
    """
    import time

    from . import router
    from .overlay_service import apply_food_poster

    t0 = time.time()
    route = router.process_input(image_path, name, knob=knob, output_dir=output_dir)
    final = route.output_path

    # 문구 (FR-09) — 상품명 + 리터치 이미지 기반. 톤은 EDITORIAL 기본.
    product = ProductInfo(name=name)
    copy = _generate_copy(final, product, StylePreset.EDITORIAL, use_vision)

    if poster:
        headline, _, subcopy = copy.copy_text.partition("\n")
        headline = headline.strip() or name
        subcopy = subcopy.strip()
        final = apply_food_poster(final, headline, subcopy, layout=layout)

    return ProcessedAd(
        final_image_path=final, domain=route.domain, engine=route.engine,
        subject_en=route.subject_en, copy_text=copy.copy_text, poster=poster,
        seconds=round(time.time() - t0, 2),
    )


def generate_editorial(
    image_path: str,
    name: str,
    eyebrow: str = "SIGNATURE",
    output_dir: str = "backend/results/ai/editorial",
) -> str:
    """에디토리얼 포스터 (단색 배경 + 중앙 히어로) — 누끼 + 클린보정 + 상단 세리프.

    카페 디저트·제품의 프리미엄 룩(FLUX 씬보다 싸고 통제 쉬움). 영문 라벨 GPT 1회.
    """
    from pathlib import Path as _P

    from PIL import Image as _Img

    from . import gpt_service, image_service, object_service
    from .overlay_service import apply_editorial_poster

    proc = image_service.preprocess(image_path, output_dir=output_dir)
    prgba = _Img.open(proc.processed_image_path).convert("RGBA")
    cleaned = object_service.clean_object(prgba, material="matte", intensity=0.8)

    try:
        en_name, en_phrase = gpt_service.generate_english_labels(ProductInfo(name=name))
        caption = en_phrase.title() if en_phrase else "Handcrafted daily"
    except Exception:  # 영문 라벨 응답 형태 변동 등 → 원문 이름으로 폴백
        en_name, caption = name, "Handcrafted daily"

    out = _P(output_dir) / f"{_P(image_path).stem}_editorial.png"
    return apply_editorial_poster(cleaned, eyebrow, en_name, caption, output_path=str(out))
