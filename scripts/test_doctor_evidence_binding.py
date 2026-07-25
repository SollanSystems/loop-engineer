"""Doctor's chain-binding walk: bound artifacts must still be the bytes that were bound."""
from __future__ import annotations

import json

import pytest

from loop import emit
from loop.contract import doctor_report
from loop.events import SQLiteEventStore
from loop.runner import dispatch_once
from loop.scaffold import scaffold

try:                                  # the repo's fallback-mode convention
    import jsonschema                 # noqa: F401
    _HAS_JSONSCHEMA = True
except ImportError:                   # pragma: no cover - exercised in the fallback leg
    _HAS_JSONSCHEMA = False

_MODES = [pytest.param("basic"),
          pytest.param("strict", marks=pytest.mark.skipif(not _HAS_JSONSCHEMA,
                                                          reason="jsonschema not installed"))]

_VERIFY = "./scripts/verify-fast.sh"
_RAMP = ("plan", "critique-plan", "queue-tasks", "execute-task")
_RUN_ID = "run-1"


def _codes(report):
    return {issue["code"] for issue in report["issues"]}


def _tree(workspace):
    return sorted(str(p.relative_to(workspace)) for p in workspace.rglob("*") if p.is_file())


def _store_path(workspace):
    return workspace / ".loop" / "events.db"


def _ready(tmp_path):
    """A contract projected to execute-task with the iteration counter still at 0.

    The ramp records the FSM walk to execute-task, not work: intake is reachable
    only by iteration_appended, so the ramp events exist, but they carry
    iteration_id 0 and no task verdict. The first dispatch is therefore iteration
    1 and every artifact path asserted below is literal.
    """
    workspace = tmp_path / "workspace"
    emit.open_contract(workspace)
    (workspace / "TASKS.json").write_text(json.dumps({
        "schema": "loop-engineer/tasks@1",
        "tasks": [{"id": "T-1", "title": "T-1", "status": "pending", "criterion_ref": "T-1",
                   "verify": _VERIFY, "depends_on": [], "attempts": 0, "evidence": None}],
    }), encoding="utf-8")
    script = workspace / "scripts" / "verify-fast.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    store = SQLiteEventStore(_store_path(workspace))
    store.append(_RUN_ID, "contract_opened", {"workspace": "workspace"}, actor="test")
    for state in _RAMP:
        store.append(_RUN_ID, "iteration_appended",
                     {"iteration_id": 0, "outcome": "replanned", "state": state}, actor="test")
    # The ramp is written straight to the store, so state.json still says intake.
    # Doctor reconciles the two, so the fixture must land where the ramp landed.
    state_path = workspace / ".loop" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["state"] = _RAMP[-1]
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return workspace


def _rebuild_unbound(workspace):
    """Replay the stream into a fresh store with nothing bound.

    The append-only triggers make retroactive unbinding impossible, so the only
    way a pre-binding contract can exist is the way it was originally written:
    every event re-appended verbatim except its artifact_hashes.
    """
    events = SQLiteEventStore(_store_path(workspace)).read(_RUN_ID)
    for suffix in ("", "-wal", "-shm"):
        _store_path(workspace).with_name("events.db" + suffix).unlink(missing_ok=True)
    store = SQLiteEventStore(_store_path(workspace))
    for event in events:
        store.append(_RUN_ID, event["type"], event["payload"], actor=event["actor"],
                     event_id=event["event_id"], causation_id=event["causation_id"],
                     correlation_id=event["correlation_id"], ts=event["ts"],
                     artifact_hashes=None)


@pytest.fixture
def scaffolded_workspace(tmp_path):
    target = tmp_path / "scaffolded"
    scaffold(target)
    return target


@pytest.fixture
def ready_workspace(tmp_path):
    return _ready(tmp_path)


@pytest.fixture
def legacy_workspace(tmp_path):
    workspace = _ready(tmp_path)
    dispatch_once(workspace)
    _rebuild_unbound(workspace)
    return workspace


@pytest.fixture
def corrupt_store_workspace(tmp_path):
    target = tmp_path / "corrupt"
    scaffold(target)
    _store_path(target).write_text("not sqlite", encoding="utf-8")
    return target


def test_absent_store_adds_no_binding_issue(scaffolded_workspace):
    assert doctor_report(scaffolded_workspace)["event_store"] == {"present": False}


@pytest.mark.parametrize("mode", _MODES)
def test_a_clean_runner_dispatch_is_doctor_clean(ready_workspace, mode):
    dispatch_once(ready_workspace)
    report = doctor_report(ready_workspace, mode=mode)
    assert report["ok"] is True and report["issues"] == []


def test_rewriting_a_bound_bundle_is_reported(ready_workspace):
    dispatch_once(ready_workspace)
    (ready_workspace / ".loop" / "artifacts" / "verify-iter1.json").write_text(
        json.dumps({"outcome": "PASS", "passed": True}), encoding="utf-8")
    assert "evidence_chain_mismatch" in _codes(doctor_report(ready_workspace))


def test_rewriting_a_bound_record_is_reported(ready_workspace):
    dispatch_once(ready_workspace)
    path = ready_workspace / ".loop" / "evidence" / "evidence-iter1.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["verified_by"]["by"] = "somebody-else"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert "evidence_chain_mismatch" in _codes(doctor_report(ready_workspace))


def test_deleting_a_bound_pair_is_reported(ready_workspace):
    dispatch_once(ready_workspace)
    (ready_workspace / ".loop" / "artifacts" / "verify-iter1.json").unlink()
    (ready_workspace / ".loop" / "evidence" / "evidence-iter1.json").unlink()
    assert "missing_bound_evidence" in _codes(doctor_report(ready_workspace))


def test_the_object_survives_and_is_named_as_the_recovery_source(ready_workspace):
    dispatch_once(ready_workspace)
    (ready_workspace / ".loop" / "artifacts" / "verify-iter1.json").write_text("{}", encoding="utf-8")
    messages = " ".join(issue["message"] for issue in doctor_report(ready_workspace)["issues"])
    assert "objects/" in messages
    assert any(p.startswith(".loop/artifacts/objects/")
               for p in _tree(ready_workspace))


@pytest.mark.parametrize("mode", _MODES)
def test_a_legacy_event_without_artifact_hashes_is_not_a_finding(legacy_workspace, mode):
    report = doctor_report(legacy_workspace, mode=mode)
    assert "missing_bound_evidence" not in _codes(report)
    assert "evidence_chain_mismatch" not in _codes(report)


def test_binding_check_writes_nothing(ready_workspace):
    dispatch_once(ready_workspace)
    before = _tree(ready_workspace)
    doctor_report(ready_workspace)
    assert _tree(ready_workspace) == before


def test_binding_issues_never_add_a_doctor_key(ready_workspace):
    dispatch_once(ready_workspace)
    (ready_workspace / ".loop" / "artifacts" / "verify-iter1.json").unlink()
    report = doctor_report(ready_workspace)
    assert set(report["event_store"]) == {
        "present", "readable", "run_id", "event_count", "state_json_agrees",
        "deterministic", "legal_sequence", "chain"}


def test_a_store_that_cannot_be_read_still_reports_its_own_error_code(corrupt_store_workspace):
    report = doctor_report(corrupt_store_workspace)
    assert report["event_store"]["readable"] is False
    assert "missing_bound_evidence" not in _codes(report)
