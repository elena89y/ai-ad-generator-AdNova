from datetime import datetime

from pydantic import BaseModel, Field


class AdminMeResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str


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
    subscription_id: int | None = None


class AdminUserListResponse(BaseModel):
    total: int
    items: list[AdminUserResponse]


class AdminUserDetailResponse(AdminUserResponse):
    business_type: str | None = None
    updated_at: datetime
    advertisement_count: int


class AdminUserStatusRequest(BaseModel):
    is_active: bool


class AdminSubscriptionUpdateRequest(BaseModel):
    plan: str = Field(min_length=1, max_length=30)


class AdminPaymentResponse(BaseModel):
    id: int
    user_id: int
    order_number: str
    user_name: str
    email: str
    business_name: str | None = None
    product: str
    amount: int
    currency: str
    paid_at: datetime
    status: str
    refund_id: int | None = None
    refund_amount: int | None = None
    refund_reason: str | None = None
    refund_requested_at: datetime | None = None


class AdminPaymentListResponse(BaseModel):
    total: int
    items: list[AdminPaymentResponse]


class AdminRefundCreateRequest(BaseModel):
    payment_id: int
    order_number: str | None = None
    amount: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=1000)


class AdminRefundRejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class AdminRefundResponse(BaseModel):
    id: int
    payment_id: int
    status: str
    amount: int
    reason: str
    rejection_reason: str | None = None
    requested_at: datetime
    processed_at: datetime | None = None


class AdminInquiryResponse(BaseModel):
    id: int
    user_id: int
    user_name: str
    email: str
    business_name: str | None = None
    title: str
    content: str
    status: str
    reply: str | None = None
    created_at: datetime
    answered_at: datetime | None = None


class AdminInquiryListResponse(BaseModel):
    total: int
    items: list[AdminInquiryResponse]


class AdminInquiryReplyRequest(BaseModel):
    reply: str = Field(min_length=1, max_length=5000)


class AdminPasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=20)


class AdminMessageResponse(BaseModel):
    message: str
