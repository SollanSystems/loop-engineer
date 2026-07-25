"""What chain-bound evidence catches, and what it provably does not.

The claim this file defends is "evidence whose bytes are bound into an ANCHORABLE
chain", never "tamper-proof evidence". Binding inherits Slice 1's trust model
exactly: a worker who can rewrite .loop/ can rewrite the store (repo-os-contract
#16, Integrity boundary), so without an external anchor a full rewrite verifies.

Every ``*_pinned`` test states an honest limitation and carries the positive control
that bounds it: a pin whose detector was never shown to fire certifies a hole as
closed. The rest prove a real detection.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metrics import compute_metrics                                       # noqa: E402

from chain_fixtures import drop_triggers, restore_triggers                # noqa: E402
from loop import emit                                                     # noqa: E402
from loop.chain import compute_event_hash                                 # noqa: E402
from loop.completion import VERIFIED_EVIDENCE_MODE                        # noqa: E402
from loop.contract import doctor_report                                   # noqa: E402
from loop.events import SQLiteEventStore                                  # noqa: E402
from loop.evidence import artifact_object_path                            # noqa: E402
from loop.runner import dispatch_once                                     # noqa: E402
from loop.runtime import bound_artifact_digests                           # noqa: E402
from loop.verifier import (executed_verifier_identity,                    # noqa: E402
                           verification_policy_digest, verifier_code_digest)

_EVENT_SCHEMA_ID = "loop-engineer/event@1"
_VERIFY = "./scripts/verify-fast.sh"
_RAMP = ("plan", "critique-plan", "queue-tasks", "execute-task")
_RUN_ID = "run-1"
_FORGED = '{"outcome": "PASS", "passed": true, "forged": true}\n'


def _codes(report):
    return {issue["code"] for issue in report["issues"]}


def _task(task_id="T-1", **overrides):
    base = {"id": task_id, "title": task_id, "status": "pending", "criterion_ref": task_id,
            "verify": _VERIFY, "depends_on": [], "attempts": 0, "evidence": None}
    base.update(overrides)
    return base


def _write_tasks(workspace, tasks):
    (workspace / "TASKS.json").write_text(
        json.dumps({"schema": "loop-engineer/tasks@1", "tasks": list(tasks)}), encoding="utf-8")


def _contract(tmp_path, name="workspace", tasks=(), *, store=True):
    """A contract, optionally with an event store ramped to execute-task.

    The ramp records the FSM walk, not work: its events carry iteration_id 0, so the
    first dispatch is iteration 1 and every artifact path asserted below is literal.
    Without a store the contract is the supported writer-API path — the one decision
    14 names as unable to chain-bind anything.
    """
    workspace = tmp_path / name
    emit.open_contract(workspace)
    if tasks:
        _write_tasks(workspace, tasks)
    script = workspace / "scripts" / "verify-fast.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    if store:
        events = SQLiteEventStore(_store_path(workspace))
        events.append(_RUN_ID, "contract_opened", {"workspace": name}, actor="test")
        for state in _RAMP:
            events.append(_RUN_ID, "iteration_appended",
                          {"iteration_id": 0, "outcome": "replanned", "state": state}, actor="test")
        # The ramp is written straight to the store, so state.json still says intake.
        # Doctor reconciles the two, so the fixture must land where the ramp landed.
        state_path = workspace / ".loop" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["state"] = _RAMP[-1]
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return workspace


def _dispatched(tmp_path, name="workspace"):
    workspace = _contract(tmp_path, name, [_task()])
    dispatch_once(workspace)
    return workspace


def _store_path(workspace):
    return workspace / ".loop" / "events.db"


def _bundle(workspace):
    return workspace / ".loop" / "artifacts" / "verify-iter1.json"


def _record(workspace):
    return workspace / ".loop" / "evidence" / "evidence-iter1.json"


def _head(workspace):
    return doctor_report(workspace)["event_store"]["chain"]["head"]["event_hash"]


def _record_at(conn, sequence, prev_event_hash):
    """Rebuild one row into the record dict read_event_rows projects (hash preimage shape)."""
    row = conn.execute(
        "SELECT run_id, sequence, event_id, type, actor, causation_id, correlation_id, ts, "
        "payload, artifact_hashes FROM events WHERE sequence = ?", (sequence,)).fetchone()
    return {"schema": _EVENT_SCHEMA_ID, "run_id": row[0], "sequence": row[1], "event_id": row[2],
            "type": row[3], "actor": row[4], "causation_id": row[5], "correlation_id": row[6],
            "ts": row[7], "payload": json.loads(row[8]), "artifact_hashes": json.loads(row[9]),
            "prev_event_hash": prev_event_hash}


def _rechain(workspace, artifact_hashes):
    """Replace the bound digests on the one binding event and re-chain from genesis."""
    store_path = _store_path(workspace)
    drop_triggers(store_path)
    conn = sqlite3.connect(str(store_path))
    try:
        conn.execute("UPDATE events SET artifact_hashes = ? WHERE artifact_hashes != '[]'",
                     (json.dumps(artifact_hashes),))
        prev = None
        for (sequence,) in conn.execute(
                "SELECT sequence FROM events ORDER BY sequence ASC").fetchall():
            digest = compute_event_hash(_record_at(conn, sequence, prev))
            conn.execute("UPDATE events SET prev_event_hash = ?, event_hash = ? WHERE sequence = ?",
                         (prev, digest, sequence))
            prev = digest
        conn.commit()
    finally:
        conn.close()
    restore_triggers(store_path)


def _rewrite_everything(workspace, *, text=_FORGED):
    """The competent adversary: new bundle bytes, a matching record, a matching object,
    the bound row's artifact_hashes replaced, and the chain recomputed from genesis."""
    bundle, record_path = _bundle(workspace), _record(workspace)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    artifact_object_path(workspace, record["sha256"]).unlink()   # burn the recovery copy
    bundle.write_text(text, encoding="utf-8")
    new_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    record["sha256"] = new_sha
    record_text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    record_path.write_text(record_text, encoding="utf-8")
    obj = artifact_object_path(workspace, new_sha)
    obj.parent.mkdir(parents=True, exist_ok=True)
    obj.write_text(text, encoding="utf-8")
    _rechain(workspace, [
        {"path": bundle.relative_to(workspace).as_posix(), "sha256": new_sha},
        {"path": record_path.relative_to(workspace).as_posix(),
         "sha256": hashlib.sha256(record_text.encode("utf-8")).hexdigest()},
        {"path": obj.relative_to(workspace).as_posix(), "sha256": new_sha},
    ])
    return new_sha


