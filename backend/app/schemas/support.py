from datetime import datetime

from pydantic import BaseModel, Field


class InquiryCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=5000)


class InquiryResponse(BaseModel):
    id: int
    title: str
    content: str
    status: str
    reply: str | None = None
    created_at: datetime
    answered_at: datetime | None = None


class RefundRequestCreate(BaseModel):
    payment_id: int
    amount: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=1000)


class RefundRequestResponse(BaseModel):
    id: int
    payment_id: int
    amount: int
    reason: str
    status: str
    rejection_reason: str | None = None
    requested_at: datetime
    processed_at: datetime | None = None
