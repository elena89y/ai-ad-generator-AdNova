"""생성 파이프라인 순수 로직 (DB·auth 없음) — 담당: 한의정.

역할: 전처리 → 배경 생성+조화 → 문구 → (포스터 오버레이) 를 한 함수로.
  API·DB 와 분리 — GPU VM 의 독립 생성 서비스(generation_app.py)와
  모놀리식 ads.py 가 공유하는 단일 진입점.

배포 구조(B): 이 파이프라인은 GPU 필요 → GPU VM 에서 실행.
  웹 백엔드(Docker, CPU)는 generation_client 로 HTTP 호출.
"""
from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from ..core.observability import observe, propagate_attributes
from ..schemas.ads import ProductInfo, StylePreset
from . import gpt_service, image_service
from .prompt_service import build_image_prompt

# asset_id 형식: preprocess 가 uuid4().hex[:12] 로 생성 → 12자리 hex 만 허용.
# 경로 탈출(../, /, \) 차단 (백엔드 리뷰 5번).
_ASSET_ID_RE = re.compile(r"^[a-f0-9]{12}$")


def is_valid_asset_id(asset_id: str) -> bool:
    return bool(_ASSET_ID_RE.match(asset_id or ""))


def _next_seed(prev_seed: Optional[int]) -> int:
    """직전 값과 다른 uint32 seed를 발급한다."""
    new_seed = random.randint(0, 2**32 - 1)
    while prev_seed is not None and new_seed == prev_seed:
        new_seed = random.randint(0, 2**32 - 1)
    return new_seed


def _style_seeds(seed: Optional[int], best_of: int) -> list[int]:
    """단일 생성은 요청 seed, Best-of-N은 서로 다른 고정 후보 seed를 사용한다."""
    if best_of <= 1:
        return [42 if seed is None else seed]

    pool = [7, 42, 123, 2024, 88, 512]
    if seed is not None:
        pool = [seed, *(candidate for candidate in pool if candidate != seed)]
    return pool[:min(best_of, len(pool))]


def _tag_seed_output(path: str, seed: int) -> str:
    """Best-of-N 후보가 같은 stem을 덮어쓰지 않도록 seed별 파일로 보존한다."""
    src = Path(path)
    tagged = src.with_name(f"{src.stem}_s{seed}{src.suffix}")
    if src != tagged:
        src.replace(tagged)
    return str(tagged)

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


# --- v2 드롭인 어댑터 (구 run_from_upload/rerun 대체) — Kontext(process_ad) 사용 -------------
#   시그니처·반환형(GenerationOutput) 동일 → ads.py·generation_app 은 함수명만 교체.
#   StylePreset(무드) → resolve_style → style_spec 키. 4매체 카피 + 정직성 게이트 포함.
def _unified_analysis_enabled() -> bool:
    """통합 Vision 분석 플래그. 기본 off로 기존 호출 그래프를 보존한다."""
    return os.environ.get("UNIFIED_ANALYSIS", "0") == "1"


def _analysis_cache_path(asset_id: str) -> Path:
    if not is_valid_asset_id(asset_id):
        raise ValueError(f"잘못된 asset_id 형식: {asset_id!r}")
    return image_service.PROCESSED_DIR / f"{asset_id}_analysis.json"


def _save_photo_analysis(asset_id: str, analysis: gpt_service.PhotoAnalysis) -> bool:
    """통합 분석을 asset별 JSON으로 원자 저장한다. 실패는 기존 경로 가용성을 막지 않는다."""
    try:
        cache_path = _analysis_cache_path(asset_id)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        pending = cache_path.with_suffix(".json.tmp")
        pending.write_text(json.dumps(asdict(analysis), ensure_ascii=False), encoding="utf-8")
        pending.replace(cache_path)
        return True
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning("통합 분석 캐시 저장 실패: %s", exc)
        return False


def _load_photo_analysis(asset_id: str) -> Optional[gpt_service.PhotoAnalysis]:
    """asset 통합 분석 캐시를 읽는다. 누락·구버전·손상 파일은 ``None``으로 폴백한다."""
    try:
        payload = json.loads(_analysis_cache_path(asset_id).read_text(encoding="utf-8"))
        return gpt_service.PhotoAnalysis(**payload)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        logging.getLogger(__name__).info("통합 분석 캐시 사용 불가: %s", exc)
        return None


