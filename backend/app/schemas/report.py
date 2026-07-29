from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ReportStatus = Literal["pending", "in_progress", "resolved", "rejected"]


class ReportCreateRequest(BaseModel):
    category: str = Field(default="other", min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=5000)
    advertisement_id: int | None = Field(default=None, ge=1)


class ReportResponse(BaseModel):
    id: int
    category: str
    title: str
    content: str
    advertisement_id: int | None = None
    status: ReportStatus
    admin_note: str | None = None
    handled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ReportListResponse(BaseModel):
    total: int
    items: list[ReportResponse]


class AdminReportResponse(ReportResponse):
    user_id: int
    username: str
    email: str
    handled_by_admin_id: int | None = None


class AdminReportListResponse(BaseModel):
    total: int
    items: list[AdminReportResponse]


class ReportStatusUpdateRequest(BaseModel):
    status: ReportStatus
    admin_note: str | None = Field(default=None, max_length=5000)
