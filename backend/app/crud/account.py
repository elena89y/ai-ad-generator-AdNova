from sqlalchemy.orm import Session

from app.database.billing_models import PaymentMethod, PurchaseHistory, Subscription
from app.database.models import Advertisement, History, Image, User


def update_user_password(db: Session, user: User, password_hash: str) -> None:
    user.password_hash = password_hash
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


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
        db.query(History).filter(History.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(Advertisement).filter(Advertisement.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(Image).filter(Image.user_id == user_id).delete(
            synchronize_session=False
        )
        db.query(PurchaseHistory).filter(PurchaseHistory.user_id == user_id).delete(
            synchronize_session=False
        )
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