def _analysis_matches_product(
    analysis: gpt_service.PhotoAnalysis,
    product_name: Optional[str],
) -> bool:
    """asset 캐시가 현재 재생성 상품명으로 만든 분석인지 확인한다."""
    return analysis.display_name.strip() == (product_name or "").strip()


def _platform_copies_safe(
    product: ProductInfo,
    style: StylePreset,
    analysis: Optional[gpt_service.PhotoAnalysis] = None,
) -> dict[str, dict]:
    """4매체 카피 + 정직성 게이트(core_ingredients 대조로 재료 환각 차단). 실패해도 {} (무해)."""
    try:
        resolved = analysis or gpt_service.analyze_menu(product.name)
        core = getattr(resolved, "core_ingredients", None) or None
        return gpt_service.generate_platform_copy(product, style, core_ingredients=core)
    except Exception:
        return {}


@observe(name="generation.run_from_upload_v2")
def run_from_upload_v2(
    image_path: str,
    product: ProductInfo,
    style: StylePreset,
    seed: Optional[int] = None,
    use_vision: bool = False,
    poster: bool = False,
) -> GenerationOutput:
    """v2 진입점 — run_from_upload 드롭인 교체. 내부는 process_ad(Kontext). GenerationOutput 반환."""
    import shutil
    import uuid
    from pathlib import Path as _P

    from ..harness.run_logger import RunLogger
    from .style_specs import resolve_style

    # asset_id 를 먼저 발급 — 이 요청 안의 모든 하위 LLM 호출(gpt_service/judge_service 트레이스)을
    # session_id=asset_id 로 묶는다. /ads/regenerate 는 같은 asset_id 로 rerun_v2 를 호출하므로,
    # Langfuse Sessions 뷰에서 최초 생성 트레이스와 재생성 트레이스가 하나의 세션으로 이어져 보인다.
    asset_id = uuid.uuid4().hex[:12]
    import os as _os
    _bon = max(1, int(_os.environ.get("BEST_OF_N", "1") or "1"))
    _steps = int(_os.environ["BEST_OF_STEPS"]) if _os.environ.get("BEST_OF_STEPS") else None
    actual_seed = 42 if seed is None else seed
    unified_analysis = _unified_analysis_enabled()

    with propagate_attributes(session_id=asset_id):
        with RunLogger(
            phase="V4P4A" if unified_analysis else "V3P1",
            mode="pending", engine="pending", input=image_path,
            seed=actual_seed,
            params={"asset_id": asset_id, "name": product.name, "style": style.value,
                    "poster": poster, "best_of": _bon, "steps": _steps,
                    "request": "generate"},
        ) as run:
            # 입력 게이트(P0): 명백한 사진-상품명 불일치만 생성 전에 차단한다.
            analysis = None
            with run.stage("input_gate"):
                if unified_analysis:
                    analysis = gpt_service.analyze_photo(image_path, product.name)
                gate = (
                    {"match": analysis.match, "seen": analysis.seen}
                    if analysis is not None
                    else gpt_service.verify_photo_subject(image_path, product.name)
                )
            if not gate["match"]:
                seen = f" (사진에는 '{gate['seen']}'이(가) 보여요)" if gate.get("seen") else ""
                raise ValueError(
                    f"사진과 상품명('{product.name}')이 서로 달라 보여요.{seen} "
                    "상품이 잘 보이는 사진인지 확인해 주세요.")

            # regen 용으로 입력 원본 보존(v2 는 누끼/mask 없음 → 원본 재투입 방식)
            with run.stage("input_prepare"):
                saved = image_service.PROCESSED_DIR / f"{asset_id}_v2input{_P(image_path).suffix}"
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(image_path, saved)
                if analysis is not None:
                    _save_photo_analysis(asset_id, analysis)

            # 결과는 서빙 디렉토리 절대경로에 저장하고 asset_id stem으로 URL 충돌을 막는다.
            r = process_ad(
                str(saved), product.name, poster=poster,
                style=resolve_style(style.value), output_dir=str(image_service.RESULTS_DIR),
                use_vision=use_vision, seed=actual_seed, best_of=_bon, steps=_steps,
                log=False, analysis=analysis, _run=run,
            )
            run.set_meta(
                mode=getattr(r, "domain", "unknown"),
                engine=getattr(r, "engine", "unknown"),
                seed=r.seed,
                subject_en=getattr(r, "subject_en", ""),
            )
            run.set_output(r.final_image_path)
            with run.stage("platform_copy"):
                platform_copies = _platform_copies_safe(product, style, analysis)
            return GenerationOutput(
                final_image_path=r.final_image_path, asset_id=asset_id, seed=r.seed, style=style,
                copy_text=r.copy_text, platform_copies=platform_copies,
                poster=poster, generate_seconds=round(r.seconds, 2), harmonize_seconds=0.0)


