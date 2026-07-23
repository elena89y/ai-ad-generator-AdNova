import json
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.history import (
    delete_generated_result,
    download_generated_result,
    read_histories,
    read_history_detail,
)
from app.database.billing_models import Subscription
from app.database.connection import Base
from app.database.models import Advertisement, History, Image, User
from app.schemas.history import HistoryResponse
from app.services import image_service


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

    def _create_history(self, file_path: Path, user: User | None = None) -> History:
        owner = user or self.user
        output_image = Image(
            user_id=owner.id,
            image_type="generated",
            original_filename="ad.png",
            file_path=str(file_path),
            content_type="image/png",
        )
        self.session.add(output_image)
        self.session.flush()
        advertisement = Advertisement(
            user_id=owner.id,
            output_image_id=output_image.id,
            ad_type="image",
            prompt="test prompt",
            status="completed",
        )
        self.session.add(advertisement)
        self.session.flush()
        history = History(
            user_id=owner.id,
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

    def test_history_list_includes_advertisement_and_image_data(self) -> None:
        input_image = Image(
            user_id=self.user.id,
            image_type="upload",
            original_filename="product.png",
            image_url="/uploads/product.png",
        )
        output_image = Image(
            user_id=self.user.id,
            image_type="generated",
            original_filename="ad.png",
            image_url="/api/ads/image/ad.png",
        )
        self.session.add_all([input_image, output_image])
        self.session.flush()
        advertisement = Advertisement(
            user_id=self.user.id,
            input_image_id=input_image.id,
            output_image_id=output_image.id,
            title="테스트 상품",
            ad_type="image",
            prompt="test prompt",
            generated_text="테스트 광고 문구",
            style="pop",
            status="completed",
        )
        self.session.add(advertisement)
        self.session.flush()
        self.session.add(
            History(
                user_id=self.user.id,
                advertisement_id=advertisement.id,
                action_type="ads.generate",
                status="completed",
            )
        )
        self.session.commit()

        histories = read_histories(
            skip=0,
            limit=50,
            db=self.session,
            current_user=self.user,
        )
        response = HistoryResponse.model_validate(histories[0])

        self.assertEqual(len(histories), 1)
        self.assertEqual(response.advertisement.title, "테스트 상품")
        self.assertEqual(response.advertisement.style, "pop")
        self.assertEqual(response.advertisement.generated_text, "테스트 광고 문구")
        self.assertEqual(response.advertisement.input_image.image_url, "/uploads/product.png")
        self.assertEqual(
            response.advertisement.output_image.image_url,
            "/api/ads/image/ad.png",
        )

    def test_history_list_excludes_other_users(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            own_history = self._create_history(Path(temp_dir) / "own.png")
            self._create_history(
                Path(temp_dir) / "other.png",
                user=self.other_user,
            )

            histories = read_histories(
                skip=0,
                limit=50,
                db=self.session,
                current_user=self.user,
            )

        self.assertEqual([history.id for history in histories], [own_history.id])

    def test_owner_can_read_history_detail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history = self._create_history(Path(temp_dir) / "ad.png")

            detail = read_history_detail(
                history_id=history.id,
                db=self.session,
                current_user=self.user,
            )

        self.assertEqual(detail.id, history.id)
        self.assertEqual(detail.advertisement_id, history.advertisement_id)

    def test_other_user_cannot_read_history_detail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history = self._create_history(Path(temp_dir) / "ad.png")

            with self.assertRaises(HTTPException) as context:
                read_history_detail(
                    history_id=history.id,
                    db=self.session,
                    current_user=self.other_user,
                )

        self.assertEqual(context.exception.status_code, 403)

    def test_missing_history_detail_returns_not_found(self) -> None:
        with self.assertRaises(HTTPException) as context:
            read_history_detail(
                history_id=9999,
                db=self.session,
                current_user=self.user,
            )

        self.assertEqual(context.exception.status_code, 404)

    def test_delete_removes_all_generated_variants_but_keeps_input_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir) / "results"
            results_dir.mkdir()
            input_path = Path(temp_dir) / "product.png"
            input_path.write_bytes(b"input")

            filenames = ["ad.png", "ad-clean.png", "ad-type.png", "ad-banner.jpg"]
            for filename in filenames:
                (results_dir / filename).write_bytes(b"generated")

            input_image = Image(
                user_id=self.user.id,
                image_type="upload",
                original_filename="product.png",
                stored_filename="product.png",
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
            self.session.add_all([input_image, *generated_images])
            self.session.flush()

            advertisement = Advertisement(
                user_id=self.user.id,
                input_image_id=input_image.id,
                output_image_id=generated_images[0].id,
                ad_type="poster",
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
                response_data=json.dumps(
                    {
                        "image_url": "/api/ads/image/ad.png",
                        "image_without_typography_url": "/api/ads/image/ad-clean.png",
                        "image_with_typography_url": "/api/ads/image/ad-type.png",
                        "format_outputs": ["/api/ads/image/ad-banner.jpg"],
                    }
                ),
            )
            self.session.add(history)
            self.session.commit()

            original_results_dir = image_service.RESULTS_DIR
            image_service.RESULTS_DIR = results_dir
            try:
                delete_generated_result(
                    history_id=history.id,
                    db=self.session,
                    current_user=self.user,
                )
            finally:
                image_service.RESULTS_DIR = original_results_dir

            self.assertIsNotNone(self.session.get(Image, input_image.id))
            self.assertTrue(input_path.is_file())
            for image in generated_images:
                self.assertIsNone(self.session.get(Image, image.id))
            for filename in filenames:
                self.assertFalse((results_dir / filename).exists())
            self.assertIsNone(self.session.get(Advertisement, advertisement.id))
            self.assertIsNone(self.session.get(History, history.id))


if __name__ == "__main__":
    unittest.main()
