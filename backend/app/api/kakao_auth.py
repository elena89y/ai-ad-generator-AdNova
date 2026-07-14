from __future__ import annotations

import os
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.database.connection import get_db
from app.database.models import User


router = APIRouter(
    prefix="/auth/kakao",
    tags=["Kakao OAuth"],
)

KAKAO_AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_USER_INFO_URL = "https://kapi.kakao.com/v2/user/me"

KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY")
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET", "")
KAKAO_REDIRECT_URI = os.getenv(
    "KAKAO_REDIRECT_URI",
    "http://localhost:8000/api/auth/kakao/callback",
)
FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "http://localhost:5500",
)


def _validate_kakao_settings() -> None:
    missing = []

    if not KAKAO_REST_API_KEY:
        missing.append("KAKAO_REST_API_KEY")

    if not KAKAO_REDIRECT_URI:
        missing.append("KAKAO_REDIRECT_URI")

    if missing:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kakao OAuth 환경변수가 없습니다: {', '.join(missing)}",
        )


def _generate_unique_username(db: Session, kakao_id: str) -> str:
    """
    User.username 길이 제한(12자)에 맞춰 Kakao 계정용 아이디를 만든다.
    """
    normalized_id = "".join(ch for ch in kakao_id if ch.isalnum())
    base = f"k_{normalized_id[-10:]}"[:12]

    if not db.query(User).filter(User.username == base).first():
        return base

    for _ in range(20):
        candidate = f"k_{secrets.token_hex(5)}"[:12]
        if not db.query(User).filter(User.username == candidate).first():
            return candidate

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Kakao 계정용 사용자 아이디 생성에 실패했습니다.",
    )


def _get_or_create_kakao_user(
    db: Session,
    *,
    email: str,
    name: str | None,
    kakao_id: str,
) -> tuple[User, bool]:
    """
    이메일이 이미 존재하면 해당 계정을 사용하고,
    없으면 Kakao 계정 기반으로 신규 사용자를 생성한다.
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
        username=_generate_unique_username(db, kakao_id),
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

        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            return existing_user, False

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Kakao 계정 생성 중 중복 데이터가 발생했습니다.",
        ) from exc


def _redirect_oauth_error(error_code: str, message: str) -> RedirectResponse:
    error_query = urlencode(
        {
            "oauth_error": error_code,
            "message": message,
        }
    )
    return RedirectResponse(
        url=f"{FRONTEND_URL}/?{error_query}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/login")
def kakao_login(request: Request):
    """
    Kakao 로그인 및 동의 화면으로 이동한다.
    """
    _validate_kakao_settings()

    state = secrets.token_urlsafe(32)
    request.session["kakao_oauth_state"] = state

    authorize_query = urlencode(
        {
            "client_id": KAKAO_REST_API_KEY,
            "redirect_uri": KAKAO_REDIRECT_URI,
            "response_type": "code",
            "state": state,
        }
    )

    return RedirectResponse(
        url=f"{KAKAO_AUTHORIZE_URL}?{authorize_query}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/callback")
def kakao_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Kakao 인증 결과를 처리하고 AdNova JWT를 발급한 뒤
    프론트엔드로 리다이렉트한다.
    """
    _validate_kakao_settings()

    oauth_error = request.query_params.get("error")
    oauth_error_description = request.query_params.get("error_description")

    if oauth_error:
        return _redirect_oauth_error(
            "kakao_authorization_denied",
            oauth_error_description or oauth_error,
        )

    code = request.query_params.get("code")
    returned_state = request.query_params.get("state")
    saved_state = request.session.pop("kakao_oauth_state", None)

    if not code:
        return _redirect_oauth_error(
            "kakao_code_missing",
            "Kakao 인가 코드가 전달되지 않았습니다.",
        )

    if not saved_state or not returned_state or saved_state != returned_state:
        return _redirect_oauth_error(
            "kakao_state_mismatch",
            "Kakao OAuth state 검증에 실패했습니다.",
        )

    token_payload = {
        "grant_type": "authorization_code",
        "client_id": KAKAO_REST_API_KEY,
        "redirect_uri": KAKAO_REDIRECT_URI,
        "code": code,
    }

    if KAKAO_CLIENT_SECRET:
        token_payload["client_secret"] = KAKAO_CLIENT_SECRET

    try:
        token_response = requests.post(
            KAKAO_TOKEN_URL,
            data=token_payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"
            },
            timeout=10,
        )
        token_response.raise_for_status()
        token_data = token_response.json()
    except requests.RequestException as exc:
        return _redirect_oauth_error(
            "kakao_token_failed",
            f"Kakao 토큰 발급에 실패했습니다: {exc}",
        )
    except ValueError:
        return _redirect_oauth_error(
            "kakao_token_invalid_response",
            "Kakao 토큰 응답을 해석하지 못했습니다.",
        )

    kakao_access_token = token_data.get("access_token")

    if not kakao_access_token:
        return _redirect_oauth_error(
            "kakao_access_token_missing",
            "Kakao 액세스 토큰을 받지 못했습니다.",
        )

    try:
        user_response = requests.get(
            KAKAO_USER_INFO_URL,
            headers={
                "Authorization": f"Bearer {kakao_access_token}",
                "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
            },
            timeout=10,
        )
        user_response.raise_for_status()
        user_info = user_response.json()
    except requests.RequestException as exc:
        return _redirect_oauth_error(
            "kakao_user_info_failed",
            f"Kakao 사용자 정보 조회에 실패했습니다: {exc}",
        )
    except ValueError:
        return _redirect_oauth_error(
            "kakao_user_info_invalid_response",
            "Kakao 사용자 정보 응답을 해석하지 못했습니다.",
        )

    kakao_id = str(user_info.get("id") or "")
    kakao_account = user_info.get("kakao_account") or {}
    profile = kakao_account.get("profile") or {}

    email = kakao_account.get("email")
    name = (
        profile.get("nickname")
        or kakao_account.get("name")
        or "Kakao 사용자"
    )

    if not kakao_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kakao 계정에서 회원번호를 받지 못했습니다.",
        )

    if not email:
        email = f"kakao_{kakao_id}@oauth.local"

    user, is_new_user = _get_or_create_kakao_user(
        db,
        email=email,
        name=name,
        kakao_id=kakao_id,
    )

    access_token_expires = timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "name": user.name,
            "provider": "kakao",
            "auth_provider": "kakao",
        },
        expires_delta=access_token_expires,
    )

    redirect_url = (
        f"{FRONTEND_URL}/"
        f"#access_token={access_token}"
        f"&token_type=bearer"
        f"&user_id={user.id}"
        f"&provider=kakao"
        f"&is_new_user={'true' if is_new_user else 'false'}"
    )

    return RedirectResponse(
        url=redirect_url,
        status_code=status.HTTP_302_FOUND,
    )
