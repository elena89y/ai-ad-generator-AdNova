from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from app.database.connection import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
        index=True,
    )
    plan = Column(String(30), default="premium", nullable=False)
    status = Column(String(30), default="active", nullable=False)
    provider = Column(String(50), nullable=True)
    provider_subscription_id = Column(String(255), unique=True, nullable=True)
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end = Column(Boolean, default=False, nullable=False)
    cancel_requested_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class PremiumCreditBalance(Base):
    __tablename__ = "premium_credit_balances"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
        index=True,
    )
    credits_remaining = Column(Integer, default=30, nullable=False)
    next_reset_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class PurchasedCreditBalance(Base):
    """데모 결제로 구매한 크레딧. 월 정기 크레딧과 별도로 보관한다."""

    __tablename__ = "purchased_credit_balances"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    credits_remaining = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class PaymentMethod(Base):
    __tablename__ = "payment_methods"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
        index=True,
    )
    provider = Column(String(50), nullable=False)
    card_brand = Column(String(50), nullable=True)
    card_last4 = Column(String(4), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class PurchaseHistory(Base):
    __tablename__ = "purchase_histories"

    id = Column(Integer, primary_key=True, index=True)
    # 탈퇴 시 "탈퇴회원" 센티넬로 재지정해 가명처리-보존(전자상거래법 5년). retention.py 참조.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider = Column(String(50), nullable=True)
    provider_payment_id = Column(String(255), unique=True, nullable=True)
    item_type = Column(String(50), nullable=False)
    description = Column(String(255), nullable=False)
    amount = Column(Integer, nullable=False)
    currency = Column(String(3), default="KRW", nullable=False)
    status = Column(String(30), nullable=False)
    purchased_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    anonymized_at = Column(DateTime(timezone=True), nullable=True)  # 탈퇴 익명화 시각
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class RefundRequest(Base):
    __tablename__ = "refund_requests"

    id = Column(Integer, primary_key=True, index=True)
    purchase_id = Column(Integer, ForeignKey("purchase_histories.id"), nullable=False, index=True)
    # 탈퇴 시 "탈퇴회원" 센티넬로 재지정해 가명처리-보존(전자상거래법 5년). retention.py 참조.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    reason = Column(String(500), nullable=False)
    status = Column(String(30), default="pending", nullable=False, index=True)
    rejection_reason = Column(String(500), nullable=True)
    processed_by_admin_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    requested_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    anonymized_at = Column(DateTime(timezone=True), nullable=True)  # 탈퇴 익명화 시각
