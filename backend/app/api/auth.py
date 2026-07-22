from datetime import timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.core.config import settings
from app.core.refresh_tokens import (
    USER_REFRESH_COOKIE_NAME,
    generate_refresh_token,
    hash_refresh_token,
    issue_user_refresh_token,
    refresh_token_expiry,
    utc_now,
)
from app.core.security import (
    create_access_token,
    create_admin_access_token,
    hash_password,
    verify_password,
)
from app.core.totp import verify_totp_code
from app.crud.admin import create_admin_login_failure_log
from app.database.connection import get_admin_db, get_db
from app.database.admin_models import AdminRefreshToken, AdminUser
from app.database.models import User, UserRefreshToken
from app.schemas.auth import (
    AdminLoginRequest,
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

ADMIN_REFRESH_COOKIE_NAME = "adnova_admin_refresh_token"


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


def _record_admin_login_failure(
    db: Session,
    *,
    username: str,
    reason: str,
    admin_user_id: int | None = None,
) -> None:
    try:
        create_admin_login_failure_log(
            db,
            attempted_username=username,
            admin_user_id=admin_user_id,
            reason=reason,
        )
    except Exception:
        db.rollback()


def _create_login_response(user: User, auth_provider: str = "local") -> dict:
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "auth_provider": auth_provider},
        expires_delta=access_token_expires,
    )
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
            "auth_provider": auth_provider,
            "is_admin": False,
            "role": "user",
        },
    }


def _set_refresh_cookie(
    response: Response,
    *,
    name: str,
    token: str,
    is_persistent: bool,
) -> None:
    max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60 if is_persistent else None
    response.set_cookie(
        key=name,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.SESSION_HTTPS_ONLY,
        samesite="lax",
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response, name: str) -> None:
    response.delete_cookie(key=name, path="/api/auth")


def _is_expired(expires_at) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= utc_now()


def _issue_user_refresh_token(
    db: Session,
    response: Response,
    *,
    user: User,
    auth_provider: str,
    is_persistent: bool,
) -> None:
    issue_user_refresh_token(
        db,
        response,
        user_id=user.id,
        auth_provider=auth_provider,
        is_persistent=is_persistent,
    )


def _issue_admin_refresh_token(
    admin_db: Session,
    response: Response,
    *,
    admin_user: AdminUser,
    is_persistent: bool,
) -> None:
    token = generate_refresh_token()
    admin_db.add(
        AdminRefreshToken(
            admin_user_id=admin_user.id,
            token_hash=hash_refresh_token(token),
            is_persistent=is_persistent,
            expires_at=refresh_token_expiry(settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    admin_db.commit()
    _set_refresh_cookie(
        response,
        name=ADMIN_REFRESH_COOKIE_NAME,
        token=token,
        is_persistent=is_persistent,
    )


class AvailabilityResponse(BaseModel):
    available: bool


@router.get("/check-username", response_model=AvailabilityResponse)
def check_username(username: str, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == username).first()
    return AvailabilityResponse(available=existing is None)


@router.get("/check-email", response_model=AvailabilityResponse)
def check_email(email: str, db: Session = Depends(get_db)):
    existing = (
        db.query(User)
        .filter(func.lower(User.email) == email.lower())
        .first()
    )
    return AvailabilityResponse(available=existing is None)
    
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
def login(
    user_data: UserLogin,
    response: Response,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
):
    admin_user = (
        admin_db.query(AdminUser)
        .filter(AdminUser.username == user_data.username)
        .first()
    )
    if admin_user is not None:
        detail = (
            "비활성화된 관리자 계정입니다."
            if not admin_user.is_active
            else "관리자 계정은 관리자 페이지에서 로그인해 주세요."
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

    user = _authenticate_credentials(user_data, db)
    _issue_user_refresh_token(
        db,
        response,
        user=user,
        auth_provider="local",
        is_persistent=user_data.remember_me,
    )
    return _create_login_response(user)


@router.post("/admin-login")
def admin_login(
    user_data: AdminLoginRequest,
    response: Response,
    admin_db: Session = Depends(get_admin_db),
):
    admin_user = (
        admin_db.query(AdminUser)
        .filter(AdminUser.username == user_data.username)
        .first()
    )
    if admin_user is None or not verify_password(
        user_data.password,
        admin_user.password_hash if admin_user else "",
    ):
        _record_admin_login_failure(
            admin_db,
            username=user_data.username,
            admin_user_id=admin_user.id if admin_user else None,
            reason="아이디 또는 비밀번호 불일치",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )
    if not admin_user.is_active:
        _record_admin_login_failure(
            admin_db,
            username=admin_user.username,
            admin_user_id=admin_user.id,
            reason="비활성화된 관리자 계정",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 관리자 계정입니다.",
        )
    if admin_user.role not in {"operator", "super_admin"}:
        _record_admin_login_failure(
            admin_db,
            username=admin_user.username,
            admin_user_id=admin_user.id,
            reason="유효하지 않은 관리자 역할",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="유효한 관리자 역할이 없습니다.",
        )
    if admin_user.totp_enabled:
        if user_data.totp_code is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="인증 앱의 6자리 코드를 입력해 주세요.",
            )
        try:
            is_valid_totp = bool(
                admin_user.totp_secret_encrypted
                and verify_totp_code(
                    admin_user.totp_secret_encrypted,
                    user_data.totp_code,
                )
            )
        except ValueError:
            is_valid_totp = False
        if not is_valid_totp:
            _record_admin_login_failure(
                admin_db,
                username=admin_user.username,
                admin_user_id=admin_user.id,
                reason="TOTP 인증 코드 불일치",
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="인증 코드가 올바르지 않습니다.",
            )

    _issue_admin_refresh_token(
        admin_db,
        response,
        admin_user=admin_user,
        is_persistent=user_data.remember_me,
    )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_admin_access_token(
        admin_user.id,
        admin_user.role,
        expires_delta=access_token_expires,
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": admin_user.id,
            "email": admin_user.email,
            "username": admin_user.username,
            "name": admin_user.name,
            "is_active": admin_user.is_active,
            "auth_provider": "local",
            "is_admin": True,
            "role": admin_user.role,
        },
    }


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


@router.post("/refresh")
def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=USER_REFRESH_COOKIE_NAME),
    db: Session = Depends(get_db),
):
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 만료되었습니다.")

    stored_token = (
        db.query(UserRefreshToken)
        .filter(UserRefreshToken.token_hash == hash_refresh_token(refresh_token))
        .first()
    )
    if stored_token is None or stored_token.revoked_at is not None or _is_expired(stored_token.expires_at):
        _clear_refresh_cookie(response, USER_REFRESH_COOKIE_NAME)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 만료되었습니다.")

    user = db.query(User).filter(User.id == stored_token.user_id, User.is_active.is_(True)).first()
    if user is None:
        stored_token.revoked_at = utc_now()
        db.commit()
        _clear_refresh_cookie(response, USER_REFRESH_COOKIE_NAME)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 만료되었습니다.")

    stored_token.revoked_at = utc_now()
    db.flush()
    _issue_user_refresh_token(
        db,
        response,
        user=user,
        auth_provider=stored_token.auth_provider,
        is_persistent=stored_token.is_persistent,
    )
    return _create_login_response(user, stored_token.auth_provider)


