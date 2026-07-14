from sqlalchemy.orm import Session

from app.database.billing_models import (
    PaymentMethod,
    PurchaseHistory,
    Subscription,
    utc_now,
)


def get_subscription_by_user(db: Session, user_id: int) -> Subscription | None:
    return db.query(Subscription).filter(Subscription.user_id == user_id).first()


def get_payment_method_by_user(db: Session, user_id: int) -> PaymentMethod | None:
    return db.query(PaymentMethod).filter(PaymentMethod.user_id == user_id).first()


def list_purchase_histories_by_user(
    db: Session,
    user_id: int,
    *,
    limit: int = 50,
) -> list[PurchaseHistory]:
    return (
        db.query(PurchaseHistory)
        .filter(PurchaseHistory.user_id == user_id)
        .order_by(PurchaseHistory.purchased_at.desc())
        .limit(limit)
        .all()
    )


def schedule_subscription_cancellation(
    db: Session,
    subscription: Subscription,
) -> Subscription:
    if not subscription.cancel_at_period_end:
        subscription.cancel_at_period_end = True
        subscription.cancel_requested_at = utc_now()
        db.commit()
        db.refresh(subscription)
    return subscription


def resume_subscription(db: Session, subscription: Subscription) -> Subscription:
    if subscription.cancel_at_period_end:
        subscription.cancel_at_period_end = False
        subscription.cancel_requested_at = None
        db.commit()
        db.refresh(subscription)
    return subscription
