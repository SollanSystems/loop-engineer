"""Behavioral and CLI coverage for the strictly read-only simulate verb."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from loop import emit, runner
from loop.events import SQLiteEventStore
from loop.runcontrol import cancel_run, pause_run
from loop.runtime import RuntimeStoreError, status_report
from loop.simulate import simulate_run

ROOT = Path(__file__).resolve().parent.parent
RUN_ID = "run-1"


def _task(task_id="T-1", deps=(), status="pending", verify="pytest -q"):
    result = {"id": task_id, "title": task_id, "status": status, "criterion_ref": task_id,
              "depends_on": list(deps), "attempts": 0, "evidence": None}
    if verify is not None:
        result["verify"] = verify
    return result


def _ws(tmp_path, tasks=None, ready=True):
    workspace = tmp_path / "workspace"; emit.open_contract(workspace)
    (workspace / "TASKS.json").write_text(json.dumps({"schema": "loop-engineer/tasks@1", "tasks": tasks or [_task()]}), encoding="utf-8")
    store = SQLiteEventStore(workspace / ".loop" / "events.db")
    store.append(RUN_ID, "contract_opened", {"workspace": "workspace"}, actor="test")
    if ready:
        for iteration_id, state in enumerate(("plan", "critique-plan", "queue-tasks", "execute-task"), 1):
            store.append(RUN_ID, "iteration_appended", {"iteration_id": iteration_id, "outcome": "replanned", "state": state}, actor="test")
            emit.append_iteration(workspace, iteration_id=iteration_id, outcome="replanned", state=state)
        _, projection = runner._projection(workspace, None)
        emit.sync_state_to_projection(workspace, projection)
        state_path = workspace / ".loop" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8")); state["active_task"] = None
        state_path.write_text(json.dumps(state), encoding="utf-8")
    return workspace, store


def _cli(*args):
    return subprocess.run([sys.executable, "-B", "-m", "loop", *args], cwd=ROOT, text=True, capture_output=True)


def _terminal(workspace):
    runner.dispatch_once(workspace, verifier=lambda task, root: runner.VerifyOutcome(True))


def test_simulate_on_non_execute_task_non_terminal_states_predicts_would_refuse_and_surfaces_approval_wait_pending_details(tmp_path):
    routes = {
        "intake": (), "plan": ("plan",), "critique-plan": ("plan", "critique-plan"),
        "queue-tasks": ("plan", "critique-plan", "queue-tasks"),
        "verify": ("plan", "critique-plan", "queue-tasks", "execute-task", "verify"),
        "repair": ("plan", "critique-plan", "queue-tasks", "execute-task", "verify", "repair"),
        "replan": ("plan", "critique-plan", "queue-tasks", "execute-task", "verify", "repair", "replan"),
    }
    for state in ("intake", "plan", "critique-plan", "queue-tasks", "verify", "repair", "replan"):
        w, store = _ws(tmp_path / state, ready=False)
        for iteration_id, next_state in enumerate(routes[state], 1):
            store.append(RUN_ID, "iteration_appended", {"iteration_id": iteration_id, "outcome": "replanned", "state": next_state}, actor="test")
            emit.append_iteration(w, iteration_id=iteration_id, outcome="replanned", state=next_state)
        report = simulate_run(w); assert report["would"]["action"] == "would_refuse" and "execute-task" in report["would"]["refusal_reason"]
    w, store = _ws(tmp_path / "approval", ready=False); store.append(RUN_ID, "iteration_appended", {"iteration_id": 1, "outcome": "replanned", "state": "plan"}, actor="test"); store.append(RUN_ID, "approval_requested", {"iteration_id": 1, "request": "approve"}, actor="test"); _, p = runner._projection(w, None); emit.sync_state_to_projection(w, p)
    report = simulate_run(w); assert report["pending_approval"] and "approval-wait" in report["would"]["refusal_reason"]


def test_simulate_on_execute_task_selects_next_pending_task_and_predicts_would_dispatch_with_verify_command_and_argv(tmp_path):
    w, _ = _ws(tmp_path); report = simulate_run(w); would = report["would"]
    assert would["action"] == "would_dispatch" and would["task_id"] == "T-1" and would["verify_command"] == "pytest -q" and would["verify_argv"] == ["pytest", "-q"]


def test_simulate_on_execute_task_with_undeclared_or_unparseable_verify_command_predicts_would_refuse(tmp_path):
    for name, verify, expected in (("missing", None, "no verify command"), ("blank", "", "no verify command"), ("bad", "'", "cannot parse")):
        w, _ = _ws(tmp_path / name, [_task(verify=verify)]); r = simulate_run(w)["would"]
        assert r["action"] == "would_refuse" and r["task_id"] == "T-1" and expected in r["refusal_reason"]


def test_simulate_on_execute_task_with_all_tasks_done_predicts_would_write_terminal_with_exact_payload_preview(tmp_path):
    w, _ = _ws(tmp_path, [_task(status="done")]); r = simulate_run(w)["would"]
    assert r["action"] == "would_write_terminal" and r["predicted_terminal"] == {"state": "Succeeded", "criteria_met": {"T-1": True}, "evidence": ["RUNLOG.md"], "false_completion": False, "completion_policy": {"mode": "all_required"}, "iteration_id": 4}


def test_simulate_on_execute_task_with_unsatisfiable_dependency_predicts_would_block_with_null_refusal_reason(tmp_path):
    w, _ = _ws(tmp_path, [_task(deps=("never",))]); r = simulate_run(w)["would"]
    assert r["action"] == "would_block" and r["refusal_reason"] is None


def test_simulate_predicted_would_dispatch_task_id_matches_real_dispatch_once_dispatched_task_id(tmp_path):
    w, _ = _ws(tmp_path); predicted = simulate_run(w)["would"]["task_id"]; actual = runner.dispatch_once(w, verifier=lambda t, p: runner.VerifyOutcome(True))
    assert actual["action"] == "dispatched" and actual["task_id"] == predicted


def test_simulate_predicted_terminal_payload_matches_real_dispatch_once_terminal_written_payload_exactly(tmp_path):
    w, store = _ws(tmp_path, [_task(status="done")]); predicted = simulate_run(w)["would"]["predicted_terminal"]; _terminal(w)
    assert predicted == store.read(RUN_ID)[-1]["payload"]


def test_simulate_predicted_would_block_matches_real_dispatch_once_blocked_action_and_null_message(tmp_path):
    w, _ = _ws(tmp_path, [_task(deps=("never",))]); assert simulate_run(w)["would"]["refusal_reason"] is None
    assert runner.dispatch_once(w) == {"ok": False, "action": "blocked", "run_id": RUN_ID}


def test_simulate_on_already_terminal_run_reports_terminal_and_would_action_already_terminal(tmp_path):
    w, _ = _ws(tmp_path, [_task(status="done")]); _terminal(w); r = simulate_run(w)
    assert r["terminal"] and r["would"]["action"] == "already_terminal"


def test_simulate_on_paused_execute_task_run_still_predicts_dispatch_pinning_current_run_behavior(tmp_path):
    w, _ = _ws(tmp_path); pause_run(w, reason="hold"); r = simulate_run(w)
    assert r["paused"] is True and r["would"]["action"] == "would_dispatch"


def test_simulate_reports_state_json_divergence_identically_to_status_report(tmp_path):
    w, _ = _ws(tmp_path); (w / ".loop" / "state.json").write_text("{}", encoding="utf-8")
    status, simulation = status_report(w), simulate_run(w)
    assert simulation["divergence"] == status["divergence"] and simulation["state_json_agrees"] == status["state_json_agrees"] and not simulation["ok"]


def test_simulate_reports_terminal_desync_when_terminal_event_present_but_file_missing(tmp_path):
    w, _ = _ws(tmp_path, [_task(status="done")]); _terminal(w); (w / ".loop" / "terminal_state.json").unlink(); r = simulate_run(w)
    assert not r["ok"] and r["terminal_desync"] and not (w / ".loop" / "terminal_state.json").exists()
    assert r["would"]["legacy_sync_would_write"] is True


def test_simulate_reports_terminal_desync_content_mismatch_without_repairing_it(tmp_path):
    w, _ = _ws(tmp_path, [_task(status="done")]); _terminal(w); path = w / ".loop" / "terminal_state.json"; path.write_text('{"state":"Nope"}', encoding="utf-8"); before = path.read_bytes(); r = simulate_run(w)
    assert r["terminal_desync"] and path.read_bytes() == before


def test_simulate_legacy_sync_would_write_true_when_runlog_entries_ahead_of_state_json_iteration_id_on_execute_task(tmp_path):
    w, store = _ws(tmp_path); store.append(RUN_ID, "iteration_appended", {"iteration_id": 5, "outcome": "task_passed", "task_id": "T-1"}, actor="test")
    assert simulate_run(w)["would"]["legacy_sync_would_write"] is True


def test_simulate_legacy_sync_would_write_false_on_terminal_run_despite_stale_runlog_iteration_lag(tmp_path):
    w, _ = _ws(tmp_path); pause_run(w, reason="hold"); cancel_run(w)
    path = w / ".loop" / "state.json"; state = json.loads(path.read_text(encoding="utf-8")); state["iteration_id"] = 0; path.write_text(json.dumps(state), encoding="utf-8")
    assert simulate_run(w)["would"]["legacy_sync_would_write"] is False


def test_simulate_reports_terminal_desync_when_terminal_file_present_but_event_absent_and_predicts_off_the_real_projection(tmp_path):
    w, _ = _ws(tmp_path); path = w / ".loop" / "terminal_state.json"; path.write_text('{"state":"Succeeded"}', encoding="utf-8"); before = path.read_bytes(); r = simulate_run(w)
    assert r["terminal"] is None and r["terminal_desync"] and not r["ok"] and r["would"]["action"] == "would_dispatch" and path.read_bytes() == before


def test_simulate_on_terminal_run_via_cancel_from_paused_retains_paused_flag_honestly(tmp_path):
    w, _ = _ws(tmp_path); pause_run(w, reason="hold"); cancel_run(w); r = simulate_run(w)
    assert r["terminal"] and r["would"]["action"] == "already_terminal" and r["paused"] is True and r["pause_reason"] == "hold"


def test_simulate_on_terminal_run_via_cancel_from_approval_wait_retains_pending_approval_honestly(tmp_path):
    w, store = _ws(tmp_path, ready=False); store.append(RUN_ID, "iteration_appended", {"iteration_id": 1, "outcome": "replanned", "state": "plan"}, actor="test"); store.append(RUN_ID, "approval_requested", {"iteration_id": 1, "request": "yes"}, actor="test"); _, p = runner._projection(w, None); emit.sync_state_to_projection(w, p); cancel_run(w); r = simulate_run(w)
    assert r["terminal"] and r["would"]["action"] == "already_terminal" and r["pending_approval"]


def test_simulate_raises_runtime_store_error_on_missing_or_empty_store(tmp_path):
    missing = tmp_path / "missing"; missing.mkdir(); (missing / ".loop").mkdir()
    with pytest.raises(RuntimeStoreError, match="missing_store"): simulate_run(missing)
    empty = tmp_path / "empty"; (empty / ".loop").mkdir(parents=True); store = SQLiteEventStore(empty / ".loop" / "events.db"); store._connect().close()
    with pytest.raises(RuntimeStoreError, match="empty_store"): simulate_run(empty)


def test_simulate_raises_runtime_store_error_on_corrupt_store(tmp_path):
    w = tmp_path / "bad"; (w / ".loop").mkdir(parents=True); (w / ".loop" / "events.db").write_bytes(b"nope")
    with pytest.raises(RuntimeStoreError, match="corrupt_store"): simulate_run(w)


def test_simulate_raises_runtime_store_error_on_ambiguous_run_id(tmp_path):
    w, store = _ws(tmp_path, ready=False); store.append("run-2", "contract_opened", {"workspace": "workspace"}, actor="test")
    with pytest.raises(RuntimeStoreError, match="ambiguous_run_id"): simulate_run(w)


def test_simulate_raises_runner_error_when_tasks_json_missing_in_execute_task_state(tmp_path):
    w, _ = _ws(tmp_path); (w / "TASKS.json").unlink()
    with pytest.raises(runner.RunnerError, match="cannot read TASKS.json"): simulate_run(w)


def test_simulate_command_listed_in_help_and_usage():
    r = _cli("--help"); assert "simulate" in r.stdout and "python3 -m loop simulate [--mode basic|strict|release] <workspace>" in r.stdout


def test_simulate_missing_target_argument_prints_usage_and_exits_nonzero():
    r = _cli("simulate"); assert r.returncode != 0 and "usage:" in r.stderr


def test_simulate_nonexistent_target_gives_actionable_error_exit_2(tmp_path):
    r = _cli("simulate", str(tmp_path / "missing")); assert r.returncode == 2 and r.stdout == "" and "does not exist" in r.stderr


def test_simulate_happy_path_exits_0_with_json_would_dispatch_report(tmp_path):
    w, _ = _ws(tmp_path); r = _cli("simulate", str(w)); assert r.returncode == 0 and json.loads(r.stdout)["would"]["action"] == "would_dispatch" and r.stderr == ""


def test_simulate_exits_1_with_json_report_when_state_json_diverges_from_projection(tmp_path):
    w, _ = _ws(tmp_path); (w / ".loop" / "state.json").write_text("{}", encoding="utf-8"); r = _cli("simulate", str(w))
    assert r.returncode == 1 and json.loads(r.stdout)["ok"] is False and r.stderr == ""


def test_simulate_accepts_mode_flag_like_doctor_and_run(tmp_path):
    w, _ = _ws(tmp_path); r = _cli("simulate", "--mode=basic", str(w)); assert r.returncode == 0 and isinstance(json.loads(r.stdout), dict)


def test_simulate_corrupt_store_exits_2_with_typed_message_no_traceback(tmp_path):
    w = tmp_path / "bad"; (w / ".loop").mkdir(parents=True); (w / ".loop" / "events.db").write_bytes(b"bad"); r = _cli("simulate", str(w))
    assert r.returncode == 2 and r.stdout == "" and "cannot read event store" in r.stderr and "Traceback" not in r.stderr
