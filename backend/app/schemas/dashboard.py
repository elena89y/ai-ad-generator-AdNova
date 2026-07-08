from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class RecentAdvertisementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: Optional[str] = None
    ad_type: str
    status: str
    created_at: datetime


class DashboardSummaryResponse(BaseModel):
    monthly_ad_count: int
    last_worked_at: Optional[datetime] = None
    recent_ads: list[RecentAdvertisementResponse]
