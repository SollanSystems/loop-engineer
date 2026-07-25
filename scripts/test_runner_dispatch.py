"""Regression coverage for the bounded event-sourced runner."""
from __future__ import annotations

import hashlib
import json
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from loop import emit
from loop.contract import doctor_report
from loop.events import SQLiteEventStore, SequenceConflictError
from loop.runner import (NotReadyError, RunnerError, VerifyOutcome, VerifierNotImplementedError,
                         dispatch_once, select_next_task)
from loop.runtime import replay_report

ROOT = Path(__file__).resolve().parent.parent


def _task(i, deps=(), status="pending"):
    return {"id": i, "title": i, "status": status, "criterion_ref": i, "verify": "true", "depends_on": list(deps), "attempts": 0, "evidence": None}


def _ws(tmp_path, tasks=None, ready=True):
    w = tmp_path / "workspace"; emit.open_contract(w)
    (w / "TASKS.json").write_text(json.dumps({"schema": "loop-engineer/tasks@1", "tasks": tasks or [_task("T-1")]}), encoding="utf-8")
    s = SQLiteEventStore(w / ".loop" / "events.db")
    s.append("run-1", "contract_opened", {"workspace": "workspace"}, actor="test")
    if ready:
        for n, state in enumerate(("plan", "critique-plan", "queue-tasks", "execute-task"), 1):
            s.append("run-1", "iteration_appended", {"iteration_id": n, "outcome": "replanned", "state": state}, actor="test")
            emit.append_iteration(w, iteration_id=n, outcome="replanned", state=state)
    return w, s


def _pass(task, workspace): return VerifyOutcome(True, "verified")
def _hashes(w): return {str(p.relative_to(w)): hashlib.sha256(p.read_bytes()).hexdigest() for p in w.rglob("*") if p.is_file() and not p.name.endswith((".db-wal", ".db-shm"))}
def _cli(*args): return subprocess.run([sys.executable, "-m", "loop", *args], cwd=ROOT, text=True, capture_output=True, timeout=15)


def test_select_next_task_respects_depends_on_and_declaration_order():
    assert select_next_task([_task("T-2", ("T-1",)), _task("T-1")], {"runlog_entries": []})["id"] == "T-1"

def test_select_next_task_returns_none_when_all_tasks_done():
    assert select_next_task([_task("T-1", status="done")], {"runlog_entries": []}) is None

def test_select_next_task_skips_task_already_recorded_task_passed_in_event_log_even_if_tasks_json_says_pending():
    assert select_next_task([_task("T-1"), _task("T-2")], {"runlog_entries": [{"task_id": "T-1", "outcome": "task_passed"}]})["id"] == "T-2"

def test_select_next_task_reports_blocked_when_a_pending_task_has_a_never_satisfiable_dependency():
    assert select_next_task([_task("T-1", ("missing",))], {"runlog_entries": []}) is None

def test_dispatch_once_raises_not_ready_when_projection_state_is_not_execute_task(tmp_path):
    w, _ = _ws(tmp_path, ready=False); before = _hashes(w)
    with pytest.raises(NotReadyError): dispatch_once(w, verifier=_pass)
    assert _hashes(w) == before

def test_dispatch_once_default_verifier_raises_and_persists_no_event_or_legacy_write(tmp_path):
    w, _ = _ws(tmp_path, [{**_task("T-1"), "verify": ""}]); before = _hashes(w)
    with pytest.raises(VerifierNotImplementedError): dispatch_once(w)
    assert _hashes(w) == before

def test_dispatch_once_appends_exactly_one_iteration_event_and_materializes_runlog_and_state(tmp_path):
    w, s = _ws(tmp_path); assert dispatch_once(w, verifier=_pass)["outcome"] == "task_passed"
    assert len(s.read("run-1")) == 6 and "## Iteration 5 —" in (w / "RUNLOG.md").read_text() and json.loads((w / ".loop" / "state.json").read_text())["iteration_id"] == 5

