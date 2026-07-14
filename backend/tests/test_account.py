import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.account import change_password, delete_account
from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.database.billing_models import PaymentMethod, PurchaseHistory, Subscription
from app.database.connection import Base
from app.database.models import Advertisement, History, Image, User
from app.schemas.account import AccountDeleteRequest, PasswordChangeRequest
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

    def test_password_can_be_changed(self) -> None:
        result = change_password(
            request=PasswordChangeRequest(
                current_password=self.password,
                new_password="NewPassword2@",
            ),
            db=self.session,
            current_user=self.user,
        )

        self.assertEqual(result.message, "비밀번호가 변경되었습니다.")
        self.assertTrue(verify_password("NewPassword2@", self.user.password_hash))
        self.assertFalse(verify_password(self.password, self.user.password_hash))

    def test_wrong_current_password_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as context:
            change_password(
                request=PasswordChangeRequest(
                    current_password="WrongPassword1!",
                    new_password="NewPassword2@",
                ),
                db=self.session,
                current_user=self.user,
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
                    PurchaseHistory(
                        user_id=self.user.id,
                        item_type="subscription",
                        description="test",
                        amount=9900,
                        status="paid",
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
                )

            self.assertEqual(self.session.query(User).count(), 0)
            self.assertEqual(self.session.query(Image).count(), 0)
            self.assertEqual(self.session.query(Advertisement).count(), 0)
            self.assertEqual(self.session.query(History).count(), 0)
            self.assertEqual(self.session.query(Subscription).count(), 0)
            self.assertEqual(self.session.query(PaymentMethod).count(), 0)
            self.assertEqual(self.session.query(PurchaseHistory).count(), 0)
            self.assertFalse(input_path.exists())
            self.assertFalse(output_path.exists())

    def test_wrong_password_does_not_delete_account(self) -> None:
        with self.assertRaises(HTTPException) as context:
            delete_account(
                request=AccountDeleteRequest(current_password="WrongPassword1!"),
                db=self.session,
                current_user=self.user,
            )

        self.assertEqual(context.exception.status_code, 400)
        self.assertEqual(self.session.query(User).count(), 1)


if __name__ == "__main__":
    unittest.main()
