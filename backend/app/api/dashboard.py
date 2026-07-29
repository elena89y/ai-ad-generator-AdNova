from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.crud.dashboard import get_dashboard_summary
from app.database.connection import get_db
from app.database.models import User
from app.schemas.dashboard import DashboardSummaryResponse


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
def read_dashboard_summary(
    recent_limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    return get_dashboard_summary(
        db,
        current_user.id,
        recent_limit=recent_limit,
    )
