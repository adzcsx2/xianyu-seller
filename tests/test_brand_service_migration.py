"""P5.2 red tests for removing implicit first-party service defaults."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.announcement import DEFAULT_ANNOUNCEMENT_URL
from app.db_manager import DBManager
from app.reply_server import AIReplySettings


ROOT = Path(__file__).resolve().parents[1]
LEGACY_ANNOUNCEMENT_URL = "https://connect." + "corleom.com/announcement.json"
LEGACY_AI_URL = "https://ai." + "corleom.com/v1"
LEGACY_ITEM_URL = "https://selfapi." + "zhinianboke.com/api/getItemDetail"


class BrandServiceMigrationTests(unittest.TestCase):
    def test_new_defaults_are_unconfigured_and_do_not_point_to_legacy_services(self):
        self.assertEqual(DEFAULT_ANNOUNCEMENT_URL, "")
        self.assertEqual(AIReplySettings(ai_enabled=False).base_url, "")

        db_source = (ROOT / "app/db_manager.py").read_text(encoding="utf-8")
        config_source = (ROOT / "global_config.yml").read_text(encoding="utf-8")
        frontend_sources = "\n".join(
            (ROOT / name).read_text(encoding="utf-8")
            for name in (
                "frontend/components/AIReply.tsx",
                "frontend/components/AccountList.tsx",
                "frontend/components/Settings.tsx",
            )
        )
        for source in (db_source, config_source, frontend_sources):
            self.assertNotIn(LEGACY_AI_URL, source)
            self.assertNotIn(LEGACY_ANNOUNCEMENT_URL, source)
            self.assertNotIn(LEGACY_ITEM_URL, source)

        self.assertIn("api_url: ''", config_source)

    def test_empty_announcement_source_does_not_become_an_implicit_request(self):
        source = (ROOT / "app/announcement.py").read_text(encoding="utf-8")
        self.assertNotIn("url = DEFAULT_ANNOUNCEMENT_URL", source)
        self.assertIn("source_configured': False", source)

    def test_exact_legacy_values_are_migrated_but_custom_values_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "migration.db"
            first = DBManager(str(path))
            first.set_system_setting("announcement_source_url", LEGACY_ANNOUNCEMENT_URL)
            first.set_system_setting("announcement_enabled", "true")
            first.conn.execute(
                "INSERT OR REPLACE INTO ai_reply_settings "
                "(cookie_id, ai_enabled, model_name, api_key, base_url, user_agent) "
                "VALUES (?, 0, 'qwen-plus', '', ?, '')",
                ("legacy-account", LEGACY_AI_URL),
            )
            first.conn.commit()
            first.conn.close()

            second = DBManager(str(path))
            try:
                self.assertEqual(second.get_system_setting("announcement_source_url"), "")
                self.assertEqual(second.get_system_setting("announcement_enabled"), "false")
                row = second.conn.execute(
                    "SELECT base_url FROM ai_reply_settings WHERE cookie_id = ?",
                    ("legacy-account",),
                ).fetchone()
                self.assertEqual(row[0], "")

                second.set_system_setting("announcement_source_url", "https://custom.invalid/notice.json")
                second.set_system_setting("announcement_enabled", "true")
                second.conn.execute(
                    "UPDATE ai_reply_settings SET base_url = ? WHERE cookie_id = ?",
                    ("https://custom.invalid/v1", "legacy-account"),
                )
                second.conn.commit()
            finally:
                second.conn.close()

            third = DBManager(str(path))
            self.assertEqual(
                third.get_system_setting("announcement_source_url"),
                "https://custom.invalid/notice.json",
            )
            self.assertEqual(third.get_system_setting("announcement_enabled"), "true")
            row = third.conn.execute(
                "SELECT base_url FROM ai_reply_settings WHERE cookie_id = ?",
                ("legacy-account",),
            ).fetchone()
            self.assertEqual(row[0], "https://custom.invalid/v1")
            third.conn.close()


if __name__ == "__main__":
    unittest.main()
