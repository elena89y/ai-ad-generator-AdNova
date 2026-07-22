import unittest

from fastapi import HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import pyotp

from app.api.auth import admin_login, admin_refresh, find_username, login, logout, refresh
from app.core.security import create_admin_access_token, get_current_user, hash_password
from app.core.totp import encrypt_totp_secret, generate_totp_secret
from app.database.admin_models import AdminLoginFailureLog, AdminRefreshToken, AdminUser
from app.database.connection import AdminBase, Base
from app.database.models import User, UserRefreshToken
from app.schemas.auth import AdminLoginRequest, UserLogin, UsernameFindRequest


class AuthApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.admin_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        AdminBase.metadata.create_all(bind=self.admin_engine)
        self.admin_session = sessionmaker(bind=self.admin_engine)()
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
        self.admin_session.close()
        AdminBase.metadata.drop_all(bind=self.admin_engine)
        self.admin_engine.dispose()

    def test_login_uses_username(self) -> None:
        result = login(
            user_data=UserLogin(username="LOGINUSER", password="Password1!"),
            response=Response(),
            db=self.session,
            admin_db=self.admin_session,
        )

        self.assertTrue(result["access_token"])
        self.assertEqual(result["user"]["username"], "loginuser")
        self.assertEqual(result["user"]["auth_provider"], "local")

    def test_unknown_username_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as context:
            login(
                user_data=UserLogin(username="missinguser", password="Password1!"),
                response=Response(),
                db=self.session,
                admin_db=self.admin_session,
            )

        self.assertEqual(context.exception.status_code, 401)
        self.assertEqual(context.exception.detail, "아이디 또는 비밀번호가 올바르지 않습니다.")

    def test_admin_account_cannot_use_regular_login(self) -> None:
        admin_user = AdminUser(
            email="admin@example.com",
            username="admin",
            password_hash=hash_password("Password1!"),
            is_active=True,
            role="super_admin",
        )
        self.admin_session.add(admin_user)
        self.admin_session.commit()

        with self.assertRaises(HTTPException) as context:
            login(
                user_data=UserLogin(username="admin", password="Password1!"),
                response=Response(),
                db=self.session,
                admin_db=self.admin_session,
            )

        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(
            context.exception.detail,
            "관리자 계정은 관리자 페이지에서 로그인해 주세요.",
        )

    def test_admin_account_uses_admin_login(self) -> None:
        admin_user = AdminUser(
            email="admin@example.com",
            username="admin",
            password_hash=hash_password("Password1!"),
            is_active=True,
            role="super_admin",
        )
        self.admin_session.add(admin_user)
        self.admin_session.commit()

        result = admin_login(
            user_data=UserLogin(username="admin", password="Password1!"),
            response=Response(),
            admin_db=self.admin_session,
        )

        self.assertTrue(result["access_token"])
        self.assertTrue(result["user"]["is_admin"])
        self.assertEqual(result["user"]["role"], "super_admin")

    def test_admin_token_cannot_access_regular_user_api(self) -> None:
        admin = AdminUser(
            email="admin@example.com",
            username="admin",
            password_hash=hash_password("Password1!"),
            is_active=True,
            role="super_admin",
        )
        self.admin_session.add(admin)
        self.admin_session.commit()

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=create_admin_access_token(admin.id, admin.role),
        )
        with self.assertRaises(HTTPException) as context:
            get_current_user(credentials=credentials, db=self.session)

        self.assertEqual(context.exception.status_code, 403)

    def test_totp_enabled_admin_requires_valid_code(self) -> None:
        secret = generate_totp_secret()
        admin = AdminUser(
            email="admin@example.com",
            username="admin",
            password_hash=hash_password("Password1!"),
            is_active=True,
            role="super_admin",
            totp_secret_encrypted=encrypt_totp_secret(secret),
            totp_enabled=True,
        )
        self.admin_session.add(admin)
        self.admin_session.commit()

        with self.assertRaises(HTTPException) as missing_code:
            admin_login(
                user_data=AdminLoginRequest(username="admin", password="Password1!"),
                response=Response(),
                admin_db=self.admin_session,
            )
        self.assertEqual(missing_code.exception.status_code, 401)

        with self.assertRaises(HTTPException) as invalid_code:
            admin_login(
                user_data=AdminLoginRequest(
                    username="admin",
                    password="Password1!",
                    totp_code="000000",
                ),
                response=Response(),
                admin_db=self.admin_session,
            )
        self.assertEqual(invalid_code.exception.status_code, 401)

        response = admin_login(
            user_data=AdminLoginRequest(
                username="admin",
                password="Password1!",
                totp_code=pyotp.TOTP(secret).now(),
            ),
            response=Response(),
            admin_db=self.admin_session,
        )
        self.assertTrue(response["access_token"])

    def test_regular_user_cannot_use_admin_login(self) -> None:
        regular_user = User(
            email="user@example.com",
            username="regularuser",
            password_hash=hash_password("Password1!"),
            is_active=True,
        )
        self.session.add(regular_user)
        self.session.commit()

        with self.assertRaises(HTTPException) as context:
            admin_login(
                user_data=UserLogin(username="regularuser", password="Password1!"),
                response=Response(),
                admin_db=self.admin_session,
            )

        self.assertEqual(context.exception.status_code, 401)
        login_failure = self.admin_session.query(AdminLoginFailureLog).one()
        self.assertEqual(login_failure.attempted_username, "regularuser")
        self.assertIsNone(login_failure.admin_user_id)
        self.assertEqual(login_failure.reason, "아이디 또는 비밀번호 불일치")

    def test_unknown_admin_login_failure_is_audited(self) -> None:
        with self.assertRaises(HTTPException) as context:
            admin_login(
                user_data=UserLogin(username="missinguser", password="Password1!"),
                response=Response(),
                admin_db=self.admin_session,
            )

        self.assertEqual(context.exception.status_code, 401)
        login_failure = self.admin_session.query(AdminLoginFailureLog).one()
        self.assertEqual(login_failure.attempted_username, "missinguser")
        self.assertIsNone(login_failure.admin_user_id)
        self.assertEqual(login_failure.reason, "아이디 또는 비밀번호 불일치")

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

    def test_login_issues_refresh_cookie_and_refresh_rotates_it(self) -> None:
        login_response = Response()
        login(
            user_data=UserLogin(username="loginuser", password="Password1!", remember_me=True),
            response=login_response,
            db=self.session,
            admin_db=self.admin_session,
        )
        cookie = login_response.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
        self.assertIn("adnova_refresh_token", login_response.headers["set-cookie"])

        refresh_response = Response()
        result = refresh(
            response=refresh_response,
            refresh_token=cookie,
            db=self.session,
        )
        self.assertTrue(result["access_token"])
        self.assertIn("adnova_refresh_token", refresh_response.headers["set-cookie"])

    def test_admin_refresh_cookie_is_rotated(self) -> None:
        admin_user = AdminUser(
            email="admin@example.com",
            username="admin",
            password_hash=hash_password("Password1!"),
            is_active=True,
            role="super_admin",
        )
        self.admin_session.add(admin_user)
        self.admin_session.commit()

        login_response = Response()
        admin_login(
            user_data=AdminLoginRequest(username="admin", password="Password1!", remember_me=True),
            response=login_response,
            admin_db=self.admin_session,
        )
        cookie = login_response.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]

        refresh_response = Response()
        result = admin_refresh(
            response=refresh_response,
            refresh_token=cookie,
            admin_db=self.admin_session,
        )

        self.assertTrue(result["access_token"])
        self.assertIn("adnova_admin_refresh_token", refresh_response.headers["set-cookie"])
        self.assertEqual(self.admin_session.query(AdminRefreshToken).count(), 2)

    def test_logout_revokes_current_refresh_token(self) -> None:
        login_response = Response()
        login(
            user_data=UserLogin(username="loginuser", password="Password1!"),
            response=login_response,
            db=self.session,
            admin_db=self.admin_session,
        )
        cookie = login_response.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]

        logout(
            response=Response(),
            user_refresh_token=cookie,
            admin_refresh_token=None,
            db=self.session,
            admin_db=self.admin_session,
        )

        stored_token = self.session.query(UserRefreshToken).one()
        self.assertIsNotNone(stored_token.revoked_at)


if __name__ == "__main__":
    unittest.main()
