"""高风险服务端 API 的运行时功能门禁回归测试。"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


_tmp = tempfile.TemporaryDirectory()
os.environ.setdefault("DB_PATH", str(Path(_tmp.name) / "feature-gates.db"))

from app import reply_server  # noqa: E402
from app.feature_flags import FEATURE_FLAG_REGISTRY  # noqa: E402


class FeatureApiGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(reply_server.app)
        cls.user = {"user_id": 7, "username": "operator", "is_admin": False}

    def setUp(self):
        reply_server.app.dependency_overrides[reply_server.get_current_user] = (
            lambda: self.user
        )

    def tearDown(self):
        reply_server.app.dependency_overrides.clear()

    def _snapshot(self, disabled_key):
        configured = {
            definition.key: definition.default
            for definition in FEATURE_FLAG_REGISTRY.definitions()
        }
        snapshot = FEATURE_FLAG_REGISTRY.build_snapshot(configured)
        snapshot.effective[disabled_key] = False
        return snapshot

    def _assert_disabled(self, response, feature):
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(
            response.json()["detail"],
            {
                "code": "feature_disabled",
                "feature": feature,
                "message": "功能已关闭，请到系统设置 > 功能区开启",
            },
        )

    def test_cards_and_automation_stop_before_domain_calls(self):
        with patch.object(
            reply_server.db_manager,
            "get_feature_flags",
            return_value=self._snapshot("feature_cards_enabled"),
        ), patch.object(reply_server.db_manager, "create_card") as create_card:
            response = self.client.post("/cards", json={})
        self._assert_disabled(response, "feature_cards_enabled")
        create_card.assert_not_called()

        with patch.object(
            reply_server.db_manager,
            "get_feature_flags",
            return_value=self._snapshot("feature_product_automation_enabled"),
        ), patch.object(reply_server.product_automation, "run_filter_rule") as run_rule:
            response = self.client.post("/product-automation/filter-rules/1/run")
        self._assert_disabled(response, "feature_product_automation_enabled")
        run_rule.assert_not_called()

    def test_knowledge_and_ai_writes_stop_before_domain_calls(self):
        with patch.object(
            reply_server.db_manager,
            "get_feature_flags",
            return_value=self._snapshot("feature_knowledge_base_enabled"),
        ), patch.object(reply_server.db_manager, "create_knowledge_base") as create_base:
            response = self.client.post("/knowledge-bases", json={"name": "test"})
        self._assert_disabled(response, "feature_knowledge_base_enabled")
        create_base.assert_not_called()

        with patch.object(
            reply_server.db_manager,
            "get_feature_flags",
            return_value=self._snapshot("feature_ai_reply_enabled"),
        ), patch.object(reply_server.db_manager, "update_ai_reply_profile") as update_style:
            response = self.client.put(
                "/ai-reply-style",
                json={"expected_version": 1, "reply_style": "friendly"},
            )
        self._assert_disabled(response, "feature_ai_reply_enabled")
        update_style.assert_not_called()

    def test_auto_reply_mutation_stops_before_keyword_or_reply_writes(self):
        with patch.object(
            reply_server.db_manager,
            "get_feature_flags",
            return_value=self._snapshot("feature_auto_reply_enabled"),
        ), patch.object(reply_server.db_manager, "save_default_reply") as save_reply:
            response = self.client.put(
                "/default-replies/account",
                json={"enabled": True, "reply_content": "hello", "reply_once": False},
            )
        self._assert_disabled(response, "feature_auto_reply_enabled")
        save_reply.assert_not_called()

    def test_item_sync_order_sync_and_buyer_actions_stop_before_side_effects(self):
        with patch.object(
            reply_server.db_manager,
            "get_feature_flags",
            return_value=self._snapshot("item_sync_enabled"),
        ), patch.object(reply_server.db_manager, "get_all_cookies") as get_cookies:
            response = self.client.post("/items/get-all-from-account", json={})
        self._assert_disabled(response, "item_sync_enabled")
        get_cookies.assert_not_called()

        with patch.object(
            reply_server.db_manager,
            "get_feature_flags",
            return_value=self._snapshot("order_sync_enabled"),
        ), patch.object(reply_server.db_manager, "get_all_cookies") as get_cookies:
            response = self.client.post("/api/orders/refresh", data={})
        self._assert_disabled(response, "order_sync_enabled")
        get_cookies.assert_not_called()

        with patch.object(
            reply_server.db_manager,
            "get_feature_flags",
            return_value=self._snapshot("feature_buyer_interaction_enabled"),
        ), patch.object(reply_server.db_manager, "get_all_cookies") as get_cookies:
            response = self.client.put(
                "/api/seller-features/account",
                json={"auto_rate_enabled": True},
            )
        self._assert_disabled(response, "feature_buyer_interaction_enabled")
        get_cookies.assert_not_called()

    def test_disabled_feature_does_not_hide_read_only_settings_and_enabled_path_works(self):
        with patch.object(
            reply_server.db_manager,
            "get_feature_flags",
            return_value=self._snapshot("feature_cards_enabled"),
        ):
            response = self.client.get("/feature-flags")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["effective"]["feature_cards_enabled"])

        with patch.object(
            reply_server.db_manager,
            "get_feature_flags",
            return_value=self._snapshot("feature_cards_enabled"),
        ), patch.object(reply_server.db_manager, "create_card", return_value=12) as create_card:
            snapshot = self._snapshot("feature_cards_enabled")
            snapshot.effective["feature_cards_enabled"] = True
            with patch.object(reply_server.db_manager, "get_feature_flags", return_value=snapshot):
                response = self.client.post("/cards", json={})
        self.assertEqual(response.status_code, 200, response.text)
        create_card.assert_called_once()


if __name__ == "__main__":
    unittest.main()
