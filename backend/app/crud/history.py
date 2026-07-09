from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload

from app.database.models import Advertisement, History


def create_history(
    db: Session,
    *,
    user_id: int,
    action_type: str,
    status: str,
    advertisement_id: Optional[int] = None,
    request_data: Optional[str] = None,
    response_data: Optional[str] = None,
    error_message: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> History:
    history = History(
        user_id=user_id,
        advertisement_id=advertisement_id,
        action_type=action_type,
        request_data=request_data,
        response_data=response_data,
        status=status,
        error_message=error_message,
        duration_ms=duration_ms,
    )
    db.add(history)
    db.commit()
    db.refresh(history)
    return history


def list_histories_by_user(
    db: Session,
    user_id: int,
    *,
    skip: int = 0,
    limit: int = 100,
) -> list[History]:
    return (
        db.query(History)
        .options(
            joinedload(History.advertisement).joinedload(Advertisement.input_image),
            joinedload(History.advertisement).joinedload(Advertisement.output_image),
        )
        .filter(History.user_id == user_id)
        .order_by(History.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
