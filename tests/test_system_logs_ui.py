"""系统日志页面 E2E：堆栈应保留原始时间和日志元数据。"""

import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import uvicorn
from playwright.sync_api import expect, sync_playwright

from app import reply_server
from app.file_log_collector import FileLogCollector


class SystemLogsUiTests(unittest.TestCase):
    def test_traceback_is_rendered_as_one_historical_log_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs_dir = root / "logs"
            logs_dir.mkdir()
            (logs_dir / "runtime.log").write_text(
                "2026-09-12 12:00:00.000 | ERROR    | app:test:10 - operation failed\n"
                "Traceback (most recent call last):\n"
                "  File \"app.py\", line 20, in run\n"
                "RuntimeError: synthetic failure\n"
                "2026-09-12 12:00:01.000 | INFO     | app:test:30 - recovered\n",
                encoding="utf-8",
            )
            collector = FileLogCollector(root=root, start_monitor=False)
            token = "system-logs-ui-test-token"
            reply_server.SESSION_TOKENS[token] = {
                "user_id": 7,
                "username": "admin",
                "timestamp": time.time(),
            }

            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
            server = uvicorn.Server(
                uvicorn.Config(reply_server.app, lifespan="off", log_level="error")
            )
            server_thread = threading.Thread(
                target=server.run,
                kwargs={"sockets": [listener]},
                daemon=True,
            )

            try:
                with patch.object(reply_server, "get_file_log_collector", return_value=collector):
                    with sync_playwright() as playwright:
                        server_thread.start()
                        for _ in range(100):
                            if server.started:
                                break
                            time.sleep(0.02)
                        self.assertTrue(server.started)

                        browser = playwright.chromium.launch(headless=True)
                        try:
                            page = browser.new_page(viewport={"width": 1440, "height": 1000})
                            page.add_init_script(
                                "localStorage.setItem('auth_token', "
                                f"{json.dumps(token)}); "
                                "localStorage.setItem('active_page', 'notifications');"
                            )
                            page.route(
                                "**/system-settings/public",
                                lambda route: route.fulfill(
                                    content_type="application/json",
                                    body=json.dumps({"admin_login_enabled": "true"}),
                                ),
                            )
                            page.route(
                                "**/verify",
                                lambda route: route.fulfill(
                                    content_type="application/json",
                                    body=json.dumps(
                                        {
                                            "authenticated": True,
                                            "user_id": 7,
                                            "username": "admin",
                                            "is_admin": True,
                                        }
                                    ),
                                ),
                            )
                            page.route(
                                "**/feature-flags",
                                lambda route: route.fulfill(
                                    content_type="application/json",
                                    body=json.dumps(
                                        {
                                            "revision": 1,
                                            "configured": {},
                                            "effective": {},
                                            "runtime_apply": None,
                                        }
                                    ),
                                ),
                            )
                            page.route(
                                "**/cookies/details",
                                lambda route: route.fulfill(
                                    content_type="application/json", body="[]"
                                ),
                            )
                            page.route(
                                "**/notification-channels",
                                lambda route: route.fulfill(
                                    content_type="application/json", body="[]"
                                ),
                            )
                            page.route(
                                "**/message-notifications",
                                lambda route: route.fulfill(
                                    content_type="application/json", body="{}"
                                ),
                            )
                            page.route(
                                "**/api/announcement**",
                                lambda route: route.fulfill(
                                    content_type="application/json", body=json.dumps({})
                                ),
                            )

                            with page.expect_response(
                                lambda response: response.url.startswith(origin + "/logs"),
                                timeout=10000,
                            ) as logs_response:
                                page.goto(origin)
                                # Depending on whether authentication resolves
                                # before this lazy page mounts, the admin can
                                # start on either the system or channels tab.
                                # Listening before navigation covers both paths.
                                system_tab = page.get_by_role(
                                    "tab", name="系统日志", exact=True
                                )
                                expect(system_tab).to_be_visible(timeout=10000)
                                system_tab.click()
                            expect(page.get_by_text("系统运行日志", exact=True)).to_be_visible(
                                timeout=10000
                            )
                            expect(
                                page.get_by_text(
                                    "默认每 30 秒自动刷新", exact=False
                                )
                            ).to_be_visible(timeout=10000)
                            expect(page.get_by_text("RuntimeError: synthetic failure")).to_be_visible(
                                timeout=10000
                            )

                            payload = logs_response.value.json()
                            entries = payload["logs"]
                            failed = next(
                                entry
                                for entry in entries
                                if entry["message"].startswith("operation failed")
                            )
                            self.assertEqual(failed["timestamp"], "2026-09-12T12:00:00")
                            self.assertEqual(failed["level"], "ERROR")
                            self.assertEqual(failed["source"], "app")
                            self.assertIn("Traceback (most recent call last):", failed["message"])
                            self.assertNotIn("system", failed["source"])
                        finally:
                            browser.close()
            finally:
                server.should_exit = True
                if server_thread.ident:
                    server_thread.join(10)
                listener.close()
                reply_server.SESSION_TOKENS.pop(token, None)


if __name__ == "__main__":
    unittest.main()
