from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.models import Notice, utc_now


def create_notice(
    db: Session,
    *,
    title: str,
    content: str,
    is_published: bool,
    admin_user_id: int,
    commit: bool = True,
) -> Notice:
    notice = Notice(
        title=title,
        content=content,
        is_published=is_published,
        published_at=utc_now() if is_published else None,
        created_by_admin_id=admin_user_id,
    )
    db.add(notice)
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(notice)
    return notice


def get_notice_by_id(db: Session, notice_id: int) -> Notice | None:
    return db.query(Notice).filter(Notice.id == notice_id).first()


def list_published_notices(
    db: Session,
    *,
    skip: int,
    limit: int,
) -> tuple[int, list[Notice]]:
    query = db.query(Notice).filter(Notice.is_published.is_(True))
    return (
        query.count(),
        query.order_by(Notice.published_at.desc()).offset(skip).limit(limit).all(),
    )


def list_notices_for_admin(
    db: Session,
    *,
    skip: int,
    limit: int,
    is_published: bool | None = None,
    search: str | None = None,
) -> tuple[int, list[Notice]]:
    query = db.query(Notice)
    if is_published is not None:
        query = query.filter(Notice.is_published.is_(is_published))
    if search:
        keyword = f"%{search}%"
        query = query.filter(
            or_(
                Notice.title.ilike(keyword),
                Notice.content.ilike(keyword),
            )
        )
    return (
        query.count(),
        query.order_by(Notice.created_at.desc()).offset(skip).limit(limit).all(),
    )


def update_notice(
    db: Session,
    notice: Notice,
    *,
    title: str | None,
    content: str | None,
    is_published: bool | None,
    admin_user_id: int,
    commit: bool = True,
) -> Notice:
    if title is not None:
        notice.title = title
    if content is not None:
        notice.content = content
    if is_published is not None and notice.is_published != is_published:
        notice.is_published = is_published
        notice.published_at = utc_now() if is_published else None
    notice.updated_by_admin_id = admin_user_id
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(notice)
    return notice


def delete_notice(db: Session, notice: Notice, *, commit: bool = True) -> None:
    db.delete(notice)
    if commit:
        db.commit()
    else:
        db.flush()
