from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.crud.admin import create_admin_login_failure_log
from app.database.connection import get_db
from app.database.admin_models import AdminAccount
from app.database.models import User
from app.schemas.auth import (
    UserCreate,
    UserLogin,
    UserResponse,
    UsernameFindRequest,
    UsernameFindResponse,
)


router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)


def _authenticate_credentials(user_data: UserLogin, db: Session) -> User:
    user = db.query(User).filter(User.username == user_data.username).first()

    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 계정입니다.",
        )

    return user


def _get_admin_account(db: Session, user_id: int) -> AdminAccount | None:
    return db.query(AdminAccount).filter(AdminAccount.user_id == user_id).first()


def _record_admin_login_failure(
    db: Session,
    *,
    username: str,
    reason: str,
    user_id: int | None = None,
) -> None:
    try:
        create_admin_login_failure_log(
            db,
            attempted_username=username,
            user_id=user_id,
            reason=reason,
        )
    except Exception:
        db.rollback()


def _create_login_response(db: Session, user: User) -> dict:
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "auth_provider": "local"},
        expires_delta=access_token_expires,
    )
    admin_account = _get_admin_account(db, user.id)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "name": user.name,
            "business_name": user.business_name,
            "business_type": user.business_type,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "auth_provider": "local",
            "is_admin": admin_account is not None and admin_account.is_active,
            "role": admin_account.role if admin_account else "user",
        },
    }


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(user_data: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user_data.email).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 가입된 이메일입니다.",
        )

    existing_username = db.query(User).filter(User.username == user_data.username).first()

    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 아이디입니다.",
        )

    hashed_password = hash_password(user_data.password)

    new_user = User(
        email=user_data.email,
        password_hash=hashed_password,
        username=user_data.username,
        name=user_data.name,
        business_name=user_data.business_name,
        business_type=user_data.business_type,
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 이메일 또는 아이디입니다.",
        ) from exc

    return new_user


@router.post("/login")
def login(user_data: UserLogin, db: Session = Depends(get_db)):
    user = _authenticate_credentials(user_data, db)
    admin_account = _get_admin_account(db, user.id)
    if admin_account is not None:
        detail = (
            "비활성화된 관리자 계정입니다."
            if not admin_account.is_active
            else "관리자 계정은 관리자 페이지에서 로그인해 주세요."
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

    return _create_login_response(db, user)


@router.post("/admin-login")
def admin_login(user_data: UserLogin, db: Session = Depends(get_db)):
    try:
        user = _authenticate_credentials(user_data, db)
    except HTTPException as exc:
        matched_user = (
            db.query(User).filter(User.username == user_data.username).first()
        )
        _record_admin_login_failure(
            db,
            username=user_data.username,
            user_id=matched_user.id if matched_user else None,
            reason=(
                "비활성화된 계정"
                if exc.status_code == status.HTTP_403_FORBIDDEN
                else "아이디 또는 비밀번호 불일치"
            ),
        )
        raise

    admin_account = _get_admin_account(db, user.id)
    if admin_account is None:
        _record_admin_login_failure(
            db,
            username=user.username,
            user_id=user.id,
            reason="일반 사용자 계정으로 관리자 로그인을 시도함",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="일반 사용자 계정은 관리자 페이지에서 로그인할 수 없습니다.",
        )
    if not admin_account.is_active:
        _record_admin_login_failure(
            db,
            username=user.username,
            user_id=user.id,
            reason="비활성화된 관리자 계정",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 관리자 계정입니다.",
        )
    if admin_account.role not in {"operator", "super_admin"}:
        _record_admin_login_failure(
            db,
            username=user.username,
            user_id=user.id,
            reason="유효하지 않은 관리자 역할",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="유효한 관리자 역할이 없습니다.",
        )

    return _create_login_response(db, user)


@router.post("/find-username", response_model=UsernameFindResponse)
def find_username(request: UsernameFindRequest, db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .filter(func.lower(User.email) == str(request.email).lower())
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="가입된 이메일을 찾을 수 없습니다.",
        )

    return UsernameFindResponse(username=user.username)


@router.post("/logout")
def logout():
    return {"message": "로그아웃되었습니다."}