def test_dispatch_once_writes_terminal_and_syncs_legacy_artifacts_when_all_tasks_done(tmp_path):
    w, _ = _ws(tmp_path, [_task("T-1", status="done")]); assert dispatch_once(w, verifier=_pass)["action"] == "terminal_written"
    assert json.loads((w / ".loop" / "state.json").read_text())["terminal_state"] == "Succeeded"

def test_dispatch_once_second_call_after_terminal_is_a_clean_noop(tmp_path):
    w, _ = _ws(tmp_path, [_task("T-1", status="done")]); dispatch_once(w, verifier=_pass)
    assert dispatch_once(w, verifier=_pass)["action"] == "noop_terminal"

def test_append_iteration_retry_with_same_iteration_id_does_not_duplicate_runlog_block(tmp_path):
    w, _ = _ws(tmp_path); emit.append_iteration(w, iteration_id=5, outcome="task_passed", task_id="T-1"); emit.append_iteration(w, iteration_id=5, outcome="task_passed", task_id="T-1")
    assert (w / "RUNLOG.md").read_text().count("## Iteration 5 —") == 1

def test_dispatch_once_sequential_calls_advance_through_all_tasks_without_repeats(tmp_path):
    w, _ = _ws(tmp_path, [_task("T-1"), _task("T-2", ("T-1",))]); a = dispatch_once(w, verifier=_pass); b = dispatch_once(w, verifier=_pass); c = dispatch_once(w, verifier=_pass)
    assert (a["task_id"], b["task_id"], c["action"]) == ("T-1", "T-2", "terminal_written")

def test_dispatch_once_surfaces_sequence_conflict_from_a_concurrent_external_append_as_typed_error(tmp_path):
    w, s = _ws(tmp_path)
    def conflict(task, root):
        s.append("run-1", "receipt_appended", {"iteration_id": 4, "role": "write", "model": "test", "outcome": "ok"}, actor="other")
        return VerifyOutcome(True)
    with pytest.raises(SequenceConflictError): dispatch_once(w, verifier=conflict)

def test_replay_report_after_normal_multi_task_run_is_ok_and_deterministic(tmp_path):
    w, _ = _ws(tmp_path, [_task("T-1"), _task("T-2", ("T-1",))]); dispatch_once(w, verifier=_pass); dispatch_once(w, verifier=_pass); dispatch_once(w, verifier=_pass)
    r = replay_report(w); assert r["ok"] and r["deterministic"] and r["terminal_desync"] is None


def _crash(tmp_path, workspace, after):
    p = tmp_path / ("after.py" if after else "before.py")
    body = "result = super().execute(sql, *args, **kwargs)\n        if isinstance(sql, str) and sql.strip().upper() == 'COMMIT': os.kill(os.getpid(), signal.SIGKILL)\n        return result" if after else "if isinstance(sql, str) and sql.strip().upper() == 'COMMIT': os.kill(os.getpid(), signal.SIGKILL)\n        return super().execute(sql, *args, **kwargs)"
    p.write_text("import os,sys,signal,sqlite3\nsys.path.insert(0, os.getcwd())\nreal=sqlite3.connect\nclass Barrier(sqlite3.Connection):\n    def execute(self,sql,*args,**kwargs):\n        " + body + "\nsqlite3.connect=lambda *a,**kw: real(*a,factory=Barrier,**kw)\nfrom loop.runner import dispatch_once,VerifyOutcome\ndispatch_once(sys.argv[1],verifier=lambda t,w: VerifyOutcome(True))\n", encoding="utf-8")
    return subprocess.run([sys.executable, "-B", str(p), str(workspace)], cwd=ROOT, timeout=15)

def test_crash_injection_before_iteration_event_commit_leaves_no_partial_dispatch(tmp_path):
    w, s = _ws(tmp_path); before = _hashes(w); p = _crash(tmp_path, w, False)
    assert p.returncode == -signal.SIGKILL and _hashes(w) == before and len(s.read("run-1")) == 5
    assert dispatch_once(w, verifier=_pass)["action"] == "dispatched"

