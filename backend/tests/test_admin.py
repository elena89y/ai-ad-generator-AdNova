import unittest

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.admin import (
    create_admin_account_by_super_admin,
    read_admin_accounts,
    read_admin_audit_logs,
    read_admin_me,
    update_admin_account_status_by_super_admin,
    update_admin_user_status,
)
from app.core.admin_security import get_current_admin, get_current_super_admin
from app.core.security import create_access_token, create_admin_access_token, hash_password
from app.database.admin_models import AdminAuditLog, AdminUser
from app.database.connection import AdminBase, Base
from app.database.models import User
from app.schemas.admin import (
    AdminAccountCreateRequest,
    AdminAccountStatusUpdateRequest,
    AdminUserStatusUpdateRequest,
)


class AdminApiTestCase(unittest.TestCase):
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
            email="user@example.com",
            username="normaluser",
            password_hash=hash_password("Password1!"),
            is_active=True,
        )
        self.admin = AdminUser(
            email="admin@example.com",
            username="adminuser",
            password_hash=hash_password("Password1!"),
            role="super_admin",
            is_active=True,
        )
        self.user_db.add(self.user)
        self.admin_db.add(self.admin)
        self.user_db.commit()
        self.admin_db.commit()

    def tearDown(self) -> None:
        self.user_db.close()
        self.admin_db.close()
        Base.metadata.drop_all(bind=self.user_engine)
        AdminBase.metadata.drop_all(bind=self.admin_engine)
        self.user_engine.dispose()
        self.admin_engine.dispose()

    def _admin_credentials(self, admin: AdminUser | None = None):
        current = admin or self.admin
        return HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=create_admin_access_token(current.id, current.role),
        )

    def test_regular_user_token_is_rejected_for_admin_api(self) -> None:
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=create_access_token({"sub": str(self.user.id)}),
        )

        with self.assertRaises(HTTPException) as context:
            get_current_admin(credentials=credentials, admin_db=self.admin_db)

        self.assertEqual(context.exception.status_code, 403)

    def test_admin_token_returns_separate_admin_identity(self) -> None:
        current_admin = get_current_admin(
            credentials=self._admin_credentials(),
            admin_db=self.admin_db,
        )
        response = read_admin_me(current_admin=current_admin)

        self.assertEqual(response.id, self.admin.id)
        self.assertEqual(response.username, "adminuser")
        self.assertEqual(response.role, "super_admin")

    def test_super_admin_can_create_operator_in_admin_database(self) -> None:
        response = create_admin_account_by_super_admin(
            request=AdminAccountCreateRequest(
                username="operator",
                email="operator@example.com",
                password="Password1!",
                name="운영 관리자",
                role="operator",
            ),
            db=self.user_db,
            admin_db=self.admin_db,
            current_admin=self.admin,
        )

        self.assertEqual(response.role, "operator")
        self.assertIsNone(
            self.user_db.query(User).filter(User.username == "operator").first()
        )
        operator = self.admin_db.query(AdminUser).filter_by(username="operator").one()
        self.assertEqual(operator.email, "operator@example.com")
        self.assertEqual(
            self.admin_db.query(AdminAuditLog)
            .filter_by(action="admin.account_created")
            .count(),
            1,
        )

    def test_admin_accounts_are_listed_from_admin_database(self) -> None:
        self.admin_db.add(
            AdminUser(
                email="operator@example.com",
                username="operator",
                password_hash=hash_password("Password1!"),
                role="operator",
                is_active=True,
            )
        )
        self.admin_db.commit()

        response = read_admin_accounts(
            skip=0,
            limit=50,
            search=None,
            admin_db=self.admin_db,
            current_admin=self.admin,
        )

        self.assertEqual(response.total, 2)
        self.assertEqual({item.username for item in response.items}, {"adminuser", "operator"})

    def test_last_active_super_admin_cannot_be_deactivated(self) -> None:
        with self.assertRaises(HTTPException) as context:
            update_admin_account_status_by_super_admin(
                admin_account_id=self.admin.id,
                request=AdminAccountStatusUpdateRequest(is_active=False),
                admin_db=self.admin_db,
                current_admin=self.admin,
            )

        self.assertEqual(context.exception.status_code, 400)

    def test_operator_cannot_use_super_admin_dependency(self) -> None:
        operator = AdminUser(
            email="operator@example.com",
            username="operator",
            password_hash=hash_password("Password1!"),
            role="operator",
            is_active=True,
        )
        self.admin_db.add(operator)
        self.admin_db.commit()

        with self.assertRaises(HTTPException) as context:
            get_current_super_admin(current_admin=operator)

        self.assertEqual(context.exception.status_code, 403)

    def test_user_status_change_writes_audit_log_to_admin_database(self) -> None:
        response = update_admin_user_status(
            user_id=self.user.id,
            request=AdminUserStatusUpdateRequest(is_active=False),
            db=self.user_db,
            admin_db=self.admin_db,
            current_admin=self.admin,
        )

        self.assertFalse(response.is_active)
        self.user_db.refresh(self.user)
        self.assertFalse(self.user.is_active)
        audit_log = self.admin_db.query(AdminAuditLog).filter_by(
            action="user.status_updated"
        ).one()
        self.assertEqual(audit_log.admin_user_id, self.admin.id)
        self.assertEqual(audit_log.target_id, self.user.id)

    def test_audit_log_api_reads_admin_database(self) -> None:
        self.admin_db.add(
            AdminAuditLog(
                admin_user_id=self.admin.id,
                action="admin.account_created",
                target_type="admin_account",
                target_id=self.admin.id,
                detail="test",
            )
        )
        self.admin_db.commit()

        response = read_admin_audit_logs(
            skip=0,
            limit=50,
            action="admin.account_created",
            admin_db=self.admin_db,
            current_admin=self.admin,
        )

        self.assertEqual(response.total, 1)
        self.assertEqual(response.items[0].admin_username, "adminuser")


if __name__ == "__main__":
    unittest.main()
