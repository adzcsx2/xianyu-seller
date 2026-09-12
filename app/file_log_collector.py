"""File-backed system log collection for the admin log view."""
from __future__ import annotations

import os
import re
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


_LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{1,6})?)\s*\|\s*"
    r"(\w+)\s*\|\s*([^:]+):([^:]+):(\d+)\s*-\s*(.*)$"
)


class FileLogCollector:
    """Read all current text logs and keep a live buffer for fast updates."""

    def __init__(
        self,
        max_logs: int = 10000,
        root: Optional[Path] = None,
        start_monitor: bool = True,
    ):
        self.max_logs = max(100, int(max_logs))
        self.logs = deque(maxlen=self.max_logs)
        self.lock = threading.Lock()
        self.root = (root or Path(__file__).resolve().parent.parent).resolve()
        self.log_dir = self.root / "logs"
        self.log_file: Optional[str] = None
        self.last_position = 0
        self._monitor_stop = threading.Event()
        self.setup_file_monitoring(start_monitor=start_monitor)

    def _candidate_files(self) -> List[Path]:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_root = self.log_dir.resolve()
        files = []
        for path in self.log_dir.glob("*.log"):
            try:
                resolved = path.resolve()
                if path.is_file() and resolved.parent == log_root:
                    files.append(path)
            except OSError:
                continue
        return sorted(files, key=lambda path: (path.stat().st_mtime, str(path)))

    def setup_file_monitoring(self, *, start_monitor: bool = True) -> None:
        files = self._candidate_files()
        self.log_file = str(files[-1]) if files else str(self.log_dir / "realtime.log")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        if start_monitor:
            self.setup_loguru_file_output()
            self._load_existing_logs()
            self.monitor_thread = threading.Thread(target=self.monitor_file, daemon=True)
            self.monitor_thread.start()

    def setup_loguru_file_output(self) -> None:
        try:
            from loguru import logger

            logger.add(
                self.log_file,
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
                level="INFO",
                rotation="10 MB",
                retention="7 days",
                enqueue=False,
                buffering=1,
                encoding="utf-8",
            )
        except ImportError:
            pass

    def _load_existing_logs(self) -> None:
        for path in self._candidate_files():
            try:
                with path.open("r", encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        self.parse_log_line(line.rstrip("\r\n"))
            except OSError:
                continue
        if self.log_file:
            try:
                self.last_position = os.path.getsize(self.log_file)
            except OSError:
                self.last_position = 0

    def monitor_file(self) -> None:
        while not self._monitor_stop.wait(0.5):
            try:
                if not self.log_file or not os.path.exists(self.log_file):
                    continue
                file_size = os.path.getsize(self.log_file)
                if file_size < self.last_position:
                    self.last_position = 0
                if file_size <= self.last_position:
                    continue
                with open(self.log_file, "r", encoding="utf-8", errors="replace") as handle:
                    handle.seek(self.last_position)
                    new_lines = handle.readlines()
                    self.last_position = handle.tell()
                for line in new_lines:
                    self.parse_log_line(line.rstrip("\r\n"))
            except OSError:
                continue

    @staticmethod
    def _parse_line(line: str) -> Optional[Dict]:
        if not line:
            return None
        match = _LOG_PATTERN.match(line)
        if not match:
            return {
                "timestamp": datetime.now().isoformat(),
                "level": "INFO",
                "source": "system",
                "function": "unknown",
                "line": 0,
                "message": line,
            }
        timestamp_text, level, source, function, line_number, message = match.groups()
        try:
            timestamp = datetime.fromisoformat(timestamp_text).isoformat()
        except ValueError:
            timestamp = datetime.now().isoformat()
        return {
            "timestamp": timestamp,
            "level": level.upper(),
            "source": source.strip(),
            "function": function.strip(),
            "line": int(line_number),
            "message": message,
        }

    def parse_log_line(self, line: str) -> None:
        entry = self._parse_line(line)
        if entry is not None:
            with self.lock:
                self.logs.append(entry)

    def _load_disk_logs(self) -> List[Dict]:
        entries: List[Dict] = []
        for path in self._candidate_files():
            try:
                with path.open("r", encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        entry = self._parse_line(line.rstrip("\r\n"))
                        if entry is not None:
                            entries.append(entry)
            except OSError:
                continue
        return entries

    @staticmethod
    def _entry_key(entry: Dict) -> tuple:
        return tuple(entry.get(field) for field in ("timestamp", "level", "source", "function", "line", "message"))

    @staticmethod
    def _timestamp_value(value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            timestamp = value
        else:
            text = str(value).strip()
            if text.endswith("Z"):
                text = f"{text[:-1]}+00:00"
            try:
                timestamp = datetime.fromisoformat(text)
            except ValueError as exc:
                raise ValueError(f"无效的日志时间: {value}") from exc
        try:
            return timestamp.timestamp()
        except (OverflowError, OSError, ValueError) as exc:
            raise ValueError(f"无效的日志时间: {value}") from exc

    def _filtered_logs(
        self,
        level_filter: Optional[str] = None,
        source_filter: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> List[Dict]:
        start_timestamp = self._timestamp_value(start_time)
        end_timestamp = self._timestamp_value(end_time)
        if start_timestamp is not None and end_timestamp is not None and start_timestamp > end_timestamp:
            raise ValueError("日志开始时间不能晚于结束时间")

        with self.lock:
            buffered = list(self.logs)
        combined: List[Dict] = []
        seen = set()
        for entry in buffered + self._load_disk_logs():
            key = self._entry_key(entry)
            if key in seen:
                continue
            seen.add(key)
            combined.append(entry)
        if level_filter:
            level = str(level_filter).upper()
            combined = [entry for entry in combined if entry["level"] == level]
        if source_filter:
            source = str(source_filter).lower()
            combined = [entry for entry in combined if source in entry["source"].lower()]
        if start_timestamp is not None or end_timestamp is not None:
            filtered = []
            for entry in combined:
                entry_timestamp = self._timestamp_value(entry.get("timestamp"))
                if entry_timestamp is None:
                    continue
                if start_timestamp is not None and entry_timestamp < start_timestamp:
                    continue
                if end_timestamp is not None and entry_timestamp > end_timestamp:
                    continue
                filtered.append(entry)
            combined = filtered
        combined.sort(key=lambda entry: entry.get("timestamp", ""))
        return combined

    def get_logs_page(
        self,
        lines: int = 1000,
        offset: int = 0,
        level_filter: Optional[str] = None,
        source_filter: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        requested_lines = max(1, min(int(lines or 1000), self.max_logs))
        requested_offset = max(0, int(offset or 0))
        combined = self._filtered_logs(
            level_filter=level_filter,
            source_filter=source_filter,
            start_time=start_time,
            end_time=end_time,
        )
        end_index = max(0, len(combined) - requested_offset)
        start_index = max(0, end_index - requested_lines)
        page = combined[start_index:end_index]
        return {
            "logs": page,
            "total": len(combined),
            "offset": requested_offset,
            "limit": requested_lines,
            "has_more": start_index > 0,
        }

    def get_logs(
        self,
        lines: int = 200,
        level_filter: Optional[str] = None,
        source_filter: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        offset: int = 0,
    ) -> List[Dict]:
        return self.get_logs_page(
            lines=lines,
            offset=offset,
            level_filter=level_filter,
            source_filter=source_filter,
            start_time=start_time,
            end_time=end_time,
        )["logs"]

    def clear_logs(self) -> None:
        with self.lock:
            self.logs.clear()
            self.last_position = 0

        files = self._candidate_files()
        if self.log_file:
            active_file = Path(self.log_file)
            try:
                active_is_safe = active_file.resolve().parent == self.log_dir.resolve()
            except OSError:
                active_is_safe = False
            if active_is_safe and active_file not in files:
                files.append(active_file)
        for path in files:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")
            except OSError:
                continue

    def get_stats(self) -> Dict:
        logs = self.get_logs(lines=self.max_logs)
        level_counts: Dict[str, int] = {}
        source_counts: Dict[str, int] = {}
        for entry in logs:
            level_counts[entry["level"]] = level_counts.get(entry["level"], 0) + 1
            source_counts[entry["source"]] = source_counts.get(entry["source"], 0) + 1
        return {
            "total_logs": len(logs),
            "level_counts": level_counts,
            "source_counts": source_counts,
            "max_capacity": self.max_logs,
            "log_file": self.log_file,
        }


_file_collector: Optional[FileLogCollector] = None
_file_collector_lock = threading.Lock()


def get_file_log_collector(root: Optional[Path] = None) -> FileLogCollector:
    global _file_collector
    if _file_collector is None:
        with _file_collector_lock:
            if _file_collector is None:
                _file_collector = FileLogCollector(root=root)
    return _file_collector


def setup_file_logging(root: Optional[Path] = None) -> FileLogCollector:
    return get_file_log_collector(root=root)
