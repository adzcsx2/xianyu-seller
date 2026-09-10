"""功能开关 registry、持久化与原子更新的语义合同。"""

import sqlite3
import tempfile
import unittest
import importlib
import os
from pathlib import Path

try:
    feature_flags = importlib.import_module("app.feature_flags")
except ModuleNotFoundError:
    # 保持 RED 为合同断言失败，而不是让测试因 import/fixture 错误中止。
    feature_flags = None


EXPECTED_KEYS = (
    "feature_items_enabled",
    "item_sync_enabled",
    "auto_polish_enabled",
    "feature_orders_enabled",
    "order_sync_enabled",
    "delivery_timeout_alert_enabled",
    "auto_delivery_enabled",
    "feature_cards_enabled",
    "feature_buyer_interaction_enabled",
    "feature_auto_reply_enabled",
    "feature_ai_reply_enabled",
    "feature_knowledge_base_enabled",
    "feature_product_automation_enabled",
    "account_profile_auto_sync_enabled",
    "scheduled_token_refresh_enabled",
    "browser_cookie_refresh_enabled",
)


class FeatureFlagRegistryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(feature_flags, "缺少 app.feature_flags，registry 合同尚未实现")

    def test_registry_is_ordered_and_has_the_complete_boolean_contract(self):
        registry = getattr(feature_flags, "FEATURE_FLAG_REGISTRY", None)
        self.assertIsNotNone(registry, "必须存在唯一的 FEATURE_FLAG_REGISTRY")
        definitions = tuple(registry.definitions())
        self.assertEqual(tuple(item.key for item in definitions), EXPECTED_KEYS)
        self.assertEqual(len({item.key for item in definitions}), len(EXPECTED_KEYS))
        self.assertTrue(all(type(item.default) is bool for item in definitions))
        self.assertTrue(all(isinstance(item.depends_on, tuple) for item in definitions))

    def test_dependencies_are_known_and_acyclic(self):
        registry = feature_flags.FEATURE_FLAG_REGISTRY
        keys = {item.key for item in registry.definitions()}
        for item in registry.definitions():
            self.assertTrue(set(item.depends_on) <= keys, item.key)
        self.assertEqual(tuple(registry.topological_keys()), EXPECTED_KEYS)

    def test_strict_http_patch_rejects_truthy_non_booleans(self):
        registry = feature_flags.FEATURE_FLAG_REGISTRY
        for value in ("false", 0, 1, None, {}, []):
            with self.subTest(value=value):
                with self.assertRaises(feature_flags.InvalidFeatureFlag):
                    registry.validate_patch({"feature_items_enabled": value})
        self.assertEqual(
            registry.validate_patch({"feature_items_enabled": False}),
            {"feature_items_enabled": False},
        )

    def test_unknown_or_empty_patch_is_rejected(self):
        registry = feature_flags.FEATURE_FLAG_REGISTRY
        for patch in ({}, {"unknown_feature": True}):
            with self.subTest(patch=patch):
                with self.assertRaises(feature_flags.InvalidFeatureFlag):
                    registry.validate_patch(patch)


class FeatureFlagDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = str(Path(self.tmp.name) / "feature-flags.db")
        self._old_db_path = os.environ.get("DB_PATH")
        os.environ["DB_PATH"] = self.db_path
        from app.db_manager import DBManager

        self.db = DBManager(self.db_path)
        self.assertTrue(
            hasattr(self.db, "get_feature_flags"),
            "DBManager 尚未提供 get_feature_flags，原子开关合同尚未实现",
        )

    def tearDown(self):
        self.db.conn.close()
        if self._old_db_path is None:
            os.environ.pop("DB_PATH", None)
        else:
            os.environ["DB_PATH"] = self._old_db_path
        self.tmp.cleanup()

    def test_missing_keys_use_compatibility_defaults_and_existing_values_win(self):
        snapshot = self.db.get_feature_flags()
        self.assertEqual(set(snapshot.configured), set(EXPECTED_KEYS))
        self.db.set_system_setting("feature_items_enabled", "false")
        self.db.set_system_setting("item_sync_enabled", "true")
        from app.db_manager import DBManager
        reopened = DBManager(self.db.db_path)
        try:
            snapshot = reopened.get_feature_flags()
            self.assertFalse(snapshot.configured["feature_items_enabled"])
            self.assertTrue(snapshot.configured["item_sync_enabled"])
        finally:
            reopened.conn.close()

    def test_parent_disabled_keeps_child_configured_but_effective_false(self):
        current = self.db.get_feature_flags()
        snapshot = self.db.update_feature_flags_atomic(
            {
                "feature_items_enabled": False,
                "item_sync_enabled": True,
                "auto_delivery_enabled": True,
            },
            current.revision,
        )
        self.assertFalse(snapshot.configured["feature_items_enabled"])
        self.assertTrue(snapshot.configured["item_sync_enabled"])
        self.assertFalse(snapshot.effective["item_sync_enabled"])
        self.assertFalse(snapshot.effective["auto_delivery_enabled"])

    def test_atomic_patch_increments_revision_and_duplicate_save_is_idempotent(self):
        current = self.db.get_feature_flags()
        updated = self.db.update_feature_flags_atomic(
            {"feature_items_enabled": False, "item_sync_enabled": False},
            current.revision,
        )
        self.assertEqual(updated.revision, current.revision + 1)
        repeated = self.db.update_feature_flags_atomic(
            {"feature_items_enabled": False, "item_sync_enabled": False},
            updated.revision,
        )
        self.assertEqual(repeated.revision, updated.revision)
        self.assertEqual(repeated.configured, updated.configured)

    def test_unknown_key_does_not_change_database_or_revision(self):
        before = self.db.get_feature_flags()
        with self.assertRaises(feature_flags.InvalidFeatureFlag):
            self.db.update_feature_flags_atomic({"unknown_feature": True}, before.revision)
        after = self.db.get_feature_flags()
        self.assertEqual(after.revision, before.revision)
        self.assertEqual(after.configured, before.configured)

    def test_mid_transaction_failure_rolls_back_all_values_and_revision(self):
        before = self.db.get_feature_flags()
        with self.db.lock:
            self.db.conn.execute(
                """
                CREATE TRIGGER fail_feature_update
                BEFORE UPDATE OF value ON system_settings
                WHEN NEW.key = 'item_sync_enabled'
                BEGIN
                    SELECT RAISE(ABORT, 'injected feature update failure');
                END
                """
            )
            self.db.conn.commit()
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.update_feature_flags_atomic(
                {"feature_items_enabled": False, "item_sync_enabled": False},
                before.revision,
            )
        after = self.db.get_feature_flags()
        self.assertEqual(after.revision, before.revision)
        self.assertEqual(after.configured, before.configured)

    def test_feature_updates_never_modify_per_account_buyer_flags(self):
        with self.db.lock:
            self.db.conn.execute(
                "INSERT INTO cookies (id, value, user_id, auto_rate_enabled, auto_flower_enabled, auto_thanks_enabled) VALUES (?, ?, ?, ?, ?, ?)",
                ("account-a", "synthetic", 1, 1, 0, 1),
            )
            self.db.conn.commit()
        before = self.db.get_buyer_interaction_settings("account-a")
        current = self.db.get_feature_flags()
        self.db.update_feature_flags_atomic(
            {"feature_orders_enabled": False, "feature_buyer_interaction_enabled": True},
            current.revision,
        )
        self.assertEqual(self.db.get_buyer_interaction_settings("account-a"), before)


if __name__ == "__main__":
    unittest.main()
