from datetime import timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.billing_models import PurchaseHistory, Subscription, utc_now
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


def update_user_active_status(
    db: Session,
    user: User,
    *,
    is_active: bool,
) -> User:
    user.is_active = is_active
    db.commit()
    db.refresh(user)
    return user


def update_user_premium_access(
    db: Session,
    user_id: int,
    *,
    is_premium: bool,
) -> tuple[User, Subscription | None]:
    subscription = (
        db.query(Subscription).filter(Subscription.user_id == user_id).first()
    )

    if is_premium:
        now = utc_now()
        if subscription is None:
            subscription = Subscription(user_id=user_id)
            db.add(subscription)

        subscription.plan = "premium"
        subscription.status = "active"
        subscription.provider = "admin"
        subscription.current_period_start = now
        subscription.current_period_end = now + timedelta(days=30)
        subscription.cancel_at_period_end = False
        subscription.cancel_requested_at = None
    elif subscription is not None:
        subscription.plan = "free"
        subscription.status = "inactive"
        subscription.cancel_at_period_end = False
        subscription.cancel_requested_at = None

    db.commit()
    user = db.query(User).filter(User.id == user_id).one()
    db.refresh(user)
    return user, subscription


def list_purchase_histories_for_admin(
    db: Session,
    *,
    skip: int,
    limit: int,
    user_id: int | None = None,
    search: str | None = None,
    payment_status: str | None = None,
) -> tuple[int, list[tuple[PurchaseHistory, User]]]:
    query = db.query(PurchaseHistory, User).join(
        User,
        User.id == PurchaseHistory.user_id,
    )
    if user_id is not None:
        query = query.filter(PurchaseHistory.user_id == user_id)
    if search:
        keyword = f"%{search}%"
        query = query.filter(
            or_(
                User.username.ilike(keyword),
                User.email.ilike(keyword),
                PurchaseHistory.description.ilike(keyword),
            )
        )
    if payment_status:
        query = query.filter(PurchaseHistory.status == payment_status)

    total = query.count()
    rows = (
        query.order_by(PurchaseHistory.purchased_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return total, rows
