"""Regression coverage for the subprocess-isolated default verifier."""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from loop import emit
from loop.events import SQLiteEventStore
from loop.runner import VerifierExecutionError, VerifierNotImplementedError, _subprocess_verifier, dispatch_once

ROOT = Path(__file__).resolve().parent.parent


def _task(verify, deps=()):
    value = {"id": "T-1", "title": "T-1", "status": "pending", "criterion_ref": "T-1", "depends_on": list(deps), "attempts": 0, "evidence": None}
    if verify is not None:
        value["verify"] = verify
    return value


def _ws(tmp_path, tasks=None, ready=True):
    workspace = tmp_path / "workspace"; emit.open_contract(workspace)
    (workspace / "TASKS.json").write_text(json.dumps({"schema": "loop-engineer/tasks@1", "tasks": tasks or [_task("true")]}), encoding="utf-8")
    store = SQLiteEventStore(workspace / ".loop" / "events.db")
    store.append("run-1", "contract_opened", {"workspace": "workspace"}, actor="test")
    if ready:
        for n, state in enumerate(("plan", "critique-plan", "queue-tasks", "execute-task"), 1):
            store.append("run-1", "iteration_appended", {"iteration_id": n, "outcome": "replanned", "state": state}, actor="test")
            emit.append_iteration(workspace, iteration_id=n, outcome="replanned", state=state)
    return workspace, store


def _script(tmp_path, name, body):
    path = tmp_path / name; path.write_text(body, encoding="utf-8"); return path


def _cmd(path): return f"{sys.executable} {path}"
def _cli(*args): return subprocess.run([sys.executable, "-m", "loop", *args], cwd=ROOT, text=True, capture_output=True, timeout=15)
def _hashes(w): return {str(p.relative_to(w)): hashlib.sha256(p.read_bytes()).hexdigest() for p in w.rglob("*") if p.is_file() and not p.name.endswith((".db-wal", ".db-shm"))}


def test_subprocess_verifier_maps_exit_zero_to_verify_outcome_passed_true(tmp_path):
    outcome = _subprocess_verifier(_task(_cmd(_script(tmp_path, "pass.py", "print('ok')\n"))), tmp_path)
    assert outcome.passed is True and outcome.summary == "ok\n"


def test_subprocess_verifier_maps_nonzero_exit_to_verify_outcome_passed_false_with_tail_summary(tmp_path):
    outcome = _subprocess_verifier(_task(_cmd(_script(tmp_path, "fail.py", "import sys\nprint('bad', file=sys.stderr)\nsys.exit(1)\n"))), tmp_path)
    assert outcome.passed is False and "bad" in outcome.summary


def test_subprocess_verifier_does_not_shell_interpret_metacharacters_in_the_verify_string(tmp_path):
    script = _script(tmp_path, "pass.py", "import sys\n"); marker = tmp_path / "marker"
    outcome = _subprocess_verifier(_task(f"{_cmd(script)} ; touch {marker}"), tmp_path)
    assert outcome.passed is True and not marker.exists()


def test_subprocess_verifier_runs_with_cwd_set_to_the_workspace_directory(tmp_path):
    workspace = tmp_path / "workspace"; workspace.mkdir()
    outcome = _subprocess_verifier(_task(_cmd(_script(tmp_path, "cwd.py", "from pathlib import Path\nprint(Path.cwd())\n"))), workspace)
    assert outcome.passed is True and outcome.summary.strip() == str(workspace)


def test_subprocess_verifier_real_timeout_kills_the_child_and_maps_to_failed_outcome(tmp_path, monkeypatch):
    pid = tmp_path / "pid"; monkeypatch.setattr("loop.runner._VERIFY_TIMEOUT_SECONDS", 1); started = time.monotonic()
    script = _script(tmp_path, "sleep.py", f"import os,time\nopen({str(pid)!r}, 'w').write(str(os.getpid()))\ntime.sleep(30)\n")
    outcome = _subprocess_verifier(_task(_cmd(script)), tmp_path)
    with pytest.raises(ProcessLookupError): os.kill(int(pid.read_text()), 0)
    assert outcome.passed is False and "timed out" in outcome.summary and time.monotonic() - started < 5


def test_subprocess_verifier_missing_executable_raises_verifier_execution_error(tmp_path):
    with pytest.raises(VerifierExecutionError): _subprocess_verifier(_task("not-a-real-verifier-command"), tmp_path)


def test_dispatch_once_task_without_verify_field_raises_verifier_not_implemented_zero_writes(tmp_path):
    workspace, _ = _ws(tmp_path, [_task(None)]); before = _hashes(workspace)
    with pytest.raises(VerifierNotImplementedError): dispatch_once(workspace)
    assert _hashes(workspace) == before


def test_dispatch_once_task_with_blank_verify_field_raises_verifier_not_implemented_zero_writes(tmp_path):
    workspace, _ = _ws(tmp_path, [_task(" ")]); before = _hashes(workspace)
    with pytest.raises(VerifierNotImplementedError): dispatch_once(workspace)
    assert _hashes(workspace) == before


