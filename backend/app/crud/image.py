from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.database.models import Advertisement, Image


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
    commit: bool = True,
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
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(image)
    return image


def get_image_by_id(db: Session, image_id: int) -> Image | None:
    return db.query(Image).filter(Image.id == image_id).first()


def delete_unreferenced_upload(
    db: Session,
    image: Image,
    *,
    commit: bool = True,
) -> str | None:
    """Delete an upload row only when no historical advertisement references it."""
    if image.image_type != "upload":
        return None
    is_referenced = (
        db.query(Advertisement.id)
        .filter(Advertisement.input_image_id == image.id)
        .first()
        is not None
    )
    if is_referenced:
        return None

    file_path = image.file_path
    db.delete(image)
    if commit:
        db.commit()
    else:
        db.flush()
    return file_path


def purge_expired_unreferenced_uploads(
    db: Session,
    *,
    created_before: datetime,
) -> list[str]:
    referenced_image_ids = db.query(Advertisement.input_image_id).filter(
        Advertisement.input_image_id.is_not(None)
    )
    images = (
        db.query(Image)
        .filter(
            Image.image_type == "upload",
            Image.created_at < created_before,
            ~Image.id.in_(referenced_image_ids),
        )
        .all()
    )
    file_paths = [image.file_path for image in images if image.file_path]
    for image in images:
        db.delete(image)
    db.commit()
    return file_paths
