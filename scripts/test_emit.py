"""B1 acceptance: emit writes schema-valid artifacts by construction and refuses
an evidence-free Succeeded at write time (G1 enforced before validate time)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from loop import emit
from loop.contract import validate_contract


@pytest.fixture()
def workspace(tmp_path):
    ws = tmp_path / "demo"
    report = emit.open_contract(ws)
    assert report["ok"] is True
    return ws


def test_open_contract_is_doctor_clean(workspace):
    assert validate_contract(workspace)["ok"] is True


def test_append_iteration_writes_parseable_runlog_and_updates_state(workspace):
    runlog = emit.append_iteration(
        workspace, iteration_id=1, outcome="task_passed", task_id="T1",
        actions=["did the thing"], verify_cmd="scripts/verify-fast", verify_outcome="pass",
    )
    text = runlog.read_text(encoding="utf-8")
    assert "## Iteration 1" in text
    assert "`task_passed`" in text

    state = json.loads((workspace / ".loop" / "state.json").read_text(encoding="utf-8"))
    assert state["iteration_id"] == "1"
    assert state["active_task"] == "T1"
    assert validate_contract(workspace)["ok"] is True


def test_append_iteration_rejects_unknown_outcome(workspace):
    with pytest.raises(emit.EmitError):
        emit.append_iteration(workspace, iteration_id=1, outcome="totally_done")


def test_append_receipt_is_schema_valid(workspace):
    path = emit.append_receipt(
        workspace, iteration_id=1, role="write", model="claude-opus", outcome="ok"
    )
    assert path == workspace / ".loop" / "receipts" / "receipts.jsonl"
    # doctor validates .loop/receipts/*.jsonl against loop-engineer/receipt@1
    report = validate_contract(workspace)
    assert report["ok"] is True
    assert "loop-engineer/receipt@1" in report["schemas_checked"]


def test_append_receipt_rejects_bad_role(workspace):
    with pytest.raises(emit.EmitError):
        emit.append_receipt(workspace, iteration_id=1, role="wizard", model="m", outcome="ok")


def test_terminate_succeeded_with_evidence_passes_doctor(workspace):
    terminal = emit.terminate(
        workspace, state="Succeeded", criteria_met={"1": True},
        evidence=["artifact.txt"], reason="verified", iteration_id=1,
    )
    data = json.loads(terminal.read_text(encoding="utf-8"))
    assert data["schema"] == "loop-engineer/terminal@1"
    assert data["false_completion"] is False
    state = json.loads((workspace / ".loop" / "state.json").read_text(encoding="utf-8"))
    assert state["terminal_state"] == "Succeeded"
    assert validate_contract(workspace)["ok"] is True


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(criteria_met={"1": True}, evidence=[]),                      # evidence-free
        dict(criteria_met={"1": False}, evidence=["a.txt"]),              # no met criterion
        dict(criteria_met={}, evidence=["a.txt"]),                        # empty criteria
        dict(criteria_met={"1": True}, evidence=["a.txt"], false_completion=True),  # G1 contradiction
    ],
)
def test_terminate_refuses_dishonest_succeeded(workspace, kwargs):
    with pytest.raises(emit.EmitError):
        emit.terminate(workspace, state="Succeeded", reason="claimed", **kwargs)
    assert not (workspace / ".loop" / "terminal_state.json").exists()


def test_terminate_honest_failure_needs_no_evidence(workspace):
    emit.terminate(
        workspace, state="FailedUnverifiable", criteria_met={"1": False},
        evidence=[], reason="could not verify",
    )
    assert validate_contract(workspace)["ok"] is True


def test_terminate_rejects_unknown_state(workspace):
    with pytest.raises(emit.EmitError):
        emit.terminate(workspace, state="Done", criteria_met={"1": True}, evidence=["a"])


def test_terminate_rejects_non_boolean_criteria_met_value(workspace):
    with pytest.raises(emit.EmitError):
        emit.terminate(
            workspace, state="FailedUnverifiable", criteria_met={"done": "yes"},
            evidence=[], reason="could not verify",
        )
    assert not (workspace / ".loop" / "terminal_state.json").exists()


def test_writes_refused_without_a_contract(tmp_path):
    with pytest.raises(emit.EmitError):
        emit.append_iteration(tmp_path / "nowhere", iteration_id=1, outcome="task_passed")
