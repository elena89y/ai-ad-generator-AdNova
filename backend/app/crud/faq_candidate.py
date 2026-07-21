"""FAQ 후보 큐 CRUD — 담당: 한의정.

관리자가 답변 완료한 1:1 문의를 FAQ 후보로 승격 → 검토 큐에서 승인/기각.
list_inquiries_for_admin 등과 같은 (total, rows) 반환 관례.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.models import FaqCandidate, utc_now


def create_faq_candidate(
    db: Session,
    *,
    source_inquiry_id: int | None,
    category: str,
    question: str,
    answer: str,
    created_by_admin_id: int,
    commit: bool = True,
) -> FaqCandidate:
    candidate = FaqCandidate(
        source_inquiry_id=source_inquiry_id,
        category=category,
        question=question,
        answer=answer,
        created_by_admin_id=created_by_admin_id,
    )
    db.add(candidate)
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(candidate)
    return candidate


def list_faq_candidates_for_admin(
    db: Session,
    *,
    skip: int,
    limit: int,
    candidate_status: str | None = None,
) -> tuple[int, list[FaqCandidate]]:
    query = db.query(FaqCandidate)
    if candidate_status:
        query = query.filter(FaqCandidate.status == candidate_status)
    return (
        query.count(),
        query.order_by(FaqCandidate.created_at.desc()).offset(skip).limit(limit).all(),
    )


def get_faq_candidate_by_id(db: Session, candidate_id: int) -> FaqCandidate | None:
    return db.query(FaqCandidate).filter(FaqCandidate.id == candidate_id).first()


def update_faq_candidate_status(
    db: Session,
    candidate: FaqCandidate,
    *,
    candidate_status: str,
    admin_user_id: int,
    commit: bool = True,
) -> FaqCandidate:
    candidate.status = candidate_status
    candidate.reviewed_by_admin_id = admin_user_id
    candidate.reviewed_at = utc_now()
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(candidate)
    return candidate


def has_open_candidate_for_inquiry(db: Session, inquiry_id: int) -> bool:
    """같은 문의로 이미 대기(pending) 후보가 있으면 중복 승격 방지."""
    return (
        db.query(FaqCandidate.id)
        .filter(
            FaqCandidate.source_inquiry_id == inquiry_id,
            FaqCandidate.status == "pending",
        )
        .first()
        is not None
    )
