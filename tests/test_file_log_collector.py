import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_traceback_continuations_keep_parent_metadata_and_timestamp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs_dir = root / "logs"
            logs_dir.mkdir()
            (logs_dir / "runtime.log").write_text(
                "2026-09-12 12:00:00.000 | ERROR    | app:test:10 - operation failed\n"
                "Traceback (most recent call last):\n"
                "  File \"app.py\", line 20, in run\n"
                "RuntimeError: operation failed\n"
                "2026-09-12 12:00:01.000 | INFO     | app:test:30 - recovered\n",
                encoding="utf-8",
            )

            collector = FileLogCollector(root=root, start_monitor=False)
            logs = collector.get_logs(lines=100)

            self.assertEqual(len(logs), 2)
            self.assertEqual(logs[0]["timestamp"], "2026-09-12T12:00:00")
            self.assertEqual(logs[0]["level"], "ERROR")
            self.assertEqual(logs[0]["source"], "app")
            self.assertIn("Traceback (most recent call last):", logs[0]["message"])
            self.assertIn("RuntimeError: operation failed", logs[0]["message"])
            self.assertNotEqual(logs[0]["source"], "system")

    def test_truncated_log_prefix_keeps_recovered_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs_dir = root / "logs"
            logs_dir.mkdir()
            (logs_dir / "runtime.log").write_text(
                "2026-09-12 12:00:00.000 | INFO     | app:test:1 - before\n"
                "ager:_migrate_buyer_interaction_per_account:1466 - "
                "为cookies表添加auto_flower_enabled字段（默认关闭）\n",
                encoding="utf-8",
            )

            collector = FileLogCollector(root=root, start_monitor=False)
            logs = collector.get_logs(lines=100)

            self.assertEqual(len(logs), 2)
            truncated = logs[1]
            self.assertEqual(truncated["timestamp"], "2026-09-12T12:00:00")
            self.assertEqual(truncated["level"], "INFO")
            self.assertEqual(truncated["source"], "ager")
            self.assertEqual(
                truncated["function"], "_migrate_buyer_interaction_per_account"
            )
            self.assertEqual(truncated["line"], 1466)
            self.assertIn("auto_flower_enabled", truncated["message"])
            self.assertNotEqual(truncated["source"], "system")

    def test_disk_logs_are_cached_until_a_file_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs_dir = root / "logs"
            logs_dir.mkdir()
            log_file = logs_dir / "runtime.log"
            log_file.write_text(
                "2026-09-12 12:00:00.000 | INFO     | app:test:1 - first\n",
                encoding="utf-8",
            )

            collector = FileLogCollector(root=root, start_monitor=False)
            with patch.object(
                collector,
                "_read_file_snapshot",
                wraps=collector._read_file_snapshot,
            ) as read_snapshot:
                self.assertEqual([item["message"] for item in collector.get_logs(lines=100)], ["first"])
                self.assertEqual([item["message"] for item in collector.get_logs(lines=100)], ["first"])
                self.assertEqual(read_snapshot.call_count, 1)

            log_file.write_text(
                "2026-09-12 12:00:00.000 | INFO     | app:test:1 - first\n"
                "2026-09-12 12:00:01.000 | INFO     | app:test:2 - second\n",
                encoding="utf-8",
            )
            with patch.object(
                collector,
                "_read_file_snapshot",
                wraps=collector._read_file_snapshot,
            ) as read_snapshot:
                self.assertEqual(
                    [item["message"] for item in collector.get_logs(lines=100)],
                    ["first", "second"],
                )
                self.assertEqual(read_snapshot.call_count, 0)

    def test_appended_log_content_is_parsed_without_reparsing_existing_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs_dir = root / "logs"
            logs_dir.mkdir()
            log_file = logs_dir / "runtime.log"
            log_file.write_text(
                "2026-09-12 12:00:00.000 | INFO     | app:test:1 - first\n",
                encoding="utf-8",
            )

            collector = FileLogCollector(root=root, start_monitor=False)
            with patch.object(
                collector,
                "_read_file_snapshot",
                wraps=collector._read_file_snapshot,
            ) as read_snapshot:
                self.assertEqual(
                    [item["message"] for item in collector.get_logs(lines=100)],
                    ["first"],
                )
                with log_file.open("a", encoding="utf-8") as handle:
                    handle.write(
                        "2026-09-12 12:00:01.000 | INFO     | app:test:2 - second\n"
                    )

                self.assertEqual(
                    [item["message"] for item in collector.get_logs(lines=100)],
                    ["first", "second"],
                )
                self.assertEqual(read_snapshot.call_count, 1)

    def test_append_during_full_parse_is_not_marked_as_already_consumed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs_dir = root / "logs"
            logs_dir.mkdir()
            log_file = logs_dir / "runtime.log"
            log_file.write_text(
                "2026-09-12 12:00:00.000 | INFO     | app:test:1 - first\n",
                encoding="utf-8",
            )

            collector = FileLogCollector(root=root, start_monitor=False)
            original_read_snapshot = collector._read_file_snapshot

            def read_then_append(path):
                snapshot = original_read_snapshot(path)
                with log_file.open("a", encoding="utf-8") as handle:
                    handle.write(
                        "2026-09-12 12:00:01.000 | INFO     | app:test:2 - second\n"
                    )
                return snapshot

            with patch.object(
                collector, "_read_file_snapshot", side_effect=read_then_append
            ):
                first_read = collector.get_logs(lines=100)

            second_read = collector.get_logs(lines=100)
            self.assertEqual([item["message"] for item in first_read], ["first"])
            self.assertEqual(
                [item["message"] for item in second_read],
                ["first", "second"],
            )

    def test_monitor_and_disk_increment_do_not_duplicate_traceback_continuation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs_dir = root / "logs"
            logs_dir.mkdir()
            log_file = logs_dir / "runtime.log"
            log_file.write_text(
                "2026-09-12 12:00:00.000 | ERROR    | app:test:1 - failed\n",
                encoding="utf-8",
            )

            collector = FileLogCollector(root=root, start_monitor=False)
            collector._load_existing_logs()
            continuation = "RuntimeError: synthetic failure"
            with log_file.open("a", encoding="utf-8") as handle:
                handle.write(f"{continuation}\n")
            collector.parse_log_line(continuation)

            logs = collector.get_logs(lines=100)

            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0]["message"].count(continuation), 1)

    def test_truncated_log_file_falls_back_to_full_reparse(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs_dir = root / "logs"
            logs_dir.mkdir()
            log_file = logs_dir / "runtime.log"
            log_file.write_text(
                "2026-09-12 12:00:00.000 | INFO     | app:test:1 - first\n"
                "2026-09-12 12:00:01.000 | INFO     | app:test:2 - second\n",
                encoding="utf-8",
            )

            collector = FileLogCollector(root=root, start_monitor=False)
            self.assertEqual(
                [item["message"] for item in collector.get_logs(lines=100)],
                ["first", "second"],
            )

            log_file.write_text(
                "2026-09-12 12:00:02.000 | INFO     | app:test:3 - after truncate\n",
                encoding="utf-8",
            )
            with patch.object(
                collector,
                "_read_file_snapshot",
                wraps=collector._read_file_snapshot,
            ) as read_snapshot:
                self.assertEqual(
                    [item["message"] for item in collector.get_logs(lines=100)],
                    ["after truncate"],
                )
                self.assertEqual(read_snapshot.call_count, 1)

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
