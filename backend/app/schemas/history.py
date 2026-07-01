from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


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
