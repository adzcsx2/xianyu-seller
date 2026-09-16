import ast
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_frontend_builder():
    source_path = PROJECT_ROOT / "Start.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_build_frontend"
    )
    module = ast.Module(body=[function], type_ignores=[])
    namespace = {
        "Path": Path,
        "os": os,
        "shutil": shutil,
        "sys": sys,
        "_OK": "[OK]",
        "_INFO": "[INFO]",
        "_WARN": "[WARN]",
    }
    exec(compile(module, str(source_path), "exec"), namespace)
    return namespace["_build_frontend"]


class StartupFrontendBuildTests(unittest.TestCase):
    def test_prebuilt_frontend_is_usable_when_source_directory_is_absent(self):
        build_frontend = load_frontend_builder()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "static").mkdir()
            (root / "static" / "index.html").write_text(
                "<!doctype html><title>ready</title>",
                encoding="utf-8",
            )
            previous_cwd = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, {}, clear=True), patch("builtins.print"):
                    self.assertTrue(build_frontend())
            finally:
                os.chdir(previous_cwd)

    def test_startup_fails_when_source_and_prebuilt_frontend_are_both_absent(self):
        build_frontend = load_frontend_builder()
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_cwd = Path.cwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {}, clear=True), patch("builtins.print"):
                    self.assertFalse(build_frontend())
            finally:
                os.chdir(previous_cwd)

    def test_build_process_uses_absolute_frontend_bin_path(self):
        build_frontend = load_frontend_builder()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frontend = root / "frontend"
            frontend.mkdir()
            (frontend / "package-lock.json").write_text("{}", encoding="utf-8")
            previous_cwd = Path.cwd()
            try:
                os.chdir(root)
                executable_paths = {
                    "npm.cmd": str(root / "runtime" / "npm.cmd"),
                    "node.exe": str(root / "runtime" / "node.exe"),
                }

                def resolve_executable(name):
                    return executable_paths.get(name)

                with (
                    patch.dict(os.environ, {}, clear=True),
                    patch("builtins.print"),
                    patch("shutil.which", side_effect=resolve_executable),
                    patch(
                        "subprocess.run",
                        return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
                    ) as run,
                ):
                    self.assertTrue(build_frontend())
            finally:
                os.chdir(previous_cwd)

            expected_bin = str((frontend / "node_modules" / ".bin").resolve())
            child_path = run.call_args_list[0].kwargs["env"]["PATH"].split(os.pathsep)
            self.assertIn(expected_bin, child_path)


if __name__ == "__main__":
    unittest.main()
