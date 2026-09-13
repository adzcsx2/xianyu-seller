"""Shared seven-day retention helpers for file-backed logs."""

from __future__ import annotations

import os
import re
import stat as stat_module
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Union


LOG_RETENTION_DAYS = 7
_LOG_FILE_SUFFIXES = (".log", ".log.zip", ".log.gz", ".txt")
_EXTENSION_PATTERN = re.compile(r"^\.[A-Za-z0-9]+$")
PathLike = Union[str, os.PathLike[str]]


def prune_expired_log_files(
    log_dir: PathLike,
    *,
    retention_days: int = LOG_RETENTION_DAYS,
    now: Optional[float] = None,
) -> int:
    """Delete expired top-level log files without following links."""
    if retention_days <= 0:
        raise ValueError("日志保留天数必须大于 0")

    root = Path(log_dir).expanduser()
    if not root.is_dir():
        return 0
    cutoff = (time.time() if now is None else float(now)) - (
        retention_days * 24 * 60 * 60
    )
    removed = 0
    try:
        candidates = list(root.iterdir())
    except OSError:
        return 0

    for path in candidates:
        if not path.name.lower().endswith(_LOG_FILE_SUFFIXES):
            continue
        try:
            stat_result = path.lstat()
            if not stat_module.S_ISREG(stat_result.st_mode):
                continue
            if stat_result.st_mtime >= cutoff:
                continue
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def append_daily_log(
    log_dir: PathLike,
    basename: str,
    line: str,
    *,
    extension: str = ".log",
    now: Optional[float] = None,
) -> Path:
    """Append one line to a date-partitioned log and enforce retention."""
    if not basename or Path(basename).name != basename:
        raise ValueError("日志基础文件名无效")
    if not _EXTENSION_PATTERN.fullmatch(extension):
        raise ValueError("日志扩展名无效")

    timestamp = time.time() if now is None else float(now)
    root = Path(log_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    prune_expired_log_files(root, now=timestamp)
    date_text = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
    path = root / f"{basename}_{date_text}{extension}"
    normalized_line = str(line).rstrip("\r\n")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{normalized_line}\n")
    return path
