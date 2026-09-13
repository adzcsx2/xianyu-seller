import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SystemLogsFrontendContractTests(unittest.TestCase):
    def test_system_logs_auto_refresh_interval_is_thirty_seconds(self):
        source = (
            PROJECT_ROOT / "frontend" / "components" / "NotificationsAndLogs.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn("const SYSTEM_LOG_REFRESH_INTERVAL_MS = 30_000;", source)
        self.assertIn("}, SYSTEM_LOG_REFRESH_INTERVAL_MS);", source)
        self.assertIn("默认每 30 秒自动刷新", source)

    def test_system_logs_refresh_uses_ref_guard_against_overlapping_requests(self):
        source = (
            PROJECT_ROOT / "frontend" / "components" / "NotificationsAndLogs.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn("const systemLoadingRef = useRef(false);", source)
        self.assertIn("const systemLoadingMoreRef = useRef(false);", source)
        self.assertIn("const systemPendingRefreshRef = useRef<", source)
        self.assertIn(
            "if (systemLoadingRef.current || systemLoadingMoreRef.current) {",
            source,
        )
        self.assertIn(
            "if (queueIfBusy) systemPendingRefreshRef.current = { silent, query };",
            source,
        )
        self.assertIn("void loadSystemLogs(true, false, true);", source)
        self.assertIn(
            "onClick={() => void loadSystemLogs(false, false, true)}", source
        )
        self.assertNotIn("if (systemLoadingMore) return;", source)


if __name__ == "__main__":
    unittest.main()
