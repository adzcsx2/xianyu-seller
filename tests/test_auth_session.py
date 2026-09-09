import unittest
from unittest.mock import patch

from fastapi.security import HTTPAuthorizationCredentials

from app import reply_server


class AuthSessionTests(unittest.TestCase):
    def setUp(self):
        self.token = "permanent-session-token"
        self.user = {
            "user_id": 1,
            "username": "admin",
            "is_admin": True,
            "timestamp": 0,
        }
        reply_server.SESSION_TOKENS[self.token] = self.user

    def tearDown(self):
        reply_server.SESSION_TOKENS.pop(self.token, None)

    def _credentials(self):
        return HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=self.token,
        )

    def test_auto_login_session_does_not_expire_when_login_is_disabled(self):
        self.user["non_expiring"] = True
        with patch.object(reply_server, "ADMIN_LOGIN_ENABLED", False):
            self.assertIs(reply_server.verify_token(self._credentials()), self.user)

    def test_expired_session_is_rejected_when_login_is_enabled(self):
        self.user["timestamp"] = 100
        with (
            patch.object(reply_server, "ADMIN_LOGIN_ENABLED", True),
            patch.object(reply_server, "SESSION_TIMEOUT_SECONDS", 3600, create=True),
            patch.object(reply_server.time, "time", return_value=3701),
        ):
            self.assertIsNone(reply_server.verify_token(self._credentials()))
        self.assertNotIn(self.token, reply_server.SESSION_TOKENS)

    def test_fresh_session_remains_valid_when_login_is_enabled(self):
        self.user["timestamp"] = 100
        with (
            patch.object(reply_server, "ADMIN_LOGIN_ENABLED", True),
            patch.object(reply_server, "SESSION_TIMEOUT_SECONDS", 3600, create=True),
            patch.object(reply_server.time, "time", return_value=3699),
        ):
            self.assertIs(reply_server.verify_token(self._credentials()), self.user)

    def test_non_expiring_flag_does_not_bypass_enabled_login_ttl(self):
        self.user.update({"timestamp": 100, "non_expiring": True})
        with (
            patch.object(reply_server, "ADMIN_LOGIN_ENABLED", True),
            patch.object(reply_server, "SESSION_TIMEOUT_SECONDS", 3600, create=True),
            patch.object(reply_server.time, "time", return_value=3701),
        ):
            self.assertIsNone(reply_server.verify_token(self._credentials()))

    def test_missing_timestamp_is_rejected_in_login_mode(self):
        self.user.pop("timestamp")
        with patch.object(reply_server, "ADMIN_LOGIN_ENABLED", True):
            self.assertIsNone(reply_server.verify_token(self._credentials()))


if __name__ == "__main__":
    unittest.main()