@observe(name="generation.rerun_v2")
def rerun_v2(
    asset_id: str,
    product: ProductInfo,
    style: StylePreset,
    prev_seed: Optional[int] = None,
    use_vision: bool = False,
    poster: bool = False,
) -> GenerationOutput:
    """v2 재생성 — 새 seed와 고유 입력 stem으로 기존 결과를 덮어쓰지 않는다."""
    import glob
    import shutil
    import uuid

    from ..harness.run_logger import RunLogger
    from .style_specs import resolve_style

    if not is_valid_asset_id(asset_id):
        raise ValueError(f"잘못된 asset_id 형식: {asset_id!r}")

    # session_id=asset_id — 최초 생성(run_from_upload_v2)이 같은 asset_id 로 연 세션에 합류.
    with propagate_attributes(session_id=asset_id):
        new_seed = _next_seed(prev_seed)
        unified_analysis = _unified_analysis_enabled()
        with RunLogger(
            phase="V4P4A" if unified_analysis else "V3P1",
            mode="pending", engine="pending", input=asset_id,
            seed=new_seed,
            params={"asset_id": asset_id, "name": product.name, "style": style.value,
                    "poster": poster, "request": "regenerate"},
        ) as run:
            with run.stage("input_prepare"):
                cands = glob.glob(str(image_service.PROCESSED_DIR / f"{asset_id}_v2input.*"))
                if not cands:
                    raise FileNotFoundError(f"v2 입력 원본 없음: asset_id={asset_id}")
                source = Path(cands[0])
                rerun_input = image_service.PROCESSED_DIR / (
                    f"{asset_id}_rerun_{uuid.uuid4().hex[:8]}_v2input{source.suffix}"
                )
                shutil.copy(source, rerun_input)
            analysis = _load_photo_analysis(asset_id) if unified_analysis else None
            if analysis is not None and not _analysis_matches_product(analysis, product.name):
                logging.getLogger(__name__).info(
                    "통합 분석 캐시 상품명 불일치 → 재분석: asset_id=%s",
                    asset_id,
                )
                analysis = None
            if unified_analysis and analysis is None:
                with run.stage("analysis"):
                    analysis = gpt_service.analyze_photo(str(source), product.name)
                if analysis is not None:
                    _save_photo_analysis(asset_id, analysis)
            try:
                r = process_ad(
                    str(rerun_input), product.name, poster=poster,
                    style=resolve_style(style.value), output_dir=str(image_service.RESULTS_DIR),
                    use_vision=use_vision, seed=new_seed, log=False,
                    analysis=analysis, _run=run,
                )
            finally:
                rerun_input.unlink(missing_ok=True)
            run.set_meta(
                mode=getattr(r, "domain", "unknown"),
                engine=getattr(r, "engine", "unknown"),
                seed=r.seed,
                subject_en=getattr(r, "subject_en", ""),
            )
            run.set_output(r.final_image_path)
            with run.stage("platform_copy"):
                platform_copies = _platform_copies_safe(product, style, analysis)
            return GenerationOutput(
                final_image_path=r.final_image_path, asset_id=asset_id, seed=r.seed, style=style,
                copy_text=r.copy_text, platform_copies=platform_copies,
                poster=poster, generate_seconds=round(r.seconds, 2), harmonize_seconds=0.0)


