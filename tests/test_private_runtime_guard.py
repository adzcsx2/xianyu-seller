import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.check_private_runtime_data import (
    find_forbidden_tracked_paths,
    is_forbidden_tracked_path,
)


class PrivateRuntimeGuardTests(unittest.TestCase):
    def test_rejects_private_runtime_and_secret_paths(self):
        forbidden = (
            ".env",
            ".env.production",
            "data/xianyu_data.db",
            "data/xianyu_data.db-wal",
            "app/knowledge/private.json",
            "browser_data/profile/state.json",
            "cookies/live.txt",
            "sessions/admin.json",
            "storage_state/account.json",
            "qrcodes/login.png",
            "logs/runtime.log",
            "secrets/provider.json",
            "keys/private.pem",
        )

        for path in forbidden:
            with self.subTest(path=path):
                self.assertTrue(is_forbidden_tracked_path(path))

    def test_allows_source_and_explicit_placeholders(self):
        allowed = (
            ".env.example",
            "app/knowledge/__init__.py",
            "app/knowledge/service.py",
            "app/knowledge/parsers/markdown.py",
            "data/.gitkeep",
            "backups/.gitkeep",
            "app/db_manager.py",
            "tests/test_knowledge_documents.py",
            "docs/guide/自动化测试指南.md",
        )

        for path in allowed:
            with self.subTest(path=path):
                self.assertFalse(is_forbidden_tracked_path(path))

    def test_current_repository_has_no_tracked_private_runtime_data(self):
        self.assertEqual(find_forbidden_tracked_paths(), [])

    def test_tracked_path_scan_accepts_text_subprocess_output(self):
        completed = SimpleNamespace(
            stdout="app/db_manager.py\0data/private.db\0",
        )
        with patch("scripts.check_private_runtime_data.subprocess.run", return_value=completed):
            self.assertEqual(
                find_forbidden_tracked_paths(Path("unused")),
                ["data/private.db"],
            )


if __name__ == "__main__":
    unittest.main()
