import json
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.database.models import Advertisement, History, Image


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


def _generated_result_urls(histories: list[History]) -> set[str]:
    urls: set[str] = set()
    fields = (
        "image_url",
        "image_without_typography_url",
        "image_with_typography_url",
    )

    for history in histories:
        if not history.response_data:
            continue
        try:
            response_data = json.loads(history.response_data)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(response_data, dict):
            continue

        for field in fields:
            value = response_data.get(field)
            if isinstance(value, str) and value:
                urls.add(value)

        format_outputs = response_data.get("format_outputs")
        if isinstance(format_outputs, list):
            urls.update(value for value in format_outputs if isinstance(value, str) and value)

    return urls


def _filename_from_url(url: str) -> str | None:
    filename = Path(urlparse(url).path).name
    return filename or None


def delete_generated_result_by_history(db: Session, history: History) -> list[str]:
    advertisement = history.advertisement
    if advertisement is None:
        return []

    output_image = advertisement.output_image
    related_histories = (
        db.query(History)
        .filter(History.advertisement_id == advertisement.id)
        .all()
    )
    result_urls = _generated_result_urls(related_histories)
    result_filenames = {
        filename
        for url in result_urls
        if (filename := _filename_from_url(url)) is not None
    }

    image_filters = []
    if output_image is not None:
        image_filters.append(Image.id == output_image.id)
    if result_urls:
        image_filters.append(Image.image_url.in_(result_urls))
    if result_filenames:
        image_filters.append(Image.stored_filename.in_(result_filenames))

    generated_images = []
    if image_filters:
        generated_images = (
            db.query(Image)
            .filter(
                Image.user_id == advertisement.user_id,
                Image.image_type == "generated",
                or_(*image_filters),
            )
            .all()
        )
    file_paths = [image.file_path for image in generated_images if image.file_path]

    for related_history in related_histories:
        db.delete(related_history)

    db.delete(advertisement)

    for image in generated_images:
        db.delete(image)

    db.commit()
    return file_paths
