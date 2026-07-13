"""B1 acceptance: emit writes schema-valid artifacts by construction and
refuses a Succeeded claim unless every required criterion has evidence-backed
proof (G1 enforced before validate time)."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import metrics
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


def test_open_contract_is_metrics_clean(workspace):
    # The seeded RUNLOG is reference-only prose — no `## Iteration` block, so a
    # fresh scaffold must score zero iterations and no outcome tokens.
    scorecard = metrics.compute_metrics(workspace)
    assert scorecard["provenance"]["unrecognized_outcomes"] == []
    assert scorecard["iterations_claiming_success"] == 0


def test_append_iteration_writes_parseable_runlog_and_updates_state(workspace):
    runlog = emit.append_iteration(
        workspace, iteration_id=1, outcome="task_passed", task_id="T1",
        actions=["did the thing"], verify_cmd="scripts/verify-fast", verify_outcome="pass",
    )
    text = runlog.read_text(encoding="utf-8")
    assert "## Iteration 1" in text
    assert "`task_passed`" in text

    state = json.loads((workspace / ".loop" / "state.json").read_text(encoding="utf-8"))
    assert state["iteration_id"] == 1
    assert state["active_task"] == "T1"
    assert validate_contract(workspace)["ok"] is True


def test_append_iteration_rejects_unknown_outcome(workspace):
    with pytest.raises(emit.EmitError):
        emit.append_iteration(workspace, iteration_id=1, outcome="totally_done")


def test_append_iteration_advances_fsm_state_when_provided(workspace):
    emit.append_iteration(workspace, iteration_id=1, outcome="task_passed", state="plan")
    state = json.loads((workspace / ".loop" / "state.json").read_text(encoding="utf-8"))
    assert state["state"] == "plan"


def test_append_iteration_rejects_illegal_fsm_transition(workspace):
    runlog = workspace / "RUNLOG.md"
    before = runlog.read_text(encoding="utf-8")
    with pytest.raises(emit.EmitError):
        emit.append_iteration(workspace, iteration_id=1, outcome="task_passed", state="verify")
    assert runlog.read_text(encoding="utf-8") == before


def test_append_iteration_state_defaults_to_no_op(workspace):
    emit.append_iteration(workspace, iteration_id=1, outcome="task_passed")
    state = json.loads((workspace / ".loop" / "state.json").read_text(encoding="utf-8"))
    assert state["state"] == "intake"


def test_append_iteration_stamps_updated_at(workspace):
    emit.append_iteration(workspace, iteration_id=1, outcome="task_passed")
    state = json.loads((workspace / ".loop" / "state.json").read_text(encoding="utf-8"))
    timestamp = datetime.fromisoformat(state["updated_at"])
    assert timestamp.utcoffset() == timedelta(0)


def test_append_iteration_rejects_blank_state(workspace):
    with pytest.raises(emit.EmitError):
        emit.append_iteration(workspace, iteration_id=1, outcome="task_passed", state="   ")


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
        workspace, state="Succeeded", criteria_met={"1": True, "2": True},
        evidence=["artifact.txt"], reason="verified", iteration_id=1,
    )
    data = json.loads(terminal.read_text(encoding="utf-8"))
    assert data["schema"] == "loop-engineer/terminal@1"
    assert data["false_completion"] is False
    assert data["completion_policy"] == {"mode": "all_required"}
    state = json.loads((workspace / ".loop" / "state.json").read_text(encoding="utf-8"))
    assert state["terminal_state"] == "Succeeded"
    assert validate_contract(workspace)["ok"] is True


def test_terminate_sets_state_field_to_terminal(workspace):
    emit.terminate(
        workspace, state="FailedBlocked", criteria_met={"1": False}, evidence=[]
    )
    state = json.loads((workspace / ".loop" / "state.json").read_text(encoding="utf-8"))
    assert state["state"] == "terminal"
    assert datetime.fromisoformat(state["updated_at"]).utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(criteria_met={"1": True}, evidence=[]),                      # evidence-free
        dict(criteria_met={"1": False}, evidence=["a.txt"]),              # no met criterion
        dict(criteria_met={"1": True, "2": False}, evidence=["a.txt"]),  # partial proof
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


@pytest.mark.parametrize("iteration_id", [-1, True, "1"])
def test_append_iteration_rejects_noncanonical_iteration_ids(workspace, iteration_id):
    with pytest.raises(emit.EmitError, match="non-negative integer"):
        emit.append_iteration(workspace, iteration_id=iteration_id, outcome="task_passed")


def test_terminate_rejects_unsupported_completion_policy(workspace):
    with pytest.raises(emit.EmitError, match="unsupported completion policy"):
        emit.terminate(
            workspace,
            state="Succeeded",
            criteria_met={"1": True},
            evidence=["artifact.txt"],
            completion_policy={"mode": "any_required"},
        )


def test_terminate_rejects_duplicate_or_blank_evidence(workspace):
    for evidence in (["a.txt", "a.txt"], [""]):
        with pytest.raises(emit.EmitError):
            emit.terminate(
                workspace,
                state="FailedUnverifiable",
                criteria_met={"1": False},
                evidence=evidence,
            )


def _loop_leftovers(workspace):
    return sorted(p.name for p in (workspace / ".loop").rglob("*.tmp"))


def test_terminate_refuses_overwrite_of_existing_terminal(workspace):
    emit.terminate(
        workspace, state="Succeeded", criteria_met={"1": True},
        evidence=["artifact.txt"], reason="first", iteration_id=1,
    )
    terminal_path = workspace / ".loop" / "terminal_state.json"
    before = terminal_path.read_text(encoding="utf-8")

    with pytest.raises(emit.EmitError) as exc:
        emit.terminate(
            workspace, state="FailedBlocked", criteria_met={"1": False},
            evidence=[], reason="second",
        )
    assert "immutable" in str(exc.value)
    # the refused call left the original terminal record byte-for-byte intact
    assert terminal_path.read_text(encoding="utf-8") == before
    assert not _loop_leftovers(workspace)


def test_terminate_force_is_refused_and_preserves_original(workspace):
    emit.terminate(
        workspace, state="Succeeded", criteria_met={"1": True},
        evidence=["artifact.txt"], reason="first", iteration_id=1,
    )
    terminal_path = workspace / ".loop" / "terminal_state.json"
    before = terminal_path.read_text(encoding="utf-8")

    with pytest.raises(emit.EmitError, match="immutable"):
        emit.terminate(
            workspace, state="FailedBlocked", criteria_met={"1": False},
            evidence=[], reason="deliberate override", force=True,
        )

    assert terminal_path.read_text(encoding="utf-8") == before
    state = json.loads((workspace / ".loop" / "state.json").read_text(encoding="utf-8"))
    assert state["terminal_state"] == "Succeeded"
    assert not _loop_leftovers(workspace)



def test_concurrent_terminators_create_exactly_one_terminal(workspace):
    barrier = threading.Barrier(2)

    def attempt(state, criteria_met, evidence):
        barrier.wait()
        try:
            emit.terminate(
                workspace,
                state=state,
                criteria_met=criteria_met,
                evidence=evidence,
                reason=f"candidate {state}",
                iteration_id=1,
            )
        except emit.EmitError as exc:
            return ("refused", str(exc))
        return ("created", state)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            pool.submit(attempt, "Succeeded", {"1": True}, ["artifact.txt"]),
            pool.submit(attempt, "FailedBlocked", {"1": False}, []),
        ]
        outcomes = [future.result() for future in results]

    assert [kind for kind, _ in outcomes].count("created") == 1
    assert [kind for kind, _ in outcomes].count("refused") == 1
    assert "immutable" in next(message for kind, message in outcomes if kind == "refused")

    terminal_path = workspace / ".loop" / "terminal_state.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    winner = next(value for kind, value in outcomes if kind == "created")
    assert terminal["state"] == winner
    state = json.loads((workspace / ".loop" / "state.json").read_text(encoding="utf-8"))
    assert state["terminal_state"] == winner
    assert not _loop_leftovers(workspace)

def test_terminate_leaves_no_tmp_litter_on_success(workspace):
    emit.terminate(
        workspace, state="Succeeded", criteria_met={"1": True},
        evidence=["artifact.txt"], reason="ok", iteration_id=1,
    )
    assert not _loop_leftovers(workspace)


def test_terminate_leaves_no_tmp_litter_on_invalid_terminate(workspace):
    with pytest.raises(emit.EmitError):
        emit.terminate(
            workspace, state="Succeeded", criteria_met={"1": True}, evidence=[],
        )
    assert not (workspace / ".loop" / "terminal_state.json").exists()
    assert not _loop_leftovers(workspace)


def test_append_iteration_leaves_no_tmp_litter(workspace):
    emit.append_iteration(workspace, iteration_id=1, outcome="task_passed", task_id="T1")
    assert not _loop_leftovers(workspace)


def test_sync_state_to_terminal_reconciles_unstamped_state(workspace):
    emit.terminate(
        workspace, state="Succeeded", criteria_met={"1": True},
        evidence=["artifact.txt"], reason="ok", iteration_id=1,
    )
    terminal_path = workspace / ".loop" / "terminal_state.json"
    before = terminal_path.read_text(encoding="utf-8")
    state_path = workspace / ".loop" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["terminal_state"] = None
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    synced = emit.sync_state_to_terminal(workspace)

    assert synced == state_path
    assert json.loads(state_path.read_text(encoding="utf-8"))["terminal_state"] == "Succeeded"
    assert terminal_path.read_text(encoding="utf-8") == before
    assert not _loop_leftovers(workspace)


def test_sync_state_to_terminal_also_reconciles_state_field(workspace):
    emit.terminate(
        workspace, state="FailedBlocked", criteria_met={"1": False}, evidence=[]
    )
    state_path = workspace / ".loop" / "state.json"
    current = json.loads(state_path.read_text(encoding="utf-8"))
    current["state"] = "intake"
    current.pop("updated_at")
    state_path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")

    emit.sync_state_to_terminal(workspace)

    synced = json.loads(state_path.read_text(encoding="utf-8"))
    assert synced["state"] == "terminal"
    assert datetime.fromisoformat(synced["updated_at"]).utcoffset() == timedelta(0)


def test_sync_state_to_terminal_requires_a_terminal_record(workspace):
    with pytest.raises(emit.EmitError, match="nothing to sync"):
        emit.sync_state_to_terminal(workspace)


def test_terminate_wraps_link_failure_as_emit_error(workspace, monkeypatch):
    def _refuse_link(src, dst):
        raise PermissionError("hard links not supported")

    monkeypatch.setattr(emit.os, "link", _refuse_link)
    with pytest.raises(emit.EmitError, match="terminal write failed"):
        emit.terminate(
            workspace, state="Succeeded", criteria_met={"1": True},
            evidence=["artifact.txt"], reason="ok", iteration_id=1,
        )
    assert not (workspace / ".loop" / "terminal_state.json").exists()
    assert not _loop_leftovers(workspace)
