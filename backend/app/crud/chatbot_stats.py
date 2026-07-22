"""챗봇 이용통계 집계 — 담당: 한의정.

ChatbotEvent(비식별 집계 이벤트)만으로 관리자 대시보드 통계를 만든다. 질문 원문은
저장하지 않으므로 개인정보 부담 없음. get_admin_summary 와 같은 dict 반환 관례.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.models import ChatbotEvent

_TOP_FAQ_LIMIT = 5


def record_chatbot_event(
    db: Session,
    *,
    matched_category: str | None,
    escalated: bool,
    rewritten: bool,
    cited_faq_id: str | None,
    commit: bool = True,
) -> ChatbotEvent:
    """챗봇 1턴 집계 이벤트 기록 (개인정보 없음)."""
    event = ChatbotEvent(
        matched_category=matched_category,
        escalated=escalated,
        rewritten=rewritten,
        cited_faq_id=cited_faq_id,
    )
    db.add(event)
    if commit:
        db.commit()
    else:
        db.flush()
    return event


def get_chatbot_stats(db: Session) -> dict:
    """상담수·에스컬레이션율·카테고리 분포·많이 인용된 FAQ 집계."""
    total = db.query(func.count(ChatbotEvent.id)).scalar() or 0
    escalated = (
        db.query(func.count(ChatbotEvent.id))
        .filter(ChatbotEvent.escalated.is_(True))
        .scalar()
        or 0
    )
    rewritten = (
        db.query(func.count(ChatbotEvent.id))
        .filter(ChatbotEvent.rewritten.is_(True))
        .scalar()
        or 0
    )

    category_rows = (
        db.query(ChatbotEvent.matched_category, func.count(ChatbotEvent.id))
        .group_by(ChatbotEvent.matched_category)
        .all()
    )
    by_category = sorted(
        ({"category": c or "미분류", "count": int(n)} for c, n in category_rows),
        key=lambda r: -r["count"],
    )

    cited_rows = (
        db.query(ChatbotEvent.cited_faq_id, func.count(ChatbotEvent.id))
        .filter(ChatbotEvent.cited_faq_id.is_not(None))
        .group_by(ChatbotEvent.cited_faq_id)
        .all()
    )
    top_cited = sorted(
        ({"faq_id": f, "count": int(n)} for f, n in cited_rows),
        key=lambda r: -r["count"],
    )[:_TOP_FAQ_LIMIT]

    return {
        "total_chats": int(total),
        "answered_chats": int(total - escalated),
        "escalated_chats": int(escalated),
        "rewritten_chats": int(rewritten),
        "escalation_rate": round(escalated / total, 4) if total else 0.0,
        "by_category": by_category,
        "top_cited_faqs": top_cited,
    }
