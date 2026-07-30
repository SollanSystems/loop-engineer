"""scripts/test_verdict_compare.py — compare_verdict(): agreement, never authenticity.

`gh attestation verify` establishes authenticity and runs FIRST; this establishes
agreement. Neither implies the other, `signature_checked` is the literal False on
every branch, and there is no flag to flip it (D7/D10.1).

The function accepts a BARE verdict@1 predicate only. An in-toto Statement or a
`gh --format json` envelope is a typed refusal that names the unwrapping step —
best-effort parsing of a vendor envelope inside the kernel is how a trust boundary rots.
"""
from __future__ import annotations

import ast
import copy
import inspect
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loop import emit                                                      # noqa: E402
from loop import verdict as verdict_module                                 # noqa: E402
from loop.completion import VERIFIED_EVIDENCE_MODE                         # noqa: E402
from loop.events import SQLiteEventStore                                   # noqa: E402
from loop.runner import dispatch_once                                      # noqa: E402
from loop.verdict import (COMPARISON_CODES, VerdictError, build_verdict,   # noqa: E402
                          compare_verdict)

_RUN_ID = "run-1"
_VERIFY = "./scripts/verify-fast.sh"
_RAMP = ("plan", "critique-plan", "queue-tasks", "execute-task")
_JQ_PATH = ".[0].verificationResult.statement.predicate"


def _task(task_id="T-1"):
    return {"id": task_id, "title": task_id, "status": "pending", "criterion_ref": task_id,
            "verify": _VERIFY, "depends_on": [], "attempts": 0, "evidence": None}


def _workspace(tmp_path, name="workspace"):
    """A dispatched contract carrying one chain-bound verified-evidence record,
    then made terminal so a verdict can be projected from it."""
    workspace = tmp_path / name
    emit.open_contract(workspace)
    (workspace / "TASKS.json").write_text(
        json.dumps({"schema": "loop-engineer/tasks@1", "tasks": [_task()]}), encoding="utf-8")
    script = workspace / "scripts" / "verify-fast.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    events = SQLiteEventStore(workspace / ".loop" / "events.db")
    events.append(_RUN_ID, "contract_opened", {"workspace": name}, actor="test")
    for state in _RAMP:
        events.append(_RUN_ID, "iteration_appended",
                      {"iteration_id": 0, "outcome": "replanned", "state": state}, actor="test")
    state_path = workspace / ".loop" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["state"] = _RAMP[-1]
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    dispatch_once(workspace)
    (workspace / ".loop" / "terminal_state.json").write_text(json.dumps({
        "schema": "loop-engineer/terminal@1", "state": "Succeeded",
        "completion_policy": {"mode": VERIFIED_EVIDENCE_MODE},
        "criteria_met": {"T-1": True},
        "evidence": [".loop/evidence/evidence-iter1.json"],
        "false_completion": False,
    }), encoding="utf-8")
    return workspace


def _codes(report):
    return {issue["code"] for issue in report["issues"]}


def _mutate(local, path, value):
    """A deep copy of `local` with one dotted path replaced."""
    document = copy.deepcopy(local)
    cursor = document
    parts = path.split(".")
    for part in parts[:-1]:
        cursor = cursor[part]
    cursor[parts[-1]] = value
    return document


# --- the negative control ----------------------------------------------------


def test_compare_passes_on_a_self_projected_verdict(tmp_path):
    """D10.2's negative control: without it, every disagreement test below could be
    passing because the comparison is broken rather than because it works."""
    ws = _workspace(tmp_path)
    local = build_verdict(ws)
    assert local["evidence"], "the fixture must carry verified evidence to compare"
    report = compare_verdict(local, ws)
    assert report["ok"] is True
    assert report["issues"] == []
    assert all(facet["agrees"] is True for facet in report["compared"].values())


# --- D10.1: signature_checked is false everywhere, with no flag to flip ------


