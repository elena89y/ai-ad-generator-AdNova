import logging
from typing import Literal

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.email import send_credit_low_email, send_marketing_email
from app.crud.billing import expire_ended_subscriptions, get_subscription_by_user
from app.crud.credits import (
    get_bonus_credits_remaining,
    get_credit_status,
    get_premium_credit_status,
    get_purchased_credits_remaining,
)
from app.database.billing_models import Subscription
from app.database.models import NotificationSettings, User

logger = logging.getLogger(__name__)
CREDIT_LOW_THRESHOLD = 1


def get_available_credits(db: Session, user_id: int) -> int:
    free_balance, _ = get_credit_status(db, user_id)
    total = free_balance.free_credits_remaining
    total += get_bonus_credits_remaining(db, user_id)
    total += get_purchased_credits_remaining(db, user_id)

    subscription = get_subscription_by_user(db, user_id)
    if subscription and subscription.plan == "premium" and subscription.status == "active":
        premium_balance, _ = get_premium_credit_status(
            db,
            user_id,
            next_reset_at=subscription.current_period_end,
        )
        total += premium_balance.credits_remaining
    return total


def notify_credit_depletion(db: Session, user_id: int) -> bool:
    """남은 전체 생성 크레딧이 적을 때 설정에 따라 메일을 보낸다."""
    try:
        remaining = get_available_credits(db, user_id)
        if remaining > CREDIT_LOW_THRESHOLD:
            return False

        settings = (
            db.query(NotificationSettings)
            .filter(
                NotificationSettings.user_id == user_id,
                NotificationSettings.credit_depletion_alert.is_(True),
            )
            .first()
        )
        user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
        if settings is None or user is None:
            return False

        send_credit_low_email(user.email, remaining)
    except Exception:
        logger.exception("크레딧 소진 알림 메일 발송 실패: user_id=%s", user_id)
        return False
    return True


def send_marketing_notifications(
    db: Session,
    *,
    subject: str,
    message: str,
    audience: Literal["all", "premium", "free", "selected"] = "all",
    user_ids: list[int] | None = None,
) -> tuple[int, int, int]:
    """마케팅 수신에 동의한 활성 사용자에게 메일을 발송한다."""
    expire_ended_subscriptions(db)
    query = (
        db.query(User)
        .join(NotificationSettings, NotificationSettings.user_id == User.id)
        .filter(
            User.is_active.is_(True),
            NotificationSettings.marketing_updates.is_(True),
        )
    )
    active_premium_subscription = and_(
        Subscription.user_id == User.id,
        Subscription.plan == "premium",
        Subscription.status == "active",
    )
    if audience == "premium":
        query = query.join(Subscription, active_premium_subscription)
    elif audience == "free":
        query = query.outerjoin(Subscription, active_premium_subscription).filter(
            Subscription.id.is_(None)
        )
    elif audience == "selected" and user_ids:
        query = query.filter(User.id.in_(set(user_ids)))

    recipients = query.all()
    sent = 0
    failed = 0
    for user in recipients:
        try:
            send_marketing_email(user.email, subject, message)
        except Exception:
            failed += 1
            logger.exception("마케팅 메일 발송 실패: user_id=%s", user.id)
        else:
            sent += 1
    return len(recipients), sent, failed
