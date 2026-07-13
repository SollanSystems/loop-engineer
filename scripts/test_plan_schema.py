"""Contract tests for the standalone loop-engineer/plan@1 Plan IR."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from loop import plan
from loop.contract import ValidationModeError


ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "examples" / "plans" / "coverage-repair.plan.json"
CYCLIC = ROOT / "examples" / "plans" / "invalid" / "cyclic-dependency.plan.json"
MISSING_GOAL = ROOT / "examples" / "plans" / "invalid" / "missing-goal.plan.json"


def _issues() -> list[dict]:
    return []


def _core_type_parity_plan() -> dict:
    return {
        "schema": plan.PLAN_SCHEMA_ID,
        "goal": "validate required core types",
        "acceptance_criteria": [{"id": 7, "description": 8}],
        "tasks": [{"id": 123, "kind": None, "title": 456, "depends_on": ["a", 5, None]}],
        "terminal_state_mapping": {"done": "Succeeded"},
    }


def test_plan_schema_has_expected_id():
    schema = json.loads((ROOT / "schemas" / "plan.schema.json").read_text(encoding="utf-8"))
    assert schema["$id"] == "loop-engineer/plan@1"


def test_task_kinds_match_issue_vocabulary():
    assert plan.TASK_KINDS == ("agent", "tool", "gate", "approval", "join", "subloop", "human", "terminal")


def test_model_policy_vocabulary_matches_issue_56():
    assert plan.MODEL_POLICY_ROLES == ("read", "reason", "write", "verify")
    assert plan.MODEL_CAPABILITIES == ("fast_low_cost", "deep_reasoning", "code_generation", "independent_review")


def test_valid_golden_example_passes_jsonschema_mode():
    pytest.importorskip("jsonschema")
    report = plan.validate_plan(GOLDEN, mode="release")
    assert report["ok"] is True
    assert report["issues"] == []


def test_valid_golden_example_passes_structural_fallback(monkeypatch):
    monkeypatch.setitem(sys.modules, "jsonschema", None)
    assert plan.validate_plan(GOLDEN, mode="basic")["ok"] is True


def test_cyclic_example_fails_both_modes_with_cyclic_dependency_code(monkeypatch):
    pytest.importorskip("jsonschema")
    for mode in ("release", "basic"):
        if mode == "basic":
            monkeypatch.setitem(sys.modules, "jsonschema", None)
        report = plan.validate_plan(CYCLIC, mode=mode)
        assert report["ok"] is False
        assert any(issue["code"] == "cyclic_dependency" for issue in report["issues"])


def test_missing_goal_example_fails_both_modes(monkeypatch):
    pytest.importorskip("jsonschema")
    strict = plan.validate_plan(MISSING_GOAL, mode="release")
    assert any(issue["code"] == "schema_violation" and "goal" in issue["message"] for issue in strict["issues"])
    monkeypatch.setitem(sys.modules, "jsonschema", None)
    basic = plan.validate_plan(MISSING_GOAL, mode="basic")
    assert any(issue["code"] == "invalid_plan" for issue in basic["issues"])


def test_required_core_type_errors_fail_in_both_modes_and_cli(tmp_path, monkeypatch):
    pytest.importorskip("jsonschema")
    source = tmp_path / "core-type-errors.json"
    source.write_text(json.dumps(_core_type_parity_plan()), encoding="utf-8")

    for mode in ("release", "basic"):
        if mode == "basic":
            monkeypatch.setitem(sys.modules, "jsonschema", None)
        report = plan.validate_plan(source, mode=mode)
        assert report["ok"] is False
        result = subprocess.run(
            [sys.executable, "-B", "-m", "loop", "plan-lint", "--mode", mode, str(source)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1


def test_non_string_dependency_entries_are_reported_in_both_modes(tmp_path, monkeypatch):
    pytest.importorskip("jsonschema")
    source = tmp_path / "invalid-dependency-entries.json"
    source.write_text(json.dumps({
        "schema": plan.PLAN_SCHEMA_ID,
        "goal": "report invalid dependency entries",
        "acceptance_criteria": [{"id": "AC1", "description": "Invalid dependency entries are rejected."}],
        "tasks": [
            {"id": "a", "kind": "human", "title": "First", "depends_on": ["b", 5, None], "instructions": "Do work."},
            {"id": "b", "kind": "join", "title": "Join", "depends_on": [], "join_on": ["a", 5, None]},
        ],
        "terminal_state_mapping": {"done": "Succeeded"},
    }), encoding="utf-8")

    for mode in ("release", "basic"):
        if mode == "basic":
            monkeypatch.setitem(sys.modules, "jsonschema", None)
        report = plan.validate_plan(source, mode=mode)
        assert report["ok"] is False
        assert sum(issue["code"] == "invalid_dependency_entry" for issue in report["issues"]) == 4


def test_cycle_detection_unit_minimal():
    issues = _issues()
    plan._check_task_ids_and_dependencies([
        {"id": "a", "depends_on": ["c"]}, {"id": "b", "depends_on": ["a"]}, {"id": "c", "depends_on": ["b"]}
    ], GOLDEN, issues)
    assert any(issue["code"] == "cyclic_dependency" for issue in issues)


def test_duplicate_task_id_detected():
    issues = _issues()
    plan._check_task_ids_and_dependencies([{"id": "a", "depends_on": []}, {"id": "a", "depends_on": []}], GOLDEN, issues)
    assert any(issue["code"] == "duplicate_task_id" for issue in issues)


def test_unknown_dependency_detected():
    issues = _issues()
    plan._check_task_ids_and_dependencies([{"id": "a", "depends_on": ["missing"]}], GOLDEN, issues)
    assert any(issue["code"] == "unknown_dependency" for issue in issues)


def test_duplicate_criterion_id_detected():
    issues = _issues()
    plan._check_acceptance_criteria_ids([{"id": "AC1"}, {"id": "AC1"}], GOLDEN, issues)
    assert any(issue["code"] == "duplicate_criterion_id" for issue in issues)


@pytest.mark.parametrize("kind", plan.TASK_KINDS)
def test_each_kind_requires_its_field(kind):
    issues = _issues()
    plan._check_task_kind_fields([{"id": "task", "kind": kind}], GOLDEN, issues)
    assert any(issue["code"] == "missing_kind_field" for issue in issues)


def test_join_requires_at_least_two_upstream_tasks():
    issues = _issues()
    plan._check_task_kind_fields([{"id": "join", "kind": "join", "join_on": ["a"]}], GOLDEN, issues)
    assert any(issue["code"] == "invalid_join" for issue in issues)


def test_terminal_task_state_must_be_canonical():
    issues = _issues()
    plan._check_task_kind_fields([{"id": "end", "kind": "terminal", "terminal_state": "Done"}], GOLDEN, issues)
    assert any(issue["code"] == "invalid_terminal_state" for issue in issues)


def test_terminal_state_mapping_values_must_be_canonical():
    data = {"schema": plan.PLAN_SCHEMA_ID, "goal": "x", "acceptance_criteria": [{"id": "a", "description": "x"}], "tasks": [{"id": "a", "kind": "human", "title": "x", "depends_on": [], "instructions": "x"}], "terminal_state_mapping": {"x": "Finished"}}
    path = GOLDEN.parent / "temporary-not-used.json"
    issues = _issues()
    plan._structural_validate_plan(data, path, issues)
    assert any(issue["code"] == "invalid_terminal_state" for issue in issues)


def test_model_policy_rejects_unknown_role_and_capability():
    for policy in ({"orchestrate": "fast_low_cost"}, {"read": "gpt-5.5"}):
        issues = _issues()
        plan._structural_validate_plan({"schema": plan.PLAN_SCHEMA_ID, "goal": "x", "acceptance_criteria": [{"id": "a", "description": "x"}], "tasks": [{"id": "a", "kind": "human", "title": "x", "depends_on": [], "instructions": "x"}], "terminal_state_mapping": {"x": "Succeeded"}, "model_policy": policy}, GOLDEN, issues)
        assert any(issue["code"] == "invalid_model_policy" for issue in issues)


def test_approval_task_without_declared_gates_flagged():
    issues = _issues()
    plan._check_approval_gates({}, [{"id": "a", "kind": "approval", "approval_gate": "gate"}], GOLDEN, issues)
    assert any(issue["code"] == "missing_approval_gates" for issue in issues)


def test_approval_task_references_undeclared_gate():
    issues = _issues()
    plan._check_approval_gates({"approval_gates": ["a"]}, [{"id": "b", "kind": "approval", "approval_gate": "b"}], GOLDEN, issues)
    assert any(issue["code"] == "unknown_approval_gate" for issue in issues)


def test_completion_policy_reuses_shared_normalizer():
    issues = _issues()
    plan._structural_validate_plan({"schema": plan.PLAN_SCHEMA_ID, "goal": "x", "acceptance_criteria": [{"id": "a", "description": "x"}], "tasks": [{"id": "a", "kind": "human", "title": "x", "depends_on": [], "instructions": "x"}], "terminal_state_mapping": {"x": "Succeeded"}, "completion_policy": {"mode": "bogus"}}, GOLDEN, issues)
    assert any(issue["code"] == "invalid_plan" and "completion_policy" in issue["message"] for issue in issues)


def test_strict_mode_without_jsonschema_raises(monkeypatch):
    monkeypatch.setitem(sys.modules, "jsonschema", None)
    with pytest.raises(ValidationModeError):
        plan.validate_plan(GOLDEN, mode="strict")


def test_missing_file_reports_missing_file_issue(tmp_path):
    report = plan.validate_plan(tmp_path / "missing.json", mode="basic")
    assert any(issue["code"] == "missing_file" for issue in report["issues"])


def test_directory_target_reports_invalid_target(tmp_path):
    report = plan.validate_plan(tmp_path, mode="basic")
    assert any(issue["code"] == "invalid_target" for issue in report["issues"])


def test_malformed_json_reports_invalid_json(tmp_path):
    source = tmp_path / "malformed.json"
    source.write_text("{", encoding="utf-8")
    report = plan.validate_plan(source, mode="basic")
    assert any(issue["code"] == "invalid_json" for issue in report["issues"])


def test_schemas_checked_names_plan_schema_id():
    assert plan.validate_plan(GOLDEN, mode="basic")["schemas_checked"] == ["loop-engineer/plan@1"]
