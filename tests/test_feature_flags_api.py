"""Feature flags HTTP 合同：认证、严格输入、revision 和逐键写保护。"""

import os
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient


_tmp = tempfile.TemporaryDirectory()
os.environ.setdefault("DB_PATH", str(Path(_tmp.name) / "feature-api.db"))

from app import reply_server  # noqa: E402
from app.feature_flags import FEATURE_FLAG_REGISTRY  # noqa: E402


class FeatureFlagApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(reply_server.app)
        cls.user = {"user_id": 7, "username": "operator", "is_admin": False}
        cls.admin = {"user_id": 1, "username": reply_server.ADMIN_USERNAME, "is_admin": True}

    def tearDown(self):
        reply_server.app.dependency_overrides.clear()

    def setUp(self):
        with reply_server.db_manager.lock:
            for definition in FEATURE_FLAG_REGISTRY.definitions():
                reply_server.db_manager.conn.execute(
                    "UPDATE system_settings SET value = ? WHERE key = ?",
                    ("true" if definition.default else "false", definition.key),
                )
            reply_server.db_manager.conn.execute(
                "UPDATE system_settings SET value = '0' WHERE key = 'feature_flags_revision'"
            )
            reply_server.db_manager.conn.commit()

    def _as_user(self, user=None):
        reply_server.app.dependency_overrides[reply_server.get_current_user] = (
            lambda: user or self.user
        )

    def _as_admin(self):
        reply_server.app.dependency_overrides[reply_server.require_admin] = lambda: self.admin

    def test_get_requires_auth_and_returns_only_feature_snapshot(self):
        response = self.client.get("/feature-flags")
        self.assertEqual(response.status_code, 401)

        self._as_user()
        response = self.client.get("/feature-flags")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertIn("revision", payload)
        self.assertEqual(set(payload), {"revision", "configured", "effective", "definitions", "warnings"})
        self.assertNotIn("smtp_password", payload)

    def test_only_admin_can_put_and_success_returns_canonical_snapshot(self):
        self._as_user()
        response = self.client.put(
            "/feature-flags",
            json={"expected_revision": 0, "flags": {"feature_items_enabled": False}},
        )
        self.assertEqual(response.status_code, 403)

        self._as_admin()
        response = self.client.put(
            "/feature-flags",
            json={"expected_revision": 0, "flags": {"feature_items_enabled": False}},
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertFalse(payload["configured"]["feature_items_enabled"])
        self.assertEqual(payload["changed_keys"], ["feature_items_enabled"])
        self.assertEqual(payload["runtime_apply"], "pending")

    def test_patch_rejects_empty_unknown_non_boolean_and_extra_fields(self):
        self._as_admin()
        cases = (
            {"expected_revision": 0, "flags": {}},
            {"expected_revision": 0, "flags": {"unknown": True}},
            {"expected_revision": 0, "flags": {"feature_items_enabled": "false"}},
            {"expected_revision": 0, "flags": {"feature_items_enabled": 0}},
            {"expected_revision": 0, "flags": {"feature_items_enabled": True}, "extra": True},
        )
        for body in cases:
            with self.subTest(body=body):
                response = self.client.put("/feature-flags", json=body)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(response.json()["detail"]["code"], "invalid_feature_flag")

    def test_revision_conflict_is_stable_and_does_not_overwrite(self):
        self._as_admin()
        first = self.client.put(
            "/feature-flags",
            json={"expected_revision": 0, "flags": {"feature_orders_enabled": False}},
        )
        self.assertEqual(first.status_code, 200, first.text)
        second = self.client.put(
            "/feature-flags",
            json={"expected_revision": 0, "flags": {"feature_items_enabled": False}},
        )
        self.assertEqual(second.status_code, 409, second.text)
        self.assertEqual(second.json()["detail"]["code"], "feature_revision_conflict")
        self._as_user()
        snapshot = self.client.get("/feature-flags").json()
        self.assertFalse(snapshot["configured"]["feature_orders_enabled"])
        self.assertTrue(snapshot["configured"]["feature_items_enabled"])

    def test_generic_feature_setting_write_is_rejected_but_normal_setting_works(self):
        self._as_admin()
        response = self.client.put(
            "/system-settings/feature_items_enabled",
            json={"value": "false"},
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("/feature-flags", response.json()["detail"])

        response = self.client.put(
            "/system-settings/theme_color",
            json={"value": "blue"},
        )
        self.assertEqual(response.status_code, 200, response.text)


if __name__ == "__main__":
    unittest.main()
