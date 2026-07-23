from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.models import User, UserReport, utc_now


def create_report(
    db: Session,
    *,
    user_id: int,
    category: str,
    title: str,
    content: str,
    advertisement_id: int | None = None,
) -> UserReport:
    report = UserReport(
        user_id=user_id,
        category=category,
        title=title,
        content=content,
        advertisement_id=advertisement_id,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def list_reports_by_user(
    db: Session,
    *,
    user_id: int,
    skip: int,
    limit: int,
) -> tuple[int, list[UserReport]]:
    query = db.query(UserReport).filter(UserReport.user_id == user_id)
    return (
        query.count(),
        query.order_by(UserReport.created_at.desc()).offset(skip).limit(limit).all(),
    )


def get_report_by_id(db: Session, report_id: int) -> UserReport | None:
    return db.query(UserReport).filter(UserReport.id == report_id).first()


def list_reports_for_admin(
    db: Session,
    *,
    skip: int,
    limit: int,
    report_status: str | None = None,
    search: str | None = None,
) -> tuple[int, list[tuple[UserReport, User]]]:
    query = db.query(UserReport, User).join(User, User.id == UserReport.user_id)
    if report_status:
        query = query.filter(UserReport.status == report_status)
    if search:
        keyword = f"%{search}%"
        query = query.filter(
            or_(
                UserReport.title.ilike(keyword),
                UserReport.content.ilike(keyword),
                UserReport.category.ilike(keyword),
                User.username.ilike(keyword),
                User.email.ilike(keyword),
            )
        )

    return (
        query.count(),
        query.order_by(UserReport.created_at.desc()).offset(skip).limit(limit).all(),
    )


def update_report_status(
    db: Session,
    report: UserReport,
    *,
    report_status: str,
    admin_note: str | None,
    admin_user_id: int,
    commit: bool = True,
) -> UserReport:
    report.status = report_status
    report.admin_note = admin_note
    report.handled_by_admin_id = admin_user_id
    report.handled_at = utc_now()
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(report)
    return report