# =============================================================================
# 통합 엔트리 (신규 흐름) — 이름 기반 자동 모드 라우팅. 기존 run_generation 과 병행.
#   사진 + 상품명 → router(A/B/C 자동) → 문구 → 포스터. StylePreset 불필요.
#   HTTP API 계약 확정·이관은 팀 공유 후(PR 직전).
# =============================================================================
@dataclass
class ProcessedAd:
    final_image_path: str
    domain: str               # food | cafe | object
    engine: str               # grade | generative | cutout+flux | objectcut:<mat> | style:<key>
    subject_en: str
    copy_text: str            # '헤드라인\n서브카피' (FR-09)
    poster: bool
    seconds: float
    seed: int
    style: Optional[str] = None       # 디자인시스템 스타일 키(있으면 style_gen 경로)
    aesthetic: Optional[float] = None # NIMA 심미 점수(플라이휠 라벨)


def _nima_best(cands: list[str]) -> str:
    """NIMA 심미 top 후보. 실패 시 첫 후보 폴백(무해). (Kontext↔지표 VRAM 순차)"""
    try:
        from . import kontext_service
        from ..harness import metrics
        kontext_service.unload()
        return max(cands, key=lambda p: (metrics.aesthetic(p).get("nima") or 0.0))
    except Exception:
        return cands[0]


def _select_best(cands: list[str], original_path: Optional[str] = None) -> str:
    """Best-of-N 선별기. SELECTOR env: nima(기본) | gpt(구조화 저지) | both(둘 다 로깅·비교).

    both 는 프로덕션-세이프하게 NIMA 결과를 반환하되 GPT 점수·양측 선택을 로깅해
    사람 선호 대비 클린 비교 데이터를 축적한다(clean-ab: 데이터로 우위 확인 전엔 배포 금지).
    gpt 실패(키 없음·langchain 미설치·네트워크) 시 NIMA 로 폴백.
    """
    if len(cands) <= 1:
        return cands[0]
    sel = os.environ.get("SELECTOR", "nima").lower()

    if sel == "nima":
        return _nima_best(cands)

    # gpt / both: GPT 구조화 저지로 채점 (실패 시 NIMA 폴백)
    try:
        from . import judge_service
        # Kontext 상주 중이면 Vision 호출엔 무관하나, both 의 NIMA 계산과 순서 정리 위해 먼저 unload
        try:
            from . import kontext_service
            kontext_service.unload()
        except Exception:
            pass
        gpt_best, scores = judge_service.pick_best(cands, original_path=original_path)
    except Exception as e:  # noqa: BLE001
        logging.getLogger(__name__).warning(f"GPT 저지 실패 → NIMA 폴백: {e}")
        return _nima_best(cands)

    if sel == "gpt":
        return gpt_best

    # both: NIMA 도 계산해 양측 선택·점수 로깅, 반환은 NIMA(프로덕션 세이프)
    nima_best = _nima_best(cands)
    log = logging.getLogger(__name__)
    log.info("[SELECTOR both] nima_pick=%s gpt_pick=%s agree=%s",
             Path(nima_best).name, Path(gpt_best).name, nima_best == gpt_best)
    for p, s in zip(cands, scores):
        log.info("[SELECTOR both]   %s gpt_overall=%s (%s)", Path(p).name, s.overall, s.reason)
    return nima_best


def _stage(run, name: str):  # noqa: ANN001, ANN202
    return run.stage(name) if run is not None else nullcontext()


