import unittest
from time import time

from fastapi.testclient import TestClient

from app import reply_server
from utils.captcha_remote_control import captcha_controller


class CaptchaRemoteSecurityTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(reply_server.app)
        self.owner_token = "captcha-owner-token"
        self.other_token = "captcha-other-token"
        reply_server.SESSION_TOKENS[self.owner_token] = {
            "user_id": 11,
            "username": "owner",
            "is_admin": False,
            "timestamp": time(),
            "non_expiring": True,
        }
        reply_server.SESSION_TOKENS[self.other_token] = {
            "user_id": 22,
            "username": "other",
            "is_admin": False,
            "timestamp": time(),
            "non_expiring": True,
        }
        captcha_controller.active_sessions["account-a"] = {
            "owner_user_id": 11,
            "screenshot": "synthetic-image",
            "captcha_info": {},
            "viewport": {"width": 800, "height": 600},
            "completed": False,
            "page": object(),
        }

    def tearDown(self):
        reply_server.SESSION_TOKENS.pop(self.owner_token, None)
        reply_server.SESSION_TOKENS.pop(self.other_token, None)
        captcha_controller.active_sessions.pop("account-a", None)
        captcha_controller.websocket_connections.pop("account-a", None)
        self.client.close()

    def test_session_screenshot_requires_authentication(self):
        response = self.client.get("/api/captcha/session/account-a")
        self.assertEqual(response.status_code, 401)

    def test_session_screenshot_rejects_another_user(self):
        response = self.client.get(
            "/api/captcha/session/account-a",
            headers={"Authorization": f"Bearer {self.other_token}"},
        )
        self.assertEqual(response.status_code, 403)

    def test_session_screenshot_allows_the_owner(self):
        response = self.client.get(
            "/api/captcha/session/account-a",
            headers={"Authorization": f"Bearer {self.owner_token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["screenshot"], "synthetic-image")

    def test_websocket_requires_authentication_before_sending_a_screenshot(self):
        with self.client.websocket_connect("/api/captcha/ws/account-a") as websocket:
            websocket.send_json({"type": "authenticate", "token": "invalid"})
            response = websocket.receive_json()
        self.assertEqual(response["type"], "error")
        self.assertIn("认证", response["message"])

    def test_websocket_allows_owner_after_authentication(self):
        with self.client.websocket_connect("/api/captcha/ws/account-a") as websocket:
            websocket.send_json({"type": "authenticate", "token": self.owner_token})
            response = websocket.receive_json()
        self.assertEqual(response["type"], "session_info")
        self.assertEqual(response["screenshot"], "synthetic-image")


if __name__ == "__main__":
    unittest.main()
