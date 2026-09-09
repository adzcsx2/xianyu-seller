import unittest
from pathlib import Path

from utils.log_sanitizer import REDACTED, redact_sensitive_text


class LogSanitizerTests(unittest.TestCase):
    def test_redacts_cookie_pairs_and_authorization(self):
        message = (
            "_m_h5_tk=secret_value; cookie2=another_secret; "
            "Authorization: Bearer bearer_secret"
        )
        redacted = redact_sensitive_text(message)
        self.assertNotIn("secret_value", redacted)
        self.assertNotIn("another_secret", redacted)
        self.assertNotIn("bearer_secret", redacted)
        self.assertGreaterEqual(redacted.count(REDACTED), 3)

    def test_redacts_dict_and_json_values(self):
        message = (
            "{'accessToken': 'token-value', \"sign\": \"signature-value\", "
            "'sgcookie': 'cookie-value'}"
        )
        redacted = redact_sensitive_text(message)
        self.assertNotIn("token-value", redacted)
        self.assertNotIn("signature-value", redacted)
        self.assertNotIn("cookie-value", redacted)

    def test_keeps_non_sensitive_diagnostics(self):
        message = "status=200 cookie_fields=18 payload_length=42"
        self.assertEqual(redact_sensitive_text(message), message)

    def test_password_login_never_logs_cookie_values(self):
        source = (
            Path(__file__).resolve().parent.parent / "XianyuAutoAsync.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("str(value)[:30]", source)
        self.assertNotIn("str(value)[-20:]", source)
        self.assertNotIn("{key}: {value}", source)


if __name__ == "__main__":
    unittest.main()
