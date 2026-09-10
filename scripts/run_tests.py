"""Project-local automation test runner.

The runner keeps the existing unittest and Python Playwright suites, adds safe
database modes, and can execute the frontend/Compose quality checks without
rewriting the committed ``static/`` build output.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIVE_DATABASE = PROJECT_ROOT / "data" / "xianyu_data.db"
DEFAULT_TEMP_ROOT = PROJECT_ROOT / ".tmp" / "test-work"
DEFAULT_ARTIFACT_ROOT = PROJECT_ROOT / "logs" / "test-artifacts"
DEFAULT_BACKUP_ROOT = PROJECT_ROOT / "backups" / "test-runs"

E2E_TEST_MODULES = frozenset(
    {
        "tests.test_manual_captcha_flow",
        "tests.test_password_login_ui",
        "tests.test_stealth_script_effective",
    }
)


@dataclass(frozen=True)
class DatabaseTarget:
    path: Path
    mode: str
    backup_path: Path | None = None
    _temporary_directory: tempfile.TemporaryDirectory | None = None

    def __enter__(self) -> "DatabaseTarget":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._temporary_directory is not None:
            self._temporary_directory.cleanup()


def _sqlite_backup(source: Path, destination: Path) -> None:
    """Create a transactionally consistent SQLite backup, including WAL data."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_uri = f"{source.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True)) as source_connection:
        with closing(sqlite3.connect(destination)) as destination_connection:
            source_connection.backup(destination_connection)


def prepare_database(
    *,
    mode: str,
    live_database: Path,
    allow_live_writes: bool,
    temp_root: Path = DEFAULT_TEMP_ROOT,
    backup_root: Path = DEFAULT_BACKUP_ROOT,
) -> DatabaseTarget:
    """Prepare a blank DB, a production snapshot, or an acknowledged live DB."""
    live_database = live_database.resolve()
    if mode not in {"temp", "snapshot", "live"}:
        raise ValueError(f"未知数据库模式: {mode}")

    if mode == "live":
        if not allow_live_writes:
            raise ValueError("真实数据库测试必须显式传入 --allow-live-writes")
        if not live_database.is_file():
            raise FileNotFoundError(f"真实数据库不存在: {live_database}")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = backup_root.resolve() / (
            f"{live_database.stem}-before-tests-{timestamp}-{uuid.uuid4().hex[:8]}.db"
        )
        _sqlite_backup(live_database, backup_path)
        return DatabaseTarget(
            path=live_database,
            mode=mode,
            backup_path=backup_path,
        )

    temp_root.mkdir(parents=True, exist_ok=True)
    temporary_directory = tempfile.TemporaryDirectory(
        prefix=f"xianyu-tests-{mode}-",
        dir=temp_root,
    )
    database_path = Path(temporary_directory.name) / "xianyu_data.db"
    if mode == "snapshot" and live_database.is_file():
        _sqlite_backup(live_database, database_path)
    return DatabaseTarget(
        path=database_path,
        mode=mode,
        _temporary_directory=temporary_directory,
    )


def build_test_environment(database_path: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "DB_PATH": os.fspath(database_path),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "SQL_LOG_ENABLED": "false",
            "TESTING": "1",
        }
    )
    return environment


def discover_test_modules(test_root: Path) -> list[str]:
    return [
        f"tests.{path.stem}"
        for path in sorted(test_root.glob("test_*.py"))
        if path.is_file()
    ]


def select_test_modules(modules: Iterable[str], suite: str) -> list[str]:
    modules = sorted(set(modules))
    if suite == "all":
        return modules
    if suite == "e2e":
        return [module for module in modules if module in E2E_TEST_MODULES]
    if suite == "core":
        return [module for module in modules if module not in E2E_TEST_MODULES]
    raise ValueError(f"未知测试套件: {suite}")


