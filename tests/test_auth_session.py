import unittest

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

    def test_session_does_not_expire_with_time(self):
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=self.token,
        )

        self.assertIs(reply_server.verify_token(credentials), self.user)


if __name__ == "__main__":
    unittest.main()
