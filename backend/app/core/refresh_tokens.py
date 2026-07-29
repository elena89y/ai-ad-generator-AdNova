import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import UserRefreshToken


USER_REFRESH_COOKIE_NAME = "adnova_refresh_token"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def refresh_token_expiry(days: int) -> datetime:
    return utc_now() + timedelta(days=days)


def issue_user_refresh_token(
    db: Session,
    response: Response,
    *,
    user_id: int,
    auth_provider: str,
    is_persistent: bool,
) -> None:
    token = generate_refresh_token()
    db.add(
        UserRefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(token),
            auth_provider=auth_provider,
            is_persistent=is_persistent,
            expires_at=refresh_token_expiry(settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    db.commit()
    response.set_cookie(
        key=USER_REFRESH_COOKIE_NAME,
        value=token,
        max_age=(
            settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
            if is_persistent
            else None
        ),
        httponly=True,
        secure=settings.SESSION_HTTPS_ONLY,
        samesite="lax",
        path="/api/auth",
    )
