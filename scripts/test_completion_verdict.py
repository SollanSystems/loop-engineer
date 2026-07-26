"""The strict mode must cite evidence of PASSING, not merely authentic evidence.

Every other sub-check of ``all_required_verified_evidence`` asks whether the record is
real: it validates, its pointer resolves and hashes, some event bound those bytes, its
goalpost is live.  None of them asked what the verdict SAYS — so a dispatch whose
verifier FAILED produced a perfectly authentic, chain-bound record that backed
``Succeeded`` end to end: ``emit.terminate`` accepted it, ``loop doctor`` reported
``ok: true`` with zero issues, and the reducer replayed ``Succeeded``.

The verdict is judged by the repo's ONE green-marker rule
(``loop.evidence.verify_bundle_is_green``), which ``scripts/metrics.py`` now imports
rather than restating: a bundle is green when ``outcome == "PASS"`` or
``passed is True``, and a ``score``-only bundle reads RED.  A bundle that reads RED to
the metrics gate can therefore never read GREEN to the completion gate.
"""
from __future__ import annotations

import hashlib
import json

import metrics
import pytest

from loop import emit, evidence
from loop.completion import VERIFIED_EVIDENCE_MODE
from loop.contract import doctor_report
from loop.events import SQLiteEventStore
from loop.reducer import reduce_events
from loop.runner import dispatch_once

_VERIFY = "./scripts/verify-fast.sh"
_RAMP = ("plan", "critique-plan", "queue-tasks", "execute-task")
_RECORD = ".loop/evidence/evidence-iter1.json"


def _codes(report):
    return {issue["code"] for issue in report["issues"]}


def _task(task_id="T-1"):
    return {"id": task_id, "title": task_id, "status": "pending", "criterion_ref": task_id,
            "verify": _VERIFY, "depends_on": [], "attempts": 0, "evidence": None}


def _dispatched(tmp_path, name, *, exit_code):
    """One real dispatch whose verifier exits with ``exit_code``.

    A failing dispatch still writes and BINDS its evidence — that is the point: the
    record is genuine provenance for a verification that did not pass.
    """
    workspace = tmp_path / name
    emit.open_contract(workspace)
    (workspace / "TASKS.json").write_text(
        json.dumps({"schema": "loop-engineer/tasks@1", "tasks": [_task()]}), encoding="utf-8")
    script = workspace / "scripts" / "verify-fast.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(f"#!/bin/sh\nexit {exit_code}\n", encoding="utf-8")
    script.chmod(0o755)
    store = SQLiteEventStore(workspace / ".loop" / "events.db")
    store.append("run-1", "contract_opened", {"workspace": name}, actor="test")
    for state in _RAMP:
        store.append("run-1", "iteration_appended",
                     {"iteration_id": 0, "outcome": "replanned", "state": state}, actor="test")
    dispatch_once(workspace)
    return workspace


def _rewrite_bundle(workspace, text):
    """Replace the bundle bytes AND the record digest, so only the verdict is wrong.

    Without re-declaring the digest the record would fail hash verification and the
    refusal would be right for the wrong reason.
    """
    bundle = workspace / ".loop" / "artifacts" / "verify-iter1.json"
    bundle.write_text(text, encoding="utf-8")
    record_path = workspace / ".loop" / "evidence" / "evidence-iter1.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record_path


def _rebind(workspace, record_path):
    """Re-bind the rewritten record at its new digest, alone, so the ambiguous-binding
    refusal (the OTHER new check) cannot be what fires."""
    events = SQLiteEventStore(workspace / ".loop" / "events.db").read("run-1")
    for suffix in ("", "-wal", "-shm"):
        (workspace / ".loop" / ("events.db" + suffix)).unlink(missing_ok=True)
    store = SQLiteEventStore(workspace / ".loop" / "events.db")
    digest = hashlib.sha256(record_path.read_bytes()).hexdigest()
    bundle = workspace / ".loop" / "artifacts" / "verify-iter1.json"
    bundle_digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    for event in events:
        hashes = event["artifact_hashes"]
        if hashes:
            hashes = [{"path": _RECORD, "sha256": digest},
                      {"path": ".loop/artifacts/verify-iter1.json", "sha256": bundle_digest}]
        store.append("run-1", event["type"], event["payload"], actor=event["actor"],
                     event_id=event["event_id"], causation_id=event["causation_id"],
                     correlation_id=event["correlation_id"], ts=event["ts"],
                     artifact_hashes=hashes or None)


