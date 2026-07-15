from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


InquiryStatus = Literal["pending", "in_progress", "answered", "closed"]


class InquiryCreateRequest(BaseModel):
    category: str = Field(default="general", min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=5000)


class InquiryResponse(BaseModel):
    id: int
    category: str
    title: str
    content: str
    status: InquiryStatus
    answer: str | None = None
    answered_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class InquiryListResponse(BaseModel):
    total: int
    items: list[InquiryResponse]


class AdminInquiryResponse(InquiryResponse):
    user_id: int
    username: str
    email: str
    answered_by_admin_id: int | None = None


class AdminInquiryListResponse(BaseModel):
    total: int
    items: list[AdminInquiryResponse]


class InquiryStatusUpdateRequest(BaseModel):
    status: InquiryStatus


class InquiryAnswerUpdateRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=5000)
