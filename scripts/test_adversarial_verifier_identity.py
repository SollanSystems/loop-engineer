"""Adversarial coverage: what verifier identity DOES and DOES NOT catch.

The claim this file defends is "surfaces DECLARED self-verification", never
"proves independence". Each *_pinned test first proves the detector fires, then
applies the evasion and proves it does not — so a deleted detector fails here.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from loop import emit
from loop.contract import doctor_report
from loop.events import SQLiteEventStore
from loop.evidence import verify_evidence
from loop.runner import dispatch_once
from loop.verifier import (executed_verifier_identity, injected_verifier_identity,
                           verification_policy_digest, verifier_code_digest)

_RAMP = ("plan", "critique-plan", "queue-tasks", "execute-task")


def _task(**overrides):
    base = {"id": "T-1", "title": "t", "status": "pending", "criterion_ref": "C-1",
            "verify": "./scripts/verify-fast.sh", "depends_on": [], "attempts": 0, "evidence": None}
    base.update(overrides)
    return base


def _ws(tmp_path):
    workspace = tmp_path / "workspace"
    emit.open_contract(workspace)
    script = workspace / "scripts" / "verify-fast.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    return workspace


@pytest.fixture
def bound_workspace(tmp_path):
    """One real dispatch behind an event store: iteration 1's artifacts ARE chain-bound.

    The store's ramp records the FSM walk to execute-task, not work — its events carry
    iteration_id 0 — so the first dispatch is iteration 1 and both paths are literal.
    """
    workspace = tmp_path / "bound"
    emit.open_contract(workspace)
    (workspace / "TASKS.json").write_text(json.dumps({
        "schema": "loop-engineer/tasks@1",
        "tasks": [_task(criterion_ref="T-1", title="T-1")]}), encoding="utf-8")
    script = workspace / "scripts" / "verify-fast.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    store = SQLiteEventStore(workspace / ".loop" / "events.db")
    store.append("run-1", "contract_opened", {"workspace": "bound"}, actor="test")
    for state in _RAMP:
        store.append("run-1", "iteration_appended",
                     {"iteration_id": 0, "outcome": "replanned", "state": state}, actor="test")
    state_path = workspace / ".loop" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["state"] = _RAMP[-1]
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    dispatch_once(workspace)
    return {"workspace": workspace,
            "bundle": workspace / ".loop" / "artifacts" / "verify-iter1.json",
            "record": workspace / ".loop" / "evidence" / "evidence-iter1.json"}


def _write(workspace, *, iteration_id=1, task=None, passed=True, **kwargs):
    task = task or _task()
    kwargs.setdefault("code_identity",
                      executed_verifier_identity(task["verify"], workspace))
    return emit.write_verify_evidence(workspace, run_id="run-1", iteration_id=iteration_id,
                                      task=task, passed=passed, **kwargs)


def _codes(report):
    return {issue["code"] for issue in report["issues"]}


# --- pinned honest limitations -------------------------------------------------

def test_disguised_verifier_identity_is_not_detected_pinned(tmp_path):
    """A worker that self-verifies but WRITES a different verifier name is not caught."""
    workspace = _ws(tmp_path)
    _write(workspace, iteration_id=1, executor="worker-a", verifier_identity="worker-a")
    assert "self_verified_evidence" in _codes(doctor_report(workspace))   # control: it fires
    _write(workspace, iteration_id=1, executor="worker-a", verifier_identity="ci")
    assert "self_verified_evidence" not in _codes(doctor_report(workspace))


def test_unattributed_executor_never_trips_the_finding_pinned(tmp_path):
    """Omitting --executor evades the check; attribution is the caller's to supply."""
    workspace = _ws(tmp_path)
    _write(workspace, iteration_id=1, executor="loop.run")
    assert "self_verified_evidence" in _codes(doctor_report(workspace))   # control: it fires
    _write(workspace, iteration_id=1)                                    # default: unattributed
    assert "self_verified_evidence" not in _codes(doctor_report(workspace))


