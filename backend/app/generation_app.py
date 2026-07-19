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
from scripts.detail_multishot_generate import ROLE_PROMPTS  # noqa: E402

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
    )


def _render_multiformat(
    out: generation_service.GenerationOutput,
    product_name: str,
    purpose: AdPurpose,
) -> GenerateAdResponse:
    """히어로 1장과 독립 생성한 4구도를 카드뉴스/상세페이지로 조판한다."""
    source = getattr(out, "image_without_typography_path", None) or out.final_image_path
    work_dir = image_service.RESULTS_DIR / f"{out.asset_id}_{purpose.value}"
    work_dir.mkdir(parents=True, exist_ok=True)
    cuts = [DetailCut(source, DetailCutRole.HERO)]
    for role, prompt in ROLE_PROMPTS.items():
        generated = kontext_service.edit(source, prompt, steps=12, output_dir=str(work_dir))
        target = work_dir / f"{role}.png"
        Path(generated).replace(target)
        cuts.append(DetailCut(str(target), DetailCutRole(role)))

    headline, _, subcopy = out.copy_text.partition("\n")
    hero = hero_from_existing(
        source,
        product_name=product_name,
        headline=headline.strip() or product_name,
        subcopy=subcopy.strip(),
        detail_cuts=tuple(cuts),
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
