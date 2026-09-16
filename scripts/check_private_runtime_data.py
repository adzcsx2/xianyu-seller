"""Fail when Git tracks private runtime data or secret-bearing files."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


PROJECT_ROOT = Path(__file__).resolve().parents[1]

_ALLOWED_PATHS = frozenset(
    {
        ".env.example",
        "app/knowledge/__init__.py",
        "backups/.gitkeep",
        "data/.gitkeep",
        "static/uploads/.gitkeep",
        "static/uploads/images/.gitkeep",
    }
)

_PRIVATE_ROOTS = frozenset(
    {
        "account_data",
        "auth_state",
        "backups",
        "browser_data",
        "captcha",
        "cookies",
        "credentials",
        "data",
        "keys",
        "knowledge",
        "knowledge_base",
        "login_data",
        "logs",
        "personal_configs",
        "qrcodes",
        "secrets",
        "sessions",
        "slider_cookies",
        "storage_state",
        "user_data",
    }
)

_DATABASE_FILE = re.compile(
    r"\.(?:db|sqlite|sqlite3)(?:-(?:journal|shm|wal))?$",
    re.IGNORECASE,
)
_PRIVATE_KEY_SUFFIXES = (".key", ".p12", ".pem", ".pfx")


def _normalize_git_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def is_forbidden_tracked_path(path: str) -> bool:
    """Return whether a repository-relative Git path may contain private data."""
    normalized = _normalize_git_path(path)
    if not normalized or normalized in _ALLOWED_PATHS:
        return False

    parts = PurePosixPath(normalized).parts
    if not parts:
        return False
    if parts[0] in _PRIVATE_ROOTS:
        return True
    if parts[:2] == ("app", "knowledge"):
        return PurePosixPath(normalized).suffix.lower() != ".py"
    if parts[:2] == ("static", "uploads"):
        return True

    filename = parts[-1].lower()
    if filename == ".env" or filename.startswith(".env."):
        return True
    if _DATABASE_FILE.search(filename):
        return True
    if filename.endswith(".log") or ".log." in filename:
        return True
    return filename.endswith(_PRIVATE_KEY_SUFFIXES)


def find_forbidden_tracked_paths(project_root: Path = PROJECT_ROOT) -> list[str]:
    """Return tracked private paths without reading or printing file contents."""
    completed = subprocess.run(
        ["git", "-C", str(project_root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    output = completed.stdout
    if isinstance(output, bytes):
        tracked_paths = (
            item.decode("utf-8", errors="surrogateescape")
            for item in output.split(b"\0")
            if item
        )
    else:
        tracked_paths = (item for item in (output or "").split("\0") if item)
    return sorted(path for path in tracked_paths if is_forbidden_tracked_path(path))


def main() -> int:
    forbidden = find_forbidden_tracked_paths()
    if not forbidden:
        print("Private runtime data tracking check passed.")
        return 0

    print("Private runtime data must not be tracked or published:", file=sys.stderr)
    for path in forbidden:
        print(f"  {path}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