@pytest.mark.parametrize("path,value", [
    (None, None),                                             # agreement
    ("chain.head", "b" * 64),                                 # head disagreement
    ("terminal.state", "FailedBlocked"),                      # terminal disagreement
    ("run_id", "some-other-run"),                             # run_id disagreement
    ("evidence", [{"digest": "c" * 64, "code_digest": None, "policy_digest": None}]),
])
def test_compare_reports_signature_checked_false_on_every_report_branch(tmp_path, path, value):
    ws = _workspace(tmp_path)
    local = build_verdict(ws)
    attested = local if path is None else _mutate(local, path, value)
    assert compare_verdict(attested, ws)["signature_checked"] is False


def test_signature_checked_is_never_assigned_true_in_source():
    """AST-level, not a substring scan: every signature_checked value in the module
    is the constant False."""
    tree = ast.parse(Path(inspect.getsourcefile(verdict_module)).read_text(encoding="utf-8"))
    seen = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "signature_checked":
                    seen += 1
                    assert isinstance(value, ast.Constant) and value.value is False
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "signature_checked":
                    seen += 1
                    assert isinstance(node.value, ast.Constant) and node.value.value is False
    assert seen >= 1, "no signature_checked literal found — the pin would be vacuous"


# --- typed disagreements -----------------------------------------------------


def test_compare_head_disagreement_is_typed(tmp_path):
    ws = _workspace(tmp_path)
    local = build_verdict(ws)
    report = compare_verdict(_mutate(local, "chain.head", "b" * 64), ws)
    assert report["ok"] is False
    assert "verdict_head_disagreement" in _codes(report)
    assert report["compared"]["head"]["agrees"] is False


def test_compare_terminal_state_disagreement_is_typed(tmp_path):
    ws = _workspace(tmp_path)
    local = build_verdict(ws)
    report = compare_verdict(_mutate(local, "terminal.state", "FailedBudget"), ws)
    assert "verdict_terminal_disagreement" in _codes(report)


def test_compare_terminal_policy_disagreement_is_typed(tmp_path):
    """all_required vs all_required_verified_evidence must never read as agreement."""
    ws = _workspace(tmp_path)
    local = build_verdict(ws)
    assert local["terminal"]["completion_policy"] == VERIFIED_EVIDENCE_MODE
    report = compare_verdict(_mutate(local, "terminal.completion_policy", "all_required"), ws)
    assert "verdict_terminal_disagreement" in _codes(report)


def test_compare_false_completion_disagreement_is_typed(tmp_path):
    ws = _workspace(tmp_path)
    local = build_verdict(ws)
    report = compare_verdict(_mutate(local, "terminal.false_completion", True), ws)
    assert "verdict_terminal_disagreement" in _codes(report)


def test_compare_run_id_disagreement_is_typed(tmp_path):
    ws = _workspace(tmp_path)
    local = build_verdict(ws)
    report = compare_verdict(_mutate(local, "run_id", "not-this-run"), ws)
    assert "verdict_run_id_disagreement" in _codes(report)


def test_compare_evidence_digest_disagreement_is_typed(tmp_path):
    """Set equality, so BOTH directions are a disagreement."""
    ws = _workspace(tmp_path)
    local = build_verdict(ws)
    extra = [*local["evidence"],
             {"digest": "d" * 64, "code_digest": None, "policy_digest": None}]
    attested_superset = compare_verdict(_mutate(local, "evidence", extra), ws)
    assert "verdict_evidence_disagreement" in _codes(attested_superset)
    attested_subset = compare_verdict(_mutate(local, "evidence", []), ws)
    assert "verdict_evidence_disagreement" in _codes(attested_subset)


def test_compare_ignores_doctor_and_tool_differences(tmp_path):
    """F4, mechanical: doctor.validation_mode and tool.version live INSIDE the
    predicate, so the same run projects different bytes across environments. Comparing
    them would make an honest environment difference read as tampering."""
    ws = _workspace(tmp_path)
    local = build_verdict(ws)
    attested = _mutate(local, "tool", {"name": "loop-engineer", "version": "0.0.1-other"})
    attested = _mutate(attested, "doctor", {**attested["doctor"],
                                            "validation_mode": "structural-fallback",
                                            "ok": not attested["doctor"]["ok"]})
    report = compare_verdict(attested, ws)
    assert report["ok"] is True, report["issues"]
    assert "doctor" not in report["compared"] and "tool" not in report["compared"]