def test_deleting_both_bundle_and_record_is_caught_only_when_the_chain_binds_them(tmp_path,
                                                                                  bound_workspace):
    """Was `test_deleting_both_bundle_and_record_leaves_doctor_clean_pinned`; the
    detection half arrived with chain-bound evidence in the evidence-wiring release.

    The RESIDUAL is unchanged and kept: written through the writer API with no event
    store behind it, nothing outside the tree remembers the dispatch happened, so
    deleting the pair is still invisible. Where a dispatch bound them, the committed
    event names artifacts that are gone — `missing_bound_evidence`.
    """
    workspace = _ws(tmp_path)
    written = _write(workspace, executor="w", verifier_identity="w")
    assert "self_verified_evidence" in _codes(doctor_report(workspace))   # control: it fires
    written["evidence"].unlink()
    assert "missing_evidence_record" in _codes(doctor_report(workspace))  # residue IS caught
    written["bundle"].unlink()
    assert doctor_report(workspace)["ok"] is True                         # residual: the pair is not
    bound_workspace["record"].unlink()
    bound_workspace["bundle"].unlink()
    assert "missing_bound_evidence" in _codes(doctor_report(bound_workspace["workspace"]))


def test_rewriting_the_evidence_record_is_caught_only_when_the_chain_binds_it(tmp_path,
                                                                              bound_workspace):
    """Was `test_rewriting_the_evidence_record_to_independent_identities_leaves_doctor_clean_pinned`;
    the detection half arrived with chain-bound evidence in the evidence-wiring release.

    The RESIDUAL is unchanged and kept: a record written by the writer API with no event
    store behind it is still a plain file, and a rewrite of it is still invisible. A
    record a dispatch bound is not — its bytes are covered by `event_hash`, so the
    rewrite surfaces as `evidence_chain_mismatch`.
    """
    workspace = _ws(tmp_path)
    written = _write(workspace, executor="solo", verifier_identity="solo")
    assert "self_verified_evidence" in _codes(doctor_report(workspace))   # control: it fires
    record = json.loads(written["evidence"].read_text(encoding="utf-8"))
    record["verified_by"]["by"] = "ci"
    written["evidence"].write_text(json.dumps(record), encoding="utf-8")
    assert doctor_report(workspace)["ok"] is True                         # residual
    bound = bound_workspace["record"]
    data = json.loads(bound.read_text(encoding="utf-8"))
    data["verified_by"]["by"] = "ci"
    bound.write_text(json.dumps(data), encoding="utf-8")
    assert "evidence_chain_mismatch" in _codes(doctor_report(bound_workspace["workspace"]))


def test_hand_written_record_with_a_fabricated_code_digest_is_doctor_clean_pinned(tmp_path):
    """Digests are values the WRITER asserts. Doctor validates their shape, never
    their truth — a hand-written record is indistinguishable from a runner-written one.

    Narrower since the evidence-wiring release, and deliberately still true: what IS
    now checked is the bundle's BYTES (the record's `sha256` must hash the file its
    `uri` names) and, for a task still declared in TASKS.json, the recorded
    `policy_digest` against the live goalpost. `code_digest` remains unchecked, and
    this record names a task the scaffold's TASKS.json does not declare.
    """
    workspace = _ws(tmp_path)
    written = _write(workspace)
    record = json.loads(written["evidence"].read_text(encoding="utf-8"))
    record["verified_by"]["code_digest"] = "NOTHEX"
    written["evidence"].write_text(json.dumps(record), encoding="utf-8")
    assert "invalid_evidence" in _codes(doctor_report(workspace))  # control: the SHAPE is checked
    record["verified_by"]["code_digest"] = "f" * 64
    record["verified_by"]["policy_digest"] = "e" * 64
    written["evidence"].write_text(json.dumps(record), encoding="utf-8")
    assert doctor_report(workspace)["ok"] is True


def test_policy_digest_comparison_fires_only_against_a_live_task_entry(tmp_path):
    """Was `test_no_automated_digest_comparison_exists_pinned`; the comparison arrived in
    the evidence-wiring release.

    The RESIDUAL is its two silences, both kept here: a record naming a task TASKS.json
    no longer declares is never compared (a rename or removal is a replan, not a
    forgery), and neither is any record that is not the latest for its task. Both
    records below move the goalpost, and doctor stays quiet until the task is live.
    """
    workspace = _ws(tmp_path)
    _write(workspace, iteration_id=1, task=_task())                # T-1 is not in TASKS.json
    _write(workspace, iteration_id=2, task=_task(verify="true"))
    digests = {json.loads((workspace / ".loop" / "evidence" / f"evidence-iter{n}.json")
                          .read_text(encoding="utf-8"))["verified_by"]["policy_digest"]
               for n in (1, 2)}
    assert len(digests) == 2                                       # the goalpost demonstrably moved
    assert "policy_digest_mismatch" not in _codes(doctor_report(workspace))       # residual
    (workspace / "TASKS.json").write_text(json.dumps(
        {"schema": "loop-engineer/tasks@1", "project": "p", "tasks": [_task(status="pending")]}),
        encoding="utf-8")
    assert "policy_digest_mismatch" in _codes(doctor_report(workspace))


