import asyncio
from datetime import timedelta
from io import BytesIO
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, UploadFile
from PIL import Image as PilImage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import Headers

from app.api.images import read_uploaded_image
from app.api.images import upload_image
from app.crud.image import create_image, purge_expired_unreferenced_uploads
from app.database.connection import Base
from app.database.models import Advertisement, Image, User, utc_now
from app.core.security import hash_password


class ImagePrivacyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.owner = User(
            email="owner@example.com",
            username="owneruser",
            password_hash=hash_password("Password1!"),
            is_active=True,
        )
        self.other_user = User(
            email="other@example.com",
            username="otheruser",
            password_hash=hash_password("Password1!"),
            is_active=True,
        )
        self.session.add_all([self.owner, self.other_user])
        self.session.commit()
        self.session.refresh(self.owner)
        self.session.refresh(self.other_user)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.upload_dir = Path(self.temp_dir.name)
        self.upload_path = self.upload_dir / "input.png"
        self.upload_path.write_bytes(b"input image")

    @staticmethod
    def _png_upload() -> UploadFile:
        content = BytesIO()
        PilImage.new("RGB", (2, 2), "white").save(content, format="PNG")
        content.seek(0)
        return UploadFile(
            file=content,
            filename="input.png",
            headers=Headers({"content-type": "image/png"}),
        )

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_upload_image_is_available_only_to_owner(self) -> None:
        image = create_image(
            self.session,
            user_id=self.owner.id,
            image_type="upload",
            file_path=str(self.upload_path),
            content_type="image/png",
            image_url=f"/api/images/1",
        )

        with patch("app.api.images.UPLOAD_DIR", self.upload_dir):
            response = read_uploaded_image(image.id, self.session, self.owner)

            self.assertEqual(Path(response.path), self.upload_path)
            with self.assertRaises(HTTPException) as context:
                read_uploaded_image(image.id, self.session, self.other_user)

        self.assertEqual(context.exception.status_code, 404)

    def test_upload_response_uses_private_image_url(self) -> None:
        with patch("app.api.images.UPLOAD_DIR", self.upload_dir):
            response = asyncio.run(
                upload_image(
                    file=self._png_upload(),
                    db=self.session,
                    current_user=self.owner,
                )
            )

        self.assertEqual(response.image_url, f"/api/images/{response.image_id}")
        image = self.session.query(Image).filter(Image.id == response.image_id).one()
        self.assertEqual(image.image_url, response.image_url)
        self.assertTrue(Path(image.file_path).is_file())

    def test_expired_unreferenced_upload_is_purged_but_legacy_input_is_kept(self) -> None:
        stale_path = self.upload_dir / "stale.png"
        legacy_path = self.upload_dir / "legacy.png"
        stale_path.write_bytes(b"stale")
        legacy_path.write_bytes(b"legacy")
        stale = Image(
            user_id=self.owner.id,
            image_type="upload",
            file_path=str(stale_path),
            created_at=utc_now() - timedelta(hours=25),
        )
        legacy = Image(
            user_id=self.owner.id,
            image_type="upload",
            file_path=str(legacy_path),
            created_at=utc_now() - timedelta(hours=25),
        )
        self.session.add_all([stale, legacy])
        self.session.flush()
        self.session.add(
            Advertisement(
                user_id=self.owner.id,
                input_image_id=legacy.id,
                ad_type="image",
                prompt="legacy",
            )
        )
        self.session.commit()

        paths = purge_expired_unreferenced_uploads(
            self.session,
            created_before=utc_now() - timedelta(hours=24),
        )

        self.assertEqual(paths, [str(stale_path)])
        self.assertIsNone(self.session.get(Image, stale.id))
        self.assertIsNotNone(self.session.get(Image, legacy.id))

if __name__ == "__main__":
    unittest.main()
