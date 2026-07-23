import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.auth import PASSWORD_PATTERN, USERNAME_PATTERN


class AdminMeResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    totp_enabled: bool


class AdminAccountResponse(BaseModel):
    id: int
    user_id: int
    username: str
    email: str
    name: str | None = None
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AdminAccountListResponse(BaseModel):
    total: int
    items: list[AdminAccountResponse]


class AdminAccountCreateRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=7, max_length=12)
    password: str = Field(min_length=8, max_length=20)
    name: str | None = Field(default=None, max_length=15)
    role: Literal["operator", "super_admin"] = "operator"

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not re.match(USERNAME_PATTERN, value):
            raise ValueError(
                "아이디는 영문과 숫자만 사용할 수 있으며 7~12자여야 합니다."
            )
        return value.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not re.match(PASSWORD_PATTERN, value):
            raise ValueError(
                "비밀번호는 8~20자이며 영문 대문자, 영문 소문자, 숫자, 특수문자를 각각 최소 1개 이상 포함해야 합니다."
            )
        return value


class AdminAccountRoleUpdateRequest(BaseModel):
    role: Literal["operator", "super_admin"]


class AdminAccountStatusUpdateRequest(BaseModel):
    is_active: bool


class AdminSummaryResponse(BaseModel):
    total_users: int
    active_users: int
    premium_users: int
    total_advertisements: int
    unresolved_inquiries: int
    paid_purchase_count: int
    paid_purchase_amount: int
    monthly_paid_purchase_amount: int


class AdminAuditLogResponse(BaseModel):
    id: int
    source: Literal["admin_action", "login_failure"]
    admin_user_id: int | None = None
    admin_username: str
    action: str
    target_type: str
    target_id: int | None = None
    detail: str | None = None
    created_at: datetime


class AdminAuditLogListResponse(BaseModel):
    total: int
    items: list[AdminAuditLogResponse]


class AdminUserResponse(BaseModel):
    id: int
    username: str
    email: str
    name: str | None = None
    business_name: str | None = None
    is_active: bool
    created_at: datetime
    plan: str
    subscription_status: str | None = None


class AdminUserListResponse(BaseModel):
    total: int
    items: list[AdminUserResponse]


class AdminUserDetailResponse(AdminUserResponse):
    business_type: str | None = None
    updated_at: datetime
    advertisement_count: int
    bonus_credits_remaining: int = Field(default=0, ge=0)


class AdminAdvertisementResponse(BaseModel):
    id: int
    user_id: int
    username: str
    email: str
    title: str | None = None
    ad_type: str
    style: str | None = None
    status: str
    prompt: str
    generated_text: str | None = None
    error_message: str | None = None
    output_image_id: int | None = None
    output_image_url: str | None = None
    created_at: datetime
    updated_at: datetime


class AdminAdvertisementListResponse(BaseModel):
    total: int
    items: list[AdminAdvertisementResponse]


class AdminUserStatusUpdateRequest(BaseModel):
    is_active: bool


class AdminUserSubscriptionUpdateRequest(BaseModel):
    is_premium: bool


class AdminBonusCreditGrantRequest(BaseModel):
    amount: int = Field(ge=1, le=10000)


class AdminBonusCreditGrantResponse(BaseModel):
    user_id: int
    bonus_credits_remaining: int = Field(ge=0)


class AdminPurchaseHistoryResponse(BaseModel):
    id: int
    user_id: int
    username: str
    email: str
    provider: str | None = None
    item_type: str
    description: str
    amount: int
    currency: str
    status: str
    purchased_at: datetime


class AdminPurchaseHistoryListResponse(BaseModel):
    total: int
    items: list[AdminPurchaseHistoryResponse]


class AdminDemoRefundRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=255)


class AdminDemoRefundResponse(BaseModel):
    purchase: AdminPurchaseHistoryResponse
    subscription_revoked: bool
    purchased_credits_revoked: int = Field(default=0, ge=0)


class AdminSubscriptionResponse(BaseModel):
    id: int
    user_id: int
    username: str
    email: str
    plan: str
    status: str
    provider: str | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool
    cancel_requested_at: datetime | None = None


class AdminSubscriptionListResponse(BaseModel):
    total: int
    items: list[AdminSubscriptionResponse]


class AdminRefundResponse(BaseModel):
    id: int
    purchase_id: int
    user_id: int
    username: str
    email: str
    description: str
    amount: int
    reason: str
    status: str
    rejection_reason: str | None = None
    requested_at: datetime
    processed_at: datetime | None = None


class AdminRefundListResponse(BaseModel):
    total: int
    items: list[AdminRefundResponse]


class AdminRefundRejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class AdminPasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=20)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if not re.match(PASSWORD_PATTERN, value):
            raise ValueError(
                "비밀번호는 8~20자이며 영문 대문자, 영문 소문자, 숫자, 특수문자를 각각 최소 1개 이상 포함해야 합니다."
            )
        return value


class AdminMessageResponse(BaseModel):
    message: str


class AdminMarketingNotificationRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=5000)
    user_ids: list[int] | None = None

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        value = value.strip()
        if not value or "\r" in value or "\n" in value:
            raise ValueError("메일 제목이 올바르지 않습니다.")
        return value

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("메일 본문이 비어 있습니다.")
        return value


class AdminMarketingNotificationResponse(BaseModel):
    eligible_count: int
    sent_count: int
    failed_count: int


class AdminTotpSetupRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)


class AdminTotpSetupResponse(BaseModel):
    manual_entry_key: str
    provisioning_uri: str
    qr_code_data_url: str


class AdminTotpVerifyRequest(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class AdminTotpDisableRequest(AdminTotpVerifyRequest):
    current_password: str = Field(min_length=1, max_length=128)

# --- 챗봇 이용통계 (한의정) ---------------------------------------------------
class ChatbotCategoryStat(BaseModel):
    category: str
    count: int


class ChatbotFaqStat(BaseModel):
    faq_id: str
    count: int


class AdminChatbotStatsResponse(BaseModel):
    total_chats: int
    answered_chats: int
    escalated_chats: int
    rewritten_chats: int
    escalation_rate: float
    by_category: list[ChatbotCategoryStat]
    top_cited_faqs: list[ChatbotFaqStat]


# --- FAQ 후보 큐 (한의정) -----------------------------------------------------
class AdminFaqCandidateResponse(BaseModel):
    id: int
    source_inquiry_id: int | None = None
    category: str
    question: str
    answer: str
    status: str
    created_at: datetime
    updated_at: datetime


class AdminFaqCandidateListResponse(BaseModel):
    total: int
    items: list[AdminFaqCandidateResponse]


class FaqCandidateStatusUpdateRequest(BaseModel):
    status: Literal["approved", "dismissed"]
