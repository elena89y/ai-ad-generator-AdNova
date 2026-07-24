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

    def test_image_format_metadata_mismatch_is_accepted(self) -> None:
        detected_format = validate_image_content(
            make_png_bytes(),
            suffix=".jpg",
            content_type="image/jpeg",
        )

        self.assertEqual(detected_format, "PNG")

    def test_unsupported_image_format_is_rejected(self) -> None:
        buffer = BytesIO()
        Image.new("RGB", (4, 4), color="white").save(buffer, format="GIF")

        with self.assertRaises(HTTPException) as context:
            validate_image_content(buffer.getvalue())

        self.assertEqual(context.exception.status_code, 400)

    def test_reader_accepts_mismatched_filename_and_content_type(self) -> None:
        from starlette.datastructures import UploadFile as StarletteUploadFile

        from app.services.upload_validation import read_image_upload_file_sync

        upload = StarletteUploadFile(
            file=BytesIO(make_png_bytes()),
            filename="kakao-photo.jpg",
            headers={"content-type": "image/jpeg"},
        )

        original_filename, suffix, normalized = read_image_upload_file_sync(upload)

        self.assertEqual(original_filename, "kakao-photo.jpg")
        self.assertEqual(suffix, ".jpg")
        with Image.open(BytesIO(normalized)) as image:
            self.assertEqual(image.format, "JPEG")


if __name__ == "__main__":
    unittest.main()


class NormalizeImageContentTestCase(unittest.TestCase):
    """업로드 정규화(2026-07-21) — 원본 미보관·장변 2048·EXIF 회전·알파 보존 계약."""

    def test_large_jpeg_downscaled_and_smaller(self) -> None:
        from app.services.upload_validation import NORMALIZE_MAX_SIDE, normalize_image_content

        buffer = BytesIO()
        Image.new("RGB", (4000, 3000), color=(180, 60, 60)).save(
            buffer, format="JPEG", quality=95)
        original = buffer.getvalue()
        normalized, suffix, ctype = normalize_image_content(original)
        self.assertEqual(suffix, ".jpg")
        self.assertEqual(ctype, "image/jpeg")
        with Image.open(BytesIO(normalized)) as im:
            self.assertLessEqual(max(im.size), NORMALIZE_MAX_SIDE)
        self.assertLess(len(normalized), len(original))

    def test_exif_orientation_applied(self) -> None:
        from PIL import Image as PILImage

        from app.services.upload_validation import normalize_image_content

        buffer = BytesIO()
        img = PILImage.new("RGB", (400, 200), color="white")
        exif = img.getexif()
        exif[0x0112] = 6  # Orientation: 90도 회전 필요(폰 세로 촬영)
        img.save(buffer, format="JPEG", exif=exif)
        normalized, _, _ = normalize_image_content(buffer.getvalue())
        with PILImage.open(BytesIO(normalized)) as im:
            self.assertEqual(im.size, (200, 400))  # 회전 반영으로 가로세로 교환

    def test_alpha_image_stays_png(self) -> None:
        from app.services.upload_validation import normalize_image_content

        buffer = BytesIO()
        Image.new("RGBA", (64, 64), color=(0, 0, 0, 0)).save(buffer, format="PNG")
        normalized, suffix, ctype = normalize_image_content(buffer.getvalue())
        self.assertEqual((suffix, ctype), (".png", "image/png"))
        with Image.open(BytesIO(normalized)) as im:
            self.assertEqual(im.mode, "RGBA")  # 누끼 입력 보호 — 알파 유지

    def test_reader_returns_normalized_suffix(self) -> None:
        from starlette.datastructures import UploadFile as StarletteUploadFile

        from app.services.upload_validation import read_image_upload_file_sync

        buffer = BytesIO()
        Image.new("RGB", (3000, 3000), color="white").save(buffer, format="PNG")
        upload = StarletteUploadFile(
            file=BytesIO(buffer.getvalue()),
            filename="phone.png",
            headers={"content-type": "image/png"},
        )
        name, suffix, content = read_image_upload_file_sync(upload)
        self.assertEqual(name, "phone.png")
        self.assertEqual(suffix, ".jpg")  # 알파 없는 PNG → JPEG 정규화
        with Image.open(BytesIO(content)) as im:
            self.assertLessEqual(max(im.size), 2048)
