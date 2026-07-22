from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from fastapi.security import HTTPAuthorizationCredentials

from app.core.security import bearer_scheme, decode_access_token
from app.database.admin_models import AdminUser
from app.database.connection import get_admin_db


ADMIN_ROLES = {"operator", "super_admin"}


def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    admin_db: Session = Depends(get_admin_db),
) -> AdminUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="관리자 로그인이 필요합니다.",
        )

    payload = decode_access_token(credentials.credentials)
    admin_id = payload.get("sub") if payload else None
    if not payload or payload.get("token_type") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 인증 토큰이 필요합니다.",
        )

    try:
        parsed_admin_id = int(admin_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="관리자 인증에 실패했습니다.",
        ) from exc

    admin_account = (
        admin_db.query(AdminUser)
        .filter(
            AdminUser.id == parsed_admin_id,
            AdminUser.is_active.is_(True),
        )
        .first()
    )
    if admin_account is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다.",
        )
    if admin_account.role not in ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="유효하지 않은 관리자 역할입니다.",
        )

    return admin_account


def get_current_super_admin(
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminUser:
    if current_admin.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="최고 관리자 권한이 필요합니다.",
        )
    return current_admin
