from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.billing_models import PremiumCreditBalance, PurchasedCreditBalance
from app.database.models import BonusCreditBalance, CreditBalance, CreditRefillState


DEFAULT_FREE_CREDITS = 3
FREE_CREDIT_REFILL_INTERVAL = timedelta(days=1)
PREMIUM_MONTHLY_CREDITS = 30
PREMIUM_CREDIT_RESET_INTERVAL = timedelta(days=30)


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


def get_bonus_credits_remaining(db: Session, user_id: int) -> int:
    balance = (
        db.query(BonusCreditBalance)
        .filter(BonusCreditBalance.user_id == user_id)
        .first()
    )
    return balance.credits_remaining if balance is not None else 0


def grant_bonus_credits(
    db: Session,
    user_id: int,
    amount: int,
    *,
    commit: bool = True,
) -> BonusCreditBalance:
    balance = (
        db.query(BonusCreditBalance)
        .filter(BonusCreditBalance.user_id == user_id)
        .first()
    )
    if balance is None:
        balance = BonusCreditBalance(user_id=user_id, credits_remaining=0)
        db.add(balance)

    balance.credits_remaining += amount
    if commit:
        db.commit()
        db.refresh(balance)
    else:
        db.flush()
    return balance


def consume_bonus_credit(db: Session, user_id: int) -> int | None:
    updated = (
        db.query(BonusCreditBalance)
        .filter(
            BonusCreditBalance.user_id == user_id,
            BonusCreditBalance.credits_remaining > 0,
        )
        .update(
            {
                BonusCreditBalance.credits_remaining: (
                    BonusCreditBalance.credits_remaining - 1
                )
            },
            synchronize_session=False,
        )
    )
    if updated != 1:
        return None

    db.commit()
    return get_bonus_credits_remaining(db, user_id)


def restore_bonus_credit(db: Session, user_id: int) -> int:
    return grant_bonus_credits(db, user_id, 1).credits_remaining


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


def grant_premium_credits(
    db: Session,
    user_id: int,
    *,
    next_reset_at: datetime | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> PremiumCreditBalance:
    current_time = _as_utc(now or datetime.now(timezone.utc))
    reset_at = _as_utc(next_reset_at) if next_reset_at else (
        current_time + PREMIUM_CREDIT_RESET_INTERVAL
    )
    balance = (
        db.query(PremiumCreditBalance)
        .filter(PremiumCreditBalance.user_id == user_id)
        .first()
    )
    if balance is None:
        balance = PremiumCreditBalance(user_id=user_id)
        db.add(balance)

    balance.credits_remaining = PREMIUM_MONTHLY_CREDITS
    balance.next_reset_at = reset_at
    if commit:
        db.commit()
        db.refresh(balance)
    else:
        db.flush()
    return balance


def get_premium_credit_status(
    db: Session,
    user_id: int,
    *,
    next_reset_at: datetime | None = None,
    now: datetime | None = None,
) -> tuple[PremiumCreditBalance, datetime]:
    current_time = _as_utc(now or datetime.now(timezone.utc))
    balance = (
        db.query(PremiumCreditBalance)
        .filter(PremiumCreditBalance.user_id == user_id)
        .first()
    )
    if balance is None:
        balance = grant_premium_credits(
            db,
            user_id,
            next_reset_at=next_reset_at,
            now=current_time,
        )

    reset_at = _as_utc(balance.next_reset_at)
    if current_time >= reset_at:
        elapsed_periods = (
            (current_time - reset_at) // PREMIUM_CREDIT_RESET_INTERVAL
        ) + 1
        balance.credits_remaining = PREMIUM_MONTHLY_CREDITS
        balance.next_reset_at = reset_at + (
            PREMIUM_CREDIT_RESET_INTERVAL * elapsed_periods
        )
        db.commit()
        db.refresh(balance)
        reset_at = _as_utc(balance.next_reset_at)

    return balance, reset_at


def consume_premium_credit(
    db: Session,
    user_id: int,
    *,
    next_reset_at: datetime | None = None,
    now: datetime | None = None,
) -> int | None:
    get_premium_credit_status(
        db,
        user_id,
        next_reset_at=next_reset_at,
        now=now,
    )
    updated = (
        db.query(PremiumCreditBalance)
        .filter(
            PremiumCreditBalance.user_id == user_id,
            PremiumCreditBalance.credits_remaining > 0,
        )
        .update(
            {
                PremiumCreditBalance.credits_remaining: (
                    PremiumCreditBalance.credits_remaining - 1
                )
            },
            synchronize_session=False,
        )
    )
    if updated != 1:
        db.rollback()
        return None

    db.commit()
    return (
        db.query(PremiumCreditBalance.credits_remaining)
        .filter(PremiumCreditBalance.user_id == user_id)
        .scalar()
    )


def restore_premium_credit(
    db: Session,
    user_id: int,
    *,
    next_reset_at: datetime | None = None,
) -> int:
    balance, _ = get_premium_credit_status(
        db,
        user_id,
        next_reset_at=next_reset_at,
    )
    if balance.credits_remaining < PREMIUM_MONTHLY_CREDITS:
        balance.credits_remaining += 1
        db.commit()
        db.refresh(balance)
    return balance.credits_remaining


def get_purchased_credits_remaining(db: Session, user_id: int) -> int:
    balance = (
        db.query(PurchasedCreditBalance)
        .filter(PurchasedCreditBalance.user_id == user_id)
        .first()
    )
    return balance.credits_remaining if balance is not None else 0


def grant_purchased_credits(
    db: Session,
    user_id: int,
    amount: int,
    *,
    commit: bool = True,
) -> PurchasedCreditBalance:
    balance = (
        db.query(PurchasedCreditBalance)
        .filter(PurchasedCreditBalance.user_id == user_id)
        .first()
    )
    if balance is None:
        balance = PurchasedCreditBalance(user_id=user_id, credits_remaining=0)
        db.add(balance)
    balance.credits_remaining += amount
    if commit:
        db.commit()
        db.refresh(balance)
    else:
        db.flush()
    return balance


def consume_purchased_credit(db: Session, user_id: int) -> int | None:
    updated = (
        db.query(PurchasedCreditBalance)
        .filter(
            PurchasedCreditBalance.user_id == user_id,
            PurchasedCreditBalance.credits_remaining > 0,
        )
        .update(
            {PurchasedCreditBalance.credits_remaining: PurchasedCreditBalance.credits_remaining - 1},
            synchronize_session=False,
        )
    )
    if updated != 1:
        return None
    db.commit()
    return get_purchased_credits_remaining(db, user_id)


def restore_purchased_credit(db: Session, user_id: int) -> int:
    return grant_purchased_credits(db, user_id, 1).credits_remaining
