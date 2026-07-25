"""dispatch_once binds its evidence digests into the iteration event before writing them."""
from __future__ import annotations

import hashlib
import json

import pytest

from loop import emit
from loop.chain import compute_event_hash
from loop.events import SQLiteEventStore
from loop.runner import RunnerError, VerifyOutcome, dispatch_once

_VERIFY = "./scripts/verify-fast.sh"
_RAMP = ("plan", "critique-plan", "queue-tasks", "execute-task")


def _task(i, deps=(), status="pending"):
    return {"id": i, "title": i, "status": status, "criterion_ref": i, "verify": _VERIFY,
            "depends_on": list(deps), "attempts": 0, "evidence": None}


def _ready(tmp_path, tasks):
    """A contract projected to execute-task with the iteration counter still at 0.

    The ramp records the FSM walk to execute-task, not work: intake is reachable
    only by iteration_appended, so the ramp events exist, but they carry
    iteration_id 0 and no task verdict. The first dispatch is therefore iteration
    1 and every artifact path asserted below is literal.
    """
    workspace = tmp_path / "workspace"
    emit.open_contract(workspace)
    (workspace / "TASKS.json").write_text(
        json.dumps({"schema": "loop-engineer/tasks@1", "tasks": tasks}), encoding="utf-8")
    script = workspace / "scripts" / "verify-fast.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    store = SQLiteEventStore(workspace / ".loop" / "events.db")
    store.append("run-1", "contract_opened", {"workspace": "workspace"}, actor="test")
    for state in _RAMP:
        store.append("run-1", "iteration_appended",
                     {"iteration_id": 0, "outcome": "replanned", "state": state}, actor="test")
    return workspace


@pytest.fixture
def ready_workspace(tmp_path):
    return _ready(tmp_path, [_task("T-1")])


@pytest.fixture
def two_task_workspace(tmp_path):
    return _ready(tmp_path, [_task("T-1"), _task("T-2", ("T-1",))])


def _events(workspace, run_id="run-1"):
    return SQLiteEventStore(workspace / ".loop" / "events.db").read(run_id)


def _iteration_events(workspace):
    """Iterations carrying a task verdict — exactly the ones a dispatch appends."""
    return [e for e in _events(workspace) if e["type"] == "iteration_appended"
            and e["payload"]["outcome"] in ("task_passed", "task_failed")]


def test_dispatch_binds_the_evidence_digests_into_the_iteration_event(ready_workspace):
    dispatch_once(ready_workspace)
    hashes = _iteration_events(ready_workspace)[-1]["artifact_hashes"]
    paths = {entry["path"] for entry in hashes}
    assert len(hashes) == 3
    assert ".loop/artifacts/verify-iter1.json" in paths
    assert ".loop/evidence/evidence-iter1.json" in paths


def test_bound_digests_match_the_files_on_disk(ready_workspace):
    dispatch_once(ready_workspace)
    for entry in _iteration_events(ready_workspace)[-1]["artifact_hashes"]:
        blob = (ready_workspace / entry["path"]).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == entry["sha256"]


def test_the_bound_event_hash_covers_the_artifact_hashes(ready_workspace):
    dispatch_once(ready_workspace)
    event = _iteration_events(ready_workspace)[-1]
    assert compute_event_hash(event) == event["event_hash"]
    tampered = {**event, "artifact_hashes": []}
    assert compute_event_hash(tampered) != event["event_hash"]


def test_a_build_failure_commits_no_event(ready_workspace):
    tasks_path = ready_workspace / "TASKS.json"
    data = json.loads(tasks_path.read_text(encoding="utf-8"))
    data["tasks"][0]["criterion_ref"] = float("nan")
    tasks_path.write_text(json.dumps(data), encoding="utf-8")
    before = len(_events(ready_workspace))
    with pytest.raises(RunnerError):
        dispatch_once(ready_workspace)
    assert len(_events(ready_workspace)) == before


def test_an_evidence_write_failure_after_the_commit_is_still_loud(ready_workspace, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(emit, "write_verify_evidence", boom)
    with pytest.raises(RunnerError, match="committed to the event log"):
        dispatch_once(ready_workspace)
    assert len(_iteration_events(ready_workspace)) == 1


def test_dispatch_result_names_the_object_and_the_record(ready_workspace):
    result = dispatch_once(ready_workspace)
    assert result["evidence"].endswith("evidence-iter1.json")
    assert "objects" in result["object"]


def test_injected_verifier_dispatch_binds_its_own_bundle(ready_workspace):
    dispatch_once(ready_workspace, verifier=lambda task, ws: VerifyOutcome(True, "injected"))
    bundle = json.loads((ready_workspace / ".loop" / "artifacts" / "verify-iter1.json")
                        .read_text(encoding="utf-8"))
    entry = next(e for e in _iteration_events(ready_workspace)[-1]["artifact_hashes"]
                 if e["path"].endswith("verify-iter1.json"))
    assert bundle["verifier"]["source"] == "injected_callable"
    assert entry["sha256"] == hashlib.sha256(
        (ready_workspace / entry["path"]).read_bytes()).hexdigest()


def test_two_dispatches_bind_distinct_artifact_sets(two_task_workspace):
    dispatch_once(two_task_workspace)
    dispatch_once(two_task_workspace)
    first, second = _iteration_events(two_task_workspace)[:2]
    assert {e["path"] for e in first["artifact_hashes"]} != {e["path"] for e in second["artifact_hashes"]}


def test_terminal_written_carries_no_artifact_hashes(ready_workspace):
    dispatch_once(ready_workspace)
    dispatch_once(ready_workspace)
    terminal = [e for e in _events(ready_workspace) if e["type"] == "terminal_written"]
    assert terminal and terminal[-1]["artifact_hashes"] == []
