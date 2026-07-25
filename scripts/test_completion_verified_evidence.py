"""all_required_verified_evidence: the same bar at four layers, each as strong as it can be.

Hash-verification ALONE is a forgeable bar: a worker with `.loop/` write access can
hand-write a bundle, its digest, a matching record and a correct policy_digest with
zero dispatch and zero events.  The two layers that hold a workspace therefore also
require chain-boundness and live-goalpost agreement (plan decision 14); the two pure
layers keep only the structural half, because pretending otherwise is the failure
this mode exists to close.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from loop import emit, integrations
from loop.completion import (VERIFIED_EVIDENCE_MODE, evidence_entry_is_record_shaped,
                             normalize_completion_policy, policy_requires_verified_evidence)
from loop.contract import doctor_report
from loop.events import SQLiteEventStore
from loop.reducer import EventReplayError, reduce_events
from loop.runner import dispatch_once
from loop.verifier import verification_policy_digest

try:                                  # the repo's fallback-mode convention
    import jsonschema                 # noqa: F401
    _HAS_JSONSCHEMA = True
except ImportError:                   # pragma: no cover - exercised in the fallback leg
    _HAS_JSONSCHEMA = False

_MODES = [pytest.param("basic"),
          pytest.param("strict", marks=pytest.mark.skipif(not _HAS_JSONSCHEMA,
                                                          reason="jsonschema not installed"))]


def _codes(report):
    return {issue["code"] for issue in report["issues"]}


_VERIFY = "./scripts/verify-fast.sh"
_RAMP = ("plan", "critique-plan", "queue-tasks", "execute-task")


def _task(task_id, deps=(), status="pending", **extra):
    return {"id": task_id, "title": task_id, "status": status, "criterion_ref": task_id,
            "verify": _VERIFY, "depends_on": list(deps), "attempts": 0, "evidence": None, **extra}


def _ready(tmp_path, tasks):
    """A contract projected to execute-task with the iteration counter still at 0.

    Same shape as scripts/test_evidence_binding_runner.py: the ramp records the FSM
    walk, not work, so the first dispatch is iteration 1 and every artifact path
    asserted below is literal.
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
def dispatched_workspace(tmp_path):
    """One real dispatch: `.loop/evidence/evidence-iter1.json` exists and IS chain-bound."""
    workspace = _ready(tmp_path, [_task("T-1")])
    dispatch_once(workspace)
    return workspace


@pytest.fixture
def predone_workspace(tmp_path):
    """Every task already declaratively done, so the auto-terminal fires with zero records."""
    return _ready(tmp_path, [_task("T-1", status="done", evidence="RUNLOG.md")])


def test_the_new_mode_is_supported_and_normalizes():
    assert normalize_completion_policy(VERIFIED_EVIDENCE_MODE) == {"mode": VERIFIED_EVIDENCE_MODE}
    assert policy_requires_verified_evidence({"mode": VERIFIED_EVIDENCE_MODE}) is True


def test_legacy_null_policy_still_normalizes_to_all_required():
    assert normalize_completion_policy(None) == {"mode": "all_required"}
    assert policy_requires_verified_evidence(None) is False


def test_terminate_refuses_unverified_evidence_under_the_new_mode(dispatched_workspace):
    with pytest.raises(emit.EmitError, match="verified evidence"):
        emit.terminate(dispatched_workspace, state="Succeeded", criteria_met={"C-1": True},
                       evidence=["RUNLOG.md"], completion_policy=VERIFIED_EVIDENCE_MODE)


def test_terminate_accepts_hash_verified_evidence_under_the_new_mode(dispatched_workspace):
    path = emit.terminate(dispatched_workspace, state="Succeeded", criteria_met={"C-1": True},
                          evidence=[".loop/evidence/evidence-iter1.json"],
                          completion_policy=VERIFIED_EVIDENCE_MODE)
    assert json.loads(path.read_text(encoding="utf-8"))["completion_policy"] == {
        "mode": VERIFIED_EVIDENCE_MODE}


def test_terminate_under_the_default_mode_is_unchanged(dispatched_workspace):
    path = emit.terminate(dispatched_workspace, state="Succeeded", criteria_met={"C-1": True},
                          evidence=["RUNLOG.md"])
    assert json.loads(path.read_text(encoding="utf-8"))["completion_policy"] == {
        "mode": "all_required"}


