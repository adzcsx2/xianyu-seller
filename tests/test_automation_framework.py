import importlib.util
import io
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = PROJECT_ROOT / "scripts" / "run_tests.py"


def load_runner():
    if not RUNNER_PATH.exists():
        raise AssertionError(f"测试入口不存在: {RUNNER_PATH}")
    spec = importlib.util.spec_from_file_location("project_test_runner", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AutomationFrameworkTests(unittest.TestCase):
    def test_core_and_e2e_suites_are_disjoint_and_complete(self):
        runner = load_runner()
        modules = runner.discover_test_modules(PROJECT_ROOT / "tests")
        core = runner.select_test_modules(modules, "core")
        e2e = runner.select_test_modules(modules, "e2e")

        self.assertIn("tests.test_auth_session", core)
        self.assertIn("tests.test_password_login_ui", e2e)
        self.assertNotIn("tests.test_password_login_ui", core)
        self.assertEqual(set(core) | set(e2e), set(modules))
        self.assertFalse(set(core) & set(e2e))

    def test_snapshot_database_uses_real_data_without_mutating_source(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            live_database = root / "live.db"
            with closing(sqlite3.connect(live_database)) as connection:
                connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
                connection.execute("INSERT INTO sentinel VALUES ('production')")
                connection.commit()

            with runner.prepare_database(
                mode="snapshot",
                live_database=live_database,
                allow_live_writes=False,
                temp_root=root / "work",
                backup_root=root / "backups",
            ) as target:
                self.assertNotEqual(target.path, live_database)
                with closing(sqlite3.connect(target.path)) as connection:
                    value = connection.execute("SELECT value FROM sentinel").fetchone()[0]
                    self.assertEqual(value, "production")
                    connection.execute("UPDATE sentinel SET value = 'test-change'")
                    connection.commit()
                snapshot_path = target.path

            self.assertFalse(snapshot_path.exists())
            with closing(sqlite3.connect(live_database)) as connection:
                value = connection.execute("SELECT value FROM sentinel").fetchone()[0]
            self.assertEqual(value, "production")

    def test_live_database_requires_acknowledgement_and_creates_backup(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            live_database = root / "live.db"
            with closing(sqlite3.connect(live_database)) as connection:
                connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
                connection.execute("INSERT INTO sentinel VALUES ('production')")
                connection.commit()

            with self.assertRaisesRegex(ValueError, "allow-live-writes"):
                runner.prepare_database(
                    mode="live",
                    live_database=live_database,
                    allow_live_writes=False,
                    temp_root=root / "work",
                    backup_root=root / "backups",
                )

            with runner.prepare_database(
                mode="live",
                live_database=live_database,
                allow_live_writes=True,
                temp_root=root / "work",
                backup_root=root / "backups",
            ) as target:
                self.assertEqual(target.path, live_database.resolve())
                self.assertIsNotNone(target.backup_path)
                self.assertTrue(target.backup_path.exists())
                with closing(sqlite3.connect(target.backup_path)) as connection:
                    value = connection.execute("SELECT value FROM sentinel").fetchone()[0]
                self.assertEqual(value, "production")

    def test_test_environment_is_utf8_and_quiet_by_default(self):
        runner = load_runner()
        environment = runner.build_test_environment(Path("C:/test/database.db"))

        self.assertEqual(environment["DB_PATH"], os.fspath(Path("C:/test/database.db")))
        self.assertEqual(environment["PYTHONUTF8"], "1")
        self.assertEqual(environment["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(environment["SQL_LOG_ENABLED"], "false")
        self.assertEqual(environment["TESTING"], "1")

    def test_quality_commands_use_detached_frontend_build(self):
        runner = load_runner()
        commands = runner.quality_commands(PROJECT_ROOT)
        rendered = [" ".join(command) for command in commands]

        self.assertIn(
            "node frontend/node_modules/typescript/bin/tsc --noEmit -p frontend/tsconfig.json",
            rendered,
        )
        self.assertIn("node frontend/scripts/build-test.mjs", rendered)
        self.assertFalse(any(command.startswith("npm ") for command in rendered))
        self.assertTrue(any("docker-compose-cn.yml" in command for command in rendered))
        self.assertTrue(any("docker-compose.nas.yml" in command for command in rendered))
        self.assertIn("git diff --check", rendered)

    def test_worker_runs_as_project_module_so_application_imports_resolve(self):
        runner = load_runner()
        command = runner.build_worker_command(
            suite="core",
            coverage=False,
            data_file=PROJECT_ROOT / ".tmp" / ".coverage",
            verbose=False,
        )

        self.assertEqual(command[:3], [sys.executable, "-m", "scripts.run_tests"])
        self.assertIn("--worker", command)

    def test_frontend_typecheck_script_is_windows_safe(self):
        runner = load_runner()
        command = runner.quality_commands(PROJECT_ROOT)[0]

        self.assertEqual(command[0], "node")
        self.assertEqual(command[1], "frontend/node_modules/typescript/bin/tsc")

    def test_detached_build_resolves_tailwind_from_frontend_directory(self):
        source = (PROJECT_ROOT / "frontend" / "scripts" / "build-test.mjs").read_text(
            encoding="utf-8"
        )

        self.assertIn("process.chdir(frontendDir);", source)

    def test_detached_build_accepts_the_runner_artifact_root(self):
        source = (PROJECT_ROOT / "frontend" / "scripts" / "build-test.mjs").read_text(
            encoding="utf-8"
        )

        self.assertIn("'logs', 'test-artifacts'", source)
        self.assertNotIn("'.tmp', 'test-artifacts'", source)

    def test_cli_can_list_suites_without_preparing_a_database(self):
        completed = subprocess.run(
            [sys.executable, os.fspath(RUNNER_PATH), "--list"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("core", completed.stdout)
        self.assertIn("tests.test_password_login_ui", completed.stdout)

    def test_database_modes_reject_invalid_inputs_and_allow_blank_snapshots(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing_database = root / "missing.db"

            with self.assertRaisesRegex(ValueError, "未知数据库模式"):
                runner.prepare_database(
                    mode="invalid",
                    live_database=missing_database,
                    allow_live_writes=False,
                    temp_root=root / "work",
                )

            with self.assertRaisesRegex(FileNotFoundError, "真实数据库不存在"):
                runner.prepare_database(
                    mode="live",
                    live_database=missing_database,
                    allow_live_writes=True,
                    temp_root=root / "work",
                )

            with runner.prepare_database(
                mode="snapshot",
                live_database=missing_database,
                allow_live_writes=False,
                temp_root=root / "work",
            ) as target:
                self.assertEqual(target.mode, "snapshot")
                self.assertFalse(target.path.exists())
                temporary_directory = target.path.parent
            self.assertFalse(temporary_directory.exists())

    def test_invalid_suite_is_rejected(self):
        runner = load_runner()

        with self.assertRaisesRegex(ValueError, "未知测试套件"):
            runner.select_test_modules([], "invalid")

    def test_worker_command_supports_coverage_and_verbose_output(self):
        runner = load_runner()
        data_file = PROJECT_ROOT / ".tmp" / "test.coverage"

        command = runner.build_worker_command(
            suite="all",
            coverage=True,
            data_file=data_file,
            verbose=True,
        )

        self.assertEqual(command[:4], [sys.executable, "-m", "coverage", "run"])
        self.assertIn(f"--data-file={data_file}", command)
        self.assertIn("--verbose", command)

    def test_executable_resolution_reports_missing_commands(self):
        runner = load_runner()
        with mock.patch.object(runner.shutil, "which", return_value="C:/bin/tool.exe"):
            self.assertEqual(
                runner._resolve_executable(["tool", "arg"]),
                ["C:/bin/tool.exe", "arg"],
            )

        with mock.patch.object(runner.shutil, "which", return_value=None):
            with self.assertRaisesRegex(FileNotFoundError, "命令不可用"):
                runner._resolve_executable(["missing"])

    def test_command_logging_and_console_output_are_actionable(self):
        runner = load_runner()
        successful = subprocess.CompletedProcess(
            ["test"],
            0,
            "noise\nRan 3 tests in 0.1s\nOK\nTOTAL 80%\n",
            "",
        )
        failed = subprocess.CompletedProcess(["test"], 1, "", "failure detail\n")

        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "command.log"
            runner._write_command_log(log_path, ["test", "arg"], successful)
            log = log_path.read_text(encoding="utf-8")
            self.assertIn("COMMAND: test arg", log)
            self.assertIn("EXIT: 0", log)

        output = io.StringIO()
        with redirect_stdout(output):
            runner._print_result("summary", successful, verbose=False)
        self.assertIn("[PASS] summary", output.getvalue())
        self.assertIn("Ran 3 tests", output.getvalue())
        self.assertNotIn("noise", output.getvalue())

        output = io.StringIO()
        with redirect_stdout(output):
            runner._print_result("failure", failed, verbose=False)
        self.assertIn("[FAIL] failure", output.getvalue())
        self.assertIn("failure detail", output.getvalue())

    def test_run_process_records_success_and_missing_executable(self):
        runner = load_runner()
        completed = subprocess.CompletedProcess(["tool"], 0, "OK\n", "")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                mock.patch.object(runner, "_resolve_executable", return_value=["tool.exe"]),
                mock.patch.object(runner.subprocess, "run", return_value=completed) as run,
                redirect_stdout(io.StringIO()),
            ):
                result = runner._run_process(
                    label="tool",
                    command=["tool"],
                    environment={"TESTING": "1"},
                    log_path=root / "success.log",
                    verbose=True,
                )
            self.assertEqual(result, 0)
            self.assertTrue((root / "success.log").is_file())
            self.assertEqual(run.call_args.kwargs["cwd"], PROJECT_ROOT)

            with (
                mock.patch.object(runner, "_resolve_executable", side_effect=OSError("boom")),
                redirect_stdout(io.StringIO()),
            ):
                result = runner._run_process(
                    label="missing",
                    command=["missing"],
                    environment={},
                    log_path=root / "missing.log",
                    verbose=False,
                )
            self.assertEqual(result, 127)
            self.assertIn("boom", (root / "missing.log").read_text(encoding="utf-8"))

    def test_backend_orchestration_short_circuits_and_emits_coverage_xml(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as directory:
            artifacts = Path(directory)
            arguments = {
                "suite": "core",
                "environment": {},
                "artifact_dir": artifacts,
                "fail_under": 80.0,
                "verbose": False,
            }

            with mock.patch.object(runner, "_run_process", return_value=0) as process:
                result = runner._run_backend(coverage=False, **arguments)
            self.assertEqual(result, 0)
            self.assertEqual(process.call_count, 1)

            with mock.patch.object(runner, "_run_process", return_value=3) as process:
                result = runner._run_backend(coverage=True, **arguments)
            self.assertEqual(result, 3)
            self.assertEqual(process.call_count, 1)

            with mock.patch.object(runner, "_run_process", side_effect=[0, 4]) as process:
                result = runner._run_backend(coverage=True, **arguments)
            self.assertEqual(result, 4)
            self.assertEqual(process.call_count, 2)

            with mock.patch.object(runner, "_run_process", side_effect=[0, 0, 0]) as process:
                result = runner._run_backend(coverage=True, **arguments)
            self.assertEqual(result, 0)
            self.assertEqual(process.call_count, 3)
            self.assertEqual(process.call_args.kwargs["label"], "Coverage XML")

    def test_quality_commands_stop_at_first_failure_and_isolate_frontend_output(self):
        runner = load_runner()
        commands = [["first"], ["second"]]
        with tempfile.TemporaryDirectory() as directory:
            artifacts = Path(directory)
            with (
                mock.patch.object(runner, "quality_commands", return_value=commands),
                mock.patch.object(runner, "_run_process", side_effect=[0, 0]) as process,
            ):
                result = runner._run_quality_commands(
                    environment={"ORIGINAL": "1"},
                    artifact_dir=artifacts,
                    verbose=False,
                )
            self.assertEqual(result, 0)
            self.assertEqual(process.call_count, 2)
            quality_environment = process.call_args.kwargs["environment"]
            self.assertEqual(quality_environment["ORIGINAL"], "1")
            self.assertEqual(
                quality_environment["TEST_ARTIFACT_DIR"],
                os.fspath(artifacts / "frontend-static"),
            )

            with (
                mock.patch.object(runner, "quality_commands", return_value=commands),
                mock.patch.object(runner, "_run_process", return_value=5) as process,
            ):
                result = runner._run_quality_commands(
                    environment={},
                    artifact_dir=artifacts,
                    verbose=False,
                )
            self.assertEqual(result, 5)
            self.assertEqual(process.call_count, 1)

    def test_worker_and_suite_listing_paths(self):
        runner = load_runner()
        successful = mock.Mock()
        successful.wasSuccessful.return_value = True
        failed = mock.Mock()
        failed.wasSuccessful.return_value = False

        with (
            mock.patch.object(runner, "discover_test_modules", return_value=["tests.test_one"]),
            mock.patch.object(runner, "_load_unittest_suite", return_value=object()),
            mock.patch.object(
                runner.unittest,
                "TextTestRunner",
            ) as text_runner,
        ):
            text_runner.return_value.run.side_effect = [successful, failed]
            self.assertEqual(runner._run_worker("core", verbose=True), 0)
            self.assertEqual(runner._run_worker("core", verbose=False), 1)
            self.assertEqual(text_runner.call_args_list[0].kwargs["verbosity"], 2)
            self.assertEqual(text_runner.call_args_list[1].kwargs["verbosity"], 1)

        output = io.StringIO()
        with (
            mock.patch.object(
                runner,
                "discover_test_modules",
                return_value=["tests.test_one", "tests.test_password_login_ui"],
            ),
            redirect_stdout(output),
        ):
            runner._print_suites()
        self.assertIn("core (1 modules)", output.getvalue())
        self.assertIn("e2e (1 modules)", output.getvalue())
        self.assertIn("all (2 modules)", output.getvalue())

    def test_artifact_creation_and_main_control_flow(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(runner, "DEFAULT_ARTIFACT_ROOT", root):
                artifact_dir = runner._create_artifact_dir("core")
            self.assertTrue(artifact_dir.is_dir())
            self.assertIn("-core-", artifact_dir.name)

            with mock.patch.object(runner, "_print_suites") as print_suites:
                self.assertEqual(runner.main(["--list"]), 0)
            print_suites.assert_called_once_with()

            with mock.patch.object(runner, "_run_worker", return_value=6) as worker:
                self.assertEqual(runner.main(["--worker", "--suite", "e2e"]), 6)
            worker.assert_called_once_with("e2e", False)

            with (
                mock.patch.object(runner, "_create_artifact_dir", return_value=root),
                mock.patch.object(runner, "prepare_database", side_effect=ValueError("unsafe")),
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()) as errors,
            ):
                self.assertEqual(runner.main([]), 2)
            self.assertIn("Database preparation", errors.getvalue())

    def test_main_propagates_backend_and_quality_results(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = runner.DatabaseTarget(path=root / "database.db", mode="temp")
            with (
                mock.patch.object(runner, "_create_artifact_dir", return_value=root),
                mock.patch.object(runner, "prepare_database", return_value=target),
                mock.patch.object(runner, "build_test_environment", return_value={}),
                mock.patch.object(runner, "_run_backend", return_value=7),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(runner.main([]), 7)

            with (
                mock.patch.object(runner, "_create_artifact_dir", return_value=root),
                mock.patch.object(runner, "prepare_database", return_value=target),
                mock.patch.object(runner, "build_test_environment", return_value={}),
                mock.patch.object(runner, "_run_backend", return_value=0),
                mock.patch.object(runner, "_run_quality_commands", return_value=8),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(runner.main(["--quality"]), 8)

            with (
                mock.patch.object(runner, "_create_artifact_dir", return_value=root),
                mock.patch.object(runner, "prepare_database", return_value=target),
                mock.patch.object(runner, "build_test_environment", return_value={}),
                mock.patch.object(runner, "_run_backend", return_value=0) as backend,
                mock.patch.object(runner, "_run_quality_commands", return_value=0) as quality,
                redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(runner.main(["--quality", "--fail-under", "42"]), 0)
            self.assertEqual(backend.call_args.kwargs["suite"], "all")
            self.assertTrue(backend.call_args.kwargs["coverage"])
            self.assertEqual(backend.call_args.kwargs["fail_under"], 42.0)
            quality.assert_called_once()
            self.assertIn("Automation test run completed", output.getvalue())


if __name__ == "__main__":
    unittest.main()
