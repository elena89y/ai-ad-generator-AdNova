import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    get_current_auth_provider,
    get_current_user,
    hash_password,
    verify_password,
)
from app.crud.account import (
    delete_user_account,
    get_notification_settings,
    update_notification_settings,
    update_user_password,
)
from app.crud.image import create_image
from app.database.admin_models import AdminAccount
from app.database.connection import get_db
from app.database.models import Image, User
from app.schemas.account import (
    AccountDeleteRequest,
    AccountMessageResponse,
    NotificationSettingsResponse,
    NotificationSettingsUpdateRequest,
    PasswordChangeRequest,
    ProfileImageResponse,
)
from app.schemas.auth import UserResponse
from app.schemas.image import ImageUploadResponse
from app.services import image_service
from app.services.upload_validation import read_image_upload_file


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/account", tags=["Account"])
SOCIAL_AUTH_PROVIDERS = {"google", "kakao", "naver"}


def _notification_settings_response(settings) -> NotificationSettingsResponse:
    if settings is None:
        return NotificationSettingsResponse(
            ad_generation_complete_email=True,
            credit_depletion_alert=True,
            marketing_updates=False,
        )
    return NotificationSettingsResponse(
        ad_generation_complete_email=settings.ad_generation_complete_email,
        credit_depletion_alert=settings.credit_depletion_alert,
        marketing_updates=settings.marketing_updates,
    )


@router.get("/me", response_model=UserResponse)
def read_current_user(
    current_user: User = Depends(get_current_user),
    auth_provider: str = Depends(get_current_auth_provider),
) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        name=current_user.name,
        business_name=current_user.business_name,
        business_type=current_user.business_type,
        auth_provider=auth_provider,
        is_active=current_user.is_active,
    )


def _profile_image_url(image_id: int) -> str:
    return f"/api/account/profile-image/{image_id}"


@router.get("/profile-image", response_model=ProfileImageResponse)
def read_profile_image(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProfileImageResponse:
    image = (
        db.query(Image)
        .filter(Image.user_id == current_user.id, Image.image_type == "profile")
        .order_by(Image.id.desc())
        .first()
    )
    return ProfileImageResponse(image_url=_profile_image_url(image.id) if image else None)


@router.get("/profile-image/{image_id}")
def read_profile_image_file(
    image_id: int,
    db: Session = Depends(get_db),
) -> FileResponse:
    image = (
        db.query(Image)
        .filter(Image.id == image_id, Image.image_type == "profile")
        .first()
    )
    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    file_path = Path(image.file_path).resolve() if image and image.file_path else None
    if (
        image is None
        or file_path is None
        or upload_dir not in file_path.parents
        or not file_path.is_file()
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="프로필 사진이 없습니다.")

    return FileResponse(file_path, media_type=image.content_type)


@router.post(
    "/profile-image",
    response_model=ImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_profile_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImageUploadResponse:
    original_filename, suffix, content = await read_image_upload_file(file)
    upload_dir = Path(settings.UPLOAD_DIR)
    stored_filename = f"profile_{current_user.id}_{uuid4().hex}{suffix}"
    upload_path = upload_dir / stored_filename

    try:
        upload_dir.mkdir(parents=True, exist_ok=True)
        upload_path.write_bytes(content)

        previous_images = (
            db.query(Image)
            .filter(Image.user_id == current_user.id, Image.image_type == "profile")
            .all()
        )
        previous_file_paths = [
            previous_image.file_path
            for previous_image in previous_images
            if previous_image.file_path
        ]
        image = create_image(
            db,
            user_id=current_user.id,
            image_type="profile",
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_path=str(upload_path),
            content_type=file.content_type,
            file_size=len(content),
            commit=False,
        )
        image.image_url = _profile_image_url(image.id)
        for previous_image in previous_images:
            db.delete(previous_image)
        db.commit()
        db.refresh(image)
    except Exception as exc:
        db.rollback()
        upload_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="프로필 사진 저장 중 오류가 발생했습니다.",
        ) from exc
    finally:
        await file.close()

    _delete_account_image_files(previous_file_paths)
    return ImageUploadResponse(
        image_id=image.id,
        filename=original_filename,
        content_type=image.content_type or "",
        image_url=image.image_url or _profile_image_url(image.id),
    )


@router.get("/notifications", response_model=NotificationSettingsResponse)
def read_notification_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationSettingsResponse:
    settings = get_notification_settings(db, current_user.id)
    return _notification_settings_response(settings)


@router.patch("/notifications", response_model=NotificationSettingsResponse)
def patch_notification_settings(
    request: NotificationSettingsUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationSettingsResponse:
    updates = request.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="변경할 알림 설정이 없습니다.",
        )
    settings = update_notification_settings(db, current_user.id, updates)
    return _notification_settings_response(settings)


def _delete_account_image_files(file_paths: list[str]) -> None:
    allowed_roots = (
        Path(settings.UPLOAD_DIR).resolve(),
        image_service.RESULTS_DIR.resolve(),
    )

    for file_path in file_paths:
        path = Path(file_path).resolve()
        if not any(root in path.parents for root in allowed_roots):
            logger.warning("계정 삭제 파일 경로가 허용 폴더 밖에 있어 건너뜁니다: %s", path)
            continue

        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.exception("계정 삭제 후 이미지 파일을 지우지 못했습니다: %s", path)


@router.post("/password", response_model=AccountMessageResponse)
def change_password(
    request: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    auth_provider: str = Depends(get_current_auth_provider),
) -> AccountMessageResponse:
    if auth_provider in SOCIAL_AUTH_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="소셜 로그인 계정의 비밀번호는 해당 서비스에서 관리됩니다.",
        )

    if not verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="현재 비밀번호가 올바르지 않습니다.",
        )

    if verify_password(request.new_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="새 비밀번호는 현재 비밀번호와 다르게 입력해주세요.",
        )

    update_user_password(db, current_user, hash_password(request.new_password))
    return AccountMessageResponse(message="비밀번호가 변경되었습니다.")


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    request: AccountDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    auth_provider: str = Depends(get_current_auth_provider),
) -> None:
    admin_account = (
        db.query(AdminAccount.id)
        .filter(AdminAccount.user_id == current_user.id)
        .first()
    )
    if admin_account is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="관리자 계정은 일반 회원탈퇴를 사용할 수 없습니다.",
        )

    is_social_login = auth_provider in SOCIAL_AUTH_PROVIDERS
    if not is_social_login and (
        not request.current_password
        or not verify_password(request.current_password, current_user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="현재 비밀번호가 올바르지 않습니다.",
        )

    image_paths = delete_user_account(db, current_user)
    _delete_account_image_files(image_paths)