def test_doctor_hash_verifies_the_referenced_bundle(tmp_path):
    """Was `test_doctor_does_not_hash_verify_the_referenced_bundle_pinned`; doctor gained
    the composition in the evidence-wiring release.

    Slice 2 checked structure, declared independence and record presence only, and the
    hash check existed but nothing called it. Doctor now composes `verify_evidence` over
    every discovered record and surfaces its `hash_mismatch` verbatim.
    """
    workspace = _ws(tmp_path)
    written = _write(workspace, passed=False)
    written["bundle"].write_text(json.dumps({"outcome": "PASS", "passed": True}), encoding="utf-8")
    record = json.loads(written["evidence"].read_text(encoding="utf-8"))
    # the standalone verb and the doctor sweep now agree, and doctor says it in its issues
    assert verify_evidence(record, workspace_root=workspace)["ok"] is False
    assert "hash_mismatch" in _codes(doctor_report(workspace))


def test_code_digest_is_null_for_the_common_python_m_pytest_command_pinned(tmp_path):
    """The most common real verify command has no hashable workspace script."""
    (tmp_path / "verify.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    digest, basis = verifier_code_digest("./verify.sh", tmp_path)   # control: it does hash a script
    assert basis == "workspace_file" and digest is not None
    assert verifier_code_digest("python3 -m pytest -q", tmp_path) == (None, "path_lookup")


def test_recorded_digests_do_not_change_when_the_verifier_file_changes_afterwards_pinned(tmp_path):
    """A digest is a record of one moment, not a live guard."""
    workspace = _ws(tmp_path)
    written = _write(workspace)
    recorded = json.loads(written["evidence"].read_text())["verified_by"]["code_digest"]
    (workspace / "scripts" / "verify-fast.sh").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    # control: the bytes demonstrably moved — a digest taken NOW differs from the record's.
    assert verifier_code_digest("./scripts/verify-fast.sh", workspace)[0] != recorded
    assert json.loads(written["evidence"].read_text())["verified_by"]["code_digest"] == recorded
    assert doctor_report(workspace)["ok"] is True


def test_a_misspelled_holdout_field_is_silently_undeclared_pinned(tmp_path):
    """tasks@1 is additionalProperties:true, so `holdout_critera` validates and yields
    declared:false with an empty holdout — indistinguishable from "none declared".
    """
    workspace = _ws(tmp_path)
    spelled = _write(workspace, task=_task(holdout_criteria=["C-9"]))   # control: it declares
    assert json.loads(spelled["bundle"].read_text(encoding="utf-8"))["partition"] == {
        "visible": ["C-1"], "holdout": ["C-9"], "declared": True, "holdout_executed": False}
    written = _write(workspace, task=_task(holdout_critera=["C-9"]))
    partition = json.loads(written["bundle"].read_text(encoding="utf-8"))["partition"]
    assert partition == {"visible": ["C-1"], "holdout": [],
                         "declared": False, "holdout_executed": False}


# --- real detections -----------------------------------------------------------

def test_moving_the_goalpost_changes_the_policy_digest(tmp_path):
    assert verification_policy_digest(_task()) != verification_policy_digest(_task(verify="true"))
    assert verification_policy_digest(_task()) == verification_policy_digest(_task(attempts=9, status="done"))


def test_swapping_the_verifier_script_changes_the_code_digest(tmp_path):
    workspace = _ws(tmp_path)
    first, _ = verifier_code_digest("./scripts/verify-fast.sh", workspace)
    (workspace / "scripts" / "verify-fast.sh").write_text("#!/bin/sh\nexit 0\n# tampered\n", encoding="utf-8")
    second, basis = verifier_code_digest("./scripts/verify-fast.sh", workspace)
    assert basis == "workspace_file" and first != second


def test_swapping_the_bundle_breaks_the_records_committed_digest(tmp_path):
    workspace = _ws(tmp_path)
    written = _write(workspace, passed=False)
    written["bundle"].write_text(json.dumps({"outcome": "PASS", "passed": True}), encoding="utf-8")
    record = json.loads(written["evidence"].read_text())
    result = verify_evidence(record, workspace_root=workspace)
    assert result["ok"] is False and result["issues"][0]["code"] == "hash_mismatch"
    assert record["sha256"] != hashlib.sha256(written["bundle"].read_bytes()).hexdigest()