def _unbind(workspace):
    """Replay the stream into a fresh store with nothing bound — a pre-release run.

    The append-only triggers make retroactive UNbinding as impossible as retroactive
    binding, so the only way a pre-binding contract can exist is the way it was
    originally written: every event re-appended verbatim except its artifact_hashes.
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


def _handwritten_record(workspace, *, task_id="T-1"):
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
        "produced_by": {"run_id": _RUN_ID, "task_id": task_id, "attempt": 1,
                        "executor": "worker-a"},
        "verified_by": {"by": "ci", "at": "2026-07-25T00:00:00+00:00",
                        "command": entry["verify"], "code_digest": None,
                        "code_digest_basis": "path_lookup",
                        "policy_digest": verification_policy_digest(entry)},
    }
    path = workspace / ".loop" / "evidence" / "evidence-iter9.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ".loop/evidence/evidence-iter9.json"


def _terminal_file(workspace, *, mode, evidence):
    (workspace / ".loop" / "terminal_state.json").write_text(json.dumps({
        "schema": "loop-engineer/terminal@1", "project": workspace.name, "state": "Succeeded",
        "criteria_met": {"T-1": True}, "completion_policy": {"mode": mode},
        "evidence": list(evidence), "false_completion": False,
        "terminated_at": "2026-07-25T00:00:00+00:00", "reason": "hand-written",
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _metrics_workspace(tmp_path, source):
    """A minimal metrics-readable loop dir: one green claim backed by one green bundle."""
    target = tmp_path / "metrics-ws"
    (target / ".loop" / "artifacts").mkdir(parents=True, exist_ok=True)
    (target / "RUNLOG.md").write_text(
        "# RUNLOG\n\n## Iteration 1 — 2026-07-25\n\n### Outcome\n\n`task_passed`\n",
        encoding="utf-8")
    (target / ".loop" / "state.json").write_text(json.dumps(
        {"schema": "loop-engineer/state@1", "state": "execute-task", "iteration_id": 1,
         "terminal_state": None}), encoding="utf-8")
    (target / ".loop" / "artifacts" / "verify-iter1.json").write_text(json.dumps(
        {"iteration_id": 1, "task": "T-1", "outcome": "PASS", "passed": True, "score": 1.0,
         "verifier": {"by": "loop.run", "source": source}}), encoding="utf-8")
    return target


# --- pinned honest limitations -------------------------------------------------

def test_a_full_rewrite_of_artifacts_and_store_is_not_caught_without_an_anchor_pinned(tmp_path):
    """Binding proves the bytes AGREE, never that a dispatch happened.

    A worker who can rewrite .loop/ owns the store too: rewrite the bundle, recompute
    the record and the content-addressed object, replace the digests the event bound and
    re-chain from genesis, and every internal check agrees again. This is Slice 1's
    trust model unchanged (repo-os-contract #16) — which is why the shipped claim is
    "bound into an ANCHORABLE chain" and never "tamper-proof". The anchor that does
    catch it is the very next test.
    """
    workspace = _dispatched(tmp_path)
    assert doctor_report(workspace)["ok"] is True                          # control: clean before
    before = bound_artifact_digests(workspace)[".loop/artifacts/verify-iter1.json"]
    new_sha = _rewrite_everything(workspace)
    # the forge is real, not a no-op: different bytes, and the chain now commits to them
    assert new_sha != before
    assert bound_artifact_digests(workspace)[".loop/artifacts/verify-iter1.json"] == new_sha
    assert json.loads(_bundle(workspace).read_text(encoding="utf-8"))["forged"] is True
    report = doctor_report(workspace)
    assert report["ok"] is True and report["issues"] == []


def test_a_record_written_outside_a_dispatch_is_never_chain_bound_pinned(tmp_path):
    """``emit.write_verify_evidence`` is a WRITER, not a dispatch: it appends no event.

    Nothing binds what it wrote, so a later rewrite of that record is invisible. The
    writer-API path is supported deliberately (decision 14's residual (i)), so this
    silence ships NAMED rather than closed. Positive control: the identical rewrite in a
    dispatched contract is caught, which is the only thing that makes this a boundary
    rather than an absence of checking.
    """
    workspace = _contract(tmp_path, "storeless", [_task()], store=False)
    written = emit.write_verify_evidence(
        workspace, run_id=_RUN_ID, iteration_id=1, task=_task(), passed=True,
        code_identity=executed_verifier_identity(_VERIFY, workspace))
    assert bound_artifact_digests(workspace) is None        # no store: nothing can bind
    record = json.loads(written["evidence"].read_text(encoding="utf-8"))
    record["verified_by"]["by"] = "ci"
    written["evidence"].write_text(json.dumps(record), encoding="utf-8")
    assert "evidence_chain_mismatch" not in _codes(doctor_report(workspace))

    bound = _dispatched(tmp_path, "bound")                  # control: a dispatch DOES bind
    data = json.loads(_record(bound).read_text(encoding="utf-8"))
    data["verified_by"]["by"] = "ci"
    _record(bound).write_text(json.dumps(data), encoding="utf-8")
    assert "evidence_chain_mismatch" in _codes(doctor_report(bound))


def test_a_legacy_iteration_event_can_never_be_bound_retroactively_pinned(tmp_path):
    """A pre-release event carries ``artifact_hashes: []`` and is silent by construction.

    It cannot be repaired either: the append-only triggers forbid the UPDATE a backfill
    would need — the same reason ``loop migrate`` refuses to backfill chain hashes. So a
    pre-release iteration whose evidence was deleted stays undetectable at this layer
    forever. Positive control: the same deletion over a BOUND event is reported.
    """
    workspace = _dispatched(tmp_path)
    _unbind(workspace)
    assert bound_artifact_digests(workspace) == {}
    _record(workspace).unlink()
    _bundle(workspace).unlink()
    assert "missing_bound_evidence" not in _codes(doctor_report(workspace))
    with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="append-only"):
        conn = sqlite3.connect(str(_store_path(workspace)))
        try:
            conn.execute("UPDATE events SET artifact_hashes = '[]' WHERE sequence = 1")
        finally:
            conn.close()

    bound = _dispatched(tmp_path, "bound")                  # control: a bound pair IS missed
    _record(bound).unlink()
    _bundle(bound).unlink()
    assert "missing_bound_evidence" in _codes(doctor_report(bound))


def test_doctor_does_not_re_hash_the_verifier_file_pinned(tmp_path):
    """``code_digest`` stays in the recorded-not-compared tier (decision 5).

    A verifier file legitimately changes between runs, and a comparison with no declared
    baseline would fire on every honest edit. Only what the chain BOUND is re-hashed, and
    the verifier script is not a bound artifact — so editing it after the dispatch leaves
    doctor clean. Control: the bytes demonstrably moved, and the record still says
    otherwise.
    """
    workspace = _dispatched(tmp_path)
    recorded = json.loads(_record(workspace).read_text(encoding="utf-8"))["verified_by"]["code_digest"]
    script = workspace / "scripts" / "verify-fast.sh"
    script.write_text("#!/bin/sh\nexit 0\n# tampered\n", encoding="utf-8")
    assert verifier_code_digest(_VERIFY, workspace)[0] != recorded          # control: bytes moved
    assert "scripts/verify-fast.sh" not in bound_artifact_digests(workspace)
    assert doctor_report(workspace)["ok"] is True


def test_an_older_record_for_a_moved_goalpost_is_not_compared_pinned(tmp_path):
    """Decision 5's cost, stated plainly: only the LATEST record per task is compared.

    A superseded record therefore keeps a goalpost nobody checks. The alternative —
    comparing every record — turns each honest re-verification into a permanent doctor
    failure, because the older record legitimately describes the goalpost that was
    current when it was written. Positive control: move the goalpost the LATEST record
    cites and the comparison fires.
    """
    workspace = _contract(tmp_path, "storeless", [_task()], store=False)
    identity = executed_verifier_identity(_VERIFY, workspace)
    emit.write_verify_evidence(workspace, run_id=_RUN_ID, iteration_id=1, task=_task(),
                               passed=False, code_identity=identity)
    emit.write_verify_evidence(workspace, run_id=_RUN_ID, iteration_id=2,
                               task=_task(verify="true"), passed=True, code_identity=identity)
    _write_tasks(workspace, [_task(verify="true")])         # the LATEST record's goalpost
    stale = json.loads(_record(workspace).read_text(encoding="utf-8"))["verified_by"]["policy_digest"]
    assert stale != verification_policy_digest(_task(verify="true"))   # iter1 IS stale
    assert "policy_digest_mismatch" not in _codes(doctor_report(workspace))

    _write_tasks(workspace, [_task(verify="false")])        # control: move the LATEST goalpost
    assert "policy_digest_mismatch" in _codes(doctor_report(workspace))


def test_deleting_every_artifact_and_the_store_leaves_a_clean_doctor_pinned(tmp_path):
    """Delete the whole run and the contract is one that never ran.

    Artifacts, records, store AND sidecars gone: nothing inside the tree remembers the
    dispatch, so doctor is clean and correct to be (repo-os-contract §22 — the
    ``missing_event_store`` tripwire fires only on the sloppier deletion that leaves
    -wal/-shm behind). Detection needs something OUTSIDE the tree; the anchored control
    at the end of this test is that something.
    """
    workspace = _dispatched(tmp_path)
    anchor = _head(workspace)
    shutil.rmtree(workspace / ".loop" / "artifacts")
    shutil.rmtree(workspace / ".loop" / "evidence")
    for suffix in ("", "-wal", "-shm"):
        _store_path(workspace).with_name("events.db" + suffix).unlink(missing_ok=True)
    report = doctor_report(workspace)
    assert report["ok"] is True and report["issues"] == []
    assert "chain_anchor_mismatch" in _codes(doctor_report(workspace, expect_chain_head=anchor))


def test_the_verified_evidence_mode_is_opt_in_and_not_retroactive_pinned(tmp_path):
    """A Succeeded terminal written under ``all_required`` keeps the OLD bar forever.

    Non-empty path strings remain sufficient there, which is why both shipped examples
    and every pre-release run survive this slice unchanged (Global Constraints: the
    tightening is opt-in, never retroactive). The positive control is exactly one field:
    the byte-identical terminal under the strict mode is reported.
    """
    workspace = _contract(tmp_path, "storeless", [_task()], store=False)
    _terminal_file(workspace, mode="all_required", evidence=["RUNLOG.md"])
    assert "unverified_evidence_terminal" not in _codes(doctor_report(workspace))
    _terminal_file(workspace, mode=VERIFIED_EVIDENCE_MODE, evidence=["RUNLOG.md"])
    assert "unverified_evidence_terminal" in _codes(doctor_report(workspace))


def test_a_hand_written_record_pointing_at_a_real_file_still_passes_pinned(tmp_path):
    """Hash verification proves the POINTER, never the PROVENANCE.

    A record hand-written to describe a file that exists is, to doctor, indistinguishable
    from one a dispatch produced: same shape, same true digest, same live goalpost. What
    this release added is that the pointer must be TRUE — the control below corrupts the
    pointed-at bytes and the new check fires.
    """
    workspace = _contract(tmp_path, "storeless", [_task()], store=False)
    _handwritten_record(workspace)
    assert doctor_report(workspace)["ok"] is True
    (workspace / ".loop" / "artifacts" / "verify-iter9.json").write_text("{}", encoding="utf-8")
    assert "hash_mismatch" in _codes(doctor_report(workspace))              # control: it fires


def test_criterion_text_is_still_unbound_pinned(tmp_path):
    """What a criterion MEANS is prose, and prose is bound by nothing.

    ``policy_digest`` covers id / verify / criterion_ref / depends_on — the POINTER to a
    criterion, not its wording — so rewriting SPEC.md's acceptance text moves no digest
    and fires nothing. Binding evidence does not bind intent. Control: the bundle IS a
    bound artifact and SPEC.md is not, so the difference is structural, not incidental.
    """
    workspace = _dispatched(tmp_path)
    recorded = json.loads(_record(workspace).read_text(encoding="utf-8"))["verified_by"]["policy_digest"]
    live = json.loads((workspace / "TASKS.json").read_text(encoding="utf-8"))["tasks"][0]
    spec = workspace / "SPEC.md"
    spec.write_text(spec.read_text(encoding="utf-8").replace(
        "REPLACE: first success criterion", "anything at all now counts as success"),
        encoding="utf-8")
    assert "anything at all" in spec.read_text(encoding="utf-8")            # the goal moved
    assert verification_policy_digest(live) == recorded                     # the digest did not
    bound = bound_artifact_digests(workspace)
    assert "SPEC.md" not in bound and ".loop/artifacts/verify-iter1.json" in bound
    assert doctor_report(workspace)["ok"] is True


def test_metrics_still_counts_a_hand_written_declared_command_bundle_pinned(tmp_path):
    """``verifier.source`` is a string the WRITER declares, not a fact metrics can check.

    Hand-writing ``declared_command`` over ``injected_callable`` restores the bundle's
    gate-evidence status and moves FCR back to 0.0. The exclusion is an honesty aid for
    honest writers, never a control against a dishonest one. Control: the same bundle,
    one string different, scores the opposite way.
    """
    loop_dir = _metrics_workspace(tmp_path, "injected_callable")
    assert compute_metrics(loop_dir)["false_completion_rate"] == 1.0        # control: excluded
    bundle = loop_dir / ".loop" / "artifacts" / "verify-iter1.json"
    body = json.loads(bundle.read_text(encoding="utf-8"))
    body["verifier"]["source"] = "declared_command"
    bundle.write_text(json.dumps(body), encoding="utf-8")
    metrics = compute_metrics(loop_dir)
    assert metrics["false_completion_rate"] == 0.0
    assert metrics["provenance"]["injected_verifier_bundles"] == []


def test_the_strict_mode_accepts_a_hand_written_record_in_a_store_less_contract_pinned(tmp_path):
    """Decision 14's residual (i), stated as MEASURED rather than as hoped.

    Where no event store exists there is nothing to bind against, so the strict mode
    degrades to hash-verification plus goalpost agreement — and a hand-written record
    satisfies it with zero dispatch and zero events.

    The plan claimed doctor's ``missing_event_store`` tripwire is what catches deleting a
    store out from under a real run. Measured here, it is NOT: that tripwire is gated on
    leftover -wal/-shm sidecars, and sidecar-free reads (v0.10.0) leave none, so deleting
    the store makes plain doctor CLEANER — ok, zero issues — rather than louder. The real
    compensating control is the EXTERNAL ANCHOR, asserted below; a pin that named the
    tripwire instead would be a false claim shipped inside an honesty test.
    """
    storeless = _contract(tmp_path, "storeless", [_task()], store=False)
    entry = _handwritten_record(storeless)
    path = emit.terminate(storeless, state="Succeeded", criteria_met={"T-1": True},
                          evidence=[entry], completion_policy=VERIFIED_EVIDENCE_MODE)
    assert json.loads(path.read_text(encoding="utf-8"))["completion_policy"] == {
        "mode": VERIFIED_EVIDENCE_MODE}                                     # ACCEPTED — residual

    bound = _dispatched(tmp_path, "bound")                  # control: a store refuses it
    with pytest.raises(emit.EmitError, match="not bound"):
        emit.terminate(bound, state="Succeeded", criteria_met={"T-1": True},
                       evidence=[_handwritten_record(bound)],
                       completion_policy=VERIFIED_EVIDENCE_MODE)
    assert "chain_anchor_mismatch" not in _codes(
        doctor_report(bound, expect_chain_head=_head(bound)))               # anchor is quiet when intact

    deleted = _dispatched(tmp_path, "deleted")              # the delete-the-store route
    anchor = _head(deleted)
    for suffix in ("", "-wal", "-shm"):
        _store_path(deleted).with_name("events.db" + suffix).unlink(missing_ok=True)
    silent = doctor_report(deleted)
    assert silent["ok"] is True and silent["issues"] == []  # MEASURED: deleting it is silent
    assert bound_artifact_digests(deleted) is None
    emit.terminate(deleted, state="Succeeded", criteria_met={"T-1": True},
                   evidence=[".loop/evidence/evidence-iter1.json"],
                   completion_policy=VERIFIED_EVIDENCE_MODE)                # ACCEPTED — residual
    assert "chain_anchor_mismatch" in _codes(
        doctor_report(deleted, expect_chain_head=anchor))                   # the anchor catches it


def test_a_full_rewrite_satisfies_the_strict_mode_without_an_anchor_pinned(tmp_path):
    """The headline residual restated at the COMPLETION layer.

    Rewrite the bundle, the record, the object and the digests the event bound, re-chain
    the tail, and ``terminate(..., all_required_verified_evidence)`` succeeds: the strict
    mode is exactly as strong as the chain it reads, and the chain is as strong as its
    anchor. Positive control: the same tree, checked against the pre-rewrite head, reports
    ``chain_anchor_mismatch``. This pin is why the shipped claim stays "bound into an
    anchorable chain" and why "tamper-proof evidence" is forbidden.
    """
    workspace = _dispatched(tmp_path)
    anchor = _head(workspace)
    _rewrite_everything(workspace)
    path = emit.terminate(workspace, state="Succeeded", criteria_met={"T-1": True},
                          evidence=[".loop/evidence/evidence-iter1.json"],
                          completion_policy=VERIFIED_EVIDENCE_MODE)
    assert json.loads(path.read_text(encoding="utf-8"))["completion_policy"] == {
        "mode": VERIFIED_EVIDENCE_MODE}
    assert json.loads(_bundle(workspace).read_text(encoding="utf-8"))["forged"] is True
    assert "chain_anchor_mismatch" in _codes(
        doctor_report(workspace, expect_chain_head=anchor))                 # control: the anchor


# --- real detections -----------------------------------------------------------

def test_an_anchored_head_catches_the_full_rewrite(tmp_path):
    """The positive control for the first pin: an anchor recorded outside the tree."""
    workspace = _dispatched(tmp_path)
    anchor = _head(workspace)
    assert "chain_anchor_mismatch" not in _codes(
        doctor_report(workspace, expect_chain_head=anchor))
    _rewrite_everything(workspace)
    assert "chain_anchor_mismatch" in _codes(
        doctor_report(workspace, expect_chain_head=anchor))


def test_deleting_the_object_alone_is_reported(tmp_path):
    """The content-addressed object is a BOUND artifact, not a convenience copy.

    Deleting the recovery source an ``evidence_chain_mismatch`` message points at is
    itself detectable, so the recovery path cannot be quietly removed first.
    """
    workspace = _dispatched(tmp_path)
    digest = json.loads(_record(workspace).read_text(encoding="utf-8"))["sha256"]
    obj = artifact_object_path(workspace, digest)
    assert obj.is_file()
    obj.unlink()
    assert "missing_bound_evidence" in _codes(doctor_report(workspace))
