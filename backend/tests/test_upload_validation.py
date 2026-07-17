from io import BytesIO
import unittest

from fastapi import HTTPException
from PIL import Image

from app.services.upload_validation import validate_image_content


def make_png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (4, 4), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


class UploadValidationTestCase(unittest.TestCase):
    def test_valid_png_is_accepted(self) -> None:
        validate_image_content(
            make_png_bytes(),
            suffix=".png",
            content_type="image/png",
        )

    def test_non_image_bytes_are_rejected(self) -> None:
        with self.assertRaises(HTTPException) as context:
            validate_image_content(
                b"not-an-image",
                suffix=".png",
                content_type="image/png",
            )

        self.assertEqual(context.exception.status_code, 400)

    def test_image_format_must_match_metadata(self) -> None:
        with self.assertRaises(HTTPException) as context:
            validate_image_content(
                make_png_bytes(),
                suffix=".jpg",
                content_type="image/jpeg",
            )

        self.assertEqual(context.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
