"""MTOP 人机验证与 Token 刷新必须使用同一份浏览器指纹。"""

import inspect
import unittest

import XianyuAutoAsync
from utils import manual_captcha
from utils.mtop_browser_fingerprint import (
    build_mtop_request_headers,
    get_playwright_context_options,
)


EDGE_151_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"
)
EDGE_151_SEC_CH_UA = (
    '"Not=A?Brand";v="99", "Microsoft Edge";v="151", '
    '"Chromium";v="151"'
)


class MtopBrowserFingerprintTests(unittest.TestCase):
    def test_default_headers_are_a_complete_edge_151_fingerprint(self):
        headers = build_mtop_request_headers("x5sec=passed")

        self.assertEqual(headers["user-agent"], EDGE_151_UA)
        self.assertEqual(headers["sec-ch-ua"], EDGE_151_SEC_CH_UA)
        self.assertEqual(headers["sec-ch-ua-mobile"], "?0")
        self.assertEqual(headers["sec-ch-ua-platform"], '"Windows"')
        self.assertEqual(headers["cookie"], "x5sec=passed")

    def test_playwright_uses_the_same_ua_and_client_hints(self):
        headers = build_mtop_request_headers("cookie2=value")
        options = get_playwright_context_options()

        self.assertEqual(options["user_agent"], headers["user-agent"])
        self.assertEqual(
            options["extra_http_headers"]["sec-ch-ua"],
            headers["sec-ch-ua"],
        )
        self.assertEqual(
            options["extra_http_headers"]["sec-ch-ua-platform"],
            headers["sec-ch-ua-platform"],
        )

    def test_token_refresh_no_longer_embeds_chrome_139(self):
        source = inspect.getsource(XianyuAutoAsync.XianyuLive.refresh_token)

        self.assertIn("build_mtop_request_headers", source)
        self.assertNotIn("Chrome/139", source)
        self.assertNotIn('"Google Chrome";v="139"', source)

    def test_manual_captcha_uses_the_shared_fingerprint(self):
        fetch_source = inspect.getsource(manual_captcha._fetch_live_verification_url)
        session_source = inspect.getsource(manual_captcha.open_manual_session)

        self.assertIn("build_mtop_request_headers", fetch_source)
        self.assertIn("get_playwright_context_options", session_source)
        self.assertNotIn("Chrome/138", session_source)
        self.assertNotIn("Chrome/139", fetch_source)

if __name__ == "__main__":
    unittest.main()
