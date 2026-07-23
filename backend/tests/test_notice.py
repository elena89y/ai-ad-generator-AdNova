import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.admin import (
    create_admin_notice,
    delete_admin_notice,
    read_admin_notices,
    update_admin_notice,
)
from app.api.notices import read_published_notice_detail, read_published_notices
from app.database.admin_models import AdminAuditLog, AdminUser
from app.database.connection import AdminBase, Base
from app.database.models import Notice
from app.schemas.admin import AdminMessageResponse
from app.schemas.notice import NoticeCreateRequest, NoticeUpdateRequest


class NoticeApiTestCase(unittest.TestCase):
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
        self.admin = AdminUser(
            email="notice-admin@example.com",
            username="noticeadmin",
            password_hash="test-hash",
            is_active=True,
            role="operator",
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

    def _create_draft(self):
        return create_admin_notice(
            request=NoticeCreateRequest(
                title="서비스 점검 안내",
                content="오늘 자정부터 30분 동안 서비스 점검이 예정되어 있습니다.",
            ),
            db=self.user_db,
            admin_db=self.admin_db,
            current_admin=self.admin,
        )

    def test_draft_is_hidden_from_public_users(self) -> None:
        created = self._create_draft()

        listed = read_published_notices(skip=0, limit=50, db=self.user_db)
        self.assertEqual(listed.total, 0)

        with self.assertRaises(HTTPException) as context:
            read_published_notice_detail(notice_id=created.id, db=self.user_db)
        self.assertEqual(context.exception.status_code, 404)

    def test_admin_can_publish_and_public_users_can_read_notice(self) -> None:
        created = self._create_draft()

        updated = update_admin_notice(
            notice_id=created.id,
            request=NoticeUpdateRequest(is_published=True),
            db=self.user_db,
            admin_db=self.admin_db,
            current_admin=self.admin,
        )
        listed = read_published_notices(skip=0, limit=50, db=self.user_db)
        detail = read_published_notice_detail(notice_id=created.id, db=self.user_db)

        self.assertTrue(updated.is_published)
        self.assertIsNotNone(updated.published_at)
        self.assertEqual(listed.total, 1)
        self.assertEqual(detail.title, "서비스 점검 안내")
        self.assertEqual(
            self.admin_db.query(AdminAuditLog)
            .filter(AdminAuditLog.action == "notice.published")
            .count(),
            1,
        )

    def test_admin_can_list_and_delete_notice(self) -> None:
        created = self._create_draft()

        listed = read_admin_notices(
            skip=0,
            limit=50,
            is_published=False,
            search="점검",
            db=self.user_db,
            current_admin=self.admin,
        )
        response = delete_admin_notice(
            notice_id=created.id,
            db=self.user_db,
            admin_db=self.admin_db,
            current_admin=self.admin,
        )

        self.assertEqual(listed.total, 1)
        self.assertIsInstance(response, AdminMessageResponse)
        self.assertIsNone(self.user_db.query(Notice).filter_by(id=created.id).first())
        self.assertEqual(
            self.admin_db.query(AdminAuditLog)
            .filter(AdminAuditLog.action == "notice.deleted")
            .count(),
            1,
        )

    def test_notice_update_rolls_back_when_audit_log_fails(self) -> None:
        created = self._create_draft()

        with patch(
            "app.api.admin.create_admin_audit_log",
            side_effect=RuntimeError("audit log failed"),
        ):
            with self.assertRaises(RuntimeError):
                update_admin_notice(
                    notice_id=created.id,
                    request=NoticeUpdateRequest(is_published=True),
                    db=self.user_db,
                    admin_db=self.admin_db,
                    current_admin=self.admin,
                )

        self.user_db.expire_all()
        notice = self.user_db.query(Notice).filter_by(id=created.id).one()
        self.assertFalse(notice.is_published)


if __name__ == "__main__":
    unittest.main()
