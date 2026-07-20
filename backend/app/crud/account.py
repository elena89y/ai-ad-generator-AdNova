from sqlalchemy.orm import Session

from app.database.billing_models import (
    PaymentMethod,
    PremiumCreditBalance,
    PurchaseHistory,
    RefundRequest,
    Subscription,
)
from app.database.models import (
    Advertisement,
    CreditBalance,
    CreditRefillState,
    History,
    Image,
    NotificationSettings,
    SupportInquiry,
    User,
)


def update_user_password(db: Session, user: User, password_hash: str) -> None:
    user.password_hash = password_hash
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


def get_notification_settings(db: Session, user_id: int) -> NotificationSettings | None:
    return (
        db.query(NotificationSettings)
        .filter(NotificationSettings.user_id == user_id)
        .first()
    )


def update_notification_settings(
    db: Session,
    user_id: int,
    updates: dict[str, bool],
) -> NotificationSettings:
    settings = get_notification_settings(db, user_id)
    if settings is None:
        settings = NotificationSettings(user_id=user_id)
        db.add(settings)

    for field, value in updates.items():
        setattr(settings, field, value)

    try:
        db.commit()
        db.refresh(settings)
    except Exception:
        db.rollback()
        raise
    return settings


def delete_user_account(db: Session, user: User) -> list[str]:
    user_id = user.id
    image_paths = [
        path
        for (path,) in db.query(Image.file_path)
        .filter(Image.user_id == user_id, Image.file_path.is_not(None))
        .all()
        if path
    ]

    try:
        db.query(CreditRefillState).filter(
            CreditRefillState.user_id == user_id
        ).delete(synchronize_session=False)
        db.query(CreditBalance).filter(CreditBalance.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(NotificationSettings).filter(
            NotificationSettings.user_id == user_id
        ).delete(synchronize_session=False)
        db.query(SupportInquiry).filter(SupportInquiry.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(History).filter(History.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(Advertisement).filter(Advertisement.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(Image).filter(Image.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(RefundRequest).filter(RefundRequest.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(PurchaseHistory).filter(PurchaseHistory.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(PremiumCreditBalance).filter(
            PremiumCreditBalance.user_id == user_id
        ).delete(synchronize_session=False)
        db.query(PaymentMethod).filter(PaymentMethod.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(Subscription).filter(Subscription.user_id == user_id).delete(
            synchronize_session=False
        )
        db.delete(user)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return image_paths
