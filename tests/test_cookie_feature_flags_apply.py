import asyncio
import threading
import unittest

from app.cookie_manager import CookieManager
from app.feature_flags import FEATURE_FLAG_REGISTRY


def _snapshot():
    configured = {
        definition.key: definition.default
        for definition in FEATURE_FLAG_REGISTRY.definitions()
    }
    return FEATURE_FLAG_REGISTRY.build_snapshot(configured, revision=2)


class _FakeInstance:
    def __init__(self, fail=False, delay=0):
        self.fail = fail
        self.delay = delay
        self.calls = 0

    async def reconcile_feature_tasks(self):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("synthetic reconcile failure")


class CookieFeatureFlagApplyTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_loop_applies_to_all_instances(self):
        manager = object.__new__(CookieManager)
        manager.loop = asyncio.get_running_loop()
        instance = _FakeInstance()
        manager.instances = {"account-1": instance}

        result = manager.apply_feature_flags(_snapshot())
        result = await result

        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["instances"], {"account-1": "applied"})
        self.assertEqual(instance.calls, 1)

    async def test_cross_thread_application_and_instance_failure_isolated(self):
        loop = asyncio.new_event_loop()
        started = threading.Event()

        def run_loop():
            asyncio.set_event_loop(loop)
            started.set()
            loop.run_forever()

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()
        self.assertTrue(started.wait(2))
        try:
            manager = object.__new__(CookieManager)
            manager.loop = loop
            ok = _FakeInstance()
            failed = _FakeInstance(fail=True)
            manager.instances = {"ok": ok, "failed": failed}

            result = manager.apply_feature_flags(_snapshot(), timeout=2)

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["instances"], {"ok": "applied", "failed": "failed"})
            self.assertEqual(ok.calls, 1)
            self.assertEqual(failed.calls, 1)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=2)
            loop.close()

    async def test_no_instances_and_timeout_are_pending(self):
        manager = object.__new__(CookieManager)
        manager.loop = asyncio.get_running_loop()
        manager.instances = {}
        result = await manager.apply_feature_flags(_snapshot())
        self.assertEqual(result["status"], "pending")

        loop = asyncio.new_event_loop()
        started = threading.Event()

        def run_loop():
            asyncio.set_event_loop(loop)
            started.set()
            loop.run_forever()

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()
        self.assertTrue(started.wait(2))
        try:
            manager.loop = loop
            manager.instances = {"slow": _FakeInstance(delay=10)}
            result = manager.apply_feature_flags(_snapshot(), timeout=0.01)
            self.assertEqual(result["status"], "pending")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=2)
            loop.close()


if __name__ == "__main__":
    unittest.main()
