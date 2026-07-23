"""독립 생성 서비스 (GPU VM 전용) — 담당: 한의정.

배포 구조 B: 웹 백엔드(Docker, CPU)와 분리된 GPU 생성 서비스.
  · DB·auth 없음 — 순수 생성만
  · 웹 백엔드가 generation_client 로 HTTP 호출
  · GPU VM 에서: uvicorn app.generation_app:app --host 127.0.0.1 --port 8100 --workers 1

엔드포인트:
  POST /generate      — 이미지 파일 + 파라미터 → 최종 이미지 + 문구
  POST /regenerate    — asset_id 재사용 + 새 seed
  GET  /result/{name} — 생성 결과 이미지 서빙 (웹 백엔드가 다운로드)
  GET  /health
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# ⚠️ 독립 프로세스라 config(load_dotenv) 를 거치지 않음 → .env 를 명시적으로 로드.
# 안 하면 OPENAI_API_KEY 미설정으로 문구 생성 단계에서 500 (실측).
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

from .core.observability import init_langfuse, shutdown_langfuse  # noqa: E402
from .schemas.ads import (  # noqa: E402
    AdPurpose,
    GenerateAdResponse,
    ProductInfo,
    RegenerateAdRequest,
    StylePreset,
)
from .services import generation_service, image_service, kontext_service  # noqa: E402
from .services import pipeline_v5  # noqa: E402
from .services.pipeline_v5.hero import (  # noqa: E402
    DetailCut,
    DetailCutRole,
    hero_from_existing,
)
from .services.pipeline_v5.similarity import (  # noqa: E402
    MAX_STRUCTURE_CORRELATION,
    correlation,
    structure_vector,
)
from scripts.detail_multishot_generate import (  # noqa: E402
    LIFESTYLE_ANGLES,
    SIDE_PROFILE_ANGLES,
    TEXTURE_CLOSEUP_VARIANTS,
    TOP_VIEW_ANGLES,
    lifestyle_prompt,
    side_profile_prompt,
    texture_closeup_prompt,
    top_view_prompt,
)

# 위 load_dotenv() 다음, 서비스 임포트로 인한 첫 OpenAI 호출보다 앞서 초기화.
init_langfuse()

logger = logging.getLogger(__name__)
_STATE = {"status": "starting", "error": None}


def _preload() -> None:
    """Kontext를 워커 프로세스에 상주시킨다. 실패 상태는 journal에 남기고 시작을 중단한다."""
    _STATE.update(status="loading", error=None)
    try:
        kontext_service.preload()
    except Exception as exc:
        _STATE.update(status="error", error=type(exc).__name__)
        logger.exception("Kontext preload 실패")
        raise
    _STATE.update(status="ready", error=None)


@asynccontextmanager
async def lifespan(_app: FastAPI):  # noqa: ANN201
    """모델 준비가 끝난 뒤에만 ASGI startup을 완료한다."""
    try:
        if os.environ.get("PRELOAD_KONTEXT", "1") == "1":
            await asyncio.get_running_loop().run_in_executor(None, _preload)
        else:
            _STATE.update(status="ready", error=None)
        yield
    finally:
        shutdown_langfuse()


def _require_ready() -> None:
    """워커 준비 상태만 확인한다. GPU 직렬화 자체는 kontext_service.acquire_gpu()가 담당한다
    (결정 D-10 — 락을 엔드포인트에서 실제 GPU 사용 지점으로 이동, 합성(CPU)이 Kontext와 병렬 가능)."""
    if _STATE["status"] != "ready":
        raise HTTPException(status_code=503, detail="GPU worker is not ready")


app = FastAPI(title="AdNova Generation Service", version="0.2.0", lifespan=lifespan)

UPLOAD_DIR = Path(image_service.PROCESSED_DIR).parent / "uploads"
ALLOWED_SUFFIX = {".png", ".jpg", ".jpeg", ".webp"}


def _to_response(out: generation_service.GenerationOutput) -> GenerateAdResponse:
    def result_url(path: str | None) -> str | None:
        return f"/result/{Path(path).name}" if path else None

    return GenerateAdResponse(
        asset_id=out.asset_id,
        seed=out.seed,
        style=out.style,
        copy_text=out.copy_text,
        platform_copies=out.platform_copies,
        image_url=f"/result/{Path(out.final_image_path).name}",
        poster=out.poster,
        image_without_typography_url=result_url(getattr(out, "image_without_typography_path", None)),
        image_with_typography_url=result_url(getattr(out, "image_with_typography_path", None)),
        typography_enabled=out.poster,
        typography_layout=getattr(out, "typography_layout", None),
        generate_seconds=out.generate_seconds,
        harmonize_seconds=out.harmonize_seconds,
        # SRV-ROUTE-001 phase2: 원격(GPU 서비스) 경로 — 이게 없으면 원격 배포는 상시 null.
        #   generation_client는 화이트리스트 없이 전 필드 통과(감사 확인)라 이 한 곳이면 충분.
        serving_type=getattr(out, "serving_type", None),
    )


# 상세/카드뉴스 4컷 생성 단계의 시간 예산(초) — GATE-001 각도 재시도가 최악(전 구도 전 변형
#   소진)에서 16회 생성 ≈ 15분까지 부풀어 클라이언트 타임아웃(600s)을 뚫는 사고 실측(2026-07-21,
#   김치찌개 상세페이지 420s 초과 502). 예산 소진 후에는 구도당 1변형만 생성하고 최저상관 채택.
MULTIFORMAT_TIME_BUDGET_S = float(os.getenv("MULTIFORMAT_TIME_BUDGET_S", "300"))


def _generate_with_retry(
    source: str, work_dir: Path, accepted_structures: list, role_label: str,
    prompt_for_variant, variants,
    deadline: float | None = None,
):
    """GATE-001(2026-07-20): 원본이 이미 단순한 구도인 상품(책상 위 마우스, 문어모양 괄사)은
    기본 프롬프트로 편집해도 이미 확정된 다른 컷과 구조적으로 거의 같아 상세페이지 구조-유사도
    게이트에 걸린다(hero 포함 4개 구도 전부에서 실측 재현). 변형을 하나씩 시도해 "지금까지
    확정된 모든 컷"과 비교, 전부와 충분히 달라지는 결과를 찾는다. 전부 실패해도 하드 실패
    대신 가장 덜 유사한(최대 상관계수가 가장 낮은) 결과를 쓴다 — 5장 생성해놓고 전체를
    날리는 것보다 낫다.

    비교 대상을 hero뿐 아니라 accepted_structures 전체로 넓혀도 GPU 생성 횟수(변형 개수)는
    그대로다 — 상관계수 비교는 32x32 흑백 벡터끼리라 사실상 공짜라 늘어나는 비용이 없다.
    반환값은 (경로, 이 컷의 구조 벡터) — 호출부가 다음 구도 비교 대상에 누적해서 넘긴다.
    """
    best_path, best_structure, best_score = None, None, None
    for variant in variants:
        # 예산 가드: 첫 변형은 무조건 생성(컷 자체는 필요), 이후 변형은 데드라인 내에서만.
        if best_path is not None and deadline is not None and time.monotonic() > deadline:
            logger.warning(
                f"{role_label}: 시간 예산 소진 — 남은 변형 생략, 최저상관 결과(corr={best_score:.3f}) 채택")
            return best_path, best_structure
        generated = kontext_service.edit(
            source, prompt_for_variant(variant), steps=12, output_dir=str(work_dir),
        )
        target = work_dir / f"{role_label}_{variant}.png"
        Path(generated).replace(target)
        candidate = structure_vector(target)
        max_score = max((correlation(existing, candidate) for _, existing in accepted_structures), default=0.0)
        if best_score is None or max_score < best_score:
            best_path, best_structure, best_score = str(target), candidate, max_score
        if max_score < MAX_STRUCTURE_CORRELATION:
            logger.info(f"{role_label} variant={variant}: 기존 컷들과 충분히 다름(corr={max_score:.3f})")
            return str(target), candidate
        logger.info(f"{role_label} variant={variant}: 기존 컷과 여전히 유사(corr={max_score:.3f}) → 다음 재시도")
    logger.warning(
        f"{role_label} 전 변형({variants})이 기존 컷과 유사 — 가장 덜 유사한 결과(corr={best_score:.3f})로 진행"
    )
    return best_path, best_structure


# GATE-001: 4개 구도 전부 재시도 대상 — role_prompts_for()의 단발성 프롬프트는 이제
# multiformat 경로에서 안 쓰인다(CLI 스크립트·기본값 조회용으로만 남김).
_ROLE_RETRY_SPECS: dict[DetailCutRole, tuple] = {
    DetailCutRole.TOP_VIEW: (top_view_prompt, TOP_VIEW_ANGLES),
    DetailCutRole.TEXTURE_CLOSEUP: (texture_closeup_prompt, TEXTURE_CLOSEUP_VARIANTS),
    DetailCutRole.SIDE_PROFILE: (side_profile_prompt, SIDE_PROFILE_ANGLES),
    DetailCutRole.LIFESTYLE: (lifestyle_prompt, LIFESTYLE_ANGLES),
}


def _render_multiformat(
    out: generation_service.GenerationOutput,
    product_name: str,
    purpose: AdPurpose,
) -> GenerateAdResponse:
    """히어로 1장과 독립 생성한 4구도를 카드뉴스/상세페이지로 조판한다."""
    source = getattr(out, "image_without_typography_path", None) or out.final_image_path
    work_dir = image_service.RESULTS_DIR / f"{out.asset_id}_{purpose.value}"
    work_dir.mkdir(parents=True, exist_ok=True)
    domain = getattr(out, "domain", "food")
    cuts = [DetailCut(source, DetailCutRole.HERO)]
    accepted_structures = [(DetailCutRole.HERO.value, structure_vector(source))]

    deadline = time.monotonic() + MULTIFORMAT_TIME_BUDGET_S
    for role, (prompt_fn, variants) in _ROLE_RETRY_SPECS.items():
        path, candidate_structure = _generate_with_retry(
            source, work_dir, accepted_structures, role.value,
            lambda variant, fn=prompt_fn: fn(domain, variant), variants,
            deadline=deadline,
        )
        cuts.append(DetailCut(path, role))
        accepted_structures.append((role.value, candidate_structure))

    headline, _, subcopy = out.copy_text.partition("\n")
    hero = hero_from_existing(
        source,
        product_name=product_name,
        headline=headline.strip() or product_name,
        subcopy=subcopy.strip(),
        detail_cuts=tuple(cuts),
        domain=domain,
        # v6-1 F1: 상세 카피 톤·팔레트가 스타일을 따라가도록 배선. StylePreset enum 이면
        # value(문자열 키), style_gen 경로의 문자열 키면 그대로.
        # ⚠️ 잔여 배선: subject_en·core_ingredients 는 GenerationOutput 이 안 실어줌 —
        # 환각 게이트가 관대 통과로 돌아간다. generation_service 확장 시 함께 태울 것.
        style=getattr(out.style, "value", out.style) if out.style else None,
    )
    rendered = pipeline_v5.generate_v5(
        source,
        product_name,
        purpose=purpose,
        hero_asset=hero,
        output_dir=str(work_dir),
    )
    urls = []
    for index, value in enumerate(rendered.outputs, start=1):
        path = Path(value)
        served = image_service.RESULTS_DIR / f"{out.asset_id}_{purpose.value}_{index:02d}{path.suffix}"
        served.write_bytes(path.read_bytes())
        urls.append(f"/result/{served.name}")
    return _to_response(out).model_copy(update={"purpose": purpose, "format_outputs": urls})


@app.get("/health", tags=["Health"])
def health() -> dict[str, object]:
    return {
        "status": "ok" if _STATE["status"] == "ready" else "degraded",
        "service": "generation",
        "worker": _STATE["status"],
        "busy": kontext_service._GPU_LOCK.locked(),
    }


@app.post("/generate", response_model=GenerateAdResponse, tags=["Generation"])
def generate(
    image: UploadFile = File(...),
    product_name: str = Form(...),
    product_description: str = Form(""),
    style: StylePreset = Form(...),
    use_vision: bool = Form(False),
    poster: bool = Form(False),
    seed: Optional[int] = Form(None),
    purpose: AdPurpose = Form(AdPurpose.SNS),
) -> GenerateAdResponse:
    """이미지 파일 → 전처리 → 생성 → 문구 (→ 포스터). GPU 필요."""
    suffix = Path(image.filename or "upload.png").suffix.lower() or ".png"
    if suffix not in ALLOWED_SUFFIX:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 형식: {suffix}")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    src = UPLOAD_DIR / f"{uuid.uuid4().hex[:12]}{suffix}"
    src.write_bytes(image.file.read())

    product = ProductInfo(name=product_name, description=product_description or None)
    _require_ready()
    try:
        multiformat = purpose in (AdPurpose.CARD_NEWS, AdPurpose.DETAIL_PAGE)
        out = generation_service.run_from_upload_v2(
            str(src), product, style, seed, use_vision, False if multiformat else poster
        )
        if multiformat:
            return _render_multiformat(out, product_name, purpose)
    except kontext_service.GpuBusyError as e:
        raise HTTPException(status_code=503, detail="GPU busy - 잠시 후 다시 시도해주세요") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"생성 실패: {e}") from e
    finally:
        src.unlink(missing_ok=True)
    return _to_response(out).model_copy(update={"purpose": purpose})


@app.post("/regenerate", response_model=GenerateAdResponse, tags=["Generation"])
def regenerate(req: RegenerateAdRequest) -> GenerateAdResponse:
    """asset_id 재사용 + 새 seed 재생성 (FR-12)."""
    product = ProductInfo(name=req.product_name, description=req.product_description)
    _require_ready()
    try:
        out = generation_service.rerun_v2(
            req.asset_id, product, req.style, req.prev_seed, req.use_vision, req.poster
        )
    except kontext_service.GpuBusyError as e:
        raise HTTPException(status_code=503, detail="GPU busy - 잠시 후 다시 시도해주세요") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"재생성 실패: {e}") from e
    return _to_response(out)


@app.get("/result/{filename}", tags=["Generation"])
def get_result(filename: str) -> FileResponse:
    """생성 결과 이미지 서빙 (results/ai 한정, 경로 탈출 차단)."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="잘못된 파일명")
    path = image_service.RESULTS_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="이미지 없음")
    return FileResponse(path, media_type="image/png")
