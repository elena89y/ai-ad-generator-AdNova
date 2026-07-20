from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user
from app.crud.image import create_image
from app.database.connection import get_db
from app.database.models import User
from app.schemas.image import ImageUploadResponse
from app.services.upload_validation import read_image_upload_file


router = APIRouter(prefix="/images", tags=["images"])

UPLOAD_DIR = Path(settings.UPLOAD_DIR)


@router.post(
    "/upload",
    response_model=ImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImageUploadResponse:
    original_filename, suffix, content = await read_image_upload_file(file)

    stored_filename = f"{uuid4().hex}{suffix}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    upload_path = UPLOAD_DIR / stored_filename
    image_url = f"/uploads/{stored_filename}"

    try:
        upload_path.write_bytes(content)
        image = create_image(
            db,
            user_id=current_user.id,
            image_type="upload",
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_path=str(upload_path),
            image_url=image_url,
            # 업로드 정규화(2026-07-21) 후에는 저장 바이트의 실제 형식이 원본과 다를 수 있어
            # 확장자 기준으로 기록한다 (upload_validation.normalize_image_content 참조)
            content_type={".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                          ".webp": "image/webp"}.get(suffix, file.content_type),
            file_size=len(content),
        )
    except Exception as exc:
        if upload_path.exists():
            upload_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="이미지 업로드 중 오류가 발생했습니다.",
        ) from exc
    finally:
        await file.close()

    return ImageUploadResponse(
        image_id=image.id,
        filename=original_filename,
        content_type=image.content_type or "",
        image_url=image.image_url or image_url,
    )
