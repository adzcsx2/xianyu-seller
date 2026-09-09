"""人工滑块前端必须等得过服务器端浏览器冷启动。"""

import re
import unittest
from pathlib import Path


ACCOUNT_LIST = (
    Path(__file__).resolve().parent.parent / "frontend" / "components" / "AccountList.tsx"
)


class ManualCaptchaFrontendRetryTests(unittest.TestCase):
    def test_websocket_retry_window_covers_browser_startup(self):
        source = ACCOUNT_LIST.read_text(encoding="utf-8")
        match = re.search(r"CAPTCHA_WS_RETRY_LIMIT\s*=\s*(\d+)", source)

        self.assertIsNotNone(match, "人工滑块 WebSocket 重试上限应使用命名常量")
        self.assertGreaterEqual(
            int(match.group(1)),
            90,
            "20 秒不足以覆盖 Docker/NAS 上的 Chromium 冷启动与验证码渲染",
        )
        self.assertIn("retry < CAPTCHA_WS_RETRY_LIMIT", source)


if __name__ == "__main__":
    unittest.main()
