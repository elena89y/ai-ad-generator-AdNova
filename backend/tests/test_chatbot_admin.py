"""챗봇 이용통계 + FAQ 후보 큐 admin 엔드포인트 테스트 — 담당: 한의정.

#216 두-DB 분리 반영: 메인 DB(user_db, Base) = ChatbotEvent·FaqCandidate·SupportInquiry,
admin DB(admin_db, AdminBase) = AdminUser·AdminAuditLog. 엔드포인트 직접 호출 +
current_admin(AdminUser) 주입 + audit 카운트 + 롤백 관례(test_admin.py) 준수.
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
from app.database.admin_models import AdminAuditLog, AdminUser
from app.database.connection import AdminBase, Base
from app.database.models import ChatbotEvent, FaqCandidate, SupportInquiry, User
from app.schemas.admin import FaqCandidateStatusUpdateRequest


class ChatbotAdminTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.user_engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(bind=self.user_engine)
        self.user_db = sessionmaker(bind=self.user_engine)()

        self.admin_engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}
        )
        AdminBase.metadata.create_all(bind=self.admin_engine)
        self.admin_db = sessionmaker(bind=self.admin_engine)()

        self.user = User(email="u@t.com", username="user01", password_hash="x")
        self.user_db.add(self.user)
        self.user_db.commit()
        self.admin = AdminUser(
            email="a@t.com", username="admin01", password_hash="x",
            role="super_admin", is_active=True,
        )
        self.admin_db.add(self.admin)
        self.admin_db.commit()

    def tearDown(self) -> None:
        self.user_db.close()
        self.admin_db.close()
        Base.metadata.drop_all(bind=self.user_engine)
        AdminBase.metadata.drop_all(bind=self.admin_engine)
        self.user_engine.dispose()
        self.admin_engine.dispose()

    def _add_inquiry(self, *, status="answered", answer="답변입니다") -> SupportInquiry:
        inq = SupportInquiry(
            user_id=self.user.id, category="요금·크레딧", title="프리미엄 요금?",
            content="얼마인가요", status=status, answer=answer,
        )
        self.user_db.add(inq)
        self.user_db.commit()
        return inq

    def _audit_count(self, action: str) -> int:
        return self.admin_db.query(AdminAuditLog).filter(AdminAuditLog.action == action).count()

    def _promote(self, inquiry_id: int):
        return promote_inquiry_to_faq(
            inquiry_id=inquiry_id, db=self.user_db, admin_db=self.admin_db,
            current_admin=self.admin,
        )

    def _update(self, candidate_id: int, status: str):
        return update_faq_candidate(
            candidate_id=candidate_id,
            request=FaqCandidateStatusUpdateRequest(status=status),
            db=self.user_db, admin_db=self.admin_db, current_admin=self.admin,
        )

    # --- 이용통계 -------------------------------------------------------------
    def test_chatbot_stats_aggregates(self):
        self.user_db.add_all([
            ChatbotEvent(matched_category="요금·크레딧", escalated=False, rewritten=False, cited_faq_id="faq-bill-002"),
            ChatbotEvent(matched_category="요금·크레딧", escalated=False, rewritten=True, cited_faq_id="faq-bill-002"),
            ChatbotEvent(matched_category="계정", escalated=True, rewritten=False, cited_faq_id=None),
        ])
        self.user_db.commit()

        res = read_chatbot_stats(db=self.user_db, current_admin=self.admin)

        self.assertEqual(res.total_chats, 3)
        self.assertEqual(res.answered_chats, 2)
        self.assertEqual(res.escalated_chats, 1)
        self.assertEqual(res.rewritten_chats, 1)
        self.assertEqual(res.escalation_rate, round(1 / 3, 4))
        self.assertEqual(res.top_cited_faqs[0].faq_id, "faq-bill-002")
        self.assertEqual(res.top_cited_faqs[0].count, 2)

    def test_chatbot_stats_empty(self):
        res = read_chatbot_stats(db=self.user_db, current_admin=self.admin)
        self.assertEqual(res.total_chats, 0)
        self.assertEqual(res.escalation_rate, 0.0)

    # --- FAQ 후보 승격 --------------------------------------------------------
    def test_promote_answered_inquiry_creates_candidate(self):
        inq = self._add_inquiry()
        res = self._promote(inq.id)
        self.assertEqual(res.status, "pending")
        self.assertEqual(res.question, "프리미엄 요금?")
        self.assertEqual(res.source_inquiry_id, inq.id)
        self.assertEqual(self._audit_count("faq_candidate.promoted"), 1)
        # 후보는 메인 DB 에 커밋됨
        self.assertEqual(self.user_db.query(FaqCandidate).count(), 1)

    def test_promote_unanswered_inquiry_409(self):
        inq = self._add_inquiry(status="pending", answer=None)
        with self.assertRaises(HTTPException) as ctx:
            self._promote(inq.id)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_promote_missing_inquiry_404(self):
        with self.assertRaises(HTTPException) as ctx:
            self._promote(999)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_promote_duplicate_pending_409(self):
        inq = self._add_inquiry()
        self._promote(inq.id)
        with self.assertRaises(HTTPException) as ctx:
            self._promote(inq.id)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_promote_after_approved_409(self):
        """승인된 후보가 있는 문의를 다시 승격하면 중복 방지 (리뷰 지적 3b)."""
        inq = self._add_inquiry()
        cand = self._promote(inq.id)
        self._update(cand.id, "approved")
        with self.assertRaises(HTTPException) as ctx:
            self._promote(inq.id)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_promote_after_dismissed_allowed(self):
        """기각된 후보만 있으면 재승격 허용 (재검토 여지)."""
        inq = self._add_inquiry()
        cand = self._promote(inq.id)
        self._update(cand.id, "dismissed")
        again = self._promote(inq.id)
        self.assertEqual(again.status, "pending")

    def test_promote_rolls_back_when_audit_log_fails(self):
        inq = self._add_inquiry()
        with patch("app.api.admin.create_admin_audit_log", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self._promote(inq.id)
        self.assertEqual(self.user_db.query(FaqCandidate).count(), 0)

    # --- 후보 큐 목록 + 승인 --------------------------------------------------
    def test_list_and_approve_candidate(self):
        inq = self._add_inquiry()
        cand = self._promote(inq.id)

        listing = read_faq_candidates(
            skip=0, limit=50, candidate_status="pending",
            db=self.user_db, current_admin=self.admin,
        )
        self.assertEqual(listing.total, 1)

        approved = self._update(cand.id, "approved")
        self.assertEqual(approved.status, "approved")
        self.assertEqual(self._audit_count("faq_candidate.approved"), 1)

    def test_update_missing_candidate_404(self):
        with self.assertRaises(HTTPException) as ctx:
            self._update(999, "dismissed")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_update_already_reviewed_candidate_409(self):
        """승인/기각된 후보의 상태 뒤집기 차단 (리뷰 지적 3a)."""
        inq = self._add_inquiry()
        cand = self._promote(inq.id)
        self._update(cand.id, "approved")
        with self.assertRaises(HTTPException) as ctx:
            self._update(cand.id, "dismissed")
        self.assertEqual(ctx.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
