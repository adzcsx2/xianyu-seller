"""P5.2 red tests for the final first-party identity contract.

Legacy values are assembled from fragments so this test file does not become
an additional tracked residue when the migration is complete.
"""

from __future__ import annotations

import hashlib
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _legacy_brand_tokens() -> tuple[str, ...]:
    return (
        "闲鱼" + "超级管家",
        "闲鱼" + "智控",
        "XIANYU SUPER " + "BUTLER",
        "xianyu-super-" + "butler",
        "23" + "Star",
        "zhinian" + "boke",
        "cor" + "leom",
    )


def _tracked_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


class BrandIdentityContractTests(unittest.TestCase):
    def test_user_surfaces_use_target_brand_and_repository(self):
        sources = {
            "README": (ROOT / "README.md").read_text(encoding="utf-8"),
            "frontend index": (ROOT / "frontend/index.html").read_text(encoding="utf-8"),
            "static index": (ROOT / "static/index.html").read_text(encoding="utf-8"),
            "app": (ROOT / "frontend/App.tsx").read_text(encoding="utf-8"),
            "sidebar": (ROOT / "frontend/components/Sidebar.tsx").read_text(encoding="utf-8"),
            "about": (ROOT / "frontend/components/About.tsx").read_text(encoding="utf-8"),
            "worker": (ROOT / "deploy/announcement-worker.js").read_text(encoding="utf-8"),
        }
        for name, source in sources.items():
            with self.subTest(surface=name):
                self.assertIn("闲鱼卖家", source)
                self.assertNotIn("闲鱼" + "超级管家", source)
                self.assertNotIn("闲鱼" + "智控", source)

        about = sources["about"]
        self.assertIn("https://github.com/adzcsx2/xianyu-seller", about)
        self.assertNotIn("xy." + "corleom.com", about)
        self.assertNotIn("mailto:" + "admin@corleom.com", about)

    def test_old_first_party_identity_only_survives_in_one_readme_fork_line(self):
        old_tokens = _legacy_brand_tokens()
        hits: list[tuple[str, int, str]] = []
        for path in _tracked_paths():
            if path.name == "LICENSE" or path.as_posix().endswith("frontend/package-lock.json"):
                continue
            if not path.is_file():
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for number, line in enumerate(lines, 1):
                if any(token in line for token in old_tokens):
                    hits.append((path.relative_to(ROOT).as_posix(), number, line))

        allowed = [item for item in hits if item[0] == "README.md" and "fork" in item[2].lower()]
        self.assertEqual(allowed, hits, msg=f"unexpected legacy identity hits: {hits}")
        self.assertEqual(len(allowed), 1)
        self.assertIn("https://github.com/23" + "Star/xianyu-super-butler", allowed[0][2])

    def test_distribution_identity_matrix_is_targeted(self):
        package = (ROOT / "frontend/package.json").read_text(encoding="utf-8")
        package_lock = (ROOT / "frontend/package-lock.json").read_text(encoding="utf-8")
        html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
        docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        docker_cn = (ROOT / "Dockerfile-cn").read_text(encoding="utf-8")
        compose = "\n".join(
            (ROOT / name).read_text(encoding="utf-8")
            for name in ("docker-compose.yml", "docker-compose-cn.yml", "docker-compose.nas.yml")
        )
        workflow = (ROOT / ".github/workflows/docker-publish.yml").read_text(encoding="utf-8")

        self.assertIn('"name": "xianyu-seller-frontend"', package)
        self.assertIn('"name": "xianyu-seller-frontend"', package_lock)
        self.assertIn('data-app-shell="xianyu-seller"', html)
        for source in (docker, docker_cn):
            self.assertIn('maintainer="adzcsx2"', source)
            self.assertIn('repository="https://github.com/adzcsx2/xianyu-seller"', source)
            self.assertIn('author="adzcsx2"', source)
        self.assertIn("xianyu-seller:latest", compose)
        self.assertIn("xianyu-seller-nginx", compose)
        self.assertIn("ghcr.io/adzcsx2/xianyu-seller:latest", compose)
        self.assertIn("IMAGE_NAME: ${{ github.repository_owner }}/xianyu-seller", workflow)

    def test_license_and_third_party_lockfile_metadata_are_excluded_from_brand_rewrite(self):
        license_hash = hashlib.sha256((ROOT / "LICENSE").read_bytes()).hexdigest().upper()
        self.assertEqual(
            license_hash,
            "E0EEDBA615D5CD1B986AFB6C5B3A4B1AE33713E7E9DC74D19DAEC5E3221F9D2E",
        )
        lockfile = (ROOT / "frontend/package-lock.json").read_text(encoding="utf-8")
        self.assertIn("https://github.com/sponsors/sindresorhus", lockfile)


if __name__ == "__main__":
    unittest.main()
