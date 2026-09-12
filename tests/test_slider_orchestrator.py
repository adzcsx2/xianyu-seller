import asyncio
import unittest

from utils.slider_orchestrator import (
    run_slider_async_strict,
    validate_slider_result,
)
from utils.slider_trajectory_pool import safe_storage_key


class SliderVerificationResultTests(unittest.TestCase):
    def test_visual_success_without_x5_cookie_is_failure(self):
        result = validate_slider_result(True, {"session": "present"})

        self.assertFalse(result.success)
        self.assertIn("x5sec", result.message)

    def test_success_requires_x5_cookie_and_preserves_cookie_snapshot(self):
        cookies = {"x5sec": "ticket", "session": "present"}
        result = validate_slider_result(True, cookies)

        self.assertTrue(result.success)
        self.assertEqual(result.x5_cookies, {"x5sec": "ticket"})
        self.assertEqual(result.cookies, cookies)

    def test_challenge_markers_are_not_success_tickets(self):
        result = validate_slider_result(
            True,
            {"x5secdata": "challenge", "x5sectag": "1"},
        )

        self.assertFalse(result.success)
        self.assertIn("x5sec", result.message)

    def test_async_solver_shape_is_normalized(self):
        class FakeSolver:
            pure_user_id = "account"

            async def solve(self, _url):
                return True, {"x5sec": "ticket"}

        result = asyncio.run(run_slider_async_strict(FakeSolver(), "https://example.test"))

        self.assertTrue(result.success)
        self.assertEqual(result.engine, "playwright")

    def test_storage_key_cannot_escape_the_data_directory(self):
        storage_key = safe_storage_key("../../outside\\account")

        self.assertNotIn("/", storage_key)
        self.assertNotIn("\\", storage_key)
        self.assertNotIn("..", storage_key)


if __name__ == "__main__":
    unittest.main()
