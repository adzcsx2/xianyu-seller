"""容器必须安装与滑块反检测运行时匹配的 Chromium。"""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class PatchrightBrowserRuntimeTests(unittest.TestCase):
    def test_patchright_version_is_pinned_for_stable_browser_revision(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")

        self.assertIn("patchright==1.62.3", requirements)

    def test_all_runtime_images_install_patchright_chromium(self):
        for name in ("Dockerfile", "Dockerfile-cn"):
            with self.subTest(name=name):
                source = (ROOT / name).read_text(encoding="utf-8")
                self.assertIn("patchright install chromium", source)

    def test_manual_captcha_uses_the_same_patchright_runtime(self):
        source = (ROOT / "utils" / "manual_captcha.py").read_text(encoding="utf-8")

        self.assertIn("from patchright.async_api import async_playwright", source)
        self.assertNotIn("from playwright.async_api import async_playwright", source)


if __name__ == "__main__":
    unittest.main()
