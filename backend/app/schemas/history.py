from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class HistoryImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    image_type: str
    original_filename: Optional[str] = None
    stored_filename: Optional[str] = None
    image_url: Optional[str] = None
    content_type: Optional[str] = None
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    created_at: datetime


class HistoryAdvertisementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    input_image_id: Optional[int] = None
    output_image_id: Optional[int] = None
    title: Optional[str] = None
    ad_type: str
    prompt: str
    generated_text: Optional[str] = None
    style: Optional[str] = None
    tone: Optional[str] = None
    target_audience: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    input_image: Optional[HistoryImageResponse] = None
    output_image: Optional[HistoryImageResponse] = None


class HistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    advertisement_id: Optional[int] = None
    action_type: str
    request_data: Optional[str] = None
    response_data: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    duration_ms: Optional[int] = None
    created_at: datetime
    advertisement: Optional[HistoryAdvertisementResponse] = None
