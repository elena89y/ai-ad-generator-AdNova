from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import CreditBalance


DEFAULT_FREE_CREDITS = 3


def get_credit_balance(db: Session, user_id: int) -> CreditBalance:
    balance = db.query(CreditBalance).filter(CreditBalance.user_id == user_id).first()
    if balance is not None:
        return balance

    balance = CreditBalance(
        user_id=user_id,
        free_credits_remaining=DEFAULT_FREE_CREDITS,
    )
    db.add(balance)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        balance = db.query(CreditBalance).filter(CreditBalance.user_id == user_id).one()
    else:
        db.refresh(balance)
    return balance


def consume_free_credit(db: Session, user_id: int) -> int | None:
    get_credit_balance(db, user_id)
    updated = (
        db.query(CreditBalance)
        .filter(
            CreditBalance.user_id == user_id,
            CreditBalance.free_credits_remaining > 0,
        )
        .update(
            {
                CreditBalance.free_credits_remaining: (
                    CreditBalance.free_credits_remaining - 1
                )
            },
            synchronize_session=False,
        )
    )
    if updated != 1:
        db.rollback()
        return None

    db.commit()
    return get_credit_balance(db, user_id).free_credits_remaining


def restore_free_credit(db: Session, user_id: int) -> int:
    balance = get_credit_balance(db, user_id)
    if balance.free_credits_remaining < DEFAULT_FREE_CREDITS:
        balance.free_credits_remaining += 1
        db.commit()
        db.refresh(balance)
    return balance.free_credits_remaining