def process_ad(
    image_path: str,
    name: str,
    knob: Optional[float] = None,
    poster: bool = True,
    layout: str = "overlay",
    use_vision: bool = False,
    style: Optional[str] = None,
    output_dir: str = "backend/results/ai/route",
    log: bool = True,
    seed: Optional[int] = None,
    best_of: int = 1,
    steps: Optional[int] = None,
    analysis: Optional[gpt_service.PhotoAnalysis] = None,
    _run=None,  # noqa: ANN001
) -> ProcessedAd:
    """사진 + 상품명 → 자동 라우팅(또는 스타일 씬) 리터치 + 문구 + 포스터. 사용자는 이름만 입력.

    knob(0~1): 공통 강도 슬라이더. layout: overlay|panel(포스터).
    style: 디자인시스템 스타일 키(editorial/realism/pop/…) 지정 시 style_gen 씬 생성 경로,
           None 이면 기존 이름기반 A/B/C 자동 라우팅(하위호환). GPU 필요.
    log: True 면 RunLogger 로 전체 시간·단계·OpenAI usage를 적재한다.
         심미 평가는 ADNOVA_EVAL=1인 평가 실행에서만 기록한다.
    """
    if _run is not None:
        return _process_ad_impl(
            image_path, name, knob, poster, layout, use_vision, style,
            output_dir, seed, best_of, steps, analysis, run=_run,
        )
    if not log:
        return _process_ad_impl(
            image_path, name, knob, poster, layout, use_vision, style,
            output_dir, seed, best_of, steps, analysis, run=None,
        )

    try:
        from ..harness.run_logger import RunLogger

        run = RunLogger(
            phase="V4P4A" if _unified_analysis_enabled() else "V3P1",
            mode="pending", engine="pending", input=image_path,
            seed=seed,
            params={"name": name, "style": style, "layout": layout,
                    "best_of": best_of, "steps": steps},
        )
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning("RunLogger 초기화 실패: %s", exc)
        return _process_ad_impl(
            image_path, name, knob, poster, layout, use_vision, style,
            output_dir, seed, best_of, steps, analysis, run=None,
        )

    with run:
        result = _process_ad_impl(
            image_path, name, knob, poster, layout, use_vision, style,
            output_dir, seed, best_of, steps, analysis, run=run,
        )
        run.set_meta(mode=result.domain, engine=result.engine, seed=result.seed)
        run.set_output(result.final_image_path)
        if result.aesthetic is not None:
            run.add_metric("aesthetic", result.aesthetic)
        return result


# 디저트 어휘 — food_mode=cafe(카페 이산제품: 음료+디저트 혼재)에서 '음료 아님'을 판별.
#   2026-07-17 라이브 결함: '말차베리쿠키'가 cafe→drink로 승격 → drink 지시문("Keep the
#   drink, cup or glass, foam…")이 존재하지 않는 컵을 지어내 쿠키가 라떼로 재생성됨(날조).
_DESSERT_HINTS = (
    "cookie", "cake", "scone", "bread", "croissant", "macaron", "macaroon", "muffin",
    "tart", "donut", "doughnut", "brownie", "pastry", "dessert", "pie", "waffle",
    "bagel", "bun", "roll", "pudding", "tiramisu", "financier", "madeleine",
)
_DRINK_CONTAINERS = ("cup", "glass", "mug", "bottle", "can", "tumbler", "jar")


def _resolve_style_domain(analysis, domain: str, food_mode: Optional[str],
                          subject_en: str) -> str:  # noqa: ANN001
    """StylePlan 도메인 정규화. drink 는 '실제 음료'일 때만 — 디저트의 drink 승격 금지.

    1차: PhotoAnalysis(UNIFIED_ANALYSIS 경로)의 container_kind — 사진 근거(D-4).
    2차(텍스트 폴백): category=bakery 또는 subject_en 디저트 어휘면 food 유지.
    """
    if domain != "food" or food_mode != "cafe":
        return domain
    container = getattr(analysis, "container_kind", None)
    if container is not None:  # Vision 근거 우선
        return "drink" if str(container).lower() in _DRINK_CONTAINERS else domain
    if getattr(analysis, "category", "") == "bakery":
        return domain
    low = (subject_en or "").lower()
    if any(hint in low for hint in _DESSERT_HINTS):
        return domain
    return "drink"


_COMPOSE_INELIGIBLE_MATERIAL = ("transparent", "reflective")


def _compose_eligible(analysis, style_domain: str) -> bool:  # noqa: ANN001
    """합성(P4D) 적합성 1차 판정 = Vision. analysis에 필드가 없으면(구 경로) False —
    합성은 opt-in 개선 경로이므로 판단 근거가 없을 때는 안전하게 기존 Kontext 경로로 둔다."""
    if style_domain == "object":
        material = getattr(analysis, "material", None)
        if material is None:
            return False
        return material not in _COMPOSE_INELIGIBLE_MATERIAL
    if style_domain == "drink":
        opacity = getattr(analysis, "container_opacity", None)
        if opacity is None:
            return False
        return opacity == "opaque"
    return False


