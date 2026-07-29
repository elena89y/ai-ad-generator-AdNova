from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TypeAlias

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.database.admin_models import AdminAuthRateLimit
from app.database.models import AuthRateLimit

RateLimitModel: TypeAlias = type[AuthRateLimit] | type[AdminAuthRateLimit]


@dataclass(frozen=True)
class RateLimitPolicy:
    max_attempts: int
    window: timedelta
    block_for: timedelta


LOGIN_RATE_LIMIT = RateLimitPolicy(
    max_attempts=5,
    window=timedelta(minutes=15),
    block_for=timedelta(minutes=15),
)
PASSWORD_RESET_RATE_LIMIT = RateLimitPolicy(
    max_attempts=3,
    window=timedelta(minutes=15),
    block_for=timedelta(minutes=15),
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def rate_limit_key_hash(value: str) -> str:
    normalized = value.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _get_record(
    db: Session,
    model: RateLimitModel,
    *,
    scope: str,
    key_hash: str,
):
    return (
        db.query(model)
        .filter(model.scope == scope, model.key_hash == key_hash)
        .first()
    )


def enforce_rate_limit(
    db: Session,
    model: RateLimitModel,
    *,
    scope: str,
    key: str,
    policy: RateLimitPolicy,
) -> None:
    now = utc_now()
    record = _get_record(
        db,
        model,
        scope=scope,
        key_hash=rate_limit_key_hash(key),
    )
    if record is None:
        return

    if record.blocked_until is not None and _as_aware(record.blocked_until) > now:
        retry_after = max(
            1,
            math.ceil((_as_aware(record.blocked_until) - now).total_seconds()),
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.",
            headers={"Retry-After": str(retry_after)},
        )

    window_started_at = _as_aware(record.window_started_at)
    if now - window_started_at >= policy.window or record.blocked_until is not None:
        record.attempts = 0
        record.window_started_at = now
        record.blocked_until = None
        db.commit()


def record_rate_limit_attempt(
    db: Session,
    model: RateLimitModel,
    *,
    scope: str,
    key: str,
    policy: RateLimitPolicy,
) -> None:
    now = utc_now()
    key_hash = rate_limit_key_hash(key)
    record = _get_record(db, model, scope=scope, key_hash=key_hash)
    if record is None:
        record = model(
            scope=scope,
            key_hash=key_hash,
            attempts=0,
            window_started_at=now,
        )
        db.add(record)
    elif now - _as_aware(record.window_started_at) >= policy.window:
        record.attempts = 0
        record.window_started_at = now
        record.blocked_until = None

    record.attempts += 1
    if record.attempts >= policy.max_attempts:
        record.blocked_until = now + policy.block_for
    db.commit()


def clear_rate_limit(
    db: Session,
    model: RateLimitModel,
    *,
    scope: str,
    key: str,
) -> None:
    db.query(model).filter(
        model.scope == scope,
        model.key_hash == rate_limit_key_hash(key),
    ).delete(synchronize_session=False)
    db.commit()


def consume_rate_limit(
    db: Session,
    model: RateLimitModel,
    *,
    scope: str,
    key: str,
    policy: RateLimitPolicy,
) -> None:
    enforce_rate_limit(db, model, scope=scope, key=key, policy=policy)
    record_rate_limit_attempt(db, model, scope=scope, key=key, policy=policy)
