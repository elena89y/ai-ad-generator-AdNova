"""광고 스타일/생성 API 라우터.

담당: 한의정
엔드포인트:
  POST /ads/style      — 스타일 결정 2경로 (FR-05)
  POST /ads/generate   — 통합 파이프라인: 전처리→생성→조화→문구(→포스터) (FR-06~09)
  POST /ads/regenerate — 동일 입력 · 새 seed 재생성 (FR-12)
  GET  /ads/image/{filename} — 생성 결과 이미지 서빙 (프론트 표시·다운로드용)

프론트(frontend/app.py) 연동 스펙에 맞춘 구성. DB 이력 저장(FR-19)은
advertisements CRUD(김범수님) 연동 시 추가 예정.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.security import get_current_user
from ..crud.advertisement import create_advertisement
from ..crud.history import create_history
from ..crud.image import create_image, get_image_by_id
from ..database.connection import get_db
from ..database.models import User
from ..schemas.ads import (
    GenerateAdResponse,
    ProductInfo,
    RegenerateAdRequest,
    StylePreset,
    StyleRequest,
    StyleResponse,
)
from ..services import (
    generation_client,
    generation_service,
    gpt_service,
    image_service,
    style_service,
)
from ..services.prompt_service import build_image_prompt
from ..services.upload_validation import read_image_upload_file_sync

router = APIRouter(prefix="/ads", tags=["ads"])

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"


def _to_response(out: generation_service.GenerationOutput) -> GenerateAdResponse:
    """순수 생성 결과 → API 응답. image_url 은 프리픽스 포함 서빙 경로로 통일."""
    return GenerateAdResponse(
        asset_id=out.asset_id,
        seed=out.seed,
        style=out.style,
        copy_text=out.copy_text,
        image_url=f"{settings.API_PREFIX}/ads/image/{Path(out.final_image_path).name}",
        poster=out.poster,
        generate_seconds=out.generate_seconds,
        harmonize_seconds=out.harmonize_seconds,
    )


@router.post("/style", response_model=StyleResponse)
def decide_style(
    req: StyleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StyleResponse:
    """스타일 결정 2경로 진입점 (경로1: 추천 / 경로2: 자유 텍스트)."""
    try:
        image_path: str | None = None
        if req.image_id is not None:
            row = get_image_by_id(db, req.image_id)
            if row is None or not row.file_path or not Path(row.file_path).is_file():
                raise HTTPException(status_code=404, detail=f"업로드 이미지 없음: image_id={req.image_id}")
            if row.user_id != current_user.id:
                raise HTTPException(status_code=403, detail="이미지 소유자만 스타일을 분석할 수 있습니다")
            image_path = row.file_path

        return style_service.decide_style(req, image_path=image_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/generate", response_model=GenerateAdResponse)
def generate_ad(
    image: Optional[UploadFile] = File(None),
    image_id: Optional[int] = Form(None),
    product_name: str = Form(...),
    product_description: str = Form(""),
    style: StylePreset = Form(...),
    use_vision: bool = Form(False),
    poster: bool = Form(False),
    seed: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GenerateAdResponse:
    """통합 광고 생성: 입력 → 전처리 → 배경 생성+조화 → 문구 (→ 포스터 오버레이).

    이미지 입력 2방식 (둘 중 하나 필수):
      - image    : 직접 파일 업로드 (단독 호출)
      - image_id : /images/upload (PR #14) 로 업로드된 DB 이미지 참조
    실행 위치: settings.GENERATION_SERVICE_URL 있으면 GPU 서비스 HTTP 호출(배포 B),
      없으면 로컬 실행(모놀리식). warm 약 20초 — 프론트 timeout 여유(60s+) 필요.
    """
    current_user_id = current_user.id
    input_image_id: Optional[int] = None
    request_data = json.dumps(
        {
            "image_id": image_id,
            "filename": image.filename if image else None,
            "product_name": product_name,
            "product_description": product_description,
            "style": style.value,
            "use_vision": use_vision,
            "poster": poster,
            "seed": seed,
        },
        ensure_ascii=False,
    )

    if image_id is not None:
        row = get_image_by_id(db, image_id)
        if row is None or not row.file_path or not Path(row.file_path).is_file():
            raise HTTPException(status_code=404, detail=f"업로드 이미지 없음: image_id={image_id}")
        if row.user_id != current_user_id:
            raise HTTPException(status_code=403, detail="이미지 소유자만 광고를 생성할 수 있습니다")
        src_path = Path(row.file_path)
        input_image_id = row.id
    elif image is not None:
        _, suffix, content = read_image_upload_file_sync(image)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        src_path = UPLOAD_DIR / f"{uuid.uuid4().hex[:12]}{suffix}"
        src_path.write_bytes(content)
    else:
        raise HTTPException(status_code=400, detail="image 파일 또는 image_id 중 하나가 필요합니다")

    product = ProductInfo(name=product_name, description=product_description or None)
    prompt = build_image_prompt(product, style)
    prompt_for_db = json.dumps(
        {"positive": prompt.positive, "negative": prompt.negative},
        ensure_ascii=False,
    )

    try:
        if generation_client.is_remote():
            result = generation_client.generate_remote(
                str(src_path), product, style, seed, use_vision, poster
            )
        else:
            out = generation_service.run_from_upload(
                str(src_path), product, style, seed, use_vision, poster
            )
            result = _to_response(out)

        advertisement = create_advertisement(
            db,
            user_id=current_user_id,
            input_image_id=input_image_id,
            title=product_name,
            ad_type="poster" if poster else "image",
            prompt=prompt_for_db,
            generated_text=result.copy_text,
            style=style.value,
            status="completed",
        )
        create_history(
            db,
            user_id=current_user_id,
            advertisement_id=advertisement.id,
            action_type="ads.generate",
            status="completed",
            request_data=request_data,
            response_data=json.dumps(result.model_dump(mode="json"), ensure_ascii=False),
        )
        return result
    except ValueError as e:
        create_history(
            db,
            user_id=current_user_id,
            action_type="ads.generate",
            status="failed",
            request_data=request_data,
            error_message=str(e),
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        db.rollback()
        create_history(
            db,
            user_id=current_user_id,
            action_type="ads.generate",
            status="failed",
            request_data=request_data,
            error_message=str(e),
        )
        raise HTTPException(status_code=500, detail=f"광고 생성 실패: {e}") from e


@router.post("/regenerate", response_model=GenerateAdResponse)
def regenerate_ad(req: RegenerateAdRequest) -> GenerateAdResponse:
    """FR-12: 기존 전처리 산출물 재사용, 새 seed 로 재생성 (전처리 생략 → 더 빠름)."""
    if not generation_service.is_valid_asset_id(req.asset_id):
        raise HTTPException(status_code=400, detail=f"잘못된 asset_id 형식: {req.asset_id}")

    product = ProductInfo(name=req.product_name, description=req.product_description)
    try:
        if generation_client.is_remote():
            return generation_client.regenerate_remote(req.model_dump())
        out = generation_service.rerun(
            req.asset_id, product, req.style, req.prev_seed, req.use_vision, req.poster
        )
        return _to_response(out)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"재생성 실패: {e}") from e


@router.get("/image/{filename}")
def get_result_image(filename: str) -> FileResponse:
    """생성 결과 이미지 서빙 (backend/results/ai/ 한정, 경로 탈출 차단)."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="잘못된 파일명")
    path = image_service.RESULTS_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="이미지 없음")
    return FileResponse(path, media_type="image/png")