def _container_desc(analysis) -> Optional[str]:  # noqa: ANN001
    """P5 재연출용 용기 묘사 — analyze_photo(Vision) 산출값만 사용(이름 추정 금지, 개정 #2)."""
    kind = getattr(analysis, "container_kind", None)
    if not kind or str(kind).lower() == "none":
        return None
    color = getattr(analysis, "container_color", None)
    color_txt = f"{color} " if color and str(color).lower() not in ("", "none") else ""
    return f"{color_txt}{kind}"


def _resolve_drink_staging(analysis, style_domain: str, style_key: str,
                           seed: Optional[int]) -> tuple[str, Optional[str]]:  # noqa: ANN001
    """P5 라우팅(결정 D-4 개정). 반환 (staging, text_zone).

    recompose 조건: drink & DRINK_RECOMPOSE=1 & (합성 부적격(투명 용기 등) 또는 시드 로테이션이
    requires_recompose 아키타입(diagonal_splash·dreamy_cloud)을 고른 경우). 그 외 전부 preserve.
    """
    if style_domain != "drink" or os.environ.get("DRINK_RECOMPOSE", "0") != "1":
        return "preserve", None
    from . import scene_plans

    rotation_seed = _style_seeds(seed, 1)[0]
    plan = scene_plans.get_plan(style_key, "drink", seed=rotation_seed, allow_recompose=True)
    plan_wants_recompose = plan is not None and plan.requires_recompose
    if plan_wants_recompose:
        return "recompose", plan.text_zone
    if not _compose_eligible(analysis, "drink"):
        zone = plan.text_zone if plan is not None else "top"
        return "recompose", zone
    return "preserve", None


