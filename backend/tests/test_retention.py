"""법정 보존 리텐션 로직 테스트 — 담당: 한의정.

전자상거래법 3년(문의)·5년(결제) 센티넬 가명처리-보존 + 파기 배치 검증.
리뷰 지적 반영: ① 활성 회원 기록은 파기 금지(anonymized 가드) ② FK 안전성.
"""
import unittest
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.crud.inquiry import list_inquiries_for_admin
from app.crud.retention import (
    INQUIRY_RETENTION_YEARS,
    PAYMENT_RETENTION_YEARS,
    WITHDRAWN_USERNAME,
    _shift_years,
    anonymize_legal_records_for_user,
    get_or_create_withdrawn_placeholder,
    purge_expired_records,
)
from app.database import billing_models  # noqa: F401 - 메타데이터 등록
from app.database.billing_models import PurchaseHistory, RefundRequest
from app.database.connection import Base
from app.database.models import SupportInquiry, User, utc_now


class RetentionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.user = User(email="u@test.com", username="user01", password_hash="x")
        self.session.add(self.user)
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()

    def _add_inquiry(self, **kw) -> SupportInquiry:
        kw.setdefault("title", "t")
        kw.setdefault("content", "c")
        uid = kw.pop("user_id", self.user.id)
        row = SupportInquiry(user_id=uid, category="general", **kw)
        self.session.add(row)
        self.session.commit()
        return row

    # --- 센티넬 & 가명처리 ------------------------------------------------------
    def test_placeholder_is_reserved_and_not_loginable(self):
        p = get_or_create_withdrawn_placeholder(self.session)
        self.session.commit()
        self.assertEqual(p.username, WITHDRAWN_USERNAME)
        self.assertFalse(p.is_active)
        # 같은 세션 재호출 시 중복 생성 안 함
        p2 = get_or_create_withdrawn_placeholder(self.session)
        self.assertEqual(p.id, p2.id)

    def test_anonymize_reassigns_to_sentinel_and_keeps_content(self):
        self._add_inquiry(content="분쟁 근거 본문")
        purchase = PurchaseHistory(
            user_id=self.user.id, item_type="subscription", description="d",
            amount=9900, status="paid",
        )
        self.session.add(purchase)
        self.session.commit()
        self.session.add(
            RefundRequest(user_id=self.user.id, purchase_id=purchase.id, amount=9900, reason="r")
        )
        self.session.commit()

        counts = anonymize_legal_records_for_user(self.session, self.user.id)
        self.session.commit()

        self.assertEqual(counts, {"inquiries": 1, "purchases": 1, "refunds": 1})
        placeholder = self.session.query(User).filter(User.username == WITHDRAWN_USERNAME).one()
        row = self.session.query(SupportInquiry).one()
        self.assertEqual(row.user_id, placeholder.id)  # 센티넬 귀속(개인 링크 단절)
        self.assertIsNotNone(row.anonymized_at)
        self.assertEqual(row.content, "분쟁 근거 본문")  # 본문(분쟁 근거) 보존

    def test_anonymize_nulls_processed_by_admin_link(self):
        """이 회원이 관리자로서 처리한 환불의 처리자 링크도 끊는다(향후 FK 안전)."""
        other = User(email="o@test.com", username="other1", password_hash="x")
        self.session.add(other)
        self.session.commit()
        purchase = PurchaseHistory(
            user_id=other.id, item_type="subscription", description="d",
            amount=9900, status="paid",
        )
        self.session.add(purchase)
        self.session.commit()
        self.session.add(
            RefundRequest(
                user_id=other.id, purchase_id=purchase.id, amount=9900, reason="r",
                processed_by_admin_id=self.user.id,
            )
        )
        self.session.commit()

        anonymize_legal_records_for_user(self.session, self.user.id)
        self.session.commit()

        self.assertIsNone(self.session.query(RefundRequest).one().processed_by_admin_id)

    # --- 파기 배치 (anonymized 가드) ------------------------------------------
    def test_purge_deletes_anonymized_inquiry_past_3_years_only(self):
        old = _shift_years(utc_now(), -INQUIRY_RETENTION_YEARS) - timedelta(days=1)
        recent = utc_now() - timedelta(days=10)
        self._add_inquiry(created_at=old, anonymized_at=utc_now())      # 만료 가명처리 → 파기
        self._add_inquiry(created_at=recent, anonymized_at=utc_now())   # 최근 가명처리 → 보존

        result = purge_expired_records(self.session)

        self.assertEqual(result["inquiries"], 1)
        self.assertEqual(self.session.query(SupportInquiry).count(), 1)

    def test_purge_skips_active_member_old_records(self):
        """리뷰 지적: 활성 회원(가명처리 안 됨)의 오래된 기록은 파기하면 안 됨."""
        old = _shift_years(utc_now(), -INQUIRY_RETENTION_YEARS) - timedelta(days=1)
        self._add_inquiry(created_at=old)  # anonymized_at=None (활성 회원)

        result = purge_expired_records(self.session)

        self.assertEqual(result["inquiries"], 0)
        self.assertEqual(self.session.query(SupportInquiry).count(), 1)

    def test_purge_uses_answered_at_anchor(self):
        """접수는 4년 전이지만 답변완료가 최근이면 보존 (기산점 = 답변완료일)."""
        self._add_inquiry(
            created_at=_shift_years(utc_now(), -4),
            answered_at=utc_now() - timedelta(days=5),
            status="answered",
            anonymized_at=utc_now(),
        )
        result = purge_expired_records(self.session)
        self.assertEqual(result["inquiries"], 0)

    def test_purge_keeps_purchase_referenced_by_retained_refund(self):
        """구매는 5년 경과지만, 참조하는 환불이 아직 보존 대상이면 FK 안전상 보존."""
        old_at = _shift_years(utc_now(), -PAYMENT_RETENTION_YEARS) - timedelta(days=1)
        purchase = PurchaseHistory(
            user_id=self.user.id, item_type="subscription", description="d",
            amount=9900, status="paid", purchased_at=old_at, anonymized_at=utc_now(),
        )
        self.session.add(purchase)
        self.session.commit()
        self.session.add(
            RefundRequest(
                user_id=self.user.id, purchase_id=purchase.id, amount=9900, reason="r",
                requested_at=utc_now() - timedelta(days=3), anonymized_at=utc_now(),
            )
        )
        self.session.commit()

        result = purge_expired_records(self.session)

        self.assertEqual(result["purchases"], 0)  # 환불이 참조 → 보존
        self.assertEqual(result["refunds"], 0)
        self.assertEqual(self.session.query(PurchaseHistory).count(), 1)

    # --- 관리자 조회 연결 (센티넬 덕에 INNER JOIN 유지, 익명화 문의도 노출) ---------
    def test_admin_list_shows_anonymized_inquiry_via_sentinel(self):
        self._add_inquiry(title="dispute")
        anonymize_legal_records_for_user(self.session, self.user.id)
        self.session.commit()

        total, rows = list_inquiries_for_admin(self.session, skip=0, limit=50)
        self.assertEqual(total, 1)  # 센티넬 귀속이라 INNER JOIN 에서 살아남음
        inquiry, user = rows[0]
        self.assertEqual(user.username, WITHDRAWN_USERNAME)  # "(탈퇴회원)"으로 표시
        self.assertEqual(inquiry.title, "dispute")


if __name__ == "__main__":
    unittest.main()
