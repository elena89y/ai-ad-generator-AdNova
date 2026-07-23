import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.admin import (
    answer_admin_inquiry,
    read_admin_inquiries,
    update_admin_inquiry_status,
)
from app.api.inquiries import (
    create_user_inquiry,
    read_user_inquiry_detail,
    read_user_inquiries,
)
from app.database.admin_models import AdminAuditLog, AdminUser
from app.database.connection import AdminBase, Base
from app.database.models import SupportInquiry, User
from app.schemas.inquiry import (
    InquiryAnswerUpdateRequest,
    InquiryCreateRequest,
    InquiryStatusUpdateRequest,
)


class InquiryApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()

        self.user = User(
            email="inquiry@example.com",
            username="inquiryuser",
            password_hash="test-hash",
            is_active=True,
        )
        self.other_user = User(
            email="other-inquiry@example.com",
            username="otheruser",
            password_hash="test-hash",
            is_active=True,
        )
        self.admin_user = AdminUser(
            email="inquiry-admin@example.com",
            username="inquiryadmin",
            password_hash="test-hash",
            is_active=True,
            role="super_admin",
        )
        self.session.add_all([self.user, self.other_user])
        self.session.commit()

        self.admin_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        AdminBase.metadata.create_all(bind=self.admin_engine)
        self.admin_session = sessionmaker(bind=self.admin_engine)()
        self.admin_session.add(self.admin_user)
        self.admin_session.commit()
        self.admin_account = self.admin_user

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()
        self.admin_session.close()
        AdminBase.metadata.drop_all(bind=self.admin_engine)
        self.admin_engine.dispose()

    def _create_inquiry(self):
        return create_user_inquiry(
            request=InquiryCreateRequest(
                category="billing",
                title="결제 문의",
                content="구독 결제 정보를 확인하고 싶습니다.",
            ),
            db=self.session,
            current_user=self.user,
        )

    def test_user_can_create_and_list_own_inquiries(self) -> None:
        created = self._create_inquiry()

        response = read_user_inquiries(
            skip=0,
            limit=50,
            db=self.session,
            current_user=self.user,
        )

        self.assertEqual(created.status, "pending")
        self.assertEqual(response.total, 1)
        self.assertEqual(response.items[0].title, "결제 문의")

    def test_user_cannot_read_another_users_inquiry(self) -> None:
        created = self._create_inquiry()

        with self.assertRaises(HTTPException) as context:
            read_user_inquiry_detail(
                inquiry_id=created.id,
                db=self.session,
                current_user=self.other_user,
            )

        self.assertEqual(context.exception.status_code, 403)

    def test_admin_can_read_and_answer_inquiry(self) -> None:
        created = self._create_inquiry()

        listed = read_admin_inquiries(
            skip=0,
            limit=50,
            inquiry_status="pending",
            search=None,
            db=self.session,
            current_admin=self.admin_account,
        )
        with patch("app.api.admin.send_inquiry_answer_email") as send_email:
            answered = answer_admin_inquiry(
                inquiry_id=created.id,
                request=InquiryAnswerUpdateRequest(answer="결제 내역에서 확인할 수 있습니다."),
                db=self.session,
                admin_db=self.admin_session,
                current_admin=self.admin_account,
            )

        self.assertEqual(listed.total, 1)
        self.assertEqual(answered.status, "answered")
        self.assertEqual(answered.answer, "결제 내역에서 확인할 수 있습니다.")
        self.assertEqual(answered.answered_by_admin_id, self.admin_user.id)
        self.assertEqual(
            self.admin_session.query(AdminAuditLog)
            .filter(AdminAuditLog.action == "inquiry.answered")
            .count(),
            1,
        )
        send_email.assert_called_once_with(
            "inquiry@example.com",
            "결제 문의",
            "결제 내역에서 확인할 수 있습니다.",
        )

    def test_admin_can_update_inquiry_status(self) -> None:
        created = self._create_inquiry()

        with patch("app.api.admin.send_inquiry_status_email") as send_email:
            updated = update_admin_inquiry_status(
                inquiry_id=created.id,
                request=InquiryStatusUpdateRequest(status="in_progress"),
                db=self.session,
                admin_db=self.admin_session,
                current_admin=self.admin_account,
            )

        self.assertEqual(updated.status, "in_progress")
        send_email.assert_called_once_with(
            "inquiry@example.com",
            "결제 문의",
            "in_progress",
        )

    def test_inquiry_status_is_saved_when_notification_email_fails(self) -> None:
        created = self._create_inquiry()

        with patch(
            "app.api.admin.send_inquiry_status_email",
            side_effect=RuntimeError("email failed"),
        ):
            updated = update_admin_inquiry_status(
                inquiry_id=created.id,
                request=InquiryStatusUpdateRequest(status="in_progress"),
                db=self.session,
                admin_db=self.admin_session,
                current_admin=self.admin_account,
            )

        self.assertEqual(updated.status, "in_progress")
        self.session.expire_all()
        stored = self.session.query(SupportInquiry).filter_by(id=created.id).one()
        self.assertEqual(stored.status, "in_progress")

    def test_inquiry_status_rolls_back_when_audit_log_fails(self) -> None:
        created = self._create_inquiry()

        with patch(
            "app.api.admin.create_admin_audit_log",
            side_effect=RuntimeError("audit log failed"),
        ):
            with self.assertRaises(RuntimeError):
                update_admin_inquiry_status(
                    inquiry_id=created.id,
                    request=InquiryStatusUpdateRequest(status="in_progress"),
                    db=self.session,
                    admin_db=self.admin_session,
                    current_admin=self.admin_account,
                )

        self.session.expire_all()
        inquiry = (
            self.session.query(SupportInquiry)
            .filter(SupportInquiry.id == created.id)
            .one()
        )
        self.assertEqual(inquiry.status, "pending")


if __name__ == "__main__":
    unittest.main()
