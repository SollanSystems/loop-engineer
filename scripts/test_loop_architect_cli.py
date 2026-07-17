"""Behavioral and CLI coverage for the fail-loud architect deferral."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

import loop.__main__ as loop_main
from loop import emit
from loop.events import SQLiteEventStore

ROOT = Path(__file__).resolve().parent.parent


def _cli(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, "-B", "-m", "loop", *args], cwd=cwd, env=env, text=True, capture_output=True)


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    emit.open_contract(workspace)
    return workspace


def _message(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "architect: " + __import__("loop.architect", fromlist=["ARCHITECT_NOT_IMPLEMENTED_MESSAGE"]).ARCHITECT_NOT_IMPLEMENTED_MESSAGE + "\n"


def _hashes(workspace: Path) -> dict[Path, str]:
    return {path.relative_to(workspace): hashlib.sha256(path.read_bytes()).hexdigest() for path in workspace.rglob("*") if path.is_file()}


def test_architect_module_importable_and_exception_is_runtime_error_subclass():
    import loop.architect
    assert issubclass(loop.architect.ArchitectNotImplementedError, RuntimeError)


def test_architect_run_always_raises_with_no_arguments():
    from loop.architect import ARCHITECT_NOT_IMPLEMENTED_MESSAGE, ArchitectNotImplementedError, architect_run
    with pytest.raises(ArchitectNotImplementedError) as exc:
        architect_run()
    assert str(exc.value) == ARCHITECT_NOT_IMPLEMENTED_MESSAGE


def test_architect_run_always_raises_regardless_of_target_and_mode_arguments():
    from loop.architect import ARCHITECT_NOT_IMPLEMENTED_MESSAGE, ArchitectNotImplementedError, architect_run
    for args, kwargs in ((("/some/path",), {}), ((Path("x"),), {"mode": "strict"}), ((None,), {"mode": "not-a-real-mode"})):
        with pytest.raises(ArchitectNotImplementedError) as exc:
            architect_run(*args, **kwargs)
        assert str(exc.value) == ARCHITECT_NOT_IMPLEMENTED_MESSAGE


def test_architect_run_touches_neither_sqlite3_connect_nor_subprocess_run(monkeypatch):
    from loop.architect import ArchitectNotImplementedError, architect_run
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("sqlite")))
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("subprocess")))
    with pytest.raises(ArchitectNotImplementedError):
        architect_run()


def test_architect_cli_help_lists_command_and_description():
    result = _cli("--help")
    assert "architect" in result.stdout and "agentic judgment" in result.stdout


def test_architect_cli_zero_arguments_exits_2_with_typed_message_not_usage_error():
    result = _cli("architect")
    _message(result)
    assert "usage:" not in result.stderr and "missing target argument" not in result.stderr


def test_architect_cli_nonexistent_target_still_gives_the_typed_deferral_not_a_does_not_exist_usage_error(tmp_path):
    result = _cli("architect", str(tmp_path / "missing"))
    _message(result)
    assert "does not exist" not in result.stderr


def test_architect_cli_on_a_real_valid_scaffolded_workspace_still_refuses(tmp_path):
    _message(_cli("architect", str(_workspace(tmp_path))))


def test_architect_cli_on_a_terminal_workspace_still_refuses_identically(tmp_path):
    workspace = _workspace(tmp_path)
    store = SQLiteEventStore(workspace / ".loop" / "events.db")
    opened = store.append("run-1", "contract_opened", {"workspace": "workspace"}, actor="test")
    store.append("run-1", "terminal_written", {"state": "Succeeded", "criteria_met": {"gate": True}, "evidence": ["proof"], "false_completion": False}, actor="test", causation_id=opened["event_id"])
    _message(_cli("architect", str(workspace)))


def test_architect_cli_ignores_mode_flag_value_entirely_including_an_invalid_one(tmp_path):
    result = _cli("architect", "--mode=not-a-real-mode", str(_workspace(tmp_path)))
    _message(result)
    assert "invalid --mode value" not in result.stderr


def test_architect_cli_ignores_arbitrary_extra_flags_and_positional_garbage():
    _message(_cli("architect", "--continuous", "--bogus", "extra1", "extra2"))


def test_architect_cli_stdout_is_always_empty_and_stderr_has_no_traceback():
    result = _cli("architect")
    _message(result)
    assert "Traceback" not in result.stderr


def test_architect_cli_message_names_the_skill_and_the_deterministic_next_step():
    result = _cli("architect")
    _message(result)
    assert "loop-architect" in result.stderr and "`loop scaffold`" in result.stderr


def test_architect_excluded_from_read_commands_target_exists_guard():
    assert "architect" not in loop_main._READ_COMMANDS


def test_architect_listed_in_commands_tuple_exactly_once():
    assert loop_main._COMMANDS.count("architect") == 1


def test_run_continuous_flag_message_is_unaffected_by_architect_addition(tmp_path):
    result = _cli("run", "--continuous", str(_workspace(tmp_path)))
    assert result.returncode == 2 and "run mode" in result.stderr and "'--continuous'" in result.stderr
    assert "loop-architect" not in result.stderr


def test_architect_stub_regression_no_op_architect_run_triggers_assertion_canary_not_silent_success(monkeypatch):
    import loop.architect
    monkeypatch.setattr(loop.architect, "architect_run", lambda *a, **kw: None)
    with pytest.raises(AssertionError, match="returned without raising ArchitectNotImplementedError"):
        loop_main.main(["architect"])


def test_architect_full_workspace_tree_byte_hash_unchanged_across_call_zero_exceptions_permitted(tmp_path):
    workspace = _workspace(tmp_path)
    before = _hashes(workspace)
    _cli("architect", str(workspace), cwd=workspace)
    assert _hashes(workspace) == before
