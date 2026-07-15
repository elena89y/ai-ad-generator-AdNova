from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import CreditBalance, CreditRefillState


DEFAULT_FREE_CREDITS = 3
FREE_CREDIT_REFILL_INTERVAL = timedelta(days=1)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _get_or_create_balance(db: Session, user_id: int) -> CreditBalance:
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


def _get_or_create_refill_state(db: Session, user_id: int) -> CreditRefillState:
    state = (
        db.query(CreditRefillState)
        .filter(CreditRefillState.user_id == user_id)
        .first()
    )
    if state is not None:
        return state

    state = CreditRefillState(user_id=user_id)
    db.add(state)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        state = (
            db.query(CreditRefillState)
            .filter(CreditRefillState.user_id == user_id)
            .one()
        )
    else:
        db.refresh(state)
    return state


def get_credit_status(
    db: Session,
    user_id: int,
    *,
    now: datetime | None = None,
) -> tuple[CreditBalance, datetime | None]:
    current_time = _as_utc(now or datetime.now(timezone.utc))
    balance = _get_or_create_balance(db, user_id)
    state = _get_or_create_refill_state(db, user_id)
    changed = False

    if balance.free_credits_remaining >= DEFAULT_FREE_CREDITS:
        if balance.free_credits_remaining != DEFAULT_FREE_CREDITS:
            balance.free_credits_remaining = DEFAULT_FREE_CREDITS
            changed = True
        if state.next_refill_at is not None:
            state.next_refill_at = None
            changed = True
    elif state.next_refill_at is None:
        state.next_refill_at = current_time + FREE_CREDIT_REFILL_INTERVAL
        changed = True
    else:
        next_refill_at = _as_utc(state.next_refill_at)
        if current_time >= next_refill_at:
            refill_count = (
                (current_time - next_refill_at) // FREE_CREDIT_REFILL_INTERVAL
            ) + 1
            balance.free_credits_remaining = min(
                DEFAULT_FREE_CREDITS,
                balance.free_credits_remaining + refill_count,
            )
            state.next_refill_at = (
                None
                if balance.free_credits_remaining >= DEFAULT_FREE_CREDITS
                else next_refill_at + (FREE_CREDIT_REFILL_INTERVAL * refill_count)
            )
            changed = True

    if changed:
        db.commit()
        db.refresh(balance)
        db.refresh(state)

    next_refill_at = (
        _as_utc(state.next_refill_at) if state.next_refill_at is not None else None
    )
    return balance, next_refill_at


def get_credit_balance(db: Session, user_id: int) -> CreditBalance:
    balance, _ = get_credit_status(db, user_id)
    return balance


def consume_free_credit(
    db: Session,
    user_id: int,
    *,
    now: datetime | None = None,
) -> int | None:
    current_time = _as_utc(now or datetime.now(timezone.utc))
    get_credit_status(db, user_id, now=current_time)
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
    balance = _get_or_create_balance(db, user_id)
    state = _get_or_create_refill_state(db, user_id)
    if (
        balance.free_credits_remaining < DEFAULT_FREE_CREDITS
        and state.next_refill_at is None
    ):
        state.next_refill_at = current_time + FREE_CREDIT_REFILL_INTERVAL
        db.commit()
        db.refresh(state)
    return balance.free_credits_remaining


def restore_free_credit(db: Session, user_id: int) -> int:
    balance, _ = get_credit_status(db, user_id)
    state = _get_or_create_refill_state(db, user_id)
    if balance.free_credits_remaining < DEFAULT_FREE_CREDITS:
        balance.free_credits_remaining += 1
        if balance.free_credits_remaining >= DEFAULT_FREE_CREDITS:
            state.next_refill_at = None
        db.commit()
        db.refresh(balance)
    return balance.free_credits_remaining
