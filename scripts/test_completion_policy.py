"""Shared completion-policy semantics are deterministic and fail closed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from loop.completion import (
    CompletionPolicyError,
    criteria_satisfy_completion,
    normalize_completion_policy,
    unmet_required_criteria,
)
from loop.contract import _check_terminal_contradiction, _validate_state, _validate_terminal


def test_all_required_policy_requires_a_nonempty_all_true_map():
    assert criteria_satisfy_completion({"a": True, "b": True}) is True
    assert criteria_satisfy_completion({"a": True, "b": False}) is False
    assert criteria_satisfy_completion({}) is False
    assert criteria_satisfy_completion({"a": 1}) is False


def test_policy_normalization_is_explicit_and_strict():
    assert normalize_completion_policy() == {"mode": "all_required"}
    assert normalize_completion_policy("all_required") == {"mode": "all_required"}
    assert normalize_completion_policy({"mode": "all_required"}) == {"mode": "all_required"}
    with pytest.raises(CompletionPolicyError):
        normalize_completion_policy({"mode": "any_required"})
    with pytest.raises(CompletionPolicyError):
        normalize_completion_policy({"mode": "all_required", "threshold": 1})


def test_unmet_criteria_are_stable_and_human_readable():
    assert unmet_required_criteria({"b": False, "a": True, "c": None}) == ("b", "c")


def test_contract_rejects_partial_success_claim(tmp_path: Path):
    issues: list[dict] = []
    _check_terminal_contradiction(
        {
            "schema": "loop-engineer/terminal@1",
            "state": "Succeeded",
            "criteria_met": {"one": True, "two": False},
            "completion_policy": {"mode": "all_required"},
            "evidence": ["artifact.json"],
            "false_completion": False,
        },
        tmp_path / "terminal_state.json",
        issues,
    )
    assert any(issue["code"] == "contradictory_terminal" for issue in issues)
    assert any("two" in issue["message"] for issue in issues)


def test_terminal_fallback_validation_rejects_bad_policy_and_evidence(tmp_path: Path):
    issues: list[dict] = []
    _validate_terminal(
        {
            "schema": "loop-engineer/terminal@1",
            "state": "FailedUnverifiable",
            "criteria_met": {"one": False},
            "completion_policy": {"mode": "any_required"},
            "evidence": ["", "duplicate", "duplicate"],
            "false_completion": False,
        },
        tmp_path / "terminal_state.json",
        issues,
    )
    messages = "\n".join(issue["message"] for issue in issues)
    assert "completion_policy" in messages
    assert "non-empty strings" in messages
    assert "unique" in messages


def test_state_fallback_validation_accepts_legacy_decimal_strings_only(tmp_path: Path):
    base = {
        "schema": "loop-engineer/state@1",
        "state": "planned",
        "plan_version": 1,
        "budget_remaining": {},
    }

    for iteration_id in (0, 7, "0", "7"):
        issues: list[dict] = []
        _validate_state({**base, "iteration_id": iteration_id}, tmp_path / "state.json", issues)
        assert not any(issue["code"] == "invalid_state" for issue in issues)

    for iteration_id in (-1, True, "-1", "1.5", "next"):
        issues = []
        _validate_state({**base, "iteration_id": iteration_id}, tmp_path / "state.json", issues)
        assert any(issue["code"] == "invalid_state" for issue in issues)

def test_explicit_null_policy_is_accepted_in_both_validation_modes(tmp_path: Path):
    # An explicit "completion_policy": null must mean the same thing as an
    # absent field in BOTH validation modes — a record must not be doctor-clean
    # on a machine without the jsonschema extra and doctor-dirty on one with it.
    record = {
        "schema": "loop-engineer/terminal@1",
        "state": "Succeeded",
        "criteria_met": {"one": True},
        "completion_policy": None,
        "evidence": ["artifact.json"],
        "false_completion": False,
    }
    issues: list[dict] = []
    _validate_terminal(record, tmp_path / "terminal_state.json", issues)
    assert issues == []

    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(
        (Path(__file__).resolve().parents[1] / "schemas" / "terminal.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.validate(record, schema)