@router.post("/admin-refresh")
def admin_refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=ADMIN_REFRESH_COOKIE_NAME),
    admin_db: Session = Depends(get_admin_db),
):
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="관리자 로그인이 만료되었습니다.")

    stored_token = (
        admin_db.query(AdminRefreshToken)
        .filter(AdminRefreshToken.token_hash == hash_refresh_token(refresh_token))
        .first()
    )
    if stored_token is None or stored_token.revoked_at is not None or _is_expired(stored_token.expires_at):
        _clear_refresh_cookie(response, ADMIN_REFRESH_COOKIE_NAME)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="관리자 로그인이 만료되었습니다.")

    admin_user = (
        admin_db.query(AdminUser)
        .filter(AdminUser.id == stored_token.admin_user_id, AdminUser.is_active.is_(True))
        .first()
    )
    if admin_user is None or admin_user.role not in {"operator", "super_admin"}:
        stored_token.revoked_at = utc_now()
        admin_db.commit()
        _clear_refresh_cookie(response, ADMIN_REFRESH_COOKIE_NAME)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="관리자 로그인이 만료되었습니다.")

    stored_token.revoked_at = utc_now()
    admin_db.flush()
    _issue_admin_refresh_token(
        admin_db,
        response,
        admin_user=admin_user,
        is_persistent=stored_token.is_persistent,
    )
    access_token = create_admin_access_token(
        admin_user.id,
        admin_user.role,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
def logout(
    response: Response,
    user_refresh_token: str | None = Cookie(default=None, alias=USER_REFRESH_COOKIE_NAME),
    admin_refresh_token: str | None = Cookie(default=None, alias=ADMIN_REFRESH_COOKIE_NAME),
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
):
    if user_refresh_token:
        db.query(UserRefreshToken).filter(
            UserRefreshToken.token_hash == hash_refresh_token(user_refresh_token)
        ).update({UserRefreshToken.revoked_at: utc_now()}, synchronize_session=False)
        db.commit()
    if admin_refresh_token:
        admin_db.query(AdminRefreshToken).filter(
            AdminRefreshToken.token_hash == hash_refresh_token(admin_refresh_token)
        ).update({AdminRefreshToken.revoked_at: utc_now()}, synchronize_session=False)
        admin_db.commit()
    _clear_refresh_cookie(response, USER_REFRESH_COOKIE_NAME)
    _clear_refresh_cookie(response, ADMIN_REFRESH_COOKIE_NAME)
    return {"message": "로그아웃되었습니다."}
