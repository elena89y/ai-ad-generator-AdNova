from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
IMAGE_FORMAT_BY_EXTENSION = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}
IMAGE_FORMAT_BY_CONTENT_TYPE = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
MAX_IMAGE_SIZE_MB = settings.MAX_IMAGE_SIZE_MB
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024

# 업로드 정규화(2026-07-21, 연정님 리포트 대응): 원본을 영구 보관하지 않는다 —
#   저장·생성에 쓰는 건 장변 상한으로 축소한 정규화본뿐(폰 사진 ~12MB → ~1MB).
#   재생성(/ads/regenerate)은 이 정규화본을 다시 읽으므로 계약 불변, 오히려 재현성↑
#   (생성 입력과 보관본이 동일). 파이프라인은 어차피 1024² 내부 처리라 품질 손실 없음.
NORMALIZE_MAX_SIDE = 2048
_JPEG_QUALITY = 90


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


def validate_image_content(
    content: bytes,
    *,
    suffix: str,
    content_type: str,
) -> None:
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

    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
            detected_format = (image.format or "").upper()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="올바른 이미지 파일이 아닙니다.",
        ) from exc

    if (
        detected_format != IMAGE_FORMAT_BY_EXTENSION[suffix]
        or detected_format != IMAGE_FORMAT_BY_CONTENT_TYPE[content_type]
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="파일 확장자와 실제 이미지 형식이 일치하지 않습니다.",
        )


def normalize_image_content(content: bytes) -> tuple[bytes, str, str]:
    """검증 통과한 이미지를 보관용으로 정규화 — (bytes, suffix, content_type) 반환.

    - EXIF 회전 보정(폰 세로 사진이 눕는 문제)
    - 장변 NORMALIZE_MAX_SIDE 초과 시 축소
    - 알파 없는 이미지는 JPEG 재인코딩(용량 1/10 수준), 알파 있으면 PNG 유지(누끼 입력 보호)
    실패 시 원본 그대로 반환(정규화는 최적화지 게이트가 아니다).
    """
    try:
        with Image.open(BytesIO(content)) as im:
            im = ImageOps.exif_transpose(im)
            has_alpha = im.mode in ("RGBA", "LA") or (
                im.mode == "P" and "transparency" in im.info)
            if max(im.size) > NORMALIZE_MAX_SIDE:
                im.thumbnail((NORMALIZE_MAX_SIDE, NORMALIZE_MAX_SIDE), Image.LANCZOS)
            buf = BytesIO()
            if has_alpha:
                im.save(buf, "PNG")
                return buf.getvalue(), ".png", "image/png"
            im.convert("RGB").save(buf, "JPEG", quality=_JPEG_QUALITY)
            return buf.getvalue(), ".jpg", "image/jpeg"
    except Exception:  # noqa: BLE001 — 검증은 이미 통과, 정규화 실패는 원본 폴백
        return content, "", ""


def _finalize(original_filename: str, suffix: str, content: bytes,
              content_type: str) -> tuple[str, str, bytes]:
    validate_image_content(content, suffix=suffix, content_type=content_type)
    normalized, new_suffix, _ = normalize_image_content(content)
    return original_filename, (new_suffix or suffix), normalized


async def read_image_upload_file(file: UploadFile) -> tuple[str, str, bytes]:
    original_filename = get_safe_filename(file.filename)
    suffix = validate_image_metadata(original_filename, file.content_type)
    content = await file.read(MAX_IMAGE_SIZE_BYTES + 1)
    return _finalize(original_filename, suffix, content, file.content_type or "")


def read_image_upload_file_sync(file: UploadFile) -> tuple[str, str, bytes]:
    original_filename = get_safe_filename(file.filename)
    suffix = validate_image_metadata(original_filename, file.content_type)
    content = file.file.read(MAX_IMAGE_SIZE_BYTES + 1)
    return _finalize(original_filename, suffix, content, file.content_type or "")
