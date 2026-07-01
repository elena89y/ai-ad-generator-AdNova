from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AdvertisementCreate(BaseModel):
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
    status: str = "pending"
    error_message: Optional[str] = None


class AdvertisementResponse(BaseModel):
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
