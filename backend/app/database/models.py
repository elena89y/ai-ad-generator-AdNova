from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database.connection import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(12), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), nullable=True)
    business_name = Column(String(150), nullable=True)
    business_type = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    images = relationship("Image", back_populates="user")
    advertisements = relationship("Advertisement", back_populates="user")
    histories = relationship("History", back_populates="user")
    inquiries = relationship("SupportInquiry", back_populates="user")
    notification_settings = relationship(
        "NotificationSettings", back_populates="user", uselist=False
    )


class UserRefreshToken(Base):
    __tablename__ = "user_refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    auth_provider = Column(String(30), default="local", nullable=False)
    is_persistent = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class CreditBalance(Base):
    __tablename__ = "credit_balances"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    free_credits_remaining = Column(Integer, default=3, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class BonusCreditBalance(Base):
    __tablename__ = "bonus_credit_balances"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    credits_remaining = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class CreditRefillState(Base):
    __tablename__ = "credit_refill_states"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    next_refill_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class NotificationSettings(Base):
    __tablename__ = "notification_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    ad_generation_complete_email = Column(Boolean, default=True, nullable=False)
    credit_depletion_alert = Column(Boolean, default=True, nullable=False)
    marketing_updates = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    user = relationship("User", back_populates="notification_settings")


class Image(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    image_type = Column(String(50), nullable=False)
    original_filename = Column(String(255), nullable=True)
    stored_filename = Column(String(255), nullable=True)
    file_path = Column(String(500), nullable=True)
    image_url = Column(String(500), nullable=True)
    content_type = Column(String(100), nullable=True)
    file_size = Column(Integer, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="images")
    input_advertisements = relationship(
        "Advertisement",
        back_populates="input_image",
        foreign_keys="Advertisement.input_image_id",
    )
    output_advertisements = relationship(
        "Advertisement",
        back_populates="output_image",
        foreign_keys="Advertisement.output_image_id",
    )


class Advertisement(Base):
    __tablename__ = "advertisements"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    input_image_id = Column(Integer, ForeignKey("images.id"), nullable=True)
    output_image_id = Column(Integer, ForeignKey("images.id"), nullable=True)
    title = Column(String(255), nullable=True)
    ad_type = Column(String(50), nullable=False)
    prompt = Column(Text, nullable=False)
    generated_text = Column(Text, nullable=True)
    style = Column(String(100), nullable=True)
    tone = Column(String(100), nullable=True)
    target_audience = Column(String(150), nullable=True)
    status = Column(String(50), default="pending", nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    user = relationship("User", back_populates="advertisements")
    input_image = relationship(
        "Image",
        back_populates="input_advertisements",
        foreign_keys=[input_image_id],
    )
    output_image = relationship(
        "Image",
        back_populates="output_advertisements",
        foreign_keys=[output_image_id],
    )
    histories = relationship("History", back_populates="advertisement")


class History(Base):
    __tablename__ = "histories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    advertisement_id = Column(
        Integer,
        ForeignKey("advertisements.id"),
        nullable=True,
        index=True,
    )
    action_type = Column(String(80), nullable=False)
    request_data = Column(Text, nullable=True)
    response_data = Column(Text, nullable=True)
    status = Column(String(50), nullable=False)
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="histories")
    advertisement = relationship("Advertisement", back_populates="histories")


class SupportInquiry(Base):
    __tablename__ = "support_inquiries"

    id = Column(Integer, primary_key=True, index=True)
    # 탈퇴 시 가명처리-보존(전자상거래법 3년): user_id 를 "탈퇴회원" 센티넬로 재지정해
    # 개인 식별 링크를 끊는다(crud/retention.py). NOT NULL 유지 → FK·기존 INNER JOIN 무결.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    category = Column(String(50), default="general", nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(30), default="pending", nullable=False, index=True)
    answer = Column(Text, nullable=True)
    answered_by_admin_id = Column(Integer, nullable=True)
    answered_at = Column(DateTime(timezone=True), nullable=True)
    anonymized_at = Column(DateTime(timezone=True), nullable=True)  # 탈퇴 익명화 시각 (감사용)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    user = relationship("User", back_populates="inquiries")


class ChatbotEvent(Base):
    """고객센터 챗봇 상담 1턴의 집계용 이벤트 — 담당: 한의정.

    ⚠️ 개인정보 최소화: 질문/답변 원문은 저장하지 않는다. 카테고리·에스컬레이션 여부 등
    비식별 집계 필드만 기록해 관리자 대시보드 통계(상담수·에스컬레이션율·카테고리 분포·
    많이 인용된 FAQ)에 사용. 사용자 계정과도 연결하지 않는다(user_id 없음).
    """

    __tablename__ = "chatbot_events"

    id = Column(Integer, primary_key=True, index=True)
    matched_category = Column(String(50), nullable=True)   # 검색 1위 FAQ 카테고리 (없으면 None)
    escalated = Column(Boolean, default=False, nullable=False, index=True)  # 1:1 문의로 이관됨
    rewritten = Column(Boolean, default=False, nullable=False)  # 쿼리 리라이팅 발동(구어체 구제)
    cited_faq_id = Column(String(40), nullable=True, index=True)  # 인용된 대표 FAQ id (통계용)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)


class FaqCandidate(Base):
    """FAQ 후보 — 담당: 한의정.

    관리자가 답변 완료한 1:1 문의를 "FAQ 후보로 등록"하면 생성. 검토 큐에서 승인/기각한다.
    자기 성장형 지식 루프: 자주 나오는 문의 → FAQ 승격 → 챗봇이 다음부터 자동 응답.
    승인분의 KB(faq_ko.yaml) 반영은 후속(수동/스크립트) — 이 테이블은 후보 관리까지.
    """

    __tablename__ = "faq_candidates"

    id = Column(Integer, primary_key=True, index=True)
    source_inquiry_id = Column(Integer, ForeignKey("support_inquiries.id"), nullable=True, index=True)
    category = Column(String(50), default="general", nullable=False)
    question = Column(String(255), nullable=False)
    answer = Column(Text, nullable=False)
    status = Column(String(20), default="pending", nullable=False, index=True)  # pending/approved/dismissed
    created_by_admin_id = Column(Integer, nullable=True)
    reviewed_by_admin_id = Column(Integer, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class EmailVerification(Base):
    """이메일 가입 인증번호(OTP). 코드 원문은 저장하지 않고 해시만 보관."""
    __tablename__ = "email_verifications"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True, nullable=False)
    code_hash = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class PasswordResetToken(Base):
    """비밀번호 재설정 링크. 원문 토큰은 저장하지 않고 해시만 보관한다."""

    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
