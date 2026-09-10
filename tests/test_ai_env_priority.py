"""AI 环境配置优先级回归测试。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.ai_config import apply_env_ai_settings, resolve_ai_config
from app.db_manager import DBManager


ROOT = Path(__file__).resolve().parents[1]


class AIEnvironmentPriorityTests(unittest.TestCase):
    def test_non_empty_manual_values_override_env_defaults(self):
        with patch.dict(
            os.environ,
            {
                "API_KEY": "env-key",
                "MODEL_BASE_URL": "https://env.invalid/v1",
                "MODEL_NAME": "env-model",
            },
        ):
            resolved = resolve_ai_config(
                api_key="manual-key",
                base_url="https://manual.invalid/v1",
                model_name="manual-model",
            )
            exposed = apply_env_ai_settings(
                {
                    "ai_api_key": "manual-key",
                    "ai_api_url": "https://manual.invalid/v1",
                    "ai_model": "manual-model",
                }
            )

        self.assertEqual(resolved, {
            "api_key": "manual-key",
            "base_url": "https://manual.invalid/v1",
            "model_name": "manual-model",
        })
        self.assertEqual(exposed["ai_api_key"], "manual-key")
        self.assertEqual(exposed["ai_api_url"], "https://manual.invalid/v1")
        self.assertEqual(exposed["ai_model"], "manual-model")
        self.assertEqual(exposed["ai_env_overrides"], {})

    def test_empty_manual_values_fall_back_to_env_defaults(self):
        with patch.dict(
            os.environ,
            {"API_KEY": "", "MODEL_BASE_URL": "", "MODEL_NAME": ""},
        ):
            resolved = resolve_ai_config(api_key="", base_url="", model_name="")
            exposed = apply_env_ai_settings(
                {
                    "ai_api_key": "",
                    "ai_api_url": "",
                    "ai_model": "",
                }
            )

        self.assertEqual(resolved["api_key"], "")
        self.assertEqual(resolved["base_url"], "")
        self.assertEqual(resolved["model_name"], "")
        self.assertEqual(exposed["ai_api_key"], "")
        self.assertEqual(exposed["ai_env_overrides"], {})

    def test_blank_manual_values_use_non_empty_env_defaults(self):
        with patch.dict(
            os.environ,
            {
                "API_KEY": "env-key",
                "MODEL_BASE_URL": "https://env.invalid/v1",
                "MODEL_NAME": "env-model",
            },
        ):
            resolved = resolve_ai_config(api_key="", base_url="", model_name="")
            exposed = apply_env_ai_settings(
                {"ai_api_key": "", "ai_api_url": "", "ai_model": ""}
            )

        self.assertEqual(resolved, {
            "api_key": "env-key",
            "base_url": "https://env.invalid/v1",
            "model_name": "env-model",
        })
        self.assertEqual(exposed["ai_api_key"], "env-key")
        self.assertEqual(exposed["ai_env_overrides"], {
            "api_key": True,
            "base_url": True,
            "model_name": True,
        })

    def test_db_ai_settings_allow_account_and_system_values_to_override_env(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "API_KEY": "env-key",
                "MODEL_BASE_URL": "https://env.invalid/v1",
                "MODEL_NAME": "env-model",
            },
        ):
            manager = DBManager(str(Path(directory) / "ai-env.db"))
            try:
                manager.set_system_setting("ai_api_key", "system-key")
                manager.set_system_setting("ai_api_url", "https://system.invalid/v1")
                manager.set_system_setting("ai_model", "system-model")
                manager.save_ai_reply_settings(
                    "account-1",
                    {
                        "ai_enabled": True,
                        "api_key": "account-key",
                        "base_url": "https://account.invalid/v1",
                        "model_name": "account-model",
                    },
                )
                result = manager.get_ai_reply_settings("account-1")
            finally:
                manager.conn.close()

        self.assertEqual(result["api_key"], "account-key")
        self.assertEqual(result["base_url"], "https://account.invalid/v1")
        self.assertEqual(result["model_name"], "account-model")

    def test_db_ai_settings_use_env_model_when_system_value_is_missing(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "API_KEY": "env-key",
                "MODEL_BASE_URL": "https://env.invalid/v1",
                "MODEL_NAME": "deepseek-v4.1-flash",
            },
        ):
            manager = DBManager(str(Path(directory) / "ai-env-default.db"))
            try:
                result = manager.get_ai_reply_settings("account-without-settings")
            finally:
                manager.conn.close()

        self.assertEqual(result["model_name"], "deepseek-v4.1-flash")
        self.assertEqual(result["base_url"], "https://env.invalid/v1")

    def test_compose_passes_ai_environment_variables_without_exposing_values(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn('API_KEY: "${API_KEY:-}"', compose)
        self.assertIn('MODEL_BASE_URL: "${MODEL_BASE_URL:-}"', compose)
        self.assertIn('MODEL_NAME: "${MODEL_NAME:-}"', compose)

    def test_settings_surface_displays_env_values_and_does_not_save_metadata(self):
        settings_source = (ROOT / "frontend/components/Settings.tsx").read_text(encoding="utf-8")
        api_source = (ROOT / "frontend/services/api.ts").read_text(encoding="utf-8")

        self.assertIn("settings.ai_env_overrides?.api_key", settings_source)
        self.assertIn("settings.ai_env_overrides?.base_url", settings_source)
        self.assertIn("settings.ai_env_overrides?.model_name", settings_source)
        self.assertIn("key !== 'ai_env_overrides'", api_source)
        self.assertNotIn("key === 'ai_api_key' && envOverrides.api_key", api_source)
        self.assertNotIn("disabled={Boolean(settings.ai_env_overrides", settings_source)
        ai_reply_source = (ROOT / "frontend/components/AIReply.tsx").read_text(encoding="utf-8")
        self.assertNotIn("disabled={Boolean(settings.ai_env_overrides", ai_reply_source)


if __name__ == "__main__":
    unittest.main()
