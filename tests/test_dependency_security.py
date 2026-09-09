import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DependencySecurityTests(unittest.TestCase):
    def test_unused_vulnerable_blackboxprotobuf_dependency_is_removed(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertNotIn("blackboxprotobuf", requirements.lower())


if __name__ == "__main__":
    unittest.main()
