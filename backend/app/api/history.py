from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.crud.history import list_histories_by_user
from app.database.connection import get_db
from app.database.models import User
from app.schemas.history import HistoryResponse


router = APIRouter(prefix="/history", tags=["history"])


@router.get("", response_model=list[HistoryResponse])
def read_histories(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[HistoryResponse]:
    return list_histories_by_user(
        db,
        current_user.id,
        skip=skip,
        limit=limit,
    )
