from typing import Optional

from sqlalchemy.orm import Session

from app.database.models import Advertisement


def create_advertisement(
    db: Session,
    *,
    user_id: int,
    ad_type: str,
    prompt: str,
    input_image_id: Optional[int] = None,
    output_image_id: Optional[int] = None,
    title: Optional[str] = None,
    generated_text: Optional[str] = None,
    style: Optional[str] = None,
    tone: Optional[str] = None,
    target_audience: Optional[str] = None,
    status: str = "pending",
    error_message: Optional[str] = None,
) -> Advertisement:
    advertisement = Advertisement(
        user_id=user_id,
        input_image_id=input_image_id,
        output_image_id=output_image_id,
        title=title,
        ad_type=ad_type,
        prompt=prompt,
        generated_text=generated_text,
        style=style,
        tone=tone,
        target_audience=target_audience,
        status=status,
        error_message=error_message,
    )
    db.add(advertisement)
    db.commit()
    db.refresh(advertisement)
    return advertisement


def get_advertisement_by_id(
    db: Session,
    advertisement_id: int,
) -> Advertisement | None:
    return db.query(Advertisement).filter(Advertisement.id == advertisement_id).first()


def list_advertisements_by_user(
    db: Session,
    user_id: int,
    *,
    skip: int = 0,
    limit: int = 100,
) -> list[Advertisement]:
    return (
        db.query(Advertisement)
        .filter(Advertisement.user_id == user_id)
        .order_by(Advertisement.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
