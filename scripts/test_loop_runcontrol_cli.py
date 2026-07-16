"""Behavioral coverage for the S2 run-control API and CLI."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from loop import emit, runner, runcontrol
from loop.events import SQLiteEventStore
from loop.runtime import RuntimeStoreError, replay_report, status_report
from loop.runcontrol import (
    IllegalRunControlStateError,
    RunControlConflictError,
    RunControlUsageError,
    approve_run,
    cancel_run,
    pause_run,
    resume_run,
)


ROOT = Path(__file__).resolve().parent.parent
RUN_ID = "run-1"


def _workspace(tmp_path: Path) -> tuple[Path, SQLiteEventStore]:
    workspace = tmp_path / "workspace"
    loop_dir = workspace / ".loop"
    loop_dir.mkdir(parents=True)
    (loop_dir / "state.json").write_text(json.dumps({
        "state": "intake", "iteration_id": 0, "active_task": None,
        "terminal_state": None,
    }), encoding="utf-8")
    return workspace, SQLiteEventStore(loop_dir / "events.db")


def _open(store: SQLiteEventStore) -> dict:
    return store.append(RUN_ID, "contract_opened", {"workspace": "workspace"}, actor="test")


def _approval_workspace(tmp_path: Path) -> tuple[Path, SQLiteEventStore, dict]:
    workspace, store = _workspace(tmp_path)
    _open(store)
    store.append(RUN_ID, "iteration_appended", {
        "iteration_id": 1, "outcome": "task_passed", "state": "plan",
    }, actor="test")
    pending = store.append(RUN_ID, "approval_requested", {
        "iteration_id": 1, "request": "operator approval",
    }, actor="test")
    _, projection = runner._projection(workspace, None)
    emit.sync_state_to_projection(workspace, projection)
    return workspace, store, pending


def _count(store: SQLiteEventStore) -> int:
    return len(store.read(RUN_ID))


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-B", "-m", "loop", *args], cwd=ROOT,
                          text=True, capture_output=True)


def _assert_refusal(exc: type[Exception], action, message: str, store: SQLiteEventStore) -> None:
    before = _count(store)
    with pytest.raises(exc, match=message):
        action()
    assert _count(store) == before


def test_approve_approved_writes_approval_resolved_event_and_advances_state(tmp_path):
    workspace, store, pending = _approval_workspace(tmp_path)
    report = approve_run(workspace, decision="approved", resume_target="execute-task")
    event = store.read(RUN_ID)[-1]
    assert report["ok"] and report["state"] == "execute-task"
    assert event["type"] == "approval_resolved" and event["sequence"] == 3
    assert event["payload"] == {"iteration_id": 1, "decision": "approved", "resume_target": "execute-task"}
    assert event["causation_id"] == pending["event_id"]


def test_approve_denied_writes_approval_resolved_event_and_stays_approval_wait(tmp_path):
    workspace, store, pending = _approval_workspace(tmp_path)
    report = approve_run(workspace, decision="denied")
    event = store.read(RUN_ID)[-1]
    assert report["state"] == "approval-wait" and event["payload"] == {"iteration_id": 1, "decision": "denied"}
    assert event["causation_id"] == pending["event_id"] and event["sequence"] == 3


def test_approve_syncs_state_json_state_and_clears_pending_approval(tmp_path):
    workspace, _, _ = _approval_workspace(tmp_path)
    approve_run(workspace, decision="approved", resume_target="plan")
    state = json.loads((workspace / ".loop" / "state.json").read_text())
    assert state["state"] == "plan" and state["pending_approval"] is None
    assert state["iteration_id"] == 1 and "updated_at" in state


def test_approve_raises_when_state_is_not_approval_wait(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    _assert_refusal(IllegalRunControlStateError,
                    lambda: approve_run(workspace, decision="denied"), "not in approval-wait", store)


def test_approve_raises_when_no_pending_approval_recorded(tmp_path, monkeypatch):
    workspace, store, _ = _approval_workspace(tmp_path)
    original = runner._projection
    monkeypatch.setattr(runner, "_projection", lambda target, mode: (
        original(target, mode)[0], {**original(target, mode)[1], "pending_approval": None}))
    _assert_refusal(IllegalRunControlStateError,
                    lambda: approve_run(workspace, decision="denied"), "no pending approval", store)


def test_approve_raises_when_resume_target_missing_for_approved_decision(tmp_path):
    workspace, store, _ = _approval_workspace(tmp_path)
    _assert_refusal(RunControlUsageError, lambda: approve_run(workspace, decision="approved"), "resume-target.*required", store)


def test_approve_raises_when_resume_target_given_for_denied_decision(tmp_path):
    workspace, store, _ = _approval_workspace(tmp_path)
    _assert_refusal(RunControlUsageError, lambda: approve_run(workspace, decision="denied", resume_target="plan"), "resume-target.*forbidden", store)


def test_approve_raises_when_resume_target_is_terminal_marker(tmp_path):
    workspace, store, _ = _approval_workspace(tmp_path)
    _assert_refusal(IllegalRunControlStateError,
                    lambda: approve_run(workspace, decision="approved", resume_target="terminal"),
                    "legal non-terminal resume target", store)


def test_approve_raises_when_resume_target_is_not_a_legal_state(tmp_path):
    workspace, store, _ = _approval_workspace(tmp_path)
    _assert_refusal(IllegalRunControlStateError,
                    lambda: approve_run(workspace, decision="approved", resume_target="intake"),
                    "legal non-terminal resume target", store)


def test_approve_causation_id_is_auto_derived_from_pending_approval_event_id(tmp_path):
    workspace, store, pending = _approval_workspace(tmp_path)
    approve_run(workspace, decision="approved", resume_target="verify")
    assert store.read(RUN_ID)[-1]["causation_id"] == pending["event_id"]


def test_pause_writes_run_paused_event_and_syncs_state_json_paused_true(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    pause_run(workspace, reason="operator break")
    event = store.read(RUN_ID)[-1]
    state = json.loads((workspace / ".loop" / "state.json").read_text())
    assert event["type"] == "run_paused" and event["payload"] == {"iteration_id": 0, "reason": "operator break"}
    assert event["sequence"] == 1 and state["paused"] is True and state["pause_reason"] == "operator break"


def test_pause_raises_when_already_paused(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    pause_run(workspace, reason="first")
    _assert_refusal(IllegalRunControlStateError, lambda: pause_run(workspace, reason="second"), "already paused", store)


def test_pause_raises_when_reason_is_empty_string(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    _assert_refusal(RunControlUsageError, lambda: pause_run(workspace, reason=""), "non-empty string", store)


def test_resume_writes_run_resumed_event_and_syncs_state_json_paused_false(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    pause_run(workspace, reason="break")
    resume_run(workspace)
    event = store.read(RUN_ID)[-1]
    state = json.loads((workspace / ".loop" / "state.json").read_text())
    assert event["type"] == "run_resumed" and event["payload"] == {"iteration_id": 0}
    assert event["sequence"] == 2 and state["paused"] is False and state["pause_reason"] is None


def test_resume_raises_when_not_paused(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    _assert_refusal(IllegalRunControlStateError, lambda: resume_run(workspace), "not paused", store)


def test_resume_accepts_optional_note(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    pause_run(workspace, reason="break")
    resume_run(workspace, note="back at desk")
    assert store.read(RUN_ID)[-1]["payload"] == {"iteration_id": 0, "note": "back at desk"}


def test_cancel_writes_terminal_written_aborted_by_human_and_terminal_file(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    cancel_run(workspace, reason="operator cancelled")
    event = store.read(RUN_ID)[-1]
    terminal = json.loads((workspace / ".loop" / "terminal_state.json").read_text())
    assert event["type"] == "terminal_written" and event["payload"] == {
        "state": "AbortedByHuman", "criteria_met": {}, "evidence": [], "false_completion": False,
        "completion_policy": {"mode": "all_required"},
    }
    assert terminal["state"] == "AbortedByHuman" and terminal["reason"] == "operator cancelled"
    replay = replay_report(workspace)
    assert replay["ok"] and replay["findings"] == []


def test_cancel_raises_when_already_terminal(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    cancel_run(workspace)
    _assert_refusal(IllegalRunControlStateError, lambda: cancel_run(workspace), "already terminal", store)


def test_cancel_is_legal_from_any_non_terminal_state(tmp_path):
    for state in ("intake", "plan", "approval-wait"):
        case = tmp_path / state
        if state == "approval-wait":
            workspace, store, _ = _approval_workspace(case)
        else:
            workspace, store = _workspace(case)
            _open(store)
            if state == "plan":
                store.append(RUN_ID, "iteration_appended", {"iteration_id": 1, "outcome": "task_passed", "state": "plan"}, actor="test")
        cancel_run(workspace)
        assert store.read(RUN_ID)[-1]["type"] == "terminal_written"


def test_iteration_id_is_derived_from_projection_never_user_supplied(tmp_path):
    workspace, store, _ = _approval_workspace(tmp_path)
    approve_run(workspace, decision="approved", resume_target="plan")
    assert store.read(RUN_ID)[-1]["payload"]["iteration_id"] == 1
    result = _cli("pause", "--reason", "hold", "--iteration-id", "999", str(workspace))
    assert result.returncode == 2 and _count(store) == 4


def test_run_control_conflict_error_raised_on_sequence_conflict_translation(tmp_path, monkeypatch):
    workspace, store = _workspace(tmp_path)
    _open(store)
    def conflict(*args, **kwargs):
        raise runcontrol.SequenceConflictError("stale")
    monkeypatch.setattr(runcontrol.SQLiteEventStore, "append", conflict)
    _assert_refusal(RunControlConflictError, lambda: pause_run(workspace, reason="hold"), "another writer advanced", store)


def test_run_control_usage_error_raised_on_event_validation_translation(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    _, projection = runner._projection(workspace, None)
    with pytest.raises(RunControlUsageError, match="run_paused"):
        runcontrol._append_event(workspace, RUN_ID, projection, "run_paused", {"iteration_id": 0, "reason": ""})
    assert _count(store) == 1


def test_run_control_raises_typed_error_on_missing_store(tmp_path):
    workspace, _ = _workspace(tmp_path)
    with pytest.raises(RuntimeStoreError, match="event store"):
        pause_run(workspace, reason="hold")


def test_run_control_raises_typed_error_on_corrupt_store(tmp_path):
    workspace, _ = _workspace(tmp_path)
    (workspace / ".loop" / "events.db").write_text("not sqlite")
    with pytest.raises(RuntimeStoreError, match="cannot read event store"):
        pause_run(workspace, reason="hold")


def test_help_lists_approve_pause_resume_cancel_commands():
    result = _cli("--help")
    assert result.returncode == 0 and all(command in result.stdout for command in ("approve", "pause", "resume", "cancel"))


def _assert_missing_target(command, args):
    result = _cli(command, *args)
    assert result.returncode == 2 and result.stdout == "" and "usage" in result.stderr.lower()


def test_approve_missing_target_argument_prints_usage_and_exits_nonzero():
    _assert_missing_target("approve", ("--decision", "denied"))


def test_pause_missing_target_argument_prints_usage_and_exits_nonzero():
    _assert_missing_target("pause", ("--reason", "hold"))


def test_resume_missing_target_argument_prints_usage_and_exits_nonzero():
    _assert_missing_target("resume", ())


def test_cancel_missing_target_argument_prints_usage_and_exits_nonzero():
    _assert_missing_target("cancel", ())


def test_approve_nonexistent_target_gives_distinct_actionable_error(tmp_path):
    result = _cli("approve", "--decision", "denied", str(tmp_path / "missing"))
    assert result.returncode == 2 and result.stdout == "" and "does not exist" in result.stderr


def test_approve_missing_decision_flag_is_a_usage_error_exit_2(tmp_path):
    workspace, _ = _workspace(tmp_path)
    result = _cli("approve", str(workspace))
    assert result.returncode == 2 and result.stdout == "" and "--decision is required" in result.stderr


def test_approve_invalid_decision_value_is_a_usage_error_exit_2(tmp_path):
    workspace, _ = _workspace(tmp_path)
    result = _cli("approve", "--decision", "maybe", str(workspace))
    assert result.returncode == 2 and result.stdout == "" and "invalid --decision" in result.stderr


def test_pause_missing_reason_flag_is_a_usage_error_exit_2(tmp_path):
    workspace, _ = _workspace(tmp_path)
    result = _cli("pause", str(workspace))
    assert result.returncode == 2 and result.stdout == "" and "--reason is required" in result.stderr


def test_approve_happy_path_exits_0_with_json_report(tmp_path):
    workspace, _, _ = _approval_workspace(tmp_path)
    result = _cli("approve", "--decision=approved", "--resume-target", "plan", str(workspace))
    assert result.returncode == 0 and json.loads(result.stdout)["ok"] is True and result.stderr == ""


def test_pause_happy_path_exits_0_with_json_report(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    result = _cli("pause", "--reason", "hold", str(workspace))
    assert result.returncode == 0 and json.loads(result.stdout)["ok"] is True and result.stderr == ""


def test_resume_happy_path_exits_0_with_json_report(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    pause_run(workspace, reason="hold")
    result = _cli("resume", "--note", "continue", str(workspace))
    assert result.returncode == 0 and json.loads(result.stdout)["ok"] is True and result.stderr == ""


def test_cancel_happy_path_exits_0_with_json_report(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    result = _cli("cancel", "--reason", "stop", str(workspace))
    assert result.returncode == 0 and json.loads(result.stdout)["ok"] is True and result.stderr == ""


def test_approve_illegal_state_exits_2_with_stderr_message_no_traceback(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    result = _cli("approve", "--decision", "denied", str(workspace))
    assert result.returncode == 2 and result.stdout == "" and "approve: run is not in approval-wait" in result.stderr
    assert "approve: approve:" not in result.stderr and "Traceback" not in result.stderr and _count(store) == 1


def test_run_control_commands_accept_mode_flag_like_doctor(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    result = _cli("pause", "--mode=basic", "--reason", "hold", str(workspace))
    assert result.returncode == 0 and json.loads(result.stdout)["ok"] is True and store.read(RUN_ID)[-1]["type"] == "run_paused"


def test_resume_raises_when_run_is_already_terminal(tmp_path):
    workspace, store = _workspace(tmp_path)
    _open(store)
    pause_run(workspace, reason="hold")
    cancel_run(workspace)
    _assert_refusal(IllegalRunControlStateError, lambda: resume_run(workspace), "already terminal", store)
    status = status_report(workspace)
    replay = replay_report(workspace)
    assert replay["ok"] and replay["legal_sequence"] and status["ok"] and status["event_count"] == _count(store)


def test_approve_raises_when_run_is_already_terminal(tmp_path):
    workspace, store, _ = _approval_workspace(tmp_path)
    cancel_run(workspace)
    _assert_refusal(IllegalRunControlStateError, lambda: approve_run(workspace, decision="denied"), "already terminal", store)
    status = status_report(workspace)
    replay = replay_report(workspace)
    assert replay["ok"] and replay["legal_sequence"] and status["ok"] and status["event_count"] == _count(store)
