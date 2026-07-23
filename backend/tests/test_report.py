import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.admin import read_admin_reports, update_admin_report
from app.api.reports import (
    create_user_report,
    read_user_report_detail,
    read_user_reports,
)
from app.database.admin_models import AdminAuditLog, AdminUser
from app.database.connection import AdminBase, Base
from app.database.models import User, UserReport
from app.schemas.report import ReportCreateRequest, ReportStatusUpdateRequest


class ReportApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.user_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.user_engine)
        self.user_db = sessionmaker(bind=self.user_engine)()

        self.admin_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        AdminBase.metadata.create_all(bind=self.admin_engine)
        self.admin_db = sessionmaker(bind=self.admin_engine)()

        self.user = User(
            email="report@example.com",
            username="reportuser",
            password_hash="test-hash",
            is_active=True,
        )
        self.other_user = User(
            email="other-report@example.com",
            username="otheruser",
            password_hash="test-hash",
            is_active=True,
        )
        self.admin = AdminUser(
            email="report-admin@example.com",
            username="reportadmin",
            password_hash="test-hash",
            is_active=True,
            role="operator",
        )
        self.user_db.add_all([self.user, self.other_user])
        self.user_db.commit()
        self.admin_db.add(self.admin)
        self.admin_db.commit()

    def tearDown(self) -> None:
        self.user_db.close()
        self.admin_db.close()
        Base.metadata.drop_all(bind=self.user_engine)
        AdminBase.metadata.drop_all(bind=self.admin_engine)
        self.user_engine.dispose()
        self.admin_engine.dispose()

    def _create_report(self):
        return create_user_report(
            request=ReportCreateRequest(
                category="bug",
                title="광고 생성 오류",
                content="생성 버튼을 눌러도 결과가 나오지 않습니다.",
            ),
            db=self.user_db,
            current_user=self.user,
        )

    def test_user_can_create_and_read_own_reports(self) -> None:
        created = self._create_report()

        listed = read_user_reports(
            skip=0,
            limit=50,
            db=self.user_db,
            current_user=self.user,
        )
        detail = read_user_report_detail(
            report_id=created.id,
            db=self.user_db,
            current_user=self.user,
        )

        self.assertEqual(created.status, "pending")
        self.assertEqual(listed.total, 1)
        self.assertEqual(detail.title, "광고 생성 오류")

    def test_user_cannot_read_another_users_report(self) -> None:
        created = self._create_report()

        with self.assertRaises(HTTPException) as context:
            read_user_report_detail(
                report_id=created.id,
                db=self.user_db,
                current_user=self.other_user,
            )

        self.assertEqual(context.exception.status_code, 403)

    def test_admin_can_list_and_update_report(self) -> None:
        created = self._create_report()

        listed = read_admin_reports(
            skip=0,
            limit=50,
            report_status="pending",
            search="광고",
            db=self.user_db,
            current_admin=self.admin,
        )
        updated = update_admin_report(
            report_id=created.id,
            request=ReportStatusUpdateRequest(
                status="resolved",
                admin_note="생성 서비스 상태를 확인했습니다.",
            ),
            db=self.user_db,
            admin_db=self.admin_db,
            current_admin=self.admin,
        )

        self.assertEqual(listed.total, 1)
        self.assertEqual(updated.status, "resolved")
        self.assertEqual(updated.handled_by_admin_id, self.admin.id)
        self.assertEqual(
            self.admin_db.query(AdminAuditLog)
            .filter(AdminAuditLog.action == "report.status_updated")
            .count(),
            1,
        )

    def test_report_update_rolls_back_when_audit_log_fails(self) -> None:
        created = self._create_report()

        with patch(
            "app.api.admin.create_admin_audit_log",
            side_effect=RuntimeError("audit log failed"),
        ):
            with self.assertRaises(RuntimeError):
                update_admin_report(
                    report_id=created.id,
                    request=ReportStatusUpdateRequest(status="rejected"),
                    db=self.user_db,
                    admin_db=self.admin_db,
                    current_admin=self.admin,
                )

        self.user_db.expire_all()
        report = self.user_db.query(UserReport).filter_by(id=created.id).one()
        self.assertEqual(report.status, "pending")


if __name__ == "__main__":
    unittest.main()
