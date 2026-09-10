import asyncio
import unittest
from unittest.mock import patch

from app.feature_flags import FEATURE_FLAG_REGISTRY, FeatureFlagSnapshot
from XianyuAutoAsync import XianyuLive


class FeatureTaskLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.live = object.__new__(XianyuLive)
        self.live.cookie_id = "lifecycle-test"
        self.live.background_tasks = set()
        self.live._profile_synced = False
        self.live.profile_sync_task = None
        self.live.heartbeat_task = object()
        self.live.cleanup_task = object()
        for attr in (
            "token_refresh_task",
            "cookie_refresh_task",
            "item_sync_task",
            "order_sync_task",
            "item_polish_task",
            "delivery_timeout_task",
            "buyer_interaction_task",
        ):
            setattr(self.live, attr, None)

        async def worker():
            while True:
                await asyncio.sleep(3600)

        async def profile_worker():
            while True:
                await asyncio.sleep(3600)

        self.live.token_refresh_loop = worker
        self.live.cookie_refresh_loop = worker
        self.live.item_sync_loop = worker
        self.live.order_sync_loop = worker
        self.live.item_polish_loop = worker
        self.live.delivery_timeout_loop = worker
        self.live.buyer_interaction_loop = worker
        self.live._sync_account_profile = profile_worker

    async def asyncTearDown(self):
        tasks = [
            getattr(self.live, name, None)
            for name in (
                "token_refresh_task",
                "cookie_refresh_task",
                "item_sync_task",
                "order_sync_task",
                "item_polish_task",
                "delivery_timeout_task",
                "buyer_interaction_task",
                "profile_sync_task",
            )
        ]
        for task in tasks:
            if isinstance(task, asyncio.Task) and not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(
                *(task for task in tasks if isinstance(task, asyncio.Task)),
                return_exceptions=True,
            )

    def _snapshot(self, **overrides):
        configured = {
            definition.key: definition.default
            for definition in FEATURE_FLAG_REGISTRY.definitions()
        }
        configured.update(overrides)
        effective = dict(configured)
        if not effective["feature_items_enabled"]:
            for key in (
                "item_sync_enabled",
                "auto_polish_enabled",
                "feature_product_automation_enabled",
            ):
                effective[key] = False
        if not effective["feature_orders_enabled"]:
            for key in (
                "order_sync_enabled",
                "delivery_timeout_alert_enabled",
                "auto_delivery_enabled",
                "feature_buyer_interaction_enabled",
            ):
                effective[key] = False
        return FeatureFlagSnapshot(
            revision=1,
            configured=configured,
            effective=effective,
            definitions=FEATURE_FLAG_REGISTRY.definitions(),
            warnings=(),
        )

    async def test_reconcile_starts_enabled_tasks_once_and_preserves_core(self):
        snapshot = self._snapshot(auto_polish_enabled=True)
        with patch("XianyuAutoAsync.db_manager.get_feature_flags", return_value=snapshot):
            await self.live.reconcile_feature_tasks()
            first = {
                name: getattr(self.live, name)
                for name in (
                    "token_refresh_task",
                    "cookie_refresh_task",
                    "item_sync_task",
                    "order_sync_task",
                    "item_polish_task",
                    "delivery_timeout_task",
                    "buyer_interaction_task",
                )
            }
            await self.live.reconcile_feature_tasks()

        self.assertTrue(all(task and not task.done() for task in first.values()))
        self.assertEqual(first["token_refresh_task"], self.live.token_refresh_task)
        self.assertEqual(first["order_sync_task"], self.live.order_sync_task)
        self.assertIsNotNone(self.live.profile_sync_task)
        self.assertIs(self.live.heartbeat_task, self.live.heartbeat_task)
        self.assertIsNotNone(self.live.cleanup_task)

    async def test_disabled_tasks_are_cancelled_and_cleared_without_touching_core(self):
        enabled = self._snapshot(auto_polish_enabled=True)
        disabled = self._snapshot(
            feature_items_enabled=False,
            feature_orders_enabled=False,
            scheduled_token_refresh_enabled=False,
            browser_cookie_refresh_enabled=False,
            account_profile_auto_sync_enabled=False,
            feature_buyer_interaction_enabled=False,
            auto_polish_enabled=True,
        )
        with patch("XianyuAutoAsync.db_manager.get_feature_flags", return_value=enabled):
            await self.live.reconcile_feature_tasks()
        heartbeat = self.live.heartbeat_task
        cleanup = self.live.cleanup_task

        with patch("XianyuAutoAsync.db_manager.get_feature_flags", return_value=disabled):
            await self.live.reconcile_feature_tasks()

        for name in (
            "token_refresh_task",
            "cookie_refresh_task",
            "item_sync_task",
            "order_sync_task",
            "item_polish_task",
            "order_sync_task",
            "delivery_timeout_task",
            "buyer_interaction_task",
            "profile_sync_task",
        ):
            self.assertIsNone(getattr(self.live, name), name)
        self.assertIs(self.live.heartbeat_task, heartbeat)
        self.assertIs(self.live.cleanup_task, cleanup)

    async def test_disabled_task_does_not_reappear_on_reconnect_reconcile(self):
        disabled = self._snapshot(scheduled_token_refresh_enabled=False)
        with patch("XianyuAutoAsync.db_manager.get_feature_flags", return_value=disabled):
            await self.live.reconcile_feature_tasks()
            await self.live.reconcile_feature_tasks()
        self.assertIsNone(self.live.token_refresh_task)
        self.assertIsNotNone(self.live.cookie_refresh_task)


if __name__ == "__main__":
    unittest.main()
