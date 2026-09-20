import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SLIDEX_FINGERPRINT_FIX_REVISION = "8a7e9616220390c5927ac282f576a181a380edef"


class DependencySecurityTests(unittest.TestCase):
    def test_unused_vulnerable_blackboxprotobuf_dependency_is_removed(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertNotIn("blackboxprotobuf", requirements.lower())

    def test_slidex_pin_contains_headful_fingerprint_and_same_thread_cleanup_fixes(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")

        self.assertIn(
            f"slidex @ git+https://github.com/dengyie/slidex.git@{SLIDEX_FINGERPRINT_FIX_REVISION}",
            requirements,
        )


if __name__ == "__main__":
    unittest.main()
