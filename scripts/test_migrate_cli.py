"""CLI contract tests for `python3 -m loop migrate` — the only store-upgrade path.

`migrate` is the one explicitly write-classed verb over an existing store: connect
never upgrades a legacy events.db, so a v0.9.0 store stays unchained until an
operator runs this command. These tests drive the real entry point as a
subprocess so the exit code and the stdout/stderr split are exercised exactly as
an operator sees them.
"""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from chain_fixtures import make_legacy_store

ROOT = Path(__file__).resolve().parent.parent


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, "-B", "-m", "loop", *args], cwd=ROOT, env=env,
                          text=True, capture_output=True, timeout=120)


def _legacy_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    (workspace / ".loop").mkdir(parents=True)
    make_legacy_store(workspace / ".loop" / "events.db")
    return workspace


def _drifted_store(path: Path) -> Path:
    """An events table that reads and writes nothing the kernel expects."""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE events (run_id TEXT, sequence INTEGER)")
        conn.execute("INSERT INTO events VALUES ('r1', 0)")
        conn.commit()
    finally:
        conn.close()
    return path


def test_migrate_on_a_legacy_workspace_exits_zero_and_reports_migrated_true(tmp_path):
    result = _cli("migrate", str(_legacy_workspace(tmp_path)))
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is True and report["migrated"] is True
    assert report["user_version"] == 2 and report["unchained_rows"] == 1
    assert report["chained_from_sequence"] == 1


def test_second_migrate_exits_zero_and_reports_migrated_false(tmp_path):
    workspace = _legacy_workspace(tmp_path)
    assert _cli("migrate", str(workspace)).returncode == 0
    second = _cli("migrate", str(workspace))
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["migrated"] is False


def test_migrate_nonexistent_target_exits_two_with_the_exists_guard_hint(tmp_path):
    missing = tmp_path / "does-not-exist"
    result = _cli("migrate", str(missing))
    assert result.returncode == 2
    assert result.stdout == ""
    assert "does not exist" in result.stderr and str(missing) in result.stderr
    assert "scaffold" in result.stderr          # the _READ_COMMANDS exists-guard hint
    assert "Traceback" not in result.stderr


def test_migrate_missing_store_in_an_existing_workspace_is_a_typed_error(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / ".loop").mkdir(parents=True)
    result = _cli("migrate", str(workspace))
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("migrate: missing_store: ")
    assert "Traceback" not in result.stderr


def test_migrate_corrupt_store_is_a_typed_error_not_a_traceback(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / ".loop").mkdir(parents=True)
    (workspace / ".loop" / "events.db").write_text("not sqlite", encoding="utf-8")
    result = _cli("migrate", str(workspace))
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("migrate: corrupt_store: ")
    assert "Traceback" not in result.stderr


def test_migrate_accepts_the_loop_dir_as_target_like_every_other_verb(tmp_path):
    workspace = _legacy_workspace(tmp_path)
    result = _cli("migrate", str(workspace / ".loop"))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["migrated"] is True


def test_help_lists_migrate_and_describes_it_as_the_only_upgrade_path():
    result = _cli("--help")
    assert result.returncode == 0
    assert "migrate" in result.stdout
    assert "only store-upgrade path" in result.stdout


def test_migrate_missing_target_argument_prints_usage_and_exits_nonzero():
    result = _cli("migrate")
    assert result.returncode == 2
    assert "usage" in result.stderr.lower()
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("command,extra", [("run", []), ("pause", ["--reason", "drift probe"])])
def test_cli_refuses_a_schema_drifted_store_without_a_traceback(tmp_path, command, extra):
    """Task-4 probe: the drift path stays typed at the CLI boundary."""
    workspace = tmp_path / "workspace"
    (workspace / ".loop").mkdir(parents=True)
    _drifted_store(workspace / ".loop" / "events.db")
    result = _cli(command, *extra, str(workspace))
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert result.stderr.strip().startswith(f"{command}: ")
