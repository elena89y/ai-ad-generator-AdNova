"""챗봇 이용통계 + FAQ 후보 큐 admin 엔드포인트 테스트 — 담당: 한의정.

test_admin.py 관례(엔드포인트 직접 호출 + current_admin 주입 + audit 카운트 + 롤백) 준수.
"""
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.admin import (
    promote_inquiry_to_faq,
    read_chatbot_stats,
    read_faq_candidates,
    update_faq_candidate,
)
from app.database.admin_models import AdminAccount, AdminAuditLog
from app.database.connection import Base
from app.database.models import ChatbotEvent, FaqCandidate, SupportInquiry, User
from app.schemas.admin import FaqCandidateStatusUpdateRequest


class ChatbotAdminTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.user = User(email="u@t.com", username="user01", password_hash="x")
        self.admin_user = User(email="a@t.com", username="admin01", password_hash="x")
        self.session.add_all([self.user, self.admin_user])
        self.session.commit()
        self.admin_account = AdminAccount(
            user_id=self.admin_user.id, role="super_admin", is_active=True
        )
        self.session.add(self.admin_account)
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()

    def _add_inquiry(self, *, status="answered", answer="답변입니다") -> SupportInquiry:
        inq = SupportInquiry(
            user_id=self.user.id, category="요금·크레딧", title="프리미엄 요금?",
            content="얼마인가요", status=status, answer=answer,
        )
        self.session.add(inq)
        self.session.commit()
        return inq

    # --- 이용통계 -------------------------------------------------------------
    def test_chatbot_stats_aggregates(self):
        self.session.add_all([
            ChatbotEvent(matched_category="요금·크레딧", escalated=False, rewritten=False, cited_faq_id="faq-bill-002"),
            ChatbotEvent(matched_category="요금·크레딧", escalated=False, rewritten=True, cited_faq_id="faq-bill-002"),
            ChatbotEvent(matched_category="계정", escalated=True, rewritten=False, cited_faq_id=None),
        ])
        self.session.commit()

        res = read_chatbot_stats(db=self.session, current_admin=self.admin_account)

        self.assertEqual(res.total_chats, 3)
        self.assertEqual(res.answered_chats, 2)
        self.assertEqual(res.escalated_chats, 1)
        self.assertEqual(res.rewritten_chats, 1)
        self.assertEqual(res.escalation_rate, round(1 / 3, 4))
        self.assertEqual(res.top_cited_faqs[0].faq_id, "faq-bill-002")
        self.assertEqual(res.top_cited_faqs[0].count, 2)
        top_cat = {c.category: c.count for c in res.by_category}
        self.assertEqual(top_cat["요금·크레딧"], 2)

    def test_chatbot_stats_empty(self):
        res = read_chatbot_stats(db=self.session, current_admin=self.admin_account)
        self.assertEqual(res.total_chats, 0)
        self.assertEqual(res.escalation_rate, 0.0)

    # --- FAQ 후보 승격 --------------------------------------------------------
    def test_promote_answered_inquiry_creates_candidate(self):
        inq = self._add_inquiry()
        res = promote_inquiry_to_faq(
            inquiry_id=inq.id, db=self.session, current_admin=self.admin_account
        )
        self.assertEqual(res.status, "pending")
        self.assertEqual(res.question, "프리미엄 요금?")
        self.assertEqual(res.source_inquiry_id, inq.id)
        self.assertEqual(
            self.session.query(AdminAuditLog)
            .filter(AdminAuditLog.action == "faq_candidate.promoted").count(), 1
        )

    def test_promote_unanswered_inquiry_409(self):
        inq = self._add_inquiry(status="pending", answer=None)
        with self.assertRaises(HTTPException) as ctx:
            promote_inquiry_to_faq(inquiry_id=inq.id, db=self.session, current_admin=self.admin_account)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_promote_missing_inquiry_404(self):
        with self.assertRaises(HTTPException) as ctx:
            promote_inquiry_to_faq(inquiry_id=999, db=self.session, current_admin=self.admin_account)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_promote_duplicate_pending_409(self):
        inq = self._add_inquiry()
        promote_inquiry_to_faq(inquiry_id=inq.id, db=self.session, current_admin=self.admin_account)
        with self.assertRaises(HTTPException) as ctx:
            promote_inquiry_to_faq(inquiry_id=inq.id, db=self.session, current_admin=self.admin_account)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_promote_rolls_back_when_audit_log_fails(self):
        inq = self._add_inquiry()
        with patch("app.api.admin.create_admin_audit_log", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                promote_inquiry_to_faq(inquiry_id=inq.id, db=self.session, current_admin=self.admin_account)
        self.assertEqual(self.session.query(FaqCandidate).count(), 0)

    # --- 후보 큐 목록 + 승인 --------------------------------------------------
    def test_list_and_approve_candidate(self):
        inq = self._add_inquiry()
        cand = promote_inquiry_to_faq(inquiry_id=inq.id, db=self.session, current_admin=self.admin_account)

        listing = read_faq_candidates(
            skip=0, limit=50, candidate_status="pending",
            db=self.session, current_admin=self.admin_account,
        )
        self.assertEqual(listing.total, 1)

        approved = update_faq_candidate(
            candidate_id=cand.id,
            request=FaqCandidateStatusUpdateRequest(status="approved"),
            db=self.session, current_admin=self.admin_account,
        )
        self.assertEqual(approved.status, "approved")
        self.assertEqual(
            self.session.query(AdminAuditLog)
            .filter(AdminAuditLog.action == "faq_candidate.approved").count(), 1
        )

    def test_update_missing_candidate_404(self):
        with self.assertRaises(HTTPException) as ctx:
            update_faq_candidate(
                candidate_id=999,
                request=FaqCandidateStatusUpdateRequest(status="dismissed"),
                db=self.session, current_admin=self.admin_account,
            )
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