def _process_ad_impl(
    image_path: str,
    name: str,
    knob: Optional[float],
    poster: bool,
    layout: str,
    use_vision: bool,
    style: Optional[str],
    output_dir: str,
    seed: Optional[int],
    best_of: int,
    steps: Optional[int],
    analysis: Optional[gpt_service.PhotoAnalysis],
    run=None,  # noqa: ANN001
) -> ProcessedAd:
    """process_ad 실제 생성 본문. run이 있으면 단계별 시간을 함께 기록한다."""

    from . import router
    from .overlay_service import apply_food_poster

    t0 = time.time()
    text_zone: Optional[str] = None

    # 스타일 지정 시: style_gen 씬 생성(정체성 보존 편집), 아니면 기존 이름기반 라우팅
    if style:
        from . import style_gen
        # subject_en 은 analyze_menu 로 산출(한글→영문, CLIP 함정 회피)
        with _stage(run, "analysis"):
            resolved_analysis = analysis or gpt_service.analyze_menu(name)
        subject_en = getattr(resolved_analysis, "subject_en", None) or name
        domain = getattr(resolved_analysis, "domain", "food")
        food_mode = getattr(resolved_analysis, "food_mode", None)
        style_domain = _resolve_style_domain(resolved_analysis, domain, food_mode, subject_en)
        # 포맷 자동감지(STYLE_SYSTEM v2): style 은 '무드', 포맷은 콘텐츠로 결정.
        #   STY-003~005 이후 사물도 선택 무드를 적용하되, StylePlan이 상품은 고정하고 배경·조명만 바꾼다.
        #   여름음료 pop_split·케이크 cross_section 은 특수 조판/게이트 필요 → 당분간 명시 호출 유지.
        effective_style = style
        final: Optional[str] = None
        compose_stats: Optional[dict] = None

        # 합성 경로(P4D, 결정 D-11): SCENE_COMPOSE=1 + object/drink + Vision 적합성일 때만 시도.
        #   실패(sc["ok"]=False)하면 아무 것도 건드리지 않고 기존 Kontext 경로로 자연 폴백한다.
        if (os.environ.get("SCENE_COMPOSE", "0") == "1" and style_domain in ("object", "drink")
                and _compose_eligible(resolved_analysis, style_domain)):
            from . import scene_service

            compose_seed = _style_seeds(seed, 1)[0]
            with _stage(run, "compose"):
                sc = scene_service.compose_scene(
                    image_path, resolved_analysis, effective_style, style_domain,
                    seed=compose_seed, output_dir=output_dir,
                )
            if sc["ok"]:
                final = sc["path"]
                engine = f"scene:{sc['plan']}"
                text_zone = sc["text_zone"]
                selected_seed = compose_seed
                compose_stats = sc.get("stats")

        if final is None:
            # P5 음료 재연출(결정 D-4 개정): drink & DRINK_RECOMPOSE=1 & (합성 부적격 또는
            #   requires_recompose 아키타입 선택 시)만 staging="recompose". 그 외는 보존 편집.
            staging, recompose_zone = _resolve_drink_staging(
                resolved_analysis, style_domain, effective_style, seed)
            recompose_kwargs = {}
            if staging == "recompose":
                recompose_kwargs = {
                    "staging": "recompose",
                    "container_desc": _container_desc(resolved_analysis),
                    "temperature": getattr(resolved_analysis, "temperature", None),
                    "text_zone": recompose_zone,
                    # 제품 이해(PU-001): 용기가 flexible이면 무드 팔레트로 리컬러 허용
                    "flexible_parts": getattr(resolved_analysis, "flexible_parts", None),
                }
                text_zone = recompose_zone
            # Best-of-N: N시드 생성 → 선별기로 top 선택. best_of=1 이면 기존 1샷.
            #   ⚠️ BON-002 기각(2026-07-13): NIMA 는 이미-좋은 이미지(5~6점대)를 변별 못 해 Best-of-N 무효.
            #   선별기는 SELECTOR env 로 교체(nima 기본|gpt=구조화 저지|both=둘 다 로깅해 클린 비교).
            seeds = _style_seeds(seed, max(1, best_of))
            cands = []
            with _stage(run, "generate"):
                for candidate_seed in seeds:
                    candidate = style_gen.generate_scene(
                        image_path, effective_style, subject_en,
                        output_dir=output_dir, seed=candidate_seed, steps=steps,
                        domain=style_domain, **recompose_kwargs,
                    )
                    cands.append(_tag_seed_output(candidate, candidate_seed))
            with _stage(run, "select"):
                final = _select_best(cands, original_path=image_path)
            selected_seed = seeds[cands.index(final)]
            sel = os.environ.get("SELECTOR", "nima")
            engine_head = "recompose" if staging == "recompose" else "style"
            engine = f"{engine_head}:{effective_style}" + (
                f"·bestof{len(seeds)}:{sel}" if len(seeds) > 1 else "")

        # 프롬프트만으로 약하게 표현된 무드를 CPU 색 마감으로 보강한다. 실제 상품 마스크가
        # 없는 현재 Kontext 경로는 중앙 소프트 보호를 쓰므로, 실제 이미지 게이트 전에는 기본 off.
        if os.environ.get("STYLE_FINISH", "0") == "1":
            from . import style_finish

            with _stage(run, "style_finish"):
                final = style_finish.apply(
                    final,
                    style_key=effective_style,
                    strength=float(os.environ.get("STYLE_FINISH_STRENGTH", "0.6")),
                )

        # P6B 인라인 게이트(결정 D-5·D-7): audit=채점만 기록, enforce=style 재마감 개입.
        #   기본 off. enforce는 P6A 캘리브레이션(V4P6-001) 후에만 켠다. gate 결과는
        #   runs.jsonl(add_metric)에만 — 응답 스키마 노출은 범수 조율 전 금지.
        from . import inline_gate

        _gate_mode = inline_gate.gate_mode()
        if _gate_mode == "audit":
            with _stage(run, "gate"):
                gate = inline_gate.evaluate(final, effective_style, compose_stats)
            if run is not None:
                run.add_metric("gate", {**gate, "mode": "audit"})
        elif _gate_mode == "enforce":
            with _stage(run, "gate"):
                enforced = inline_gate.enforce(final, effective_style, compose_stats)
            final = enforced["path"]
            if run is not None:
                run.add_metric("gate", {**enforced["gate"], "mode": "enforce",
                                        "gate_failed": enforced["gate_failed"],
                                        "refinished": enforced["refinished"]})
    else:
        with _stage(run, "generate"):
            route = router.process_input(
                image_path, name, knob=knob, output_dir=output_dir, analysis=analysis,
            )
        final = route.output_path
        subject_en, domain, engine = route.subject_en, route.domain, route.engine
        selected_seed = 0 if seed is None else seed

    # 문구 (FR-09) — 상품명 + 리터치 이미지 기반. 톤은 EDITORIAL 기본.
    product = ProductInfo(name=name)
    with _stage(run, "copy"):
        copy = _generate_copy(final, product, StylePreset.EDITORIAL, use_vision)

    if poster:
        headline, _, subcopy = copy.copy_text.partition("\n")
        headline = headline.strip() or name
        subcopy = subcopy.strip()
        # 카피 폴백 누출 가드(콜드런 배치 실측): 캡션 실패 시 GPT 가 "이미지 정보가 제공되지
        #   않았습니다" 류 에러 문구를 헤드라인으로 내는 경우 → 상품명으로 폴백.
        if any(k in headline for k in ("제공되지 않", "이미지 정보", "이미지 설명", "알 수 없")):
            headline, subcopy = name, ""
        # 스타일 지정 시 폰트·액센트 자동 매핑(style_specs)
        with _stage(run, "poster"):
            final = apply_food_poster(final, headline, subcopy, layout=layout, style_key=style,
                                      text_zone=text_zone)

    # 심미 점수(플라이휠 라벨) — 실패 무해
    aesthetic = None
    # 운영 의존성에 pyiqa/CLIP이 없으면 매 요청 실패만 반복한다. 평가 실행은 명시적으로 켠다.
    if os.environ.get("ADNOVA_EVAL", "0") == "1":
        with _stage(run, "evaluate"):
            try:
                from ..harness.metrics import aesthetic_primary
                aesthetic = aesthetic_primary(final)
            except Exception:
                pass

    result = ProcessedAd(
        final_image_path=final, domain=domain, engine=engine,
        subject_en=subject_en, copy_text=copy.copy_text, poster=poster,
        seconds=round(time.time() - t0, 2), seed=selected_seed,
        style=style, aesthetic=aesthetic,
    )

    return result


