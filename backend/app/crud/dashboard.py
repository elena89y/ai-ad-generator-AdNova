from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.models import Advertisement, History


def _month_range(reference_time: datetime | None = None) -> tuple[datetime, datetime]:
    now = reference_time or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)

    return start, end


def count_monthly_advertisements(
    db: Session,
    user_id: int,
    *,
    reference_time: datetime | None = None,
) -> int:
    start, end = _month_range(reference_time)
    return (
        db.query(func.count(Advertisement.id))
        .filter(Advertisement.user_id == user_id)
        .filter(Advertisement.created_at >= start)
        .filter(Advertisement.created_at < end)
        .scalar()
        or 0
    )


def get_last_worked_at(db: Session, user_id: int) -> datetime | None:
    return (
        db.query(History.created_at)
        .filter(History.user_id == user_id)
        .order_by(History.created_at.desc())
        .limit(1)
        .scalar()
    )


def list_recent_advertisements(
    db: Session,
    user_id: int,
    *,
    limit: int = 5,
) -> list[Advertisement]:
    return (
        db.query(Advertisement)
        .filter(Advertisement.user_id == user_id)
        .order_by(Advertisement.created_at.desc())
        .limit(limit)
        .all()
    )


def get_dashboard_summary(
    db: Session,
    user_id: int,
    *,
    recent_limit: int = 5,
    reference_time: datetime | None = None,
) -> dict[str, object]:
    return {
        "monthly_ad_count": count_monthly_advertisements(
            db,
            user_id,
            reference_time=reference_time,
        ),
        "last_worked_at": get_last_worked_at(db, user_id),
        "recent_ads": list_recent_advertisements(
            db,
            user_id,
            limit=recent_limit,
        ),
    }
