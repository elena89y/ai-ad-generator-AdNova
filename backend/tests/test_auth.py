import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.auth import admin_login, find_username, login
from app.core.security import hash_password
from app.database.admin_models import AdminAccount
from app.database.connection import Base
from app.database.models import User
from app.schemas.auth import UserLogin, UsernameFindRequest


class AuthApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.user = User(
            email="login@example.com",
            username="loginuser",
            password_hash=hash_password("Password1!"),
            is_active=True,
        )
        self.session.add(self.user)
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_login_uses_username(self) -> None:
        result = login(
            user_data=UserLogin(username="LOGINUSER", password="Password1!"),
            db=self.session,
        )

        self.assertTrue(result["access_token"])
        self.assertEqual(result["user"]["username"], "loginuser")
        self.assertEqual(result["user"]["auth_provider"], "local")

    def test_unknown_username_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as context:
            login(
                user_data=UserLogin(username="missinguser", password="Password1!"),
                db=self.session,
            )

        self.assertEqual(context.exception.status_code, 401)
        self.assertEqual(context.exception.detail, "아이디 또는 비밀번호가 올바르지 않습니다.")

    def test_admin_account_cannot_use_regular_login(self) -> None:
        admin_user = User(
            email="admin@example.com",
            username="admin",
            password_hash=hash_password("Password1!"),
            is_active=True,
        )
        self.session.add(admin_user)
        self.session.flush()
        self.session.add(
            AdminAccount(
                user_id=admin_user.id,
                role="super_admin",
                is_active=True,
            )
        )
        self.session.commit()

        with self.assertRaises(HTTPException) as context:
            login(
                user_data=UserLogin(username="admin", password="Password1!"),
                db=self.session,
            )

        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(
            context.exception.detail,
            "관리자 계정은 관리자 페이지에서 로그인해 주세요.",
        )

    def test_admin_account_uses_admin_login(self) -> None:
        admin_user = User(
            email="admin@example.com",
            username="admin",
            password_hash=hash_password("Password1!"),
            is_active=True,
        )
        self.session.add(admin_user)
        self.session.flush()
        self.session.add(
            AdminAccount(
                user_id=admin_user.id,
                role="super_admin",
                is_active=True,
            )
        )
        self.session.commit()

        result = admin_login(
            user_data=UserLogin(username="admin", password="Password1!"),
            db=self.session,
        )

        self.assertTrue(result["access_token"])
        self.assertTrue(result["user"]["is_admin"])
        self.assertEqual(result["user"]["role"], "super_admin")

    def test_username_can_be_found_by_email(self) -> None:
        result = find_username(
            request=UsernameFindRequest(email="LOGIN@EXAMPLE.COM"),
            db=self.session,
        )

        self.assertEqual(result.username, "loginuser")

    def test_unknown_email_is_rejected_when_finding_username(self) -> None:
        with self.assertRaises(HTTPException) as context:
            find_username(
                request=UsernameFindRequest(email="missing@example.com"),
                db=self.session,
            )

        self.assertEqual(context.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
