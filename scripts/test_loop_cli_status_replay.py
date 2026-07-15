"""Runtime CLI contract tests for read-only event-log status and replay."""

import hashlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from loop.events import SQLiteEventStore
from loop.runtime import RuntimeStoreError, replay_report, status_report


ROOT = Path(__file__).resolve().parent.parent


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "loop", *args], cwd=ROOT, text=True, capture_output=True)


def _workspace(tmp_path: Path, *, state: bool = True) -> tuple[Path, SQLiteEventStore]:
    workspace = tmp_path / "workspace"
    loop = workspace / ".loop"
    loop.mkdir(parents=True)
    if state:
        (loop / "state.json").write_text(json.dumps({"state": "intake", "iteration_id": 0, "active_task": None, "terminal_state": None}), encoding="utf-8")
    return workspace, SQLiteEventStore(loop / "events.db")


def _open(store: SQLiteEventStore, run_id: str = "run-1") -> dict:
    return store.append(run_id, "contract_opened", {"workspace": "workspace"}, actor="test")


def _terminal(store: SQLiteEventStore, run_id: str = "run-1") -> dict:
    opened = _open(store, run_id)
    return store.append(run_id, "terminal_written", {"state": "Succeeded", "criteria_met": {"gate": True}, "evidence": ["proof"], "false_completion": False}, actor="test", causation_id=opened["event_id"])


def _write_state(workspace: Path, **values: object) -> None:
    (workspace / ".loop" / "state.json").write_text(json.dumps(values), encoding="utf-8")


def test_status_report_missing_store_is_distinct_from_empty_store(tmp_path):
    workspace, _ = _workspace(tmp_path)
    with pytest.raises(RuntimeStoreError) as missing:
        status_report(workspace)
    SQLiteEventStore(workspace / ".loop" / "events.db")._connect().close()
    with pytest.raises(RuntimeStoreError) as empty:
        status_report(workspace)
    assert (missing.value.code, empty.value.code) == ("missing_store", "empty_store")


def test_status_report_empty_store_reports_typed_finding(tmp_path):
    workspace, store = _workspace(tmp_path)
    store._connect().close()
    with pytest.raises(RuntimeStoreError) as exc:
        status_report(workspace)
    assert exc.value.code == "empty_store"


def test_replay_report_missing_store_is_distinct_from_empty_store(tmp_path):
    workspace, _ = _workspace(tmp_path)
    with pytest.raises(RuntimeStoreError) as missing:
        replay_report(workspace)
    SQLiteEventStore(workspace / ".loop" / "events.db")._connect().close()
    with pytest.raises(RuntimeStoreError) as empty:
        replay_report(workspace)
    assert (missing.value.code, empty.value.code) == ("missing_store", "empty_store")