@pytest.mark.parametrize("mode", _MODES)
def test_doctor_reports_unverified_evidence_terminal(dispatched_workspace, mode):
    emit.terminate(dispatched_workspace, state="Succeeded", criteria_met={"C-1": True},
                   evidence=[".loop/evidence/evidence-iter1.json"],
                   completion_policy=VERIFIED_EVIDENCE_MODE)
    (dispatched_workspace / ".loop" / "artifacts" / "verify-iter1.json").write_text(
        "{}", encoding="utf-8")
    assert "unverified_evidence_terminal" in _codes(doctor_report(dispatched_workspace, mode=mode))


# --- decision 14: hash-verified is NOT enough when the layer can reach further ---

def _handwritten_record(workspace, *, name="evidence-iter9.json", task_id="T-1"):
    """A self-consistent, never-dispatched record: real bundle, real digest, real policy."""
    bundle = workspace / ".loop" / "artifacts" / "verify-iter9.json"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    text = '{"outcome": "PASS", "passed": true}'
    bundle.write_text(text, encoding="utf-8")
    tasks = json.loads((workspace / "TASKS.json").read_text(encoding="utf-8"))
    entry = next(t for t in tasks["tasks"] if t["id"] == task_id)
    record = {
        "schema": "loop-engineer/evidence@1", "id": "hand:9:verify", "kind": "verify-bundle",
        "uri": ".loop/artifacts/verify-iter9.json",
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "media_type": "application/json", "created_at": "2026-07-25T00:00:00+00:00",
        "produced_by": {"run_id": "run-1", "task_id": task_id, "attempt": 1,
                        "executor": "worker-a"},
        "verified_by": {"by": "ci", "at": "2026-07-25T00:00:00+00:00",
                        "command": entry["verify"], "code_digest": None,
                        "code_digest_basis": "path_lookup",
                        "policy_digest": verification_policy_digest(entry)},
    }
    path = workspace / ".loop" / "evidence" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return f".loop/evidence/{name}"


def test_terminate_refuses_a_hash_verified_but_unbound_record_when_a_store_exists(
        dispatched_workspace):
    """The BLOCKER case: self-consistency is not dispatch. No event bound this record."""
    entry = _handwritten_record(dispatched_workspace)
    with pytest.raises(emit.EmitError, match="not bound"):
        emit.terminate(dispatched_workspace, state="Succeeded", criteria_met={"C-1": True},
                       evidence=[entry], completion_policy=VERIFIED_EVIDENCE_MODE)


def test_terminate_refuses_a_cited_record_whose_goalpost_moved_or_cannot_be_computed(
        dispatched_workspace):
    """Per-cited-record, deliberately stricter than doctor's latest-per-task rule.

    Both halves live in one test because the acceptance count is fixed at 17: a moved
    goalpost and an UNCOMPUTABLE one are the same refusal, since a comparison that
    cannot run has not passed (R007 — an errored check fails, it never skips).
    """
    tasks_path = dispatched_workspace / "TASKS.json"
    data = json.loads(tasks_path.read_text(encoding="utf-8"))
    data["tasks"][0]["verify"] = "true"
    tasks_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(emit.EmitError, match="goalpost"):
        emit.terminate(dispatched_workspace, state="Succeeded", criteria_met={"C-1": True},
                       evidence=[".loop/evidence/evidence-iter1.json"],
                       completion_policy=VERIFIED_EVIDENCE_MODE)

    data["tasks"][0]["criterion_ref"] = float("nan")   # json.loads accepts it; canonical JSON does not
    tasks_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(emit.EmitError, match="goalpost"):
        emit.terminate(dispatched_workspace, state="Succeeded", criteria_met={"C-1": True},
                       evidence=[".loop/evidence/evidence-iter1.json"],
                       completion_policy=VERIFIED_EVIDENCE_MODE)


