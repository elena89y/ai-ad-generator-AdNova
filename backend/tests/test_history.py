import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.history import download_generated_result
from app.database.billing_models import Subscription
from app.database.connection import Base
from app.database.models import Advertisement, History, Image, User


class HistoryDownloadApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.user = User(
            email="history@example.com",
            username="history1",
            password_hash="test-hash",
            is_active=True,
        )
        self.other_user = User(
            email="other-history@example.com",
            username="history2",
            password_hash="test-hash",
            is_active=True,
        )
        self.session.add_all([self.user, self.other_user])
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _create_history(self, file_path: Path) -> History:
        output_image = Image(
            user_id=self.user.id,
            image_type="generated",
            original_filename="ad.png",
            file_path=str(file_path),
            content_type="image/png",
        )
        self.session.add(output_image)
        self.session.flush()
        advertisement = Advertisement(
            user_id=self.user.id,
            output_image_id=output_image.id,
            ad_type="image",
            prompt="test prompt",
            status="completed",
        )
        self.session.add(advertisement)
        self.session.flush()
        history = History(
            user_id=self.user.id,
            advertisement_id=advertisement.id,
            action_type="ads.generate",
            status="completed",
        )
        self.session.add(history)
        self.session.commit()
        self.session.refresh(history)
        return history

    def test_premium_user_can_download_own_generated_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "ad.png"
            image_path.write_bytes(b"image")
            history = self._create_history(image_path)
            self.session.add(
                Subscription(
                    user_id=self.user.id,
                    plan="premium",
                    status="active",
                )
            )
            self.session.commit()

            response = download_generated_result(
                history_id=history.id,
                db=self.session,
                current_user=self.user,
            )

            self.assertIn("attachment", response.headers["content-disposition"])
            self.assertIn("ad.png", response.headers["content-disposition"])

    def test_free_user_cannot_download_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "ad.png"
            image_path.write_bytes(b"image")
            history = self._create_history(image_path)

            with self.assertRaises(HTTPException) as context:
                download_generated_result(
                    history_id=history.id,
                    db=self.session,
                    current_user=self.user,
                )

            self.assertEqual(context.exception.status_code, 403)

    def test_other_user_cannot_download_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "ad.png"
            image_path.write_bytes(b"image")
            history = self._create_history(image_path)
            self.session.add(
                Subscription(
                    user_id=self.other_user.id,
                    plan="premium",
                    status="active",
                )
            )
            self.session.commit()

            with self.assertRaises(HTTPException) as context:
                download_generated_result(
                    history_id=history.id,
                    db=self.session,
                    current_user=self.other_user,
                )

            self.assertEqual(context.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
