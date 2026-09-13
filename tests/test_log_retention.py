import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.file_log_collector import FileLogCollector
from utils.log_retention import (
    LOG_RETENTION_DAYS,
    append_daily_log,
    prune_expired_log_files,
)


class LogRetentionTests(unittest.TestCase):
    def test_retention_policy_is_seven_days(self):
        self.assertEqual(LOG_RETENTION_DAYS, 7)

    def test_prune_removes_only_expired_top_level_log_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            now = time.time()
            old_timestamp = now - (8 * 24 * 60 * 60)
            recent_timestamp = now - (6 * 24 * 60 * 60)

            expired = [
                root / "old.log",
                root / "old.log.zip",
                root / "old.txt",
                root / "old.log.gz",
            ]
            for path in expired:
                path.write_text("expired", encoding="utf-8")
                os.utime(path, (old_timestamp, old_timestamp))

            recent = root / "recent.log"
            recent.write_text("recent", encoding="utf-8")
            os.utime(recent, (recent_timestamp, recent_timestamp))
            unrelated = root / "keep.db"
            unrelated.write_text("not a log", encoding="utf-8")
            os.utime(unrelated, (old_timestamp, old_timestamp))
            nested = root / "nested"
            nested.mkdir()
            nested_log = nested / "old.log"
            nested_log.write_text("nested", encoding="utf-8")
            os.utime(nested_log, (old_timestamp, old_timestamp))

            removed = prune_expired_log_files(root, now=now)

            self.assertEqual(removed, 4)
            self.assertTrue(all(not path.exists() for path in expired))
            self.assertTrue(recent.exists())
            self.assertTrue(unrelated.exists())
            self.assertTrue(nested_log.exists())

    def test_daily_log_rotation_prunes_old_files_and_appends_today(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            now = time.mktime((2026, 9, 13, 12, 0, 0, 0, 0, -1))
            old = root / "captcha_verification_2026-09-01.txt"
            old.write_text("expired\n", encoding="utf-8")
            old_timestamp = now - (8 * 24 * 60 * 60)
            os.utime(old, (old_timestamp, old_timestamp))

            first_path = append_daily_log(
                root,
                "captcha_verification",
                "first",
                extension=".txt",
                now=now,
            )
            second_path = append_daily_log(
                root,
                "captcha_verification",
                "second",
                extension=".txt",
                now=now,
            )

            self.assertEqual(first_path, root / "captcha_verification_2026-09-13.txt")
            self.assertEqual(second_path, first_path)
            self.assertEqual(first_path.read_text(encoding="utf-8"), "first\nsecond\n")
            self.assertFalse(old.exists())

    def test_collector_prunes_expired_logs_on_startup_and_rotates_daily(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs_dir = root / "logs"
            logs_dir.mkdir()
            expired = logs_dir / "expired.log"
            expired.write_text("expired", encoding="utf-8")
            old_timestamp = time.time() - (8 * 24 * 60 * 60)
            os.utime(expired, (old_timestamp, old_timestamp))

            collector = FileLogCollector(root=root, start_monitor=False)

            self.assertFalse(expired.exists())
            with patch("loguru.logger.add") as add:
                collector.setup_loguru_file_output()
            self.assertEqual(add.call_args.kwargs["rotation"], "1 day")
            self.assertEqual(add.call_args.kwargs["retention"], "7 days")

    def test_captcha_logs_no_longer_use_one_unbounded_file(self):
        project_root = Path(__file__).resolve().parents[1]
        for relative_path in ("XianyuAutoAsync.py", "utils/refresh_util.py"):
            source = (project_root / relative_path).read_text(encoding="utf-8")
            self.assertNotIn("'captcha_verification.txt'", source)
            self.assertIn("append_daily_log(", source)
            self.assertIn("redact_sensitive_text(details)", source)

        main_source = (project_root / "XianyuAutoAsync.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("prune_expired_log_files(log_dir)", main_source)


if __name__ == "__main__":
    unittest.main()