def quality_commands(project_root: Path) -> list[list[str]]:
    del project_root  # Commands are intentionally relative to the repository root.
    return [
        [
            "node",
            "frontend/node_modules/typescript/bin/tsc",
            "--noEmit",
            "-p",
            "frontend/tsconfig.json",
        ],
        ["node", "frontend/scripts/build-test.mjs"],
        ["docker", "compose", "config", "--quiet"],
        ["docker", "compose", "-f", "docker-compose-cn.yml", "config", "--quiet"],
        ["docker", "compose", "-f", "docker-compose.nas.yml", "config", "--quiet"],
        ["git", "diff", "--check"],
    ]


def _load_unittest_suite(modules: Sequence[str]) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    test_root = PROJECT_ROOT / "tests"
    for module in modules:
        filename = f"{module.rsplit('.', 1)[-1]}.py"
        loader = unittest.TestLoader()
        suite.addTests(loader.discover(os.fspath(test_root), pattern=filename))
    return suite


def _run_worker(suite_name: str, verbose: bool) -> int:
    modules = select_test_modules(
        discover_test_modules(PROJECT_ROOT / "tests"),
        suite_name,
    )
    suite = _load_unittest_suite(modules)
    result = unittest.TextTestRunner(verbosity=2 if verbose else 1).run(suite)
    return 0 if result.wasSuccessful() else 1


def _resolve_executable(command: Sequence[str]) -> list[str]:
    resolved = shutil.which(command[0])
    if resolved is None:
        raise FileNotFoundError(f"命令不可用: {command[0]}")
    return [resolved, *command[1:]]


def _write_command_log(path: Path, command: Sequence[str], completed: subprocess.CompletedProcess) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output = (completed.stdout or "") + (completed.stderr or "")
    path.write_text(
        f"COMMAND: {' '.join(command)}\nEXIT: {completed.returncode}\n\n{output}",
        encoding="utf-8",
    )


def _print_result(label: str, completed: subprocess.CompletedProcess, verbose: bool) -> None:
    output = (completed.stdout or "") + (completed.stderr or "")
    status = "PASS" if completed.returncode == 0 else "FAIL"
    print(f"[{status}] {label}")
    if verbose or completed.returncode != 0:
        print(output.rstrip())
        return
    summary = [
        line
        for line in output.splitlines()
        if line.startswith("Ran ") or line in {"OK", "FAILED"} or line.startswith("TOTAL")
    ]
    for line in summary[-4:]:
        print(f"  {line}")


