from typing import Optional

from sqlalchemy.orm import Session

from app.database.models import Image


def create_image(
    db: Session,
    *,
    user_id: int,
    image_type: str,
    original_filename: Optional[str] = None,
    stored_filename: Optional[str] = None,
    file_path: Optional[str] = None,
    image_url: Optional[str] = None,
    content_type: Optional[str] = None,
    file_size: Optional[int] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> Image:
    image = Image(
        user_id=user_id,
        image_type=image_type,
        original_filename=original_filename,
        stored_filename=stored_filename,
        file_path=file_path,
        image_url=image_url,
        content_type=content_type,
        file_size=file_size,
        width=width,
        height=height,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image


def get_image_by_id(db: Session, image_id: int) -> Image | None:
    return db.query(Image).filter(Image.id == image_id).first()