def _terminal_file(workspace, entry):
    """A hand-written strict terminal — the only way one citing a red verdict reaches
    disk now that ``emit.terminate`` refuses to write it."""
    (workspace / ".loop" / "terminal_state.json").write_text(json.dumps({
        "schema": "loop-engineer/terminal@1", "project": workspace.name, "state": "Succeeded",
        "criteria_met": {"T-1": True}, "completion_policy": {"mode": VERIFIED_EVIDENCE_MODE},
        "evidence": [entry], "false_completion": False,
        "terminated_at": "2026-07-25T00:00:00+00:00", "reason": "hand-written"},
        indent=2, sort_keys=True) + "\n", encoding="utf-8")


# --- the reproduction ---------------------------------------------------------


def test_a_failing_verdict_cannot_back_succeeded_at_write_time(tmp_path):
    workspace = _dispatched(tmp_path, "failing", exit_code=1)
    bundle = json.loads((workspace / ".loop" / "artifacts" / "verify-iter1.json")
                        .read_text(encoding="utf-8"))
    assert bundle["outcome"] == "FAIL" and bundle["passed"] is False   # genuine red
    with pytest.raises(emit.EmitError, match="verdict is not a pass"):
        emit.terminate(workspace, state="Succeeded", criteria_met={"T-1": True},
                       evidence=[_RECORD], completion_policy=VERIFIED_EVIDENCE_MODE)


def test_doctor_reports_a_strict_terminal_backed_by_a_failing_verdict(tmp_path):
    workspace = _dispatched(tmp_path, "failing", exit_code=1)
    _terminal_file(workspace, _RECORD)
    report = doctor_report(workspace)
    assert "unverified_evidence_terminal" in _codes(report)
    assert any("verdict is not a pass" in issue["message"] for issue in report["issues"])


def test_a_passing_dispatch_is_still_accepted(tmp_path):
    """Positive control: the check narrows nothing that was honestly green."""
    workspace = _dispatched(tmp_path, "passing", exit_code=0)
    path = emit.terminate(workspace, state="Succeeded", criteria_met={"T-1": True},
                          evidence=[_RECORD], completion_policy=VERIFIED_EVIDENCE_MODE)
    assert json.loads(path.read_text(encoding="utf-8"))["completion_policy"] == {
        "mode": VERIFIED_EVIDENCE_MODE}


# --- the green-marker rule, one definition ------------------------------------


def test_metrics_and_the_completion_bar_share_one_green_marker_definition():
    assert metrics.verify_bundle_is_green is evidence.verify_bundle_is_green


@pytest.mark.parametrize("bundle,expected", [
    ({"outcome": "PASS"}, True),
    ({"passed": True}, True),
    ({"outcome": "pass"}, True),
    ({"outcome": "FAIL", "passed": False}, False),
    ({"score": 1.0}, False),                      # a score is not a verdict
    ({"passed": 1}, False),                       # truthy is not True
    ({}, False),
])
def test_the_green_marker_rule(bundle, expected):
    assert evidence.verify_bundle_is_green(bundle) is expected


def test_a_score_only_bundle_reads_red_at_the_strict_bar(tmp_path):
    """The durable repo lesson, now load-bearing in two places at once: a bundle with a
    perfect score and no verdict token is RED to metrics, and must be RED here too."""
    workspace = _dispatched(tmp_path, "scored", exit_code=0)
    record_path = _rewrite_bundle(workspace, json.dumps({"score": 1.0}) + "\n")
    _rebind(workspace, record_path)
    with pytest.raises(emit.EmitError, match="verdict is not a pass"):
        emit.terminate(workspace, state="Succeeded", criteria_met={"T-1": True},
                       evidence=[_RECORD], completion_policy=VERIFIED_EVIDENCE_MODE)


