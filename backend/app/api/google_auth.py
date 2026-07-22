from __future__ import annotations

import os
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.refresh_tokens import issue_user_refresh_token
from app.core.security import create_access_token, hash_password
from app.database.connection import get_db
from app.database.models import User


router = APIRouter(
    prefix="/auth/google",
    tags=["Google OAuth"],
)

oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile",
    },
)

GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI",
    "http://localhost:8000/api/auth/google/callback",
)
FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "http://localhost:5500",
)


def _validate_oauth_settings() -> None:
    missing = []

    if not os.getenv("GOOGLE_CLIENT_ID"):
        missing.append("GOOGLE_CLIENT_ID")

    if not os.getenv("GOOGLE_CLIENT_SECRET"):
        missing.append("GOOGLE_CLIENT_SECRET")

    if missing:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Google OAuth 환경변수가 없습니다: {', '.join(missing)}",
        )


def _generate_unique_username(db: Session, google_sub: str) -> str:
    """
    User.username 길이 제한(12자)에 맞춰 Google 계정용 아이디를 만든다.
    """
    normalized_sub = "".join(ch for ch in google_sub if ch.isalnum())
    base = f"g_{normalized_sub[-10:]}"[:12]

    if not db.query(User).filter(User.username == base).first():
        return base

    for _ in range(20):
        candidate = f"g_{secrets.token_hex(5)}"[:12]
        if not db.query(User).filter(User.username == candidate).first():
            return candidate

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Google 계정용 사용자 아이디 생성에 실패했습니다.",
    )


def _get_or_create_google_user(
    db: Session,
    *,
    email: str,
    name: str | None,
    google_sub: str,
) -> tuple[User, bool]:
    """
    이메일이 이미 존재하면 해당 계정을 사용하고,
    없으면 Google 계정 기반으로 신규 사용자를 생성한다.
    """
    existing_user = db.query(User).filter(User.email == email).first()

    if existing_user:
        if not existing_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="비활성화된 계정입니다.",
            )
        return existing_user, False
    
    

    new_user = User(
        email=email,
        username=_generate_unique_username(db, google_sub),
        password_hash=hash_password(secrets.token_urlsafe(48)),
        name=name,
        business_name=None,
        business_type=None,
        is_active=True,
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user, True
    except IntegrityError as exc:
        db.rollback()

        # 동시에 같은 이메일로 가입 요청이 들어온 경우 재조회한다.
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            return existing_user, False

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Google 계정 생성 중 중복 데이터가 발생했습니다.",
        ) from exc


@router.get("/login")
async def google_login(request: Request):
    """
    Google 로그인 화면으로 이동한다.
    """
    _validate_oauth_settings()

    return await oauth.google.authorize_redirect(
        request,
        GOOGLE_REDIRECT_URI,
    )


@router.get("/callback")
async def google_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Google 인증 결과를 처리하고 AdNova JWT를 발급한 뒤
    프론트엔드로 리다이렉트한다.
    """
    _validate_oauth_settings()

    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as exc:
        error_query = urlencode(
            {
                "oauth_error": "google_auth_failed",
                "message": str(exc),
            }
        )
        return RedirectResponse(
            url=f"{FRONTEND_URL}/login?{error_query}",
            status_code=status.HTTP_302_FOUND,
        )

    user_info = token.get("userinfo")

    if not user_info:
        try:
            user_info = await oauth.google.parse_id_token(request, token)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google 사용자 정보를 확인하지 못했습니다.",
            ) from exc

    email = user_info.get("email")
    email_verified = user_info.get("email_verified")
    google_sub = user_info.get("sub")
    name = user_info.get("name")

    if not email or not google_sub:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google 계정에서 필수 사용자 정보를 받지 못했습니다.",
        )

    if email_verified is not True:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google 이메일 인증이 완료되지 않은 계정입니다.",
        )

    user, is_new_user = _get_or_create_google_user(
        db,
        email=email,
        name=name,
        google_sub=google_sub,
    )

    access_token_expires = timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "name": user.name,
            "provider": "google",
            "auth_provider": "google",
        },
        expires_delta=access_token_expires,
    )

    # 로컬 테스트용: URL query 대신 fragment에 토큰을 실어 서버 로그 노출을 줄인다.
    redirect_url = (
        f"{FRONTEND_URL}/auth/callback"
        f"#access_token={access_token}"
        f"&token_type=bearer"
        f"&user_id={user.id}"
        f"&provider=google"
        f"&is_new_user={'true' if is_new_user else 'false'}"
    )

    response = RedirectResponse(
        url=redirect_url,
        status_code=status.HTTP_302_FOUND,
    )
    issue_user_refresh_token(
        db,
        response,
        user_id=user.id,
        auth_provider="google",
        is_persistent=False,
    )
    return response
