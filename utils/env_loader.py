"""Small, dependency-free loader for project ``.env`` files."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Union


_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PathLike = Union[str, os.PathLike[str]]


def _unescape_double_quoted(value: str) -> str:
    """Decode the escapes commonly supported in double-quoted env values."""
    escaped = {
        "\\": "\\",
        '"': '"',
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "$": "$",
    }
    result: list[str] = []
    index = 0
    while index < len(value):
        character = value[index]
        if character == "\\" and index + 1 < len(value):
            next_character = value[index + 1]
            result.append(escaped.get(next_character, f"\\{next_character}"))
            index += 2
            continue
        result.append(character)
        index += 1
    return "".join(result)


def _parse_value(raw_value: str) -> str:
    value = raw_value.strip()
    if value.startswith('"'):
        closing_quote = value.rfind('"')
        if closing_quote > 0:
            return _unescape_double_quoted(value[1:closing_quote])
    elif value.startswith("'"):
        closing_quote = value.rfind("'")
        if closing_quote > 0:
            return value[1:closing_quote]

    # In an unquoted value, ``#`` starts a comment only when preceded by
    # whitespace. This keeps values such as tokens or URLs containing ``#``.
    return re.split(r"\s+#", value, maxsplit=1)[0].rstrip()


def load_env_file(path: PathLike, *, override: bool = False) -> int:
    """Load valid assignments from *path* into ``os.environ``.

    The process environment wins by default, matching Docker and shell
    configuration precedence. The return value is the number of assignments
    applied to the process environment.
    """
    env_path = Path(path)
    try:
        content = env_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return 0

    loaded = 0
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()

        key, separator, raw_value = line.partition("=")
        key = key.strip()
        if not separator or not _ENV_KEY.fullmatch(key):
            continue
        if not override and key in os.environ:
            continue

        os.environ[key] = _parse_value(raw_value)
        loaded += 1
    return loaded
