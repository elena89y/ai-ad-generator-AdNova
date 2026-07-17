from typing import Optional

from sqlalchemy.orm import Session, joinedload

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
    commit: bool = True,
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
    if commit:
        db.commit()
    else:
        db.flush()
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


def get_history_with_result_by_id(db: Session, history_id: int) -> History | None:
    return (
        db.query(History)
        .options(
            joinedload(History.advertisement).joinedload(Advertisement.input_image),
            joinedload(History.advertisement).joinedload(Advertisement.output_image),
        )
        .filter(History.id == history_id)
        .first()
    )


def delete_generated_result_by_history(db: Session, history: History) -> None:
    advertisement = history.advertisement
    if advertisement is None:
        return

    output_image = advertisement.output_image
    related_histories = (
        db.query(History)
        .filter(History.advertisement_id == advertisement.id)
        .all()
    )

    for related_history in related_histories:
        db.delete(related_history)

    db.delete(advertisement)

    if (
        output_image is not None
        and output_image.image_type == "generated"
        and output_image.user_id == advertisement.user_id
    ):
        db.delete(output_image)

    db.commit()