def _run_process(
    *,
    label: str,
    command: Sequence[str],
    environment: dict[str, str],
    log_path: Path,
    verbose: bool,
) -> int:
    try:
        resolved_command = _resolve_executable(command)
        completed = subprocess.run(
            resolved_command,
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        completed = subprocess.CompletedProcess(command, 127, "", f"{exc}\n")
    _write_command_log(log_path, command, completed)
    _print_result(label, completed, verbose)
    return completed.returncode


def build_worker_command(
    *,
    suite: str,
    coverage: bool,
    data_file: Path,
    verbose: bool,
) -> list[str]:
    worker_arguments = ["--worker", "--suite", suite]
    if verbose:
        worker_arguments.append("--verbose")
    if not coverage:
        return [sys.executable, "-m", "scripts.run_tests", *worker_arguments]
    return [
        sys.executable,
        "-m",
        "coverage",
        "run",
        f"--rcfile={PROJECT_ROOT / '.coveragerc'}",
        f"--data-file={data_file}",
        "-m",
        "scripts.run_tests",
        *worker_arguments,
    ]


def _run_backend(
    *,
    suite: str,
    environment: dict[str, str],
    artifact_dir: Path,
    coverage: bool,
    fail_under: float,
    verbose: bool,
) -> int:
    data_file = artifact_dir / ".coverage"
    worker_command = build_worker_command(
        suite=suite,
        coverage=coverage,
        data_file=data_file,
        verbose=verbose,
    )

    result = _run_process(
        label=f"Python {suite} tests",
        command=worker_command,
        environment=environment,
        log_path=artifact_dir / f"python-{suite}.log",
        verbose=verbose,
    )
    if result != 0 or not coverage:
        return result

    report_command = [
        sys.executable,
        "-m",
        "coverage",
        "report",
        f"--rcfile={PROJECT_ROOT / '.coveragerc'}",
        f"--data-file={data_file}",
        f"--fail-under={fail_under}",
    ]
    report_result = _run_process(
        label=f"Coverage >= {fail_under:g}%",
        command=report_command,
        environment=environment,
        log_path=artifact_dir / "coverage-report.log",
        verbose=verbose,
    )
    if report_result != 0:
        return report_result

    xml_command = [
        sys.executable,
        "-m",
        "coverage",
        "xml",
        f"--rcfile={PROJECT_ROOT / '.coveragerc'}",
        f"--data-file={data_file}",
        "-o",
        os.fspath(artifact_dir / "coverage.xml"),
    ]
    return _run_process(
        label="Coverage XML",
        command=xml_command,
        environment=environment,
        log_path=artifact_dir / "coverage-xml.log",
        verbose=verbose,
    )


def _run_quality_commands(
    *,
    environment: dict[str, str],
    artifact_dir: Path,
    verbose: bool,
) -> int:
    environment = environment.copy()
    environment["TEST_ARTIFACT_DIR"] = os.fspath(artifact_dir / "frontend-static")
    for index, command in enumerate(quality_commands(PROJECT_ROOT), start=1):
        label = " ".join(command)
        result = _run_process(
            label=label,
            command=command,
            environment=environment,
            log_path=artifact_dir / f"quality-{index}.log",
            verbose=verbose,
        )
        if result != 0:
            return result
    return 0


def _create_artifact_dir(suite: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    artifact_dir = DEFAULT_ARTIFACT_ROOT / f"{timestamp}-{suite}-{uuid.uuid4().hex[:8]}"
    artifact_dir.mkdir(parents=True, exist_ok=False)
    return artifact_dir


def _print_suites() -> None:
    modules = discover_test_modules(PROJECT_ROOT / "tests")
    for suite_name in ("core", "e2e", "all"):
        selected = select_test_modules(modules, suite_name)
        print(f"{suite_name} ({len(selected)} modules)")
        for module in selected:
            print(f"  {module}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="闲鱼卖家自动化测试入口")
    parser.add_argument("--suite", choices=("core", "e2e", "all"), default="core")
    parser.add_argument("--database", choices=("temp", "snapshot", "live"), default="snapshot")
    parser.add_argument("--live-database", type=Path, default=DEFAULT_LIVE_DATABASE)
    parser.add_argument("--allow-live-writes", action="store_true")
    parser.add_argument("--coverage", action="store_true")
    parser.add_argument("--quality", action="store_true", help="追加前端、Compose 和 diff 门禁")
    parser.add_argument("--fail-under", type=float, default=20.0)
    parser.add_argument("--list", action="store_true", help="列出测试套件，不执行测试")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list:
        _print_suites()
        return 0
    if args.worker:
        return _run_worker(args.suite, args.verbose)

    suite = "all" if args.quality else args.suite
    use_coverage = args.coverage or args.quality
    artifact_dir = _create_artifact_dir(suite)
    print(f"Artifacts: {artifact_dir}")

    try:
        target = prepare_database(
            mode=args.database,
            live_database=args.live_database,
            allow_live_writes=args.allow_live_writes,
        )
    except (FileNotFoundError, OSError, ValueError, sqlite3.Error) as exc:
        print(f"[FAIL] Database preparation: {exc}", file=sys.stderr)
        return 2

    with target:
        print(f"Database mode: {target.mode}")
        print(f"Database path: {target.path}")
        if target.backup_path is not None:
            print(f"Live database backup: {target.backup_path}")
        environment = build_test_environment(target.path)
        result = _run_backend(
            suite=suite,
            environment=environment,
            artifact_dir=artifact_dir,
            coverage=use_coverage,
            fail_under=args.fail_under,
            verbose=args.verbose,
        )
        if result != 0:
            return result
        if args.quality:
            result = _run_quality_commands(
                environment=environment,
                artifact_dir=artifact_dir,
                verbose=args.verbose,
            )
            if result != 0:
                return result

    print("[PASS] Automation test run completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
