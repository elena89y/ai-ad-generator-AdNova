from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user
from app.crud.image import create_image
from app.database.connection import get_db
from app.database.models import Image, User
from app.schemas.image import ImageUploadResponse
from app.services.upload_validation import (
    normalized_content_type_for_suffix,
    read_image_upload_file,
)


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

    try:
        upload_path.write_bytes(content)
        image = create_image(
            db,
            user_id=current_user.id,
            image_type="upload",
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_path=str(upload_path),
            content_type=normalized_content_type_for_suffix(suffix),
            file_size=len(content),
            commit=False,
        )
        image.image_url = f"{settings.API_PREFIX}/images/{image.id}"
        db.commit()
        db.refresh(image)
    except Exception as exc:
        db.rollback()
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
        image_url=image.image_url or f"{settings.API_PREFIX}/images/{image.id}",
    )


@router.get("/{image_id}")
def read_uploaded_image(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """로그인한 사용자가 본인 업로드 이미지만 조회한다."""
    image = (
        db.query(Image)
        .filter(
            Image.id == image_id,
            Image.user_id == current_user.id,
            Image.image_type == "upload",
        )
        .first()
    )
    upload_dir = UPLOAD_DIR.resolve()
    file_path = Path(image.file_path).resolve() if image and image.file_path else None
    if (
        image is None
        or file_path is None
        or upload_dir not in file_path.parents
        or not file_path.is_file()
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="업로드 이미지를 찾을 수 없습니다.",
        )

    return FileResponse(file_path, media_type=image.content_type or "application/octet-stream")
