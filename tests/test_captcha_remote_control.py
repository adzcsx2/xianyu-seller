import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from utils.captcha_remote_control import CaptchaRemoteController


class CaptchaRemoteCoordinateTests(unittest.IsolatedAsyncioTestCase):
    async def test_relative_screenshot_coordinates_are_translated_to_page_coordinates(self):
        controller = CaptchaRemoteController()
        mouse = SimpleNamespace(move=AsyncMock(), down=AsyncMock(), up=AsyncMock())
        controller.active_sessions["session"] = {
            "page": SimpleNamespace(mouse=mouse),
            "screenshot_clip": {"x": 90, "y": 40, "width": 320, "height": 180},
        }

        self.assertTrue(await controller.handle_mouse_event("session", "down", 15, 20))

        mouse.move.assert_awaited_once_with(105, 60)
        mouse.down.assert_awaited_once_with()

    async def test_coordinates_outside_the_captcha_image_are_rejected(self):
        controller = CaptchaRemoteController()
        mouse = SimpleNamespace(move=AsyncMock(), down=AsyncMock(), up=AsyncMock())
        controller.active_sessions["session"] = {
            "page": SimpleNamespace(mouse=mouse),
            "screenshot_clip": {"x": 90, "y": 40, "width": 320, "height": 180},
        }

        self.assertFalse(await controller.handle_mouse_event("session", "move", 321, 20))
        mouse.move.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
