import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials
from PIL import Image as PilImage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import Headers

from app.api.account import (
    change_password,
    delete_account,
    patch_notification_settings,
    read_current_user,
    read_notification_settings,
    read_profile_image,
    upload_profile_image,
)
from app.core.config import settings
from app.core.security import (
    create_access_token,
    get_current_auth_provider,
    hash_password,
    verify_password,
)
from app.database.admin_models import AdminAccount
from app.database.billing_models import (
    PaymentMethod,
    PremiumCreditBalance,
    PurchaseHistory,
    RefundRequest,
    Subscription,
)
from app.database.connection import Base
from app.database.models import (
    Advertisement,
    CreditBalance,
    CreditRefillState,
    History,
    Image,
    NotificationSettings,
    SupportInquiry,
    User,
)
from app.schemas.account import (
    AccountDeleteRequest,
    NotificationSettingsUpdateRequest,
    PasswordChangeRequest,
)
from app.services import image_service


class AccountApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.password = "Password1!"
        self.user = User(
            email="account@example.com",
            username="account1",
            password_hash=hash_password(self.password),
            is_active=True,
        )
        self.session.add(self.user)
        self.session.commit()
        self.session.refresh(self.user)

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    @staticmethod
    def _profile_upload(filename: str) -> UploadFile:
        content = BytesIO()
        PilImage.new("RGB", (2, 2), "white").save(content, format="PNG")
        content.seek(0)
        return UploadFile(
            file=content,
            filename=filename,
            headers=Headers({"content-type": "image/png"}),
        )

    def test_password_can_be_changed(self) -> None:
        result = change_password(
            request=PasswordChangeRequest(
                current_password=self.password,
                new_password="NewPassword2@",
            ),
            db=self.session,
            current_user=self.user,
            auth_provider="local",
        )

        self.assertEqual(result.message, "비밀번호가 변경되었습니다.")
        self.assertTrue(verify_password("NewPassword2@", self.user.password_hash))
        self.assertFalse(verify_password(self.password, self.user.password_hash))

    def test_current_user_endpoint_returns_user_and_auth_provider(self) -> None:
        result = read_current_user(
            current_user=self.user,
            auth_provider="local",
        )

        self.assertEqual(result.id, self.user.id)
        self.assertEqual(result.username, "account1")
        self.assertEqual(result.email, "account@example.com")
        self.assertEqual(result.auth_provider, "local")
        self.assertTrue(result.is_active)

    def test_notification_settings_are_saved_per_user(self) -> None:
        defaults = read_notification_settings(db=self.session, current_user=self.user)
        self.assertTrue(defaults.ad_generation_complete_email)
        self.assertTrue(defaults.credit_depletion_alert)
        self.assertFalse(defaults.marketing_updates)

        updated = patch_notification_settings(
            request=NotificationSettingsUpdateRequest(
                ad_generation_complete_email=False,
                marketing_updates=True,
            ),
            db=self.session,
            current_user=self.user,
        )

        self.assertFalse(updated.ad_generation_complete_email)
        self.assertTrue(updated.credit_depletion_alert)
        self.assertTrue(updated.marketing_updates)
        self.assertEqual(self.session.query(NotificationSettings).count(), 1)

    def test_profile_image_is_replaced_and_read_from_server(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            upload_dir = Path(temp_dir) / "uploads"
            with patch.object(settings, "UPLOAD_DIR", str(upload_dir)):
                first = asyncio.run(
                    upload_profile_image(
                        file=self._profile_upload("first.png"),
                        db=self.session,
                        current_user=self.user,
                    )
                )
                first_path = Path(
                    self.session.query(Image)
                    .filter(Image.id == first.image_id)
                    .one()
                    .file_path
                )

                second = asyncio.run(
                    upload_profile_image(
                        file=self._profile_upload("second.png"),
                        db=self.session,
                        current_user=self.user,
                    )
                )
                profile = read_profile_image(db=self.session, current_user=self.user)

            self.assertEqual(self.session.query(Image).filter(Image.image_type == "profile").count(), 1)
            self.assertEqual(profile.image_url, second.image_url)
            self.assertFalse(first_path.exists())
            self.assertTrue(
                Path(
                    self.session.query(Image)
                    .filter(Image.id == second.image_id)
                    .one()
                    .file_path
                ).exists()
            )

    def test_wrong_current_password_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as context:
            change_password(
                request=PasswordChangeRequest(
                    current_password="WrongPassword1!",
                    new_password="NewPassword2@",
                ),
                db=self.session,
                current_user=self.user,
                auth_provider="local",
            )

        self.assertEqual(context.exception.status_code, 400)
        self.assertTrue(verify_password(self.password, self.user.password_hash))

    def test_current_password_cannot_be_reused(self) -> None:
        with self.assertRaises(HTTPException) as context:
            change_password(
                request=PasswordChangeRequest(
                    current_password=self.password,
                    new_password=self.password,
                ),
                db=self.session,
                current_user=self.user,
                auth_provider="local",
            )

        self.assertEqual(context.exception.status_code, 400)

    def test_account_deletion_removes_related_data_and_image_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            upload_dir = Path(temp_dir) / "uploads"
            results_dir = Path(temp_dir) / "results"
            upload_dir.mkdir()
            results_dir.mkdir()
            input_path = upload_dir / "input.png"
            output_path = results_dir / "output.png"
            input_path.write_bytes(b"input")
            output_path.write_bytes(b"output")

            input_image = Image(
                user_id=self.user.id,
                image_type="upload",
                file_path=str(input_path),
            )
            output_image = Image(
                user_id=self.user.id,
                image_type="generated",
                file_path=str(output_path),
            )
            self.session.add_all([input_image, output_image])
            self.session.flush()

            advertisement = Advertisement(
                user_id=self.user.id,
                input_image_id=input_image.id,
                output_image_id=output_image.id,
                ad_type="image",
                prompt="test prompt",
                status="completed",
            )
            self.session.add(advertisement)
            self.session.flush()
            purchase = PurchaseHistory(
                user_id=self.user.id,
                item_type="subscription",
                description="test",
                amount=9900,
                status="paid",
            )
            self.session.add(purchase)
            self.session.flush()
            self.session.add_all(
                [
                    History(
                        user_id=self.user.id,
                        advertisement_id=advertisement.id,
                        action_type="ads.generate",
                        status="completed",
                    ),
                    Subscription(user_id=self.user.id),
                    PaymentMethod(user_id=self.user.id, provider="demo"),
                    RefundRequest(
                        user_id=self.user.id,
                        purchase_id=purchase.id,
                        amount=9900,
                        reason="test refund",
                    ),
                    SupportInquiry(
                        user_id=self.user.id,
                        category="general",
                        title="test inquiry",
                        content="test content",
                    ),
                    CreditBalance(user_id=self.user.id, free_credits_remaining=2),
                    CreditRefillState(
                        user_id=self.user.id,
                        next_refill_at=datetime.now(timezone.utc) + timedelta(days=1),
                    ),
                    NotificationSettings(
                        user_id=self.user.id,
                        marketing_updates=True,
                    ),
                    PremiumCreditBalance(
                        user_id=self.user.id,
                        credits_remaining=29,
                        next_reset_at=datetime.now(timezone.utc) + timedelta(days=30),
                    ),
                ]
            )
            self.session.commit()

            with (
                patch.object(settings, "UPLOAD_DIR", str(upload_dir)),
                patch.object(image_service, "RESULTS_DIR", results_dir),
            ):
                delete_account(
                    request=AccountDeleteRequest(current_password=self.password),
                    db=self.session,
                    current_user=self.user,
                    auth_provider="local",
                )

            # 탈퇴 회원 본인 계정은 삭제됨 (법정 보존 기록 귀속용 "탈퇴회원" 센티넬만 잔존)
            from app.crud.retention import WITHDRAWN_USERNAME

            self.assertEqual(
                self.session.query(User).filter(User.username != WITHDRAWN_USERNAME).count(), 0
            )
            self.assertEqual(self.session.query(Image).count(), 0)
            self.assertEqual(self.session.query(Advertisement).count(), 0)
            self.assertEqual(self.session.query(History).count(), 0)
            self.assertEqual(self.session.query(Subscription).count(), 0)
            self.assertEqual(self.session.query(PaymentMethod).count(), 0)
            # 법정 보존 기록(문의 3년·구매/환불 5년)은 삭제되지 않고 센티넬로 가명처리-보존된다.
            # (전자상거래법 시행령 제6조 + 개인정보보호법 제21조)
            placeholder = (
                self.session.query(User)
                .filter(User.username == WITHDRAWN_USERNAME)
                .one()
            )
            for model in (PurchaseHistory, RefundRequest, SupportInquiry):
                retained = self.session.query(model).all()
                self.assertEqual(len(retained), 1, f"{model.__name__} 보존돼야 함")
                self.assertEqual(
                    retained[0].user_id, placeholder.id, f"{model.__name__} 센티넬 귀속돼야 함"
                )
                self.assertIsNotNone(
                    retained[0].anonymized_at, f"{model.__name__} anonymized_at 기록돼야 함"
                )
            self.assertEqual(self.session.query(CreditBalance).count(), 0)
            self.assertEqual(self.session.query(CreditRefillState).count(), 0)
            self.assertEqual(self.session.query(PremiumCreditBalance).count(), 0)
            self.assertEqual(self.session.query(NotificationSettings).count(), 0)
            self.assertFalse(input_path.exists())
            self.assertFalse(output_path.exists())

    def test_wrong_password_does_not_delete_account(self) -> None:
        with self.assertRaises(HTTPException) as context:
            delete_account(
                request=AccountDeleteRequest(current_password="WrongPassword1!"),
                db=self.session,
                current_user=self.user,
                auth_provider="local",
            )

        self.assertEqual(context.exception.status_code, 400)
        self.assertEqual(self.session.query(User).count(), 1)

    def test_admin_account_cannot_use_regular_account_deletion(self) -> None:
        self.session.add(
            AdminAccount(
                user_id=self.user.id,
                role="operator",
                is_active=True,
            )
        )
        self.session.commit()

        with self.assertRaises(HTTPException) as context:
            delete_account(
                request=AccountDeleteRequest(current_password=self.password),
                db=self.session,
                current_user=self.user,
                auth_provider="local",
            )

        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(self.session.query(User).count(), 1)
        self.assertEqual(self.session.query(AdminAccount).count(), 1)

    def test_social_login_user_can_delete_account_without_password(self) -> None:
        delete_account(
            request=AccountDeleteRequest(),
            db=self.session,
            current_user=self.user,
            auth_provider="google",
        )

        self.assertEqual(self.session.query(User).count(), 0)

    def test_social_login_user_cannot_change_password(self) -> None:
        with self.assertRaises(HTTPException) as context:
            change_password(
                request=PasswordChangeRequest(
                    current_password=self.password,
                    new_password="NewPassword2@",
                ),
                db=self.session,
                current_user=self.user,
                auth_provider="kakao",
            )

        self.assertEqual(context.exception.status_code, 400)

    def test_social_provider_is_read_from_both_token_fields(self) -> None:
        for payload in (
            {"sub": str(self.user.id), "auth_provider": "google"},
            {"sub": str(self.user.id), "provider": "kakao"},
            {"sub": str(self.user.id), "auth_provider": "naver"},
        ):
            token = create_access_token(payload)
            provider = get_current_auth_provider(
                credentials=HTTPAuthorizationCredentials(
                    scheme="Bearer",
                    credentials=token,
                )
            )
            self.assertIn(provider, {"google", "kakao", "naver"})


if __name__ == "__main__":
    unittest.main()
