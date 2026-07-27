import unittest

from app.api.google_auth import _redirect_oauth_error


class GoogleOAuthErrorTestCase(unittest.TestCase):
    def test_cancel_error_redirects_to_login_with_error_code(self) -> None:
        response = _redirect_oauth_error(
            "google_authorization_denied",
            "access_denied",
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login?oauth_error=google_authorization_denied", response.headers["location"])


if __name__ == "__main__":
    unittest.main()
