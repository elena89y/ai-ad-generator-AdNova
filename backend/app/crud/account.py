from sqlalchemy.orm import Session

from app.crud.retention import anonymize_legal_records_for_user
from app.database.billing_models import (
    PaymentMethod,
    PremiumCreditBalance,
    PurchasedCreditBalance,
    Subscription,
)
from app.database.models import (
    Advertisement,
    CreditBalance,
    CreditRefillState,
    History,
    Image,
    NotificationSettings,
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
        # 법정 보존 기록(문의 3년·구매/환불 5년)은 삭제하지 않고 가명처리-보존한다.
        # user_id 를 "탈퇴회원" 센티넬 계정으로 재지정(NOT NULL 유지)하므로 개인 식별
        # 링크만 끊긴다. (전자상거래법 시행령 제6조 + 개인정보보호법 제21조 — retention.py 참조)
        anonymize_legal_records_for_user(db, user_id)

        # 운영 데이터는 종전대로 즉시 파기.
        db.query(CreditRefillState).filter(
            CreditRefillState.user_id == user_id
        ).delete(synchronize_session=False)
        db.query(CreditBalance).filter(CreditBalance.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(NotificationSettings).filter(
            NotificationSettings.user_id == user_id
        ).delete(synchronize_session=False)
        db.query(History).filter(History.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(Advertisement).filter(Advertisement.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(Image).filter(Image.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(PremiumCreditBalance).filter(
            PremiumCreditBalance.user_id == user_id
        ).delete(synchronize_session=False)
        db.query(PurchasedCreditBalance).filter(
            PurchasedCreditBalance.user_id == user_id
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