def test_doctor_reports_an_unbound_record_cited_by_a_strict_terminal(dispatched_workspace):
    """Read-time twin of the write-time refusal — same predicate, one definition.

    The terminal file is hand-written, not emitted: emit.terminate REFUSES this exact
    record (the test above), so the only way a strict terminal citing an unbound record
    reaches disk is a worker writing it directly — which is the adversary being modelled.
    """
    entry = _handwritten_record(dispatched_workspace)
    (dispatched_workspace / ".loop" / "terminal_state.json").write_text(json.dumps({
        "schema": "loop-engineer/terminal@1", "project": dispatched_workspace.name,
        "state": "Succeeded", "criteria_met": {"C-1": True},
        "completion_policy": {"mode": VERIFIED_EVIDENCE_MODE}, "evidence": [entry],
        "false_completion": False, "terminated_at": "2026-07-25T00:00:00+00:00",
        "reason": "hand-written"}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert "unverified_evidence_terminal" in _codes(doctor_report(dispatched_workspace))


def test_the_write_layers_reject_an_entry_the_pure_layers_would_reject(tmp_path):
    """The workspace-bearing bar must be a SUPERSET of the pure one.

    A store-less contract skips chain-boundness by design, so without an entry-shape
    check a Succeeded terminal could cite a record living outside the workspace: written
    happily by ``emit.terminate``, then refused by the reducer replaying that same
    terminal. Layers that disagree about what Succeeded means are the defect.
    """
    workspace = tmp_path / "storeless"
    emit.open_contract(workspace)
    outside = tmp_path / "elsewhere" / "rec.json"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("{}", encoding="utf-8")
    entry = "../elsewhere/rec.json"
    assert evidence_entry_is_record_shaped(entry) is False
    with pytest.raises(emit.EmitError, match="record path"):
        emit.terminate(workspace, state="Succeeded", criteria_met={"C-1": True},
                       evidence=[entry], completion_policy=VERIFIED_EVIDENCE_MODE)


def _corrupt_store(workspace):
    """Make the event store genuinely unreadable, at the bytes.

    Not a chmod: this suite runs as root in CI, where mode bits are advisory and the
    'unreadable' store would still open.  Overwriting the header (and dropping the WAL
    sidecars sqlite would otherwise recover from) is unreadable for everyone.
    """
    loop_dir = workspace / ".loop"
    for sidecar in ("events.db-wal", "events.db-shm"):
        (loop_dir / sidecar).unlink(missing_ok=True)
    (loop_dir / "events.db").write_bytes(b"this is not a sqlite database" * 64)


def test_terminate_refuses_the_new_mode_when_the_event_store_cannot_be_read(dispatched_workspace):
    """Fail-closed, not fail-open: a chain nobody can read binds nothing (R007)."""
    _corrupt_store(dispatched_workspace)
    with pytest.raises(emit.EmitError, match="event store could not be read"):
        emit.terminate(dispatched_workspace, state="Succeeded", criteria_met={"C-1": True},
                       evidence=[".loop/evidence/evidence-iter1.json"],
                       completion_policy=VERIFIED_EVIDENCE_MODE)


def test_doctor_reports_a_strict_terminal_whose_event_store_cannot_be_read(dispatched_workspace):
    """The read-time twin degrades to a FINDING rather than an exception: doctor's job is
    to report every issue it can see, so an unreadable store must not abort the sweep."""
    emit.terminate(dispatched_workspace, state="Succeeded", criteria_met={"C-1": True},
                   evidence=[".loop/evidence/evidence-iter1.json"],
                   completion_policy=VERIFIED_EVIDENCE_MODE)
    _corrupt_store(dispatched_workspace)
    report = doctor_report(dispatched_workspace)      # must not raise
    assert "unverified_evidence_terminal" in _codes(report)
    # Pinned to the store-read branch: the cited record itself is still perfectly valid,
    # so any OTHER path to this code would mean the finding is right for the wrong reason.
    assert any("event store could not be read" in issue["message"]
               for issue in report["issues"]
               if issue["code"] == "unverified_evidence_terminal")


def _terminal_event(evidence, mode):
    return [{"schema": "loop-engineer/event@1", "run_id": "r", "sequence": 0, "event_id": "e0",
             "type": "contract_opened", "actor": "op", "ts": "2026-07-25T00:00:00+00:00",
             "causation_id": None, "correlation_id": None, "payload": {"workspace": "ws"},
             "artifact_hashes": []},
            {"schema": "loop-engineer/event@1", "run_id": "r", "sequence": 1, "event_id": "e1",
             "type": "terminal_written", "actor": "op", "ts": "2026-07-25T00:00:01+00:00",
             "causation_id": None, "correlation_id": None, "artifact_hashes": [],
             "payload": {"state": "Succeeded", "criteria_met": {"C-1": True},
                         "evidence": evidence, "false_completion": False,
                         "completion_policy": {"mode": mode}}}]


def test_the_reducer_refuses_a_non_record_evidence_entry_under_the_new_mode():
    with pytest.raises(EventReplayError, match="verified evidence"):
        reduce_events(_terminal_event(["RUNLOG.md"], VERIFIED_EVIDENCE_MODE))


def test_the_reducer_accepts_record_shaped_evidence_under_the_new_mode():
    projection = reduce_events(
        _terminal_event([".loop/evidence/evidence-iter1.json"], VERIFIED_EVIDENCE_MODE))
    assert projection["terminal"]["state"] == "Succeeded"


def test_integrations_projection_refuses_non_record_evidence_under_the_new_mode():
    outcome = integrations.EngineOutcome(reached_end=True, artifacts=("RUNLOG.md",))
    body = integrations.to_terminal_state(
        outcome, {"verdict": "Succeeded", "passed_visible": True, "passed_holdout": True,
                  "false_completion": False,
                  "visible": [{"id": "C-1", "passed": True}],
                  "holdout": [{"id": "H-1", "passed": True}]},
        # A clean anticheat result needs `downgrade_to` present, or the projection fails
        # closed on the anticheat input and never reaches the evidence bar under test.
        {"findings": [], "clean": True, "downgrade_to": None}, {"C-1": True},
        completion_policy=VERIFIED_EVIDENCE_MODE)
    assert body["state"] == "FailedUnverifiable" and "verified evidence" in body["reason"]


def test_runner_auto_terminal_adopts_the_verified_mode_only_when_the_records_pass_the_bar(
        tmp_path, ready_workspace):
    """Existence is not satisfaction, and the check runs BEFORE the event is appended.

    Both halves live in one test because the acceptance count is fixed: they are the two
    sides of a single decision — the runner evaluates the shared predicate against every
    candidate record, then chooses the mode.  Evaluating it afterwards (what `emit`
    already did) would leave `terminal_written` durable and then raise, which is exactly
    the committed-then-refused seam this slice removes.
    """
    dispatch_once(ready_workspace)
    dispatch_once(ready_workspace)
    terminal = json.loads((ready_workspace / ".loop" / "terminal_state.json")
                          .read_text(encoding="utf-8"))
    assert terminal["completion_policy"] == {"mode": VERIFIED_EVIDENCE_MODE}
    assert terminal["evidence"] == [".loop/evidence/evidence-iter1.json"]

    moved = _ready(tmp_path / "moved", [_task("T-1")])
    dispatch_once(moved)
    tasks_path = moved / "TASKS.json"                  # move the goalpost the record cites
    data = json.loads(tasks_path.read_text(encoding="utf-8"))
    data["tasks"][0]["verify"] = "true"
    tasks_path.write_text(json.dumps(data), encoding="utf-8")
    result = dispatch_once(moved)                      # must not raise, and must not lie
    assert result["action"] == "terminal_written"
    written = json.loads((moved / ".loop" / "terminal_state.json").read_text(encoding="utf-8"))
    assert written["completion_policy"] == {"mode": "all_required"}
    assert written["evidence"] == ["RUNLOG.md"]
    assert ".loop/evidence/evidence-iter1.json" in written["reason"]
    assert "goalpost" in written["reason"]
    # The durable event says the same thing the file does: one decision, taken once.
    event = SQLiteEventStore(moved / ".loop" / "events.db").read("run-1")[-1]
    assert event["type"] == "terminal_written"
    assert event["payload"]["completion_policy"] == {"mode": "all_required"}
    assert event["payload"]["reason"] == written["reason"]


def test_runner_auto_terminal_keeps_all_required_when_a_task_has_no_record(predone_workspace):
    dispatch_once(predone_workspace)
    terminal = json.loads((predone_workspace / ".loop" / "terminal_state.json")
                          .read_text(encoding="utf-8"))
    assert terminal["completion_policy"] == {"mode": "all_required"}
    assert terminal["evidence"] == ["RUNLOG.md"]
    assert "no evidence record" in terminal["reason"]


@pytest.mark.parametrize("mode", _MODES)
def test_terminal_schema_accepts_both_modes(ready_workspace, mode):
    """terminal@1 admits the new mode in BOTH validation modes, end to end.

    Driven through the runner's own auto-terminal rather than a bare emit.terminate:
    a hand-terminated dispatched workspace is doctor-dirty for unrelated reasons (a
    terminal file with no terminal_written event is a desynced terminal window), so
    `ok is True` there would prove nothing about the schema.
    """
    dispatch_once(ready_workspace)
    dispatch_once(ready_workspace)
    report = doctor_report(ready_workspace, mode=mode)
    assert report["ok"] is True, report["issues"]