# --- typed refusals: bare predicate only -------------------------------------


@pytest.mark.parametrize("key", ["_type", "subject", "predicateType", "predicate"])
def test_compare_refuses_an_in_toto_statement(tmp_path, key):
    ws = _workspace(tmp_path)
    statement = {**build_verdict(ws), key: "anything"}
    with pytest.raises(VerdictError) as excinfo:
        compare_verdict(statement, ws)
    assert key in str(excinfo.value)
    assert "Statement" in str(excinfo.value)


def test_compare_refuses_a_gh_format_json_array_wrapper(tmp_path):
    ws = _workspace(tmp_path)
    with pytest.raises(VerdictError) as excinfo:
        compare_verdict([{"verificationResult": {}}], ws)
    assert "array" in str(excinfo.value)


def test_compare_refuses_a_gh_verification_result_object(tmp_path):
    ws = _workspace(tmp_path)
    for key in ("verificationResult", "attestation"):
        with pytest.raises(VerdictError) as excinfo:
            compare_verdict({key: {"statement": {}}}, ws)
        assert key in str(excinfo.value)


def test_compare_refuses_an_unrecognized_schema(tmp_path):
    ws = _workspace(tmp_path)
    local = build_verdict(ws)
    for document in ({**local, "schema": "loop-engineer/evidence@1"},
                     {k: v for k, v in local.items() if k != "schema"}):
        with pytest.raises(VerdictError):
            compare_verdict(document, ws)


def test_compare_refusal_names_the_unwrapping_step(tmp_path):
    """Every refusal tells the operator the documented jq path they skipped."""
    ws = _workspace(tmp_path)
    documents = [
        {**build_verdict(ws), "predicateType": "urn:loop-engineer:verdict:1"},
        [{"verificationResult": {}}],
        {"verificationResult": {}},
        {"schema": "something-else"},
        "not an object",
    ]
    for document in documents:
        with pytest.raises(VerdictError) as excinfo:
            compare_verdict(document, ws)
        assert _JQ_PATH in str(excinfo.value), document


def test_compare_refuses_a_non_object_document(tmp_path):
    ws = _workspace(tmp_path)
    for document in ("a string", 17, None, True):
        with pytest.raises(VerdictError):
            compare_verdict(document, ws)


def test_compare_treats_an_ancestor_head_as_a_disagreement(tmp_path):
    """Rule 4: a verdict projects ONE run. An attested head that is merely an ancestor
    of the local head is a different run's verdict — a fact to report, not to excuse.
    Ancestry is the doctor gate's question, where it is the question being asked."""
    ws = _workspace(tmp_path)
    local = build_verdict(ws)
    events = SQLiteEventStore(ws / ".loop" / "events.db")
    previous_head = local["chain"]["head"]
    events.append(_RUN_ID, "receipt_appended",
                  {"iteration_id": 1, "role": "write", "model": "m", "outcome": "ok"},
                  actor="test")
    grown = build_verdict(ws)
    assert grown["chain"]["head"] != previous_head
    report = compare_verdict(local, ws)          # local doc now carries the ANCESTOR head
    assert report["ok"] is False
    assert "verdict_head_disagreement" in _codes(report)


def test_compare_report_field_allowlist_holds(tmp_path):
    ws = _workspace(tmp_path)
    local = build_verdict(ws)
    report = compare_verdict(local, ws)
    assert set(report) == {"ok", "signature_checked", "compared", "issues"}
    assert set(report["compared"]) == {"run_id", "head", "terminal", "evidence"}
    assert set(COMPARISON_CODES) == {"verdict_head_disagreement", "verdict_terminal_disagreement",
                                     "verdict_run_id_disagreement", "verdict_evidence_disagreement"}
