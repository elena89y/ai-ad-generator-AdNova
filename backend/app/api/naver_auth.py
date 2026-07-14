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
    prefix="/auth/naver",
    tags=["Naver OAuth"],
)

NAVER_AUTHORIZE_URL = "https://nid.naver.com/oauth2.0/authorize"
NAVER_TOKEN_URL = "https://nid.naver.com/oauth2.0/token"
NAVER_USER_INFO_URL = "https://openapi.naver.com/v1/nid/me"

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
NAVER_REDIRECT_URI = os.getenv(
    "NAVER_REDIRECT_URI",
    "http://localhost:8000/api/auth/naver/callback",
)
FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "http://localhost:5500",
)


def _validate_naver_settings() -> None:
    missing = []

    if not NAVER_CLIENT_ID:
        missing.append("NAVER_CLIENT_ID")

    if not NAVER_CLIENT_SECRET:
        missing.append("NAVER_CLIENT_SECRET")

    if not NAVER_REDIRECT_URI:
        missing.append("NAVER_REDIRECT_URI")

    if missing:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Naver OAuth 환경변수가 없습니다: {', '.join(missing)}",
        )


def _generate_unique_username(db: Session, naver_id: str) -> str:
    """
    User.username 길이 제한(12자)에 맞춰 Naver 계정용 아이디를 만든다.
    """
    normalized_id = "".join(ch for ch in naver_id if ch.isalnum())
    base = f"n_{normalized_id[-10:]}"[:12]

    if not db.query(User).filter(User.username == base).first():
        return base

    for _ in range(20):
        candidate = f"n_{secrets.token_hex(5)}"[:12]
        if not db.query(User).filter(User.username == candidate).first():
            return candidate

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Naver 계정용 사용자 아이디 생성에 실패했습니다.",
    )


def _get_or_create_naver_user(
    db: Session,
    *,
    email: str,
    name: str | None,
    naver_id: str,
) -> User:
    """
    이메일이 이미 존재하면 해당 계정을 사용하고,
    없으면 Naver 계정 기반으로 신규 사용자를 생성한다.
    """
    existing_user = db.query(User).filter(User.email == email).first()

    if existing_user:
        if not existing_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="비활성화된 계정입니다.",
            )
        return existing_user

    new_user = User(
        email=email,
        username=_generate_unique_username(db, naver_id),
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
        return new_user
    except IntegrityError as exc:
        db.rollback()

        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            return existing_user

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Naver 계정 생성 중 중복 데이터가 발생했습니다.",
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
def naver_login(request: Request):
    """
    Naver 로그인 및 동의 화면으로 이동한다.
    """
    _validate_naver_settings()

    state = secrets.token_urlsafe(32)
    request.session["naver_oauth_state"] = state

    authorize_query = urlencode(
        {
            "response_type": "code",
            "client_id": NAVER_CLIENT_ID,
            "redirect_uri": NAVER_REDIRECT_URI,
            "state": state,
        }
    )

    return RedirectResponse(
        url=f"{NAVER_AUTHORIZE_URL}?{authorize_query}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/callback")
def naver_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Naver 인증 결과를 처리하고 AdNova JWT를 발급한 뒤
    프론트엔드로 리다이렉트한다.
    """
    _validate_naver_settings()

    oauth_error = request.query_params.get("error")
    oauth_error_description = request.query_params.get("error_description")

    if oauth_error:
        return _redirect_oauth_error(
            "naver_authorization_denied",
            oauth_error_description or oauth_error,
        )

    code = request.query_params.get("code")
    returned_state = request.query_params.get("state")
    saved_state = request.session.pop("naver_oauth_state", None)

    if not code:
        return _redirect_oauth_error(
            "naver_code_missing",
            "Naver 인가 코드가 전달되지 않았습니다.",
        )

    if not saved_state or not returned_state or saved_state != returned_state:
        return _redirect_oauth_error(
            "naver_state_mismatch",
            "Naver OAuth state 검증에 실패했습니다.",
        )

    token_params = {
        "grant_type": "authorization_code",
        "client_id": NAVER_CLIENT_ID,
        "client_secret": NAVER_CLIENT_SECRET,
        "code": code,
        "state": returned_state,
    }

    try:
        token_response = requests.get(
            NAVER_TOKEN_URL,
            params=token_params,
            timeout=10,
        )
        token_response.raise_for_status()
        token_data = token_response.json()
    except requests.RequestException as exc:
        return _redirect_oauth_error(
            "naver_token_failed",
            f"Naver 토큰 발급에 실패했습니다: {exc}",
        )
    except ValueError:
        return _redirect_oauth_error(
            "naver_token_invalid_response",
            "Naver 토큰 응답을 해석하지 못했습니다.",
        )

    naver_access_token = token_data.get("access_token")

    if not naver_access_token:
        error_message = token_data.get("error_description") or token_data.get("error")
        return _redirect_oauth_error(
            "naver_access_token_missing",
            error_message or "Naver 액세스 토큰을 받지 못했습니다.",
        )

    try:
        user_response = requests.get(
            NAVER_USER_INFO_URL,
            headers={
                "Authorization": f"Bearer {naver_access_token}",
            },
            timeout=10,
        )
        user_response.raise_for_status()
        user_data = user_response.json()
    except requests.RequestException as exc:
        return _redirect_oauth_error(
            "naver_user_info_failed",
            f"Naver 사용자 정보 조회에 실패했습니다: {exc}",
        )
    except ValueError:
        return _redirect_oauth_error(
            "naver_user_info_invalid_response",
            "Naver 사용자 정보 응답을 해석하지 못했습니다.",
        )

    if user_data.get("resultcode") != "00":
        return _redirect_oauth_error(
            "naver_user_info_error",
            user_data.get("message") or "Naver 사용자 정보를 받지 못했습니다.",
        )

    profile = user_data.get("response") or {}

    naver_id = str(profile.get("id") or "")
    email = profile.get("email")
    name = (
        profile.get("name")
        or profile.get("nickname")
        or "Naver 사용자"
    )

    if not naver_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Naver 계정에서 회원 식별자를 받지 못했습니다.",
        )

    # 이메일 제공 동의를 하지 않았거나 계정 상태상 이메일이 없는 경우
    if not email:
        email = f"naver_{naver_id}@oauth.local"

    user = _get_or_create_naver_user(
        db,
        email=email,
        name=name,
        naver_id=naver_id,
    )

    access_token_expires = timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "name": user.name,
            "provider": "naver",
        },
        expires_delta=access_token_expires,
    )

    redirect_url = (
        f"{FRONTEND_URL}/"
        f"#access_token={access_token}"
        f"&token_type=bearer"
        f"&user_id={user.id}"
        f"&provider=naver"
    )

    return RedirectResponse(
        url=redirect_url,
        status_code=status.HTTP_302_FOUND,
    )