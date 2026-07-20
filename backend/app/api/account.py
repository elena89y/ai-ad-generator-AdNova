import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    get_current_auth_provider,
    get_current_user,
    hash_password,
    verify_password,
)
from app.crud.account import delete_user_account, update_user_password
from app.database.admin_models import AdminAccount
from app.database.connection import get_db
from app.database.models import User
from app.schemas.account import (
    AccountDeleteRequest,
    AccountMessageResponse,
    PasswordChangeRequest,
)
from app.schemas.auth import UserResponse
from app.services import image_service


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/account", tags=["Account"])
SOCIAL_AUTH_PROVIDERS = {"google", "kakao", "naver"}


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
