import unittest
from unittest.mock import patch

from fastapi import HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import pyotp

from app.api.auth import (
    admin_login,
    admin_refresh,
    confirm_password_reset,
    extend_admin_session,
    find_username,
    login,
    logout,
    refresh,
    request_password_reset,
)
from app.core.refresh_tokens import issue_user_refresh_token
from app.core.security import (
    create_admin_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.core.totp import encrypt_totp_secret, generate_totp_secret
from app.database.admin_models import AdminLoginFailureLog, AdminRefreshToken, AdminUser
from app.database.connection import AdminBase, Base
from app.database.models import PasswordResetToken, User, UserRefreshToken
from app.schemas.auth import (
    AdminLoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    UserLogin,
    UsernameFindRequest,
)


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

    @patch("app.api.auth.send_password_reset_email")
    def test_password_reset_changes_password_and_invalidates_token(self, send_email) -> None:
        issue_user_refresh_token(
            self.session,
            Response(),
            user_id=self.user.id,
            auth_provider="local",
            is_persistent=False,
        )
        request_password_reset(
            request=PasswordResetRequest(email="LOGIN@EXAMPLE.COM"),
            db=self.session,
        )
        send_email.assert_called_once()
        raw_token = send_email.call_args.args[1]

        result = confirm_password_reset(
            request=PasswordResetConfirm(
                token=raw_token,
                new_password="NewPassword1!",
            ),
            db=self.session,
        )

        self.assertIn("비밀번호가 변경되었습니다", result["message"])
        self.session.refresh(self.user)
        self.assertTrue(verify_password("NewPassword1!", self.user.password_hash))
        token = self.session.query(PasswordResetToken).one()
        self.assertIsNotNone(token.used_at)
        self.assertIsNotNone(self.session.query(UserRefreshToken).one().revoked_at)

        with self.assertRaises(HTTPException) as context:
            confirm_password_reset(
                request=PasswordResetConfirm(
                    token=raw_token,
                    new_password="AnotherPassword1!",
                ),
                db=self.session,
            )
        self.assertEqual(context.exception.status_code, 400)

    @patch("app.api.auth.send_password_reset_email")
    def test_password_reset_request_does_not_reveal_unknown_email(self, send_email) -> None:
        result = request_password_reset(
            request=PasswordResetRequest(email="missing@example.com"),
            db=self.session,
        )

        self.assertIn("가입된 이메일이라면", result["message"])
        send_email.assert_not_called()

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
        original_token = self.admin_session.query(AdminRefreshToken).one()
        original_expiry = original_token.expires_at

        refresh_response = Response()
        result = admin_refresh(
            response=refresh_response,
            refresh_token=cookie,
            admin_db=self.admin_session,
        )

        self.assertTrue(result["access_token"])
        self.assertIn("adnova_admin_refresh_token", refresh_response.headers["set-cookie"])
        self.assertEqual(self.admin_session.query(AdminRefreshToken).count(), 2)
        refreshed_token = (
            self.admin_session.query(AdminRefreshToken)
            .filter(AdminRefreshToken.revoked_at.is_(None))
            .one()
        )
        self.assertFalse(refreshed_token.is_persistent)
        self.assertEqual(refreshed_token.expires_at, original_expiry)

    def test_admin_session_is_not_persistent_and_can_be_extended(self) -> None:
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
        original_token = self.admin_session.query(AdminRefreshToken).one()
        original_expiry = original_token.expires_at

        self.assertFalse(original_token.is_persistent)
        self.assertNotIn("Max-Age", login_response.headers["set-cookie"])

        extend_response = Response()
        result = extend_admin_session(
            response=extend_response,
            refresh_token=cookie,
            admin_db=self.admin_session,
        )

        self.assertTrue(result["access_token"])
        self.assertEqual(self.admin_session.query(AdminRefreshToken).count(), 2)
        self.assertIsNotNone(original_token.revoked_at)
        extended_token = (
            self.admin_session.query(AdminRefreshToken)
            .filter(AdminRefreshToken.revoked_at.is_(None))
            .one()
        )
        self.assertFalse(extended_token.is_persistent)
        self.assertGreaterEqual(extended_token.expires_at, original_expiry)

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

    def test_social_login_session_keeps_provider_on_refresh_token(self) -> None:
        response = Response()
        issue_user_refresh_token(
            self.session,
            response,
            user_id=self.user.id,
            auth_provider="google",
            is_persistent=False,
        )

        stored_token = self.session.query(UserRefreshToken).one()
        self.assertEqual(stored_token.auth_provider, "google")
        self.assertFalse(stored_token.is_persistent)
        self.assertIn("adnova_refresh_token", response.headers["set-cookie"])
        self.assertNotIn("Max-Age", response.headers["set-cookie"])


if __name__ == "__main__":
    unittest.main()
