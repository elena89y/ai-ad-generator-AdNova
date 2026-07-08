from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE_MB = settings.MAX_IMAGE_SIZE_MB
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024


def get_safe_filename(filename: str | None) -> str:
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="파일 이름이 비어 있습니다.",
        )
    return Path(filename).name


def validate_image_metadata(filename: str, content_type: str | None) -> str:
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


def validate_image_content(content: bytes) -> None:
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


async def read_image_upload_file(file: UploadFile) -> tuple[str, str, bytes]:
    original_filename = get_safe_filename(file.filename)
    suffix = validate_image_metadata(original_filename, file.content_type)
    content = await file.read(MAX_IMAGE_SIZE_BYTES + 1)
    validate_image_content(content)
    return original_filename, suffix, content


def read_image_upload_file_sync(file: UploadFile) -> tuple[str, str, bytes]:
    original_filename = get_safe_filename(file.filename)
    suffix = validate_image_metadata(original_filename, file.content_type)
    content = file.file.read(MAX_IMAGE_SIZE_BYTES + 1)
    validate_image_content(content)
    return original_filename, suffix, content
