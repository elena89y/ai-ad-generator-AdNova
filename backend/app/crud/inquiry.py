from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.models import SupportInquiry, User, utc_now


def create_inquiry(
    db: Session,
    *,
    user_id: int,
    category: str,
    title: str,
    content: str,
) -> SupportInquiry:
    inquiry = SupportInquiry(
        user_id=user_id,
        category=category,
        title=title,
        content=content,
    )
    db.add(inquiry)
    db.commit()
    db.refresh(inquiry)
    return inquiry


def list_inquiries_by_user(
    db: Session,
    *,
    user_id: int,
    skip: int,
    limit: int,
) -> tuple[int, list[SupportInquiry]]:
    query = db.query(SupportInquiry).filter(SupportInquiry.user_id == user_id)
    return (
        query.count(),
        query.order_by(SupportInquiry.created_at.desc()).offset(skip).limit(limit).all(),
    )


def get_inquiry_by_id(db: Session, inquiry_id: int) -> SupportInquiry | None:
    return db.query(SupportInquiry).filter(SupportInquiry.id == inquiry_id).first()


def list_inquiries_for_admin(
    db: Session,
    *,
    skip: int,
    limit: int,
    inquiry_status: str | None = None,
    search: str | None = None,
) -> tuple[int, list[tuple[SupportInquiry, User]]]:
    query = db.query(SupportInquiry, User).join(User, User.id == SupportInquiry.user_id)
    if inquiry_status:
        query = query.filter(SupportInquiry.status == inquiry_status)
    if search:
        keyword = f"%{search}%"
        query = query.filter(
            or_(
                SupportInquiry.title.ilike(keyword),
                SupportInquiry.content.ilike(keyword),
                User.username.ilike(keyword),
                User.email.ilike(keyword),
            )
        )

    return (
        query.count(),
        query.order_by(SupportInquiry.created_at.desc()).offset(skip).limit(limit).all(),
    )


def update_inquiry_status(
    db: Session,
    inquiry: SupportInquiry,
    *,
    inquiry_status: str,
) -> SupportInquiry:
    inquiry.status = inquiry_status
    db.commit()
    db.refresh(inquiry)
    return inquiry


def answer_inquiry(
    db: Session,
    inquiry: SupportInquiry,
    *,
    answer: str,
    admin_user_id: int,
) -> SupportInquiry:
    inquiry.answer = answer
    inquiry.answered_by_admin_id = admin_user_id
    inquiry.answered_at = utc_now()
    inquiry.status = "answered"
    db.commit()
    db.refresh(inquiry)
    return inquiry
