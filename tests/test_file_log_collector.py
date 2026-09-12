import tempfile
import unittest
from pathlib import Path

from app.file_log_collector import FileLogCollector


class FileLogCollectorTests(unittest.TestCase):
    def test_reads_log_file_relative_to_explicit_project_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs_dir = root / "logs"
            logs_dir.mkdir()
            log_file = logs_dir / "xianyu_2026-09-12.log"
            log_file.write_text(
                "2026-09-12 12:00:00.000 | INFO     | app:test:1 - first\n"
                "2026-09-12 12:00:01.000 | ERROR    | app:test:2 - second\n",
                encoding="utf-8",
            )

            collector = FileLogCollector(root=root, start_monitor=False)
            logs = collector.get_logs(lines=100)

            self.assertEqual([item["message"] for item in logs], ["first", "second"])
            self.assertEqual(collector.get_stats()["total_logs"], 2)

    def test_unparseable_lines_are_visible_as_system_logs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            collector = FileLogCollector(root=Path(temp_dir), start_monitor=False)
            collector.parse_log_line("plain system line")

            logs = collector.get_logs(lines=10)

            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0]["source"], "system")
            self.assertEqual(logs[0]["message"], "plain system line")

    def test_filters_logs_by_time_window(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs_dir = root / "logs"
            logs_dir.mkdir()
            (logs_dir / "runtime.log").write_text(
                "2026-09-12 12:00:00.000 | INFO     | app:test:1 - before\n"
                "2026-09-12 12:01:00.000 | INFO     | app:test:2 - inside\n"
                "2026-09-12 12:02:00.000 | INFO     | app:test:3 - after\n",
                encoding="utf-8",
            )

            collector = FileLogCollector(root=root, start_monitor=False)
            logs = collector.get_logs(
                lines=100,
                start_time="2026-09-12T12:00:30",
                end_time="2026-09-12T12:01:30",
            )

            self.assertEqual([item["message"] for item in logs], ["inside"])

    def test_clear_logs_removes_disk_logs_and_buffer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs_dir = root / "logs"
            logs_dir.mkdir()
            log_file = logs_dir / "runtime.log"
            log_file.write_text(
                "2026-09-12 12:00:00.000 | INFO     | app:test:1 - persisted\n",
                encoding="utf-8",
            )

            collector = FileLogCollector(root=root, start_monitor=False)
            collector.parse_log_line(
                "2026-09-12 12:00:01.000 | INFO     | app:test:2 - buffered"
            )
            collector.clear_logs()

            self.assertEqual(collector.get_logs(lines=100), [])
            self.assertEqual(log_file.read_text(encoding="utf-8"), "")

    def test_returns_newest_page_and_older_page_by_offset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs_dir = root / "logs"
            logs_dir.mkdir()
            (logs_dir / "runtime.log").write_text(
                "2026-09-12 12:00:00.000 | INFO     | app:test:1 - first\n"
                "2026-09-12 12:01:00.000 | INFO     | app:test:2 - second\n"
                "2026-09-12 12:02:00.000 | INFO     | app:test:3 - third\n",
                encoding="utf-8",
            )

            collector = FileLogCollector(root=root, start_monitor=False)
            newest = collector.get_logs(lines=2, offset=0)
            older = collector.get_logs(lines=2, offset=2)

            self.assertEqual([item["message"] for item in newest], ["second", "third"])
            self.assertEqual([item["message"] for item in older], ["first"])


if __name__ == "__main__":
    unittest.main()
