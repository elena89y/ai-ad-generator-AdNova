import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.admin import read_admin_me
from app.core.admin_security import get_current_admin
from app.database.admin_models import AdminAccount
from app.database.connection import Base
from app.database.models import User


class AdminApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()

        self.user = User(
            email="user@example.com",
            username="normaluser",
            password_hash="test-hash",
            is_active=True,
        )
        self.admin_user = User(
            email="admin@example.com",
            username="adminuser",
            password_hash="test-hash",
            is_active=True,
        )
        self.session.add_all([self.user, self.admin_user])
        self.session.commit()

        self.admin_account = AdminAccount(
            user_id=self.admin_user.id,
            role="super_admin",
        )
        self.session.add(self.admin_account)
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_normal_user_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as context:
            get_current_admin(current_user=self.user, db=self.session)

        self.assertEqual(context.exception.status_code, 403)

    def test_active_admin_can_read_own_admin_profile(self) -> None:
        current_admin = get_current_admin(
            current_user=self.admin_user,
            db=self.session,
        )

        response = read_admin_me(
            current_user=self.admin_user,
            current_admin=current_admin,
        )

        self.assertEqual(response.username, "adminuser")
        self.assertEqual(response.role, "super_admin")

    def test_inactive_admin_is_rejected(self) -> None:
        self.admin_account.is_active = False
        self.session.commit()

        with self.assertRaises(HTTPException) as context:
            get_current_admin(current_user=self.admin_user, db=self.session)

        self.assertEqual(context.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
