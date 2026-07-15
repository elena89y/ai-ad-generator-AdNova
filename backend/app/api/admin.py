from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.admin_security import get_current_admin
from app.core.security import get_current_user
from app.crud.admin import (
    count_advertisements_by_user,
    get_user_for_admin,
    list_users_for_admin,
    update_user_active_status,
)
from app.database.admin_models import AdminAccount
from app.database.billing_models import Subscription
from app.database.connection import get_db
from app.database.models import User
from app.schemas.admin import (
    AdminMeResponse,
    AdminUserDetailResponse,
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserStatusUpdateRequest,
)


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/me", response_model=AdminMeResponse)
def read_admin_me(
    current_user: User = Depends(get_current_user),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminMeResponse:
    return AdminMeResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=current_admin.role,
    )


def _build_admin_user_response(
    user: User,
    subscription: Subscription | None,
) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        name=user.name,
        business_name=user.business_name,
        is_active=user.is_active,
        created_at=user.created_at,
        plan=subscription.plan if subscription else "free",
        subscription_status=subscription.status if subscription else None,
    )


@router.get("/users", response_model=AdminUserListResponse)
def read_admin_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None, min_length=1, max_length=100),
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminUserListResponse:
    del current_admin
    total, rows = list_users_for_admin(
        db,
        skip=skip,
        limit=limit,
        search=search,
    )
    return AdminUserListResponse(
        total=total,
        items=[_build_admin_user_response(user, subscription) for user, subscription in rows],
    )


@router.get("/users/{user_id}", response_model=AdminUserDetailResponse)
def read_admin_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminUserDetailResponse:
    del current_admin
    row = get_user_for_admin(db, user_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    user, subscription = row
    response = _build_admin_user_response(user, subscription)
    return AdminUserDetailResponse(
        **response.model_dump(),
        business_type=user.business_type,
        updated_at=user.updated_at,
        advertisement_count=count_advertisements_by_user(db, user.id),
    )


@router.patch("/users/{user_id}/status", response_model=AdminUserResponse)
def update_admin_user_status(
    user_id: int,
    request: AdminUserStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminUserResponse:
    if user_id == current_admin.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="현재 로그인한 관리자 계정의 상태는 변경할 수 없습니다.",
        )

    target_admin = (
        db.query(AdminAccount).filter(AdminAccount.user_id == user_id).first()
    )
    if target_admin is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 계정 상태는 이 기능으로 변경할 수 없습니다.",
        )

    row = get_user_for_admin(db, user_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    user, subscription = row
    update_user_active_status(db, user, is_active=request.is_active)
    return _build_admin_user_response(user, subscription)
