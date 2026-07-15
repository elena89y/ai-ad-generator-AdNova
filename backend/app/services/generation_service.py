"""생성 파이프라인 순수 로직 (DB·auth 없음) — 담당: 한의정.

역할: 전처리 → 배경 생성+조화 → 문구 → (포스터 오버레이) 를 한 함수로.
  API·DB 와 분리 — GPU VM 의 독립 생성 서비스(generation_app.py)와
  모놀리식 ads.py 가 공유하는 단일 진입점.

배포 구조(B): 이 파이프라인은 GPU 필요 → GPU VM 에서 실행.
  웹 백엔드(Docker, CPU)는 generation_client 로 HTTP 호출.
"""
from __future__ import annotations

import os
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

from ..core.observability import observe, propagate_attributes
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


# --- v2 드롭인 어댑터 (구 run_from_upload/rerun 대체) — Kontext(process_ad) 사용 -------------
#   시그니처·반환형(GenerationOutput) 동일 → ads.py·generation_app 은 함수명만 교체.
#   StylePreset(무드) → resolve_style → style_spec 키. 4매체 카피 + 정직성 게이트 포함.
def _platform_copies_safe(product: ProductInfo, style: StylePreset) -> dict[str, dict]:
    """4매체 카피 + 정직성 게이트(core_ingredients 대조로 재료 환각 차단). 실패해도 {} (무해)."""
    try:
        analysis = gpt_service.analyze_menu(product.name)
        core = getattr(analysis, "core_ingredients", None) or None
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

    from .style_specs import resolve_style

    # asset_id 를 먼저 발급 — 이 요청 안의 모든 하위 LLM 호출(gpt_service/judge_service 트레이스)을
    # session_id=asset_id 로 묶는다. /ads/regenerate 는 같은 asset_id 로 rerun_v2 를 호출하므로,
    # Langfuse Sessions 뷰에서 최초 생성 트레이스와 재생성 트레이스가 하나의 세션으로 이어져 보인다.
    asset_id = uuid.uuid4().hex[:12]

    with propagate_attributes(session_id=asset_id):
        # 입력 게이트(P0, 콜드런 배치 실측): 사진 피사체 ≠ 상품명이면 이름 기반 날조(없는 제품 생성)
        #   위험 → 생성 전 차단. 관대한 판정(명백한 무관 사진만 거부), 판정 실패 시 통과.
        gate = gpt_service.verify_photo_subject(image_path, product.name)
        if not gate["match"]:
            seen = f" (사진에는 '{gate['seen']}'이(가) 보여요)" if gate.get("seen") else ""
            raise ValueError(
                f"사진과 상품명('{product.name}')이 서로 달라 보여요.{seen} "
                "상품이 잘 보이는 사진인지 확인해 주세요.")

        # regen 용으로 입력 원본 보존(v2 는 누끼/mask 없음 → 원본 재투입 방식)
        saved = image_service.PROCESSED_DIR / f"{asset_id}_v2input{_P(image_path).suffix}"
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(image_path, saved)

        # ⚠️ 결과는 서빙 디렉토리(RESULTS_DIR, 절대경로)에 저장 — process_ad 기본 output_dir 은
        #   상대경로("backend/results/ai/route")라 uvicorn CWD(backend/)에서 backend/backend/... 로 풀려
        #   /ads/image/{filename} 서빙이 404 남(실측 2026-07-10). 절대경로로 고정.
        # ⚠️ 입력을 원본이 아니라 asset_id 로 이름 지은 saved(고유) 로 넣는다(실측 2026-07-12):
        #   출력 파일명은 입력 stem 기반 → 같은 업로드를 다시 생성/스타일변경하면 URL 동일 → 브라우저가
        #   캐시된 옛 이미지를 보여줘 "스타일 바꿔도 똑같이 나옴". saved(매 생성 고유) 로 넣으면 URL도 고유.
        # Best-of-N: env BEST_OF_N 로 배포에서 제어(기본 1=기존 1샷). steps 도 env BEST_OF_STEPS.
        import os as _os
        _bon = max(1, int(_os.environ.get("BEST_OF_N", "1") or "1"))
        _steps = int(_os.environ["BEST_OF_STEPS"]) if _os.environ.get("BEST_OF_STEPS") else None
        r = process_ad(str(saved), product.name, poster=poster,
                       style=resolve_style(style.value),
                       output_dir=str(image_service.RESULTS_DIR),
                       best_of=_bon, steps=_steps)
        return GenerationOutput(
            final_image_path=r.final_image_path, asset_id=asset_id, seed=seed or 0, style=style,
            copy_text=r.copy_text, platform_copies=_platform_copies_safe(product, style),
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
    """v2 재생성 — 보존한 입력 원본으로 process_ad 재실행."""
    import glob

    from .style_specs import resolve_style

    if not is_valid_asset_id(asset_id):
        raise ValueError(f"잘못된 asset_id 형식: {asset_id!r}")

    # session_id=asset_id — 최초 생성(run_from_upload_v2)이 같은 asset_id 로 연 세션에 합류.
    with propagate_attributes(session_id=asset_id):
        cands = glob.glob(str(image_service.PROCESSED_DIR / f"{asset_id}_v2input.*"))
        if not cands:
            raise FileNotFoundError(f"v2 입력 원본 없음: asset_id={asset_id}")
        r = process_ad(cands[0], product.name, poster=poster, style=resolve_style(style.value),
                       output_dir=str(image_service.RESULTS_DIR))
        return GenerationOutput(
            final_image_path=r.final_image_path, asset_id=asset_id, seed=0, style=style,
            copy_text=r.copy_text, platform_copies=_platform_copies_safe(product, style),
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
    best_of: int = 1,
    steps: Optional[int] = None,
) -> ProcessedAd:
    """사진 + 상품명 → 자동 라우팅(또는 스타일 씬) 리터치 + 문구 + 포스터. 사용자는 이름만 입력.

    knob(0~1): 공통 강도 슬라이더. layout: overlay|panel(포스터).
    style: 디자인시스템 스타일 키(editorial/realism/pop/…) 지정 시 style_gen 씬 생성 경로,
           None 이면 기존 이름기반 A/B/C 자동 라우팅(하위호환). GPU 필요.
    log: True 면 RunLogger 로 원장 적재 + NIMA 심미 기록(Phase 5 플라이휠 축적). 실패해도 결과엔 영향 없음.
    """
    import time

    from . import router
    from .overlay_service import apply_food_poster

    t0 = time.time()

    # 스타일 지정 시: style_gen 씬 생성(정체성 보존 편집), 아니면 기존 이름기반 라우팅
    if style:
        from . import style_gen
        # subject_en 은 analyze_menu 로 산출(한글→영문, CLIP 함정 회피)
        analysis = gpt_service.analyze_menu(name)
        subject_en = getattr(analysis, "subject_en", None) or name
        domain = getattr(analysis, "domain", "food")
        food_mode = getattr(analysis, "food_mode", None)
        style_domain = "drink" if food_mode == "cafe" else domain
        # 포맷 자동감지(STYLE_SYSTEM v2): style 은 '무드', 포맷은 콘텐츠로 결정.
        #   STY-003~005 이후 사물도 선택 무드를 적용하되, StylePlan이 상품은 고정하고 배경·조명만 바꾼다.
        #   여름음료 pop_split·케이크 cross_section 은 특수 조판/게이트 필요 → 당분간 명시 호출 유지.
        effective_style = style
        # Best-of-N: N시드 생성 → 선별기로 top 선택. best_of=1 이면 기존 1샷.
        #   ⚠️ BON-002 기각(2026-07-13): NIMA 는 이미-좋은 이미지(5~6점대)를 변별 못 해 Best-of-N 무효.
        #   선별기는 SELECTOR env 로 교체(nima 기본|gpt=구조화 저지|both=둘 다 로깅해 클린 비교).
        n = max(1, best_of)
        seeds = [7, 42, 123, 2024, 88, 512][:n]
        cands = [style_gen.generate_scene(image_path, effective_style, subject_en,
                                          output_dir=output_dir, seed=s, steps=steps,
                                          domain=style_domain) for s in seeds]
        final = _select_best(cands, original_path=image_path)
        sel = os.environ.get("SELECTOR", "nima")
        engine = f"style:{effective_style}" + (f"·bestof{n}:{sel}" if n > 1 else "")
    else:
        route = router.process_input(image_path, name, knob=knob, output_dir=output_dir)
        final = route.output_path
        subject_en, domain, engine = route.subject_en, route.domain, route.engine

    # 문구 (FR-09) — 상품명 + 리터치 이미지 기반. 톤은 EDITORIAL 기본.
    product = ProductInfo(name=name)
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
        final = apply_food_poster(final, headline, subcopy, layout=layout, style_key=style)

    # 심미 점수(플라이휠 라벨) — 실패 무해
    aesthetic = None
    try:
        from ..harness.metrics import aesthetic_primary
        aesthetic = aesthetic_primary(final)
    except Exception:
        pass

    result = ProcessedAd(
        final_image_path=final, domain=domain, engine=engine,
        subject_en=subject_en, copy_text=copy.copy_text, poster=poster,
        seconds=round(time.time() - t0, 2), style=style, aesthetic=aesthetic,
    )

    # 원장 적재(재생성 불가 결과를 학습자산으로 — DIRECTION D-플라이휠)
    if log:
        try:
            from ..harness.run_logger import RunLogger
            with RunLogger(phase="P6", mode=domain, engine=engine, input=image_path,
                           params={"name": name, "style": style, "subject_en": subject_en,
                                   "layout": layout}) as run:
                run.set_output(final)
                if aesthetic is not None:
                    run.add_metric("aesthetic", aesthetic)
        except Exception:
            pass

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
