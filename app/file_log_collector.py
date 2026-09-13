"""File-backed system log collection for the admin log view."""
from __future__ import annotations

import os
import re
import stat as stat_module
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.log_retention import LOG_RETENTION_DAYS, prune_expired_log_files


_LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{1,6})?)\s*\|\s*"
    r"(\w+)\s*\|\s*([^:]+):([^:]+):(\d+)\s*-\s*(.*)$"
)
_PARTIAL_LOG_PATTERN = re.compile(
    r"^([^:\s|]+):([^:|]+):(\d+)\s*-\s*(.*)$"
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
        explicit_root = root is not None
        self.root = (root or Path(__file__).resolve().parent.parent).resolve()
        configured_log_dir = None if explicit_root else os.getenv("LOG_DIR")
        self.log_dir = (
            Path(configured_log_dir).expanduser().resolve()
            if configured_log_dir
            else self.root / "logs"
        )
        prune_expired_log_files(self.log_dir)
        self.log_file: Optional[str] = None
        self.last_position = 0
        self._disk_file_states: Dict[str, Dict[str, Any]] = {}
        self._disk_lock = threading.Lock()
        self._monitor_stop = threading.Event()
        self.setup_file_monitoring(start_monitor=start_monitor)

    def _candidate_files(self) -> List[Path]:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_root = self.log_dir.resolve()
        files = []
        for path in self.log_dir.glob("*.log"):
            try:
                resolved = path.resolve()
                stat_result = path.stat()
                if stat_module.S_ISREG(stat_result.st_mode) and resolved.parent == log_root:
                    files.append((stat_result.st_mtime, str(path), path))
            except OSError:
                continue
        return [path for _, _, path in sorted(files)]

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
                rotation="1 day",
                retention=f"{LOG_RETENTION_DAYS} days",
                enqueue=False,
                buffering=1,
                encoding="utf-8",
            )
        except ImportError:
            pass

    def _load_existing_logs(self) -> None:
        entries = self._load_disk_logs()
        with self.lock:
            self.logs.extend(dict(entry) for entry in entries)
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
    def _parse_line(line: str, fallback_timestamp: Optional[str] = None) -> Optional[Dict]:
        if not line:
            return None
        match = _LOG_PATTERN.match(line)
        if not match:
            return {
                "timestamp": fallback_timestamp or datetime.now().isoformat(),
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

    @staticmethod
    def _parse_partial_line(
        line: str, fallback_timestamp: Optional[str] = None
    ) -> Optional[Dict]:
        """Parse a Loguru record whose timestamp/level prefix was truncated.

        Concurrent writers can interleave at a byte boundary while a log file
        is being rotated, leaving e.g. ``ager:_migrate...:1466 - message``.
        Keeping the recovered metadata is more useful than treating it as a
        fresh ``system`` event with the time at which the log endpoint is read.
        """
        match = _PARTIAL_LOG_PATTERN.match(line)
        if not match:
            return None
        source, function, line_number, message = match.groups()
        return {
            "timestamp": fallback_timestamp or datetime.now().isoformat(),
            "level": "INFO",
            "source": source.strip(),
            "function": function.strip(),
            "line": int(line_number),
            "message": message,
        }

    @staticmethod
    def _file_identity(stat_result: os.stat_result) -> tuple:
        return (stat_result.st_dev, stat_result.st_ino)

    @staticmethod
    def _read_file_snapshot(path: Path) -> Optional[tuple[os.stat_result, bytes]]:
        """Read the byte range covered by one descriptor-level stat call."""
        try:
            with path.open("rb") as handle:
                stat_result = os.fstat(handle.fileno())
                content = handle.read(stat_result.st_size)
        except OSError:
            return None
        return stat_result, content

    @classmethod
    def _append_parsed_text(
        cls,
        entries: List[Dict],
        text: str,
        fallback_timestamp: Optional[str] = None,
    ) -> None:
        last_timestamp = (
            entries[-1].get("timestamp") if entries else fallback_timestamp
        )
        for raw_line in text.splitlines():
            line = raw_line.rstrip("\r\n")
            if not line:
                continue
            if _LOG_PATTERN.match(line):
                entry = cls._parse_line(line)
                if entry is not None:
                    entries.append(entry)
                    last_timestamp = entry["timestamp"]
            elif (partial_entry := cls._parse_partial_line(
                line, fallback_timestamp=last_timestamp
            )) is not None:
                entries.append(partial_entry)
            elif entries:
                entries[-1]["message"] = f"{entries[-1]['message']}\n{line}"
            else:
                entries.append(cls._parse_line(line, fallback_timestamp=last_timestamp))

    def _full_file_state(
        self, path: Path, stat_result: Optional[os.stat_result] = None
    ) -> Optional[Dict[str, Any]]:
        del stat_result  # The descriptor snapshot is the authoritative boundary.
        snapshot = self._read_file_snapshot(path)
        if snapshot is None:
            return None
        observed_stat, content = snapshot
        try:
            fallback_timestamp = datetime.fromtimestamp(observed_stat.st_mtime).isoformat()
        except (ValueError, OverflowError, OSError):
            fallback_timestamp = None
        entries: List[Dict] = []
        self._append_parsed_text(
            entries,
            content.decode("utf-8", errors="replace"),
            fallback_timestamp=fallback_timestamp,
        )
        size = len(content)
        tail = content[-512:]
        return {
            "identity": self._file_identity(observed_stat),
            "offset": size,
            "mtime_ns": observed_stat.st_mtime_ns,
            "tail": tail,
            "ends_with_newline": size == 0 or tail.endswith((b"\n", b"\r")),
            "entries": entries,
        }

    def _increment_file_state(
        self,
        path: Path,
        stat_result: os.stat_result,
        previous: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        previous_offset = int(previous["offset"])
        try:
            with path.open("rb") as handle:
                observed_stat = os.fstat(handle.fileno())
                observed_identity = self._file_identity(observed_stat)
                if (
                    observed_identity != self._file_identity(stat_result)
                    or observed_identity != previous.get("identity")
                    or observed_stat.st_size <= previous_offset
                ):
                    return None
                tail_start = max(0, previous_offset - 512)
                handle.seek(tail_start)
                previous_tail = handle.read(previous_offset - tail_start)
                if previous_tail != previous.get("tail", b""):
                    return None
                handle.seek(previous_offset)
                expected_length = observed_stat.st_size - previous_offset
                appended = handle.read(expected_length)
        except OSError:
            return None
        if len(appended) != expected_length:
            return None

        entries = [dict(entry) for entry in previous["entries"]]
        if appended:
            self._append_parsed_text(entries, appended.decode("utf-8", errors="replace"))
        offset = previous_offset + len(appended)
        tail = (previous_tail + appended)[-512:]
        return {
            "identity": self._file_identity(observed_stat),
            "offset": offset,
            "mtime_ns": observed_stat.st_mtime_ns,
            "tail": tail,
            "ends_with_newline": offset == 0 or tail.endswith((b"\n", b"\r")),
            "entries": entries,
        }

    def parse_log_line(self, line: str) -> None:
        if not line:
            return
        if _LOG_PATTERN.match(line):
            entry = self._parse_line(line)
            if entry is not None:
                with self.lock:
                    self.logs.append(entry)
            return

        with self.lock:
            fallback_timestamp = self.logs[-1].get("timestamp") if self.logs else None
        partial_entry = self._parse_partial_line(
            line, fallback_timestamp=fallback_timestamp
        )
        if partial_entry is not None:
            with self.lock:
                self.logs.append(partial_entry)
            return

        with self.lock:
            if self.logs:
                self.logs[-1]["message"] = f"{self.logs[-1]['message']}\n{line}"
            else:
                entry = self._parse_line(line)
                if entry is not None:
                    self.logs.append(entry)

    def _load_disk_logs(self) -> List[Dict]:
        with self._disk_lock:
            files = self._candidate_files()
            next_states: Dict[str, Dict[str, Any]] = {}
            entries: List[Dict] = []

            for path in files:
                try:
                    stat_result = path.stat()
                    path_key = str(path.resolve())
                except OSError:
                    continue

                previous = self._disk_file_states.get(path_key)
                state: Optional[Dict[str, Any]] = None
                if previous is not None:
                    same_file = (
                        previous.get("identity") == self._file_identity(stat_result)
                    )
                    previous_offset = int(previous.get("offset", 0))
                    if (
                        same_file
                        and stat_result.st_size == previous_offset
                        and stat_result.st_mtime_ns == previous.get("mtime_ns")
                    ):
                        state = previous
                    elif (
                        same_file
                        and stat_result.st_size > previous_offset
                        and previous.get("ends_with_newline", False)
                    ):
                        state = self._increment_file_state(path, stat_result, previous)

                if state is None:
                    state = self._full_file_state(path, stat_result)
                if state is None:
                    continue
                next_states[path_key] = state
                entries.extend(state["entries"])

            with self.lock:
                self._disk_file_states = next_states
            return list(entries)

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
        with self._disk_lock:
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

            with self.lock:
                self.logs.clear()
                self.last_position = 0
                self._disk_file_states = {}

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
