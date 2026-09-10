"""AI 模型列表接口与配置展示的回归测试。"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app import reply_server
from app.ai_models import extract_model_ids, fetch_available_models


ROOT = Path(__file__).resolve().parents[1]


class AIModelListingTests(unittest.TestCase):
    def test_extract_model_ids_supports_openai_compatible_payload(self):
        payload = {
            "data": [
                {"id": "gpt-4o"},
                {"id": "qwen-plus"},
                {"id": "gpt-4o"},
                {"id": ""},
            ]
        }

        self.assertEqual(extract_model_ids(payload), ["gpt-4o", "qwen-plus"])

    def test_fetch_models_uses_bearer_key_and_returns_sorted_ids(self):
        response = Mock()
        response.json.return_value = {
            "data": [{"id": "z-model"}, {"id": "a-model"}]
        }
        response.raise_for_status.return_value = None

        with patch("app.ai_models.requests.get", return_value=response) as request:
            result = fetch_available_models(
                "https://provider.invalid/v1",
                "secret-key",
            )

        self.assertEqual(result, ["a-model", "z-model"])
        request.assert_called_once_with(
            "https://provider.invalid/v1/models",
            headers={"Authorization": "Bearer secret-key"},
            timeout=15,
        )

    def test_missing_base_url_is_rejected_without_network_call(self):
        with patch("app.ai_models.requests.get") as request:
            with self.assertRaises(ValueError):
                fetch_available_models("", "secret-key")
        request.assert_not_called()

    def test_frontend_exposes_refreshable_model_dropdown_and_env_key(self):
        settings_source = (ROOT / "frontend/components/Settings.tsx").read_text(
            encoding="utf-8"
        )
        ai_reply_source = (ROOT / "frontend/components/AIReply.tsx").read_text(
            encoding="utf-8"
        )
        api_source = (ROOT / "frontend/services/api.ts").read_text(encoding="utf-8")

        self.assertIn("getAvailableAIModels", api_source)
        self.assertIn("ai-models", api_source)
        self.assertIn("刷新模型列表", settings_source)
        self.assertIn("availableModels", settings_source)
        self.assertIn("settings.ai_api_key || ''", settings_source)
        self.assertIn("showApiKey", settings_source)
        self.assertIn("getAvailableAIModels(cookieId)", ai_reply_source)
        self.assertIn("settings.ai_env_overrides?.api_key", ai_reply_source)
        for source in (settings_source, ai_reply_source, api_source):
            self.assertNotIn("qwen-plus", source)
            self.assertNotIn("qwen-turbo", source)
            self.assertNotIn("gpt-3.5-turbo", source)
            self.assertNotIn("gpt-4", source)


class AIModelEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(reply_server.app)
        reply_server.app.dependency_overrides[reply_server.get_current_user] = (
            lambda: {"user_id": 1, "username": "admin", "is_admin": True}
        )

    def tearDown(self):
        reply_server.app.dependency_overrides.clear()

    def test_endpoint_returns_models_from_effective_system_config(self):
        with (
            patch.object(
                reply_server.db_manager,
                "get_all_system_settings",
                return_value={
                    "ai_api_url": "https://provider.invalid/v1",
                    "ai_api_key": "configured-key",
                    "ai_model": "current-model",
                },
            ),
            patch.object(
                reply_server,
                "fetch_available_models",
                return_value=["a-model", "z-model"],
            ) as fetch,
        ):
            response = self.client.get("/ai-models")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["models"], ["a-model", "z-model"])
        fetch.assert_called_once()

    def test_endpoint_hides_upstream_failure_details(self):
        with (
            patch.object(
                reply_server.db_manager,
                "get_all_system_settings",
                return_value={"ai_api_url": "https://provider.invalid/v1"},
            ),
            patch.object(
                reply_server,
                "fetch_available_models",
                side_effect=RuntimeError("secret-key leaked by provider"),
            ),
        ):
            response = self.client.get("/ai-models")

        self.assertEqual(response.status_code, 502)
        self.assertNotIn("secret-key", response.text)


if __name__ == "__main__":
    unittest.main()