def generate_ingredient_callout_ad(
    image_path: str,
    n: int = 3,
    output_dir: str = "backend/results/ai/callout",
) -> str:
    """재료 콜아웃 광고 — 음식 사진 위에 재료별 [흰 점→선→클로즈업 박스] (09_기타/부분클로즈업).

    ①gpt_service.detect_ingredients 로 재료 n개+좌표 탐지(Vision) ②각 재료 영역을 크롭해
    Kontext 로 신선 클로즈업 생성(같은 재료, 새 각도) ③overlay_service 로 점·선·박스 조판.
    정직성: 박스 재료 = 원본 재료(같은 종류라 생성이어도 정직). GPU 필요.
    """
    from pathlib import Path as _P

    from PIL import Image as _Img

    from . import gpt_service, kontext_service
    from .overlay_service import apply_ingredient_callout

    out = _P(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    base = _Img.open(image_path).convert("RGB")
    W, H = base.size

    items = gpt_service.detect_ingredients(image_path, n=n)
    callouts = []
    for i, it in enumerate(items):
        # 재료 영역 크롭(점 주변 정사각) → Kontext 신선 클로즈업(같은 재료)
        cx, cy = int(it["x"] * W), int(it["y"] * H)
        r = int(min(W, H) * 0.16)
        region = base.crop((max(0, cx - r), max(0, cy - r),
                            min(W, cx + r), min(H, cy + r)))
        crop_path = out / f"crop_{i}.png"
        region.save(crop_path)
        # ⚠️ 정직성(2026-07-11 콜아웃 엔드투엔드 실측): 이름 기반 'close-up of the {subj}, new angle'는
        #   Vision 오탐(감자→'사과') + 재생성이 겹쳐 접시에 없는 재료를 만들어냄. 박스 재료=원본 재료가
        #   깨짐. → 이름 의존·재생성 제거, 크롭된 실제 픽셀을 '그대로 두고 배경만 정리'하는 최소 편집으로.
        instr = ("Keep this exact food unchanged — same food type, shape, color and texture, do not turn "
                 "it into any other food. Only clean up and softly blur the background behind it and sharpen "
                 "its appetizing detail. No text.")
        closeup = kontext_service.edit(str(crop_path), instr, output_dir=str(out))
        callouts.append({"start": (it["x"], it["y"]), "closeup": closeup})

    kontext_service.unload()
    if not callouts:
        return image_path  # 탐지 실패 시 원본 반환(무해)
    final = out / f"{_P(image_path).stem}_callout.png"
    return apply_ingredient_callout(image_path, callouts, str(final))


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
