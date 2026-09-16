import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils.env_loader import load_env_file


class EnvLoaderTests(unittest.TestCase):
    def test_loads_common_dotenv_syntax_and_preserves_process_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text(
                "\ufeff# comment\r\n"
                "PLAIN_VALUE=from-file\r\n"
                "DOUBLE_VALUE=\"quoted value\"\r\n"
                "SINGLE_VALUE='single value'\r\n"
                "export LOADED_EXPORT=from-export\r\n"
                "export EXPORTED_VALUE=exported\r\n"
                "HASH_VALUE=abc#def\r\n"
                "COMMENT_VALUE=abc # trailing comment\r\n"
                "EMPTY_VALUE=\r\n"
                "NOT_A_VARIABLE\r\n",
                encoding="utf-8",
                newline="",
            )

            with patch.dict(os.environ, {"EXPORTED_VALUE": "from-process"}, clear=True):
                loaded = load_env_file(env_file)

                self.assertEqual(loaded, 7)
                self.assertEqual(os.environ["PLAIN_VALUE"], "from-file")
                self.assertEqual(os.environ["DOUBLE_VALUE"], "quoted value")
                self.assertEqual(os.environ["SINGLE_VALUE"], "single value")
                self.assertEqual(os.environ["LOADED_EXPORT"], "from-export")
                self.assertEqual(os.environ["EXPORTED_VALUE"], "from-process")
                self.assertEqual(os.environ["HASH_VALUE"], "abc#def")
                self.assertEqual(os.environ["COMMENT_VALUE"], "abc")
                self.assertEqual(os.environ["EMPTY_VALUE"], "")

    def test_missing_file_is_a_noop(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_file = Path(temp_dir) / "missing.env"
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(load_env_file(missing_file), 0)
                self.assertEqual(dict(os.environ), {})

    def test_startup_loads_dotenv_before_importing_environment_consumers(self):
        source = (Path(__file__).resolve().parents[1] / "Start.py").read_text(
            encoding="utf-8"
        )

        self.assertLess(
            source.index("load_env_file(_ENV_FILE)"),
            source.index("from app.config import"),
        )


if __name__ == "__main__":
    unittest.main()
