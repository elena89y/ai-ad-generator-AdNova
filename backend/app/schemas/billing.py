from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
    subscription: SubscriptionResponse | None = None
    payment_method: PaymentMethodResponse | None = None
