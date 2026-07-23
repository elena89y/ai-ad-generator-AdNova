from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.crud.credits import grant_premium_credits, grant_purchased_credits
from app.database.billing_models import (
    PaymentMethod,
    PurchaseHistory,
    Subscription,
    utc_now,
)


DEMO_CREDIT_PACKS = {
    "credit_10": {"credits": 10, "amount": 4900, "description": "크레딧 10개 (테스트)"},
    "credit_30": {"credits": 30, "amount": 9900, "description": "크레딧 30개 (테스트)"},
}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _expire_subscription(subscription: Subscription, now: datetime) -> bool:
    if (
        subscription.plan != "premium"
        or subscription.status != "active"
        or subscription.current_period_end is None
        or _as_utc(subscription.current_period_end) > now
    ):
        return False

    subscription.status = (
        "canceled" if subscription.cancel_at_period_end else "expired"
    )
    subscription.cancel_at_period_end = False
    return True


def expire_ended_subscriptions(db: Session, *, now: datetime | None = None) -> int:
    current_time = _as_utc(now or utc_now())
    subscriptions = (
        db.query(Subscription)
        .filter(
            Subscription.plan == "premium",
            Subscription.status == "active",
            Subscription.current_period_end.is_not(None),
        )
        .all()
    )
    expired = [
        subscription
        for subscription in subscriptions
        if _expire_subscription(subscription, current_time)
    ]
    if expired:
        db.commit()
        for subscription in expired:
            db.refresh(subscription)
    return len(expired)


def get_subscription_by_user(db: Session, user_id: int) -> Subscription | None:
    subscription = (
        db.query(Subscription).filter(Subscription.user_id == user_id).first()
    )
    if subscription is not None and _expire_subscription(subscription, _as_utc(utc_now())):
        db.commit()
        db.refresh(subscription)
    return subscription


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


def activate_demo_subscription(
    db: Session,
    user_id: int,
    *,
    card_brand: str,
    card_last4: str,
) -> Subscription:
    now = utc_now()
    subscription = get_subscription_by_user(db, user_id)
    if subscription is None:
        subscription = Subscription(
            user_id=user_id,
            provider_subscription_id=f"demo-sub-{uuid4().hex}",
        )
        db.add(subscription)

    subscription.plan = "premium"
    subscription.status = "active"
    subscription.provider = "demo"
    subscription.current_period_start = now
    subscription.current_period_end = now + timedelta(days=30)
    subscription.cancel_at_period_end = False
    subscription.cancel_requested_at = None

    payment_method = get_payment_method_by_user(db, user_id)
    if payment_method is None:
        payment_method = PaymentMethod(user_id=user_id, provider="demo")
        db.add(payment_method)
    payment_method.provider = "demo"
    payment_method.card_brand = card_brand
    payment_method.card_last4 = card_last4

    db.add(
        PurchaseHistory(
            user_id=user_id,
            provider="demo",
            provider_payment_id=f"demo-pay-{uuid4().hex}",
            item_type="subscription",
            description="프리미엄 월 구독 (테스트)",
            amount=9900,
            currency="KRW",
            status="paid",
            purchased_at=now,
        )
    )
    grant_premium_credits(
        db,
        user_id,
        next_reset_at=subscription.current_period_end,
        now=now,
        commit=False,
    )
    db.commit()
    db.refresh(subscription)
    return subscription


def update_demo_payment_method(
    db: Session,
    user_id: int,
    *,
    card_brand: str,
    card_last4: str,
) -> PaymentMethod:
    payment_method = get_payment_method_by_user(db, user_id)
    if payment_method is None:
        payment_method = PaymentMethod(user_id=user_id, provider="demo")
        db.add(payment_method)

    payment_method.provider = "demo"
    payment_method.card_brand = card_brand
    payment_method.card_last4 = card_last4
    db.commit()
    db.refresh(payment_method)
    return payment_method


def purchase_demo_credit_pack(
    db: Session,
    user_id: int,
    *,
    product_id: str,
    card_brand: str,
    card_last4: str,
) -> PurchaseHistory:
    product = DEMO_CREDIT_PACKS[product_id]
    subscription = get_subscription_by_user(db, user_id)
    if subscription is None or subscription.plan != "premium" or subscription.status != "active":
        raise ValueError("크레딧 추가 구매는 프리미엄 구독자만 이용할 수 있습니다.")

    payment_method = get_payment_method_by_user(db, user_id)
    if payment_method is None:
        payment_method = PaymentMethod(user_id=user_id, provider="demo")
        db.add(payment_method)
    payment_method.provider = "demo"
    payment_method.card_brand = card_brand
    payment_method.card_last4 = card_last4

    grant_purchased_credits(db, user_id, product["credits"], commit=False)
    purchase = PurchaseHistory(
        user_id=user_id,
        provider="demo",
        provider_payment_id=f"demo-credit-{uuid4().hex}",
        item_type="credit_pack",
        description=product["description"],
        amount=product["amount"],
        currency="KRW",
        status="paid",
        purchased_at=utc_now(),
    )
    db.add(purchase)
    db.commit()
    db.refresh(purchase)
    return purchase


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