def test_status_report_healthy_single_event_run_agrees_with_state_json(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    report = status_report(workspace)
    assert report["ok"] and report["state_json_agrees"] and report["event_count"] == 1


def test_status_report_detects_state_json_divergence(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    _write_state(workspace, state="verify", iteration_id=0, active_task=None, terminal_state=None)
    assert status_report(workspace)["divergence"][0]["code"] == "state_field_mismatch"


def test_replay_report_healthy_log_is_consistent_on_double_fold(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    report = replay_report(workspace)
    assert report["ok"] and report["deterministic"] and report["legal_sequence"]


def test_replay_report_reports_illegal_sequence_as_typed_finding_not_traceback(tmp_path):
    workspace, store = _workspace(tmp_path)
    store.append("run-1", "iteration_appended", {"iteration_id": 0, "outcome": "task_passed"}, actor="test")
    report = replay_report(workspace)
    assert not report["legal_sequence"] and report["findings"][0]["code"] == "illegal_event_sequence"


def test_replay_report_detects_desynced_terminal_window_file_without_event(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    (workspace / ".loop" / "terminal_state.json").write_text('{"state":"Succeeded"}', encoding="utf-8")
    assert replay_report(workspace)["findings"][0]["code"] == "desynced_terminal_window"


def test_replay_report_detects_desynced_terminal_window_event_without_file(tmp_path):
    workspace, store = _workspace(tmp_path)
    _terminal(store)
    assert replay_report(workspace)["findings"][0]["code"] == "desynced_terminal_window"


def test_replay_report_detects_terminal_state_mismatch_between_file_and_projection(tmp_path):
    workspace, store = _workspace(tmp_path)
    _terminal(store)
    (workspace / ".loop" / "terminal_state.json").write_text('{"state":"FailedBlocked"}', encoding="utf-8")
    assert replay_report(workspace)["findings"][0]["code"] == "desynced_terminal_window"


def test_ambiguous_run_id_is_a_typed_usage_error(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store, "run-a")
    _open(store, "run-b")
    with pytest.raises(RuntimeStoreError, match="ambiguous") as exc:
        status_report(workspace)
    assert exc.value.code == "ambiguous_run_id"


def test_events_db_is_opened_strictly_read_only_no_write_side_effects(tmp_path):
    workspace, store = _workspace(tmp_path)
    _terminal(store)
    (workspace / ".loop" / "terminal_state.json").write_text('{"state":"Succeeded"}', encoding="utf-8")
    files = sorted((workspace / ".loop").iterdir())
    before = {p.name: (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in files if p.is_file()}
    status_report(workspace)
    replay_report(workspace)
    after = {p.name: (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in files if p.is_file()}
    assert after == before


def test_status_report_reports_completion_policy_satisfaction_for_succeeded_terminal(tmp_path):
    workspace, store = _workspace(tmp_path)
    _terminal(store)
    _write_state(workspace, state="terminal", iteration_id=0, active_task=None, terminal_state="Succeeded")
    assert status_report(workspace)["completion_satisfied"] is True


def test_corrupt_store_file_is_a_typed_usage_error_not_a_traceback(tmp_path):
    workspace, _ = _workspace(tmp_path)
    (workspace / ".loop" / "events.db").write_text("not sqlite", encoding="utf-8")
    with pytest.raises(RuntimeStoreError) as exc:
        replay_report(workspace)
    assert exc.value.code == "corrupt_store"


def test_help_lists_status_and_replay_commands():
    result = _run("--help")
    assert result.returncode == 0 and "status" in result.stdout and "replay" in result.stdout


def test_status_missing_target_argument_prints_usage_and_exits_nonzero():
    result = _run("status")
    assert result.returncode != 0 and "usage" in result.stderr.lower()


def test_replay_missing_target_argument_prints_usage_and_exits_nonzero():
    result = _run("replay")
    assert result.returncode != 0 and "usage" in result.stderr.lower()


def test_status_nonexistent_target_gives_distinct_actionable_error(tmp_path):
    result = _run("status", str(tmp_path / "missing"))
    assert result.returncode == 2 and result.stdout == "" and "does not exist" in result.stderr


def test_replay_nonexistent_target_gives_distinct_actionable_error(tmp_path):
    result = _run("replay", str(tmp_path / "missing"))
    assert result.returncode == 2 and result.stdout == "" and "does not exist" in result.stderr


def test_status_accepts_mode_flag_like_doctor(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    result = _run("status", "--mode", "basic", str(workspace))
    assert result.returncode == 0 and json.loads(result.stdout)["requested_mode"] == "basic"


def test_replay_accepts_mode_flag_like_doctor(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    result = _run("replay", "--mode=basic", str(workspace))
    assert result.returncode == 0 and json.loads(result.stdout)["requested_mode"] == "basic"


def test_status_missing_event_store_exits_2_with_stderr_message_and_empty_stdout(tmp_path):
    workspace, _ = _workspace(tmp_path)
    result = _run("status", str(workspace))
    assert result.returncode == 2 and result.stdout == "" and "event store" in result.stderr


def test_replay_missing_event_store_exits_2_with_stderr_message_and_empty_stdout(tmp_path):
    workspace, _ = _workspace(tmp_path)
    result = _run("replay", str(workspace))
    assert result.returncode == 2 and result.stdout == "" and "event store" in result.stderr


def test_status_healthy_run_exits_0_with_json_report(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    result = _run("status", str(workspace))
    assert result.returncode == 0 and json.loads(result.stdout)["ok"] is True


def test_replay_healthy_log_exits_0_with_json_report(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    result = _run("replay", str(workspace))
    assert result.returncode == 0 and json.loads(result.stdout)["ok"] is True


def test_replay_illegal_sequence_exits_1_with_json_finding_no_traceback(tmp_path):
    workspace, store = _workspace(tmp_path)
    store.append("run-1", "iteration_appended", {"iteration_id": 0, "outcome": "task_passed"}, actor="test")
    result = _run("replay", str(workspace))
    assert result.returncode == 1 and json.loads(result.stdout)["findings"][0]["code"] == "illegal_event_sequence" and "Traceback" not in result.stderr


def test_status_and_replay_mode_release_without_jsonschema_is_a_usage_error(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    for command in ("status", "replay"):
        result = _run(command, "--mode", "release", str(workspace))
        if importlib.util.find_spec("jsonschema") is None:
            assert result.returncode == 2 and result.stdout == "" and "jsonschema" in result.stderr
        else:
            assert result.returncode == 0 and json.loads(result.stdout)["requested_mode"] == "release"
