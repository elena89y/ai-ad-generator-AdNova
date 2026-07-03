from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.crud.dashboard import get_dashboard_summary
from app.database.connection import get_db
from app.database.models import User
from app.schemas.dashboard import DashboardSummaryResponse


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
def read_dashboard_summary(
    user_id: int = Query(..., ge=1),
    recent_limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    return get_dashboard_summary(
        db,
        user_id,
        recent_limit=recent_limit,
    )
