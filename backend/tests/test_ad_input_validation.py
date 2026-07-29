import unittest

from fastapi import HTTPException

from app.api.ads import _reject_emoji_inputs
from app.core.input_validation import contains_emoji


class AdInputValidationTestCase(unittest.TestCase):
    def test_detects_emoji_characters(self) -> None:
        self.assertTrue(contains_emoji("딸기 라떼 🍓"))
        self.assertTrue(contains_emoji("반짝이는 분위기 ✨"))
        self.assertTrue(contains_emoji("한국 국기 🇰🇷"))

    def test_allows_korean_and_common_symbols(self) -> None:
        self.assertFalse(contains_emoji("신메뉴 1+1, 20% 할인 & 무료 배송"))

    def test_rejects_emoji_in_product_name(self) -> None:
        with self.assertRaises(HTTPException) as context:
            _reject_emoji_inputs(product_name="딸기 라떼 🍓")

        self.assertEqual(context.exception.status_code, 422)
        self.assertIn("상품명", str(context.exception.detail))

    def test_rejects_emoji_in_extra_request(self) -> None:
        with self.assertRaises(HTTPException) as context:
            _reject_emoji_inputs(
                product_name="딸기 라떼",
                extra_request="여름 분위기 ✨",
            )

        self.assertEqual(context.exception.status_code, 422)
        self.assertIn("추가 요청", str(context.exception.detail))
