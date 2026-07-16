from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DemoCardRequest(BaseModel):
    card_brand: str = Field(min_length=1, max_length=50)
    card_last4: str = Field(pattern=r"^\d{4}$")


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan: str
    status: str
    provider: str | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool
    cancel_requested_at: datetime | None = None


class PaymentMethodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    card_brand: str | None = None
    card_last4: str | None = None
    updated_at: datetime


class PurchaseHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_type: str
    description: str
    amount: int
    currency: str
    status: str
    purchased_at: datetime


class BillingSummaryResponse(BaseModel):
    is_premium: bool
    free_credits_remaining: int = Field(ge=0)
    free_credit_limit: int = Field(ge=1)
    next_free_credit_at: datetime | None = None
    subscription: SubscriptionResponse | None = None
    payment_method: PaymentMethodResponse | None = None


class RefundRequestCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class RefundRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    purchase_id: int
    amount: int
    reason: str
    status: str
    requested_at: datetime
    processed_at: datetime | None = None
