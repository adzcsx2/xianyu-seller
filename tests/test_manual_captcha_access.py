"""人工滑块入口与自动重试之间必须互斥。"""

import inspect
import unittest
from unittest.mock import AsyncMock

import XianyuAutoAsync
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

    def test_automatic_slider_is_opt_in(self):
        self.assertFalse(XianyuAutoAsync.is_auto_slider_enabled(None))
        self.assertFalse(XianyuAutoAsync.is_auto_slider_enabled("false"))
        self.assertTrue(XianyuAutoAsync.is_auto_slider_enabled("true"))

    def test_manual_success_restarts_account_with_new_cookie(self):
        source = inspect.getsource(reply_server.start_manual_captcha)

        self.assertIn("manual_captcha_required = True", source)
        self.assertIn("manager.update_cookie", source)
        self.assertIn("asyncio.to_thread", source)


class ManualCaptchaRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_required_manual_captcha_short_circuits_token_refresh(self):
        live = XianyuAutoAsync.XianyuLive.__new__(XianyuAutoAsync.XianyuLive)
        live.cookie_id = "account-1"
        live.manual_captcha_required = True

        result = await live.refresh_token()

        self.assertIsNone(result)
        self.assertEqual(live.last_token_refresh_status, "manual_captcha_required")

    async def test_init_raises_terminal_manual_captcha_signal(self):
        live = XianyuAutoAsync.XianyuLive.__new__(XianyuAutoAsync.XianyuLive)
        live.cookie_id = "account-1"
        live.current_token = None
        live.last_token_refresh_time = 0
        live.token_refresh_interval = 1
        live.manual_captcha_required = True
        live.refresh_token = AsyncMock(return_value=None)

        with self.assertRaises(XianyuAutoAsync.ManualCaptchaRequired):
            await live.init(AsyncMock())


if __name__ == "__main__":
    unittest.main()
