from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class NoticeCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=10000)
    is_published: bool = False


class NoticeUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1, max_length=10000)
    is_published: bool | None = None

    @model_validator(mode="after")
    def validate_update(self):
        if self.title is None and self.content is None and self.is_published is None:
            raise ValueError("변경할 공지사항 항목이 필요합니다.")
        return self


class NoticeResponse(BaseModel):
    id: int
    title: str
    content: str
    published_at: datetime
    created_at: datetime
    updated_at: datetime


class NoticeListResponse(BaseModel):
    total: int
    items: list[NoticeResponse]


class AdminNoticeResponse(NoticeResponse):
    published_at: datetime | None = None
    is_published: bool
    created_by_admin_id: int
    updated_by_admin_id: int | None = None


class AdminNoticeListResponse(BaseModel):
    total: int
    items: list[AdminNoticeResponse]
