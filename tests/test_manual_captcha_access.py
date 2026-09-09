"""人工滑块入口不应只依赖仍在递减的冷却计时。"""

import unittest

from app import reply_server


class ManualCaptchaAccessTests(unittest.TestCase):
    def test_fresh_slider_event_remains_actionable_after_cooldown(self):
        state = {"blocked": False, "verification_type": "slider"}

        self.assertTrue(reply_server.should_allow_manual_captcha(state))

    def test_normal_account_cannot_open_unnecessary_session(self):
        state = {"blocked": False, "verification_type": "none"}

        self.assertFalse(reply_server.should_allow_manual_captcha(state))

    def test_active_risk_cooldown_remains_actionable(self):
        state = {"blocked": True, "verification_type": "risk_control"}

        self.assertTrue(reply_server.should_allow_manual_captcha(state))


if __name__ == "__main__":
    unittest.main()
