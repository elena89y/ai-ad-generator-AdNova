from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings

try:
    from pillow_heif import register_heif_opener
except ImportError:
    pass
else:
    register_heif_opener()

SUPPORTED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "HEIF", "HEIC"}
NORMALIZED_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}
MAX_IMAGE_SIZE_MB = settings.MAX_IMAGE_SIZE_MB
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024

# 업로드 정규화(2026-07-21, 연정님 용량 리포트 대응 — 담당 확인: 한의정):
#   [경위] 원본 영구 보관은 초기 설계부터 있던 것 — '이 이미지로 광고 재생성'(FR-12,
#   /ads/regenerate)이 저장된 입력 파일을 다시 읽는 구조라 필요했다. 그러나 폰 원본
#   (5~12MB)이 용량 한도에 걸리고 디스크에 무한 누적되는 문제로 **원본 비보관**으로 전환.
#   [현재] 업로드 즉시 장변 상한 축소·재인코딩한 정규화본(~1MB)만 저장한다.
#   재생성은 이 정규화본을 읽으므로 기능은 유지된다(생성 입력=보관본이라 재현성도 개선).
#   파이프라인은 어차피 1024² 내부 처리라 품질 손실 없음.
NORMALIZE_MAX_SIDE = 2048
_JPEG_QUALITY = 90


def get_safe_filename(filename: str | None) -> str:
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="파일 이름이 비어 있습니다.",
        )
    return Path(filename).name


def validate_image_content(
    content: bytes,
    *,
    suffix: str | None = None,
    content_type: str | None = None,
) -> str:
    """파일명/MIME 대신 실제 이미지 바이트를 기준으로 검증한다."""
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
        with Image.open(BytesIO(content)) as image:
            detected_format = (image.format or "").upper()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="올바른 이미지 파일이 아닙니다.",
        ) from exc

    if detected_format not in SUPPORTED_IMAGE_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="JPG, PNG, WebP, HEIC 이미지 파일만 업로드할 수 있습니다.",
        )

    return detected_format


def normalize_image_content(content: bytes) -> tuple[bytes, str, str]:
    """검증 통과한 이미지를 보관용으로 정규화 — (bytes, suffix, content_type) 반환.

    - EXIF 회전 보정(폰 세로 사진이 눕는 문제)
    - 장변 NORMALIZE_MAX_SIDE 초과 시 축소
    - 알파 없는 이미지는 JPEG 재인코딩(용량 1/10 수준), 알파 있으면 PNG 유지(누끼 입력 보호)
    실제 바이트 형식과 무관하게 서버 보관본은 JPG 또는 PNG로 통일한다.
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
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미지를 변환할 수 없습니다.",
        ) from exc


def normalized_content_type_for_suffix(suffix: str) -> str:
    return NORMALIZED_CONTENT_TYPES[suffix]


def _finalize(original_filename: str, content: bytes) -> tuple[str, str, bytes]:
    validate_image_content(content)
    normalized, suffix, _ = normalize_image_content(content)
    return original_filename, suffix, normalized


async def read_image_upload_file(file: UploadFile) -> tuple[str, str, bytes]:
    original_filename = get_safe_filename(file.filename)
    content = await file.read(MAX_IMAGE_SIZE_BYTES + 1)
    return _finalize(original_filename, content)


def read_image_upload_file_sync(file: UploadFile) -> tuple[str, str, bytes]:
    original_filename = get_safe_filename(file.filename)
    content = file.file.read(MAX_IMAGE_SIZE_BYTES + 1)
    return _finalize(original_filename, content)
