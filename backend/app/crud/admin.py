from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.billing_models import Subscription
from app.database.models import Advertisement, User


def list_users_for_admin(
    db: Session,
    *,
    skip: int,
    limit: int,
    search: str | None = None,
) -> tuple[int, list[tuple[User, Subscription | None]]]:
    query = db.query(User, Subscription).outerjoin(
        Subscription,
        Subscription.user_id == User.id,
    )
    if search:
        keyword = f"%{search}%"
        query = query.filter(
            or_(
                User.username.ilike(keyword),
                User.email.ilike(keyword),
                User.business_name.ilike(keyword),
            )
        )

    total = query.count()
    rows = (
        query.order_by(User.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return total, rows


def get_user_for_admin(
    db: Session,
    user_id: int,
) -> tuple[User, Subscription | None] | None:
    return (
        db.query(User, Subscription)
        .outerjoin(Subscription, Subscription.user_id == User.id)
        .filter(User.id == user_id)
        .first()
    )


def count_advertisements_by_user(db: Session, user_id: int) -> int:
    return db.query(Advertisement).filter(Advertisement.user_id == user_id).count()
