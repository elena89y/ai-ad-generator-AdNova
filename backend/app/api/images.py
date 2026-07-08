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


router = APIRouter(prefix="/images", tags=["images"])

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
UPLOAD_DIR = Path(settings.UPLOAD_DIR)
MAX_IMAGE_SIZE_MB = settings.MAX_IMAGE_SIZE_MB
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024


def _get_safe_filename(filename: str | None) -> str:
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="파일 이름이 비어 있습니다.",
        )
    return Path(filename).name


def _validate_image_file(filename: str, content_type: str | None) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="jpg, jpeg, png, webp 파일만 업로드할 수 있습니다.",
        )

    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="지원하지 않는 이미지 형식입니다.",
        )

    return suffix


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
    original_filename = _get_safe_filename(file.filename)
    suffix = _validate_image_file(original_filename, file.content_type)

    content = await file.read(MAX_IMAGE_SIZE_BYTES + 1)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="빈 이미지 파일은 업로드할 수 없습니다.",
        )

    if len(content) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"이미지 파일은 {MAX_IMAGE_SIZE_MB}MB 이하만 업로드할 수 있습니다.",
        )

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
            content_type=file.content_type,
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
