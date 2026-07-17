import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.auth import PASSWORD_PATTERN


class AdminMeResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str


class AdminAccountResponse(BaseModel):
    id: int
    user_id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AdminAccountListResponse(BaseModel):
    total: int
    items: list[AdminAccountResponse]


class AdminAccountCreateRequest(BaseModel):
    user_id: int = Field(gt=0)
    role: Literal["operator", "super_admin"] = "operator"


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
    admin_user_id: int
    admin_username: str
    action: str
    target_type: str
    target_id: int
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


class AdminUserStatusUpdateRequest(BaseModel):
    is_active: bool


class AdminUserSubscriptionUpdateRequest(BaseModel):
    is_premium: bool


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