def test_crash_injection_after_iteration_event_commit_before_legacy_sync_resumes_without_duplicate_event(tmp_path):
    w, s = _ws(tmp_path); p = _crash(tmp_path, w, True)
    assert p.returncode == -signal.SIGKILL and len(s.read("run-1")) == 6 and json.loads((w / ".loop" / "state.json").read_text())["iteration_id"] == 4
    assert dispatch_once(w, verifier=_pass)["action"] == "terminal_written" and len(s.read("run-1")) == 7 and (w / "RUNLOG.md").read_text().count("## Iteration 5 —") == 1

def test_crash_injection_after_terminal_event_commit_before_legacy_write_resumes_via_sync(tmp_path):
    w, s = _ws(tmp_path, [_task("T-1", status="done")]); p = _crash(tmp_path, w, True); terminal = w / ".loop" / "terminal_state.json"
    assert p.returncode == -signal.SIGKILL and s.read("run-1")[-1]["type"] == "terminal_written" and not terminal.exists()
    assert dispatch_once(w, verifier=_pass)["action"] == "noop_terminal"; stamp = terminal.stat().st_mtime_ns
    assert dispatch_once(w, verifier=_pass)["action"] == "noop_terminal" and terminal.stat().st_mtime_ns == stamp and replay_report(w)["terminal_desync"] is None

def test_run_command_listed_in_help_and_usage():
    r = _cli("--help"); assert r.returncode == 0 and "run" in r.stdout and "python3 -m loop run [--mode basic|strict|release] <workspace>" in r.stdout

def test_run_missing_target_argument_prints_usage_and_exits_nonzero():
    r = _cli("run"); assert r.returncode != 0 and "usage:" in r.stderr

def test_run_nonexistent_target_gives_actionable_error_exit_2(tmp_path):
    r = _cli("run", str(tmp_path / "missing")); assert r.returncode == 2 and "does not exist" in r.stderr

def test_run_cli_default_verifier_not_implemented_exits_2_no_traceback(tmp_path):
    w, _ = _ws(tmp_path, [{**_task("T-1"), "verify": ""}]); r = _cli("run", str(w))
    assert r.returncode == 2 and "no verify command declared" in r.stderr and r.stdout == "" and "Traceback" not in r.stderr


def _verify_ws(tmp_path, verify="./scripts/verify-fast.sh"):
    workspace, store = _ws(tmp_path, [{**_task("T-1"), "verify": verify}])
    script = workspace / "scripts" / "verify-fast.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    return workspace, store


def _bundle(workspace, n=5):
    return json.loads((workspace / ".loop" / "artifacts" / f"verify-iter{n}.json").read_text())


def _record(workspace, n=5):
    return json.loads((workspace / ".loop" / "evidence" / f"evidence-iter{n}.json").read_text())


def test_dispatch_with_the_declared_verifier_records_a_workspace_file_digest(tmp_path):
    """Only the path that ACTUALLY executes ./scripts/verify-fast.sh may hash it."""
    workspace, _ = _verify_ws(tmp_path)
    result = dispatch_once(workspace)  # no injected verifier -> the declared command runs
    record = _record(workspace)
    assert _bundle(workspace)["outcome"] == "PASS"
    assert record["verified_by"]["command"] == "./scripts/verify-fast.sh"
    assert record["verified_by"]["code_digest_basis"] == "workspace_file"
    assert record["verified_by"]["code_digest"] == hashlib.sha256(
        (workspace / "scripts" / "verify-fast.sh").read_bytes()).hexdigest()
    assert result["evidence"].endswith("evidence-iter5.json")