def test_a_self_contradicting_verdict_reads_green_pinned(tmp_path):
    """The OR rule's cost, pinned rather than discovered later.

    ``verify_bundle_is_green`` is satisfied by EITHER token, so a bundle claiming
    ``outcome: PASS`` while ``passed`` is false reads green and can back a strict
    ``Succeeded``. That is the repo's canonical rule, shared object-for-object with
    the FCR gate, so tightening it here alone would make one bundle green to the
    completion bar and red to metrics — a worse defect than the one it fixes.
    Changing it is a repo-wide decision about what a verdict means, not a patch.
    """
    workspace = _dispatched(tmp_path, "contradicting", exit_code=0)
    record_path = _rewrite_bundle(
        workspace, json.dumps({"outcome": "PASS", "passed": False}) + "\n")
    _rebind(workspace, record_path)
    path = emit.terminate(workspace, state="Succeeded", criteria_met={"T-1": True},
                          evidence=[_RECORD], completion_policy=VERIFIED_EVIDENCE_MODE)
    assert json.loads(path.read_text(encoding="utf-8"))["completion_policy"] == {
        "mode": VERIFIED_EVIDENCE_MODE}                                    # accepted
    assert evidence.verify_bundle_is_green({"outcome": "PASS", "passed": False}) is True


# --- the non-verify-bundle kind, decided explicitly ---------------------------


def test_a_record_of_another_kind_cannot_back_succeeded(tmp_path):
    """evidence@1's ``kind`` is an open vocabulary (log, diff, screenshot, report).

    A non-``verify-bundle`` record carries no verdict this layer can read, so it is
    REFUSED rather than waved through: the strict mode's claim is that completion is
    backed by a verification that passed, and an artifact with no verdict cannot make
    that claim.
    """
    workspace = _dispatched(tmp_path, "logkind", exit_code=0)
    record_path = workspace / ".loop" / "evidence" / "evidence-iter1.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["kind"] = "log"
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _rebind(workspace, record_path)
    with pytest.raises(emit.EmitError, match="carries no verdict"):
        emit.terminate(workspace, state="Succeeded", criteria_met={"T-1": True},
                       evidence=[_RECORD], completion_policy=VERIFIED_EVIDENCE_MODE)


def test_an_unparseable_verdict_is_a_refusal_not_a_skip(tmp_path):
    workspace = _dispatched(tmp_path, "garbage", exit_code=0)
    record_path = _rewrite_bundle(workspace, "not json at all\n")
    _rebind(workspace, record_path)
    with pytest.raises(emit.EmitError, match="not UTF-8 JSON"):
        emit.terminate(workspace, state="Succeeded", criteria_met={"T-1": True},
                       evidence=[_RECORD], completion_policy=VERIFIED_EVIDENCE_MODE)


def test_a_non_object_verdict_is_a_refusal(tmp_path):
    workspace = _dispatched(tmp_path, "listy", exit_code=0)
    record_path = _rewrite_bundle(workspace, "[]\n")
    _rebind(workspace, record_path)
    with pytest.raises(emit.EmitError, match="not a JSON object"):
        emit.terminate(workspace, state="Succeeded", criteria_met={"T-1": True},
                       evidence=[_RECORD], completion_policy=VERIFIED_EVIDENCE_MODE)


# --- the pure layers are unchanged, deliberately ------------------------------


def test_the_reducer_still_admits_a_record_shaped_entry_without_reading_it():
    """Decision 14 stands: the reducer holds no filesystem, so it checks SHAPE only.

    Pinned so the verdict check is not later mistaken for something the pure fold
    enforces — a fold that pretended to read a verdict would be the overclaim this
    slice exists to prevent.
    """
    projection = reduce_events([
        {"schema": "loop-engineer/event@1", "run_id": "r", "sequence": 0, "event_id": "e0",
         "type": "contract_opened", "actor": "op", "ts": "2026-07-25T00:00:00+00:00",
         "causation_id": None, "correlation_id": None, "artifact_hashes": [],
         "payload": {"workspace": "ws"}},
        {"schema": "loop-engineer/event@1", "run_id": "r", "sequence": 1, "event_id": "e1",
         "type": "terminal_written", "actor": "op", "ts": "2026-07-25T00:00:01+00:00",
         "causation_id": None, "correlation_id": None, "artifact_hashes": [],
         "payload": {"state": "Succeeded", "criteria_met": {"T-1": True}, "evidence": [_RECORD],
                     "false_completion": False,
                     "completion_policy": {"mode": VERIFIED_EVIDENCE_MODE}}}])
    assert projection["terminal"]["state"] == "Succeeded"
