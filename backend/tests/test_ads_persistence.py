import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.ads import _record_generated_result, get_result_image
from app.database.connection import Base
from app.database.models import Advertisement, History, Image, User
from app.schemas.ads import GenerateAdResponse, StylePreset
from app.services import image_service


class AdsPersistenceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.user = User(
            email="ads-owner@example.com",
            username="adsowner",
            password_hash="test-hash",
            is_active=True,
        )
        self.other_user = User(
            email="ads-other@example.com",
            username="adsother",
            password_hash="test-hash",
            is_active=True,
        )
        self.session.add_all([self.user, self.other_user])
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    @staticmethod
    def _result(filename: str) -> GenerateAdResponse:
        return GenerateAdResponse(
            asset_id="abcdef123456",
            seed=1,
            style=StylePreset.POP,
            copy_text="광고 문구",
            image_url=f"/api/ads/image/{filename}",
            poster=False,
            generate_seconds=0.1,
            harmonize_seconds=0.1,
        )

    def test_generated_result_records_are_committed_together(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            (results_dir / "result.png").write_bytes(b"image")

            with (
                patch.object(image_service, "RESULTS_DIR", results_dir),
                patch("app.api.ads.create_history", side_effect=RuntimeError("failed")),
            ):
                with self.assertRaises(RuntimeError):
                    _record_generated_result(
                        self.session,
                        user_id=self.user.id,
                        input_image_id=None,
                        product_name="상품",
                        style=StylePreset.POP,
                        poster=False,
                        prompt_for_db="{}",
                        result=self._result("result.png"),
                        action_type="ads.generate",
                        request_data="{}",
                    )

            self.assertEqual(self.session.query(Image).count(), 0)
            self.assertEqual(self.session.query(Advertisement).count(), 0)
            self.assertEqual(self.session.query(History).count(), 0)

    def test_generated_result_returns_saved_history_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            (results_dir / "result.png").write_bytes(b"image")

            with patch.object(image_service, "RESULTS_DIR", results_dir):
                history_id = _record_generated_result(
                    self.session,
                    user_id=self.user.id,
                    input_image_id=None,
                    product_name="상품",
                    style=StylePreset.POP,
                    poster=False,
                    prompt_for_db="{}",
                    result=self._result("result.png"),
                    action_type="ads.generate",
                    request_data="{}",
                )

            history = self.session.get(History, history_id)
            self.assertIsNotNone(history)
            self.assertEqual(history.advertisement_id, history.advertisement.id)

    def test_owner_can_read_generated_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            image_path = results_dir / "owned.png"
            image_path.write_bytes(b"image")
            self.session.add(
                Image(
                    user_id=self.user.id,
                    image_type="generated",
                    stored_filename=image_path.name,
                    file_path=str(image_path),
                    content_type="image/png",
                )
            )
            self.session.commit()

            with patch.object(image_service, "RESULTS_DIR", results_dir):
                response = get_result_image(
                    filename=image_path.name,
                    db=self.session,
                    current_user=self.user,
                )

            self.assertEqual(Path(response.path), image_path)

    def test_other_user_cannot_read_generated_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            image_path = results_dir / "private.png"
            image_path.write_bytes(b"image")
            self.session.add(
                Image(
                    user_id=self.user.id,
                    image_type="generated",
                    stored_filename=image_path.name,
                    file_path=str(image_path),
                )
            )
            self.session.commit()

            with (
                patch.object(image_service, "RESULTS_DIR", results_dir),
                self.assertRaises(HTTPException) as context,
            ):
                get_result_image(
                    filename=image_path.name,
                    db=self.session,
                    current_user=self.other_user,
                )

            self.assertEqual(context.exception.status_code, 404)

    def test_generated_image_path_traversal_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as context:
            get_result_image(
                filename="../private.png",
                db=self.session,
                current_user=self.user,
            )

        self.assertEqual(context.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