def test_dispatch_with_an_injected_verifier_records_no_fabricated_identity(tmp_path):
    """The declared command never ran, so command/digest are null with an explicit basis."""
    workspace, _ = _verify_ws(tmp_path)
    dispatch_once(workspace, verifier=_pass)
    record = _record(workspace)
    assert record["verified_by"]["command"] is None
    assert record["verified_by"]["code_digest"] is None
    assert record["verified_by"]["code_digest_basis"] == "injected_verifier"
    assert _bundle(workspace)["verifier"]["source"] == "injected_callable"


def test_dispatch_once_writes_a_red_bundle_for_a_failing_task(tmp_path):
    workspace, _ = _verify_ws(tmp_path)
    dispatch_once(workspace, verifier=lambda task, root: VerifyOutcome(False, "boom"))
    assert _bundle(workspace)["passed"] is False and _bundle(workspace)["summary"] == "boom"


def test_dispatch_once_records_the_supplied_executor(tmp_path):
    workspace, _ = _verify_ws(tmp_path)
    dispatch_once(workspace, verifier=_pass, executor="worker-a")
    record = _record(workspace)
    assert record["produced_by"]["executor"] == "worker-a" and record["verified_by"]["by"] == "loop.run"


def test_attempt_counts_durable_prior_iterations_for_this_task(tmp_path):
    """Derived from the event log, not from the never-incremented TASKS.json `attempts`."""
    workspace, _ = _verify_ws(tmp_path)
    dispatch_once(workspace, verifier=lambda task, root: VerifyOutcome(False, "red"))
    assert _record(workspace, 5)["produced_by"]["attempt"] == 1
    dispatch_once(workspace, verifier=lambda task, root: VerifyOutcome(False, "red again"))
    assert _record(workspace, 6)["produced_by"]["attempt"] == 2


def test_terminal_dispatch_writes_no_verify_bundle(tmp_path):
    workspace, _ = _ws(tmp_path, [_task("T-1", status="done")])
    assert dispatch_once(workspace, verifier=_pass)["action"] == "terminal_written"
    assert not (workspace / ".loop" / "evidence").exists()


def test_evidence_write_failure_after_a_committed_event_is_loud(tmp_path, monkeypatch):
    workspace, store = _verify_ws(tmp_path)
    def boom(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(emit, "write_verify_evidence", boom)
    with pytest.raises(RunnerError, match="committed"):
        dispatch_once(workspace, verifier=_pass)
    assert len(store.read("run-1")) == 6  # the event IS durable; the failure is reported, not hidden


def test_run_cli_accepts_executor_and_records_it(tmp_path):
    workspace, _ = _verify_ws(tmp_path, verify="true")
    result = _cli("run", "--executor", "worker-a", str(workspace))
    assert result.returncode == 0 and _record(workspace)["produced_by"]["executor"] == "worker-a"


@pytest.mark.xfail(strict=True, reason="doctor does not discover .loop/evidence/*.json yet: the "
                                       "self_verified_evidence finding is wired in the doctor-discovery "
                                       "slice. Delete this marker there — strict=True makes it XPASS loudly.")
def test_run_cli_verifier_identity_makes_the_finding_reachable(tmp_path):
    """Without this flag verified_by.by is always 'loop.run' and the kernel's own
    write path could never trip self_verified_evidence."""
    workspace, _ = _verify_ws(tmp_path, verify="true")
    result = _cli("run", "--executor", "solo", "--verifier-identity", "Solo", str(workspace))
    assert result.returncode == 0
    assert _record(workspace)["verified_by"]["by"] == "Solo"
    assert "self_verified_evidence" in {i["code"] for i in doctor_report(workspace)["issues"]}


def test_identity_flags_are_rejected_on_other_commands_and_create_nothing(tmp_path):
    for flag in ("--executor", "--verifier-identity"):
        target = tmp_path / f"fresh{flag}"
        result = _cli("scaffold", flag, "worker-a", str(target))
        assert result.returncode == 2 and "only valid for run" in result.stderr and not target.exists()


def test_run_help_documents_the_identity_flags():
    result = _cli("--help")
    assert result.returncode == 0
    assert "--executor" in result.stdout and "--verifier-identity" in result.stdout