def test_dispatch_once_end_to_end_with_a_real_passing_verify_script_records_task_passed(tmp_path):
    workspace, store = _ws(tmp_path, [_task(_cmd(_script(tmp_path, "pass.py", "print('verified')\n")))])
    assert dispatch_once(workspace)["outcome"] == "task_passed" and store.read("run-1")[-1]["payload"]["summary"] == "verified\n"


def test_dispatch_once_end_to_end_with_a_real_failing_verify_script_records_task_failed_with_summary(tmp_path):
    workspace, store = _ws(tmp_path, [_task(_cmd(_script(tmp_path, "fail.py", "import sys\nprint('failure-tail', file=sys.stderr)\nsys.exit(1)\n")))])
    assert dispatch_once(workspace)["outcome"] == "task_failed" and "failure-tail" in store.read("run-1")[-1]["payload"]["summary"]


def test_run_cli_end_to_end_dispatches_via_a_real_declared_verify_script_and_exits_0(tmp_path):
    workspace, _ = _ws(tmp_path, [_task(_cmd(_script(tmp_path, "pass.py", "print('cli-ok')\n")))])
    result = _cli("run", str(workspace)); assert result.returncode == 0 and json.loads(result.stdout)["outcome"] == "task_passed"


def test_run_cli_reports_blocked_action_as_exit_1_json_with_no_traceback(tmp_path):
    workspace, _ = _ws(tmp_path, [_task("true", ("missing",))]); result = _cli("run", str(workspace))
    assert result.returncode == 1 and json.loads(result.stdout)["action"] == "blocked" and "Traceback" not in result.stderr


def test_run_cli_missing_declared_verify_command_exits_2_with_typed_message_no_traceback(tmp_path):
    workspace, _ = _ws(tmp_path, [_task("")]); result = _cli("run", str(workspace))
    assert result.returncode == 2 and "no verify command declared" in result.stderr and "Traceback" not in result.stderr


def test_run_cli_continuous_flag_raises_typed_error_exits_2_zero_writes_dispatch_never_called(tmp_path):
    workspace, _ = _ws(tmp_path, ready=False); before = _hashes(workspace)
    result = _cli("run", "--continuous", "--mode=bad", str(workspace))
    assert result.returncode == 2 and "not implemented" in result.stderr and "does not exist" not in result.stderr and _hashes(workspace) == before


def test_run_cli_approve_flag_raises_typed_error_exits_2_zero_writes_dispatch_never_called(tmp_path):
    workspace, _ = _ws(tmp_path, ready=False); before = _hashes(workspace)
    result = _cli("run", "--approve", str(workspace))
    assert result.returncode == 2 and "not implemented" in result.stderr and "does not exist" not in result.stderr and _hashes(workspace) == before


def test_crash_injection_after_subprocess_verify_completes_before_iteration_commit_is_safely_retried(tmp_path):
    counter = tmp_path / "counter"
    command = _cmd(_script(tmp_path, "pass.py", f"from pathlib import Path\np=Path({str(counter)!r})\np.write_text(str(int(p.read_text()) + 1) if p.exists() else '1')\n"))
    workspace, store = _ws(tmp_path, [_task(command)])
    body = f"import sys\nsys.path.insert(0, {str(ROOT)!r})\n" + "import os,signal,sqlite3\nreal=sqlite3.connect\nclass Kill(sqlite3.Connection):\n def execute(self,sql,*a,**kw):\n  if isinstance(sql,str) and sql.strip().upper()=='COMMIT': os.kill(os.getpid(),signal.SIGKILL)\n  return super().execute(sql,*a,**kw)\nsqlite3.connect=lambda *a,**kw: real(*a,factory=Kill,**kw)\nfrom loop.runner import dispatch_once\ndispatch_once(sys.argv[1])\n"
    crash = _script(tmp_path, "crash.py", body)
    result = subprocess.run([sys.executable, "-B", str(crash), str(workspace)], cwd=ROOT, timeout=15)
    assert result.returncode == -signal.SIGKILL and len(store.read("run-1")) == 5
    assert dispatch_once(workspace)["outcome"] == "task_passed" and counter.read_text() == "2"


def test_malformed_verify_string_raises_typed_verifier_execution_error_zero_writes(tmp_path):
    workspace, _ = _ws(tmp_path, [_task("echo 'unbalanced")]); before = _hashes(workspace)
    with pytest.raises(VerifierExecutionError): dispatch_once(workspace)
    assert _hashes(workspace) == before


def test_noexec_launch_failure_raises_typed_verifier_execution_error(tmp_path):
    verifier = _script(tmp_path, "not-an-executable-script", "plain data\n"); verifier.chmod(0o755)
    with pytest.raises(VerifierExecutionError): _subprocess_verifier(_task(str(verifier)), tmp_path)


def test_non_utf8_verify_output_is_replaced_not_fatal(tmp_path):
    verifier = _script(tmp_path, "non-utf8.py", "import sys\nsys.stdout.buffer.write(b'\\xff\\xfeok')\n")
    outcome = _subprocess_verifier(_task(_cmd(verifier)), tmp_path)
    assert outcome.passed is True and isinstance(outcome.summary, str)
