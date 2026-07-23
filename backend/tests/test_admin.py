import json
import tempfile
import unittest
from pathlib import Path

import pyotp

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.admin import (
    confirm_admin_totp,
    create_admin_account_by_super_admin,
    delete_admin_advertisement,
    disable_admin_totp,
    refund_admin_demo_purchase,
    read_admin_accounts,
    read_admin_advertisement_detail,
    read_admin_advertisements,
    read_admin_audit_logs,
    read_admin_me,
    grant_admin_user_bonus_credits,
    setup_admin_totp,
    update_admin_account_status_by_super_admin,
    update_admin_user_status,
)
from app.core.admin_security import get_current_admin, get_current_super_admin
from app.core.security import create_access_token, create_admin_access_token, hash_password
from app.core.totp import decrypt_totp_secret
from app.database.admin_models import AdminAuditLog, AdminUser
from app.database.billing_models import PurchaseHistory, PurchasedCreditBalance
from app.database.connection import AdminBase, Base
from app.database.models import Advertisement, History, Image, User
from app.schemas.admin import (
    AdminAccountCreateRequest,
    AdminAccountStatusUpdateRequest,
    AdminUserStatusUpdateRequest,
    AdminBonusCreditGrantRequest,
    AdminDemoRefundRequest,
    AdminTotpDisableRequest,
    AdminTotpSetupRequest,
    AdminTotpVerifyRequest,
)
from app.services import image_service


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

    def test_admin_account_search_includes_display_name(self) -> None:
        self.admin_db.add(
            AdminUser(
                email="named@example.com",
                username="namedadmin",
                name="검색 관리자",
                password_hash=hash_password("Password1!"),
                role="operator",
                is_active=True,
            )
        )
        self.admin_db.commit()

        response = read_admin_accounts(
            skip=0,
            limit=50,
            search="검색 관리자",
            admin_db=self.admin_db,
            current_admin=self.admin,
        )

        self.assertEqual(response.total, 1)
        self.assertEqual(response.items[0].name, "검색 관리자")

    def test_super_admin_can_refund_credit_pack_and_revoke_remaining_credits(self) -> None:
        purchase = PurchaseHistory(
            user_id=self.user.id,
            provider="demo",
            item_type="credit_pack",
            description="크레딧 10개 (테스트)",
            amount=4900,
            status="paid",
        )
        self.user_db.add_all(
            [
                purchase,
                PurchasedCreditBalance(user_id=self.user.id, credits_remaining=10),
            ]
        )
        self.user_db.commit()

        response = refund_admin_demo_purchase(
            purchase_id=purchase.id,
            request=AdminDemoRefundRequest(reason="구매 취소 요청"),
            db=self.user_db,
            admin_db=self.admin_db,
            current_admin=self.admin,
        )

        balance = self.user_db.query(PurchasedCreditBalance).filter_by(user_id=self.user.id).one()
        self.assertEqual(response.purchased_credits_revoked, 10)
        self.assertEqual(balance.credits_remaining, 0)
        self.assertEqual(response.purchase.status, "refunded")

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

    def test_super_admin_can_grant_bonus_credits_with_audit_log(self) -> None:
        response = grant_admin_user_bonus_credits(
            user_id=self.user.id,
            request=AdminBonusCreditGrantRequest(amount=12),
            db=self.user_db,
            admin_db=self.admin_db,
            current_admin=self.admin,
        )

        self.assertEqual(response.bonus_credits_remaining, 12)
        audit_log = self.admin_db.query(AdminAuditLog).filter_by(
            action="user.bonus_credits_granted"
        ).one()
        self.assertEqual(audit_log.target_id, self.user.id)
        self.assertIn("amount=12", audit_log.detail)

    def test_super_admin_can_manage_advertisements_without_deleting_input_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir) / "results"
            results_dir.mkdir()
            input_path = Path(temp_dir) / "product.png"
            input_path.write_bytes(b"input")
            filenames = ["ad.png", "ad-clean.png", "ad-banner.jpg"]
            for filename in filenames:
                (results_dir / filename).write_bytes(b"generated")

            input_image = Image(
                user_id=self.user.id,
                image_type="upload",
                original_filename="product.png",
                file_path=str(input_path),
                image_url="/uploads/product.png",
            )
            generated_images = [
                Image(
                    user_id=self.user.id,
                    image_type="generated",
                    original_filename=filename,
                    stored_filename=filename,
                    file_path=str(results_dir / filename),
                    image_url=f"/api/ads/image/{filename}",
                )
                for filename in filenames
            ]
            self.user_db.add_all([input_image, *generated_images])
            self.user_db.flush()

            advertisement = Advertisement(
                user_id=self.user.id,
                input_image_id=input_image.id,
                output_image_id=generated_images[0].id,
                title="테스트 라떼",
                ad_type="poster",
                prompt="test prompt",
                style="pop",
                status="completed",
            )
            self.user_db.add(advertisement)
            self.user_db.flush()
            self.user_db.add(
                History(
                    user_id=self.user.id,
                    advertisement_id=advertisement.id,
                    action_type="ads.generate",
                    status="completed",
                    response_data=json.dumps(
                        {
                            "image_url": "/api/ads/image/ad.png",
                            "image_without_typography_url": "/api/ads/image/ad-clean.png",
                            "format_outputs": ["/api/ads/image/ad-banner.jpg"],
                        }
                    ),
                )
            )
            self.user_db.commit()

            listing = read_admin_advertisements(
                skip=0,
                limit=50,
                user_id=self.user.id,
                search="라떼",
                status="completed",
                db=self.user_db,
                current_admin=self.admin,
            )
            self.assertEqual(listing.total, 1)
            self.assertEqual(listing.items[0].output_image_url, "/api/ads/image/ad.png")

            detail = read_admin_advertisement_detail(
                advertisement_id=advertisement.id,
                db=self.user_db,
                current_admin=self.admin,
            )
            self.assertEqual(detail.username, self.user.username)
            self.assertEqual(detail.title, "테스트 라떼")

            original_results_dir = image_service.RESULTS_DIR
            image_service.RESULTS_DIR = results_dir
            try:
                delete_admin_advertisement(
                    advertisement_id=advertisement.id,
                    db=self.user_db,
                    admin_db=self.admin_db,
                    current_admin=self.admin,
                )
            finally:
                image_service.RESULTS_DIR = original_results_dir

            self.assertIsNotNone(self.user_db.get(Image, input_image.id))
            self.assertTrue(input_path.is_file())
            for image in generated_images:
                self.assertIsNone(self.user_db.get(Image, image.id))
            for filename in filenames:
                self.assertFalse((results_dir / filename).exists())
            self.assertIsNone(self.user_db.get(Advertisement, advertisement.id))
            self.assertEqual(
                self.admin_db.query(AdminAuditLog)
                .filter_by(action="advertisement.force_deleted")
                .count(),
                1,
            )

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

    def test_admin_can_enable_and_disable_totp(self) -> None:
        setup = setup_admin_totp(
            request=AdminTotpSetupRequest(current_password="Password1!"),
            admin_db=self.admin_db,
            current_admin=self.admin,
        )
        self.assertTrue(setup.provisioning_uri.startswith("otpauth://totp/"))
        self.assertNotEqual(self.admin.totp_secret_encrypted, setup.manual_entry_key)
        self.assertFalse(self.admin.totp_enabled)

        code = pyotp.TOTP(setup.manual_entry_key).now()
        confirm_admin_totp(
            request=AdminTotpVerifyRequest(code=code),
            admin_db=self.admin_db,
            current_admin=self.admin,
        )
        self.assertTrue(self.admin.totp_enabled)
        self.assertEqual(
            decrypt_totp_secret(self.admin.totp_secret_encrypted),
            setup.manual_entry_key,
        )

        disable_admin_totp(
            request=AdminTotpDisableRequest(
                current_password="Password1!",
                code=code,
            ),
            admin_db=self.admin_db,
            current_admin=self.admin,
        )
        self.assertFalse(self.admin.totp_enabled)
        self.assertIsNone(self.admin.totp_secret_encrypted)


if __name__ == "__main__":
    unittest.main()
