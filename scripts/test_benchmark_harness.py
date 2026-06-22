"""Tests for the comparative benchmark harness (M5 / G5).

The harness reads TWO result inputs — a reference-harness run and a
loop-engineer run — each a list of per-task outcome dicts, and reports
per-harness false-completion-rate (FCR), repair-productivity (RP), and
criteria-met rate, plus the DELTA (swing) between the two harnesses.

These tests pin the EXISTING metric definitions from reference/eval-suite.md:
  FCR = (claimed_done AND NOT verification_passed) / (claimed_done)
  RP  = (productive_repairs) / (repairs)
"""

from __future__ import annotations

import benchmark_harness as bh


def _reference_outcomes() -> list[dict]:
    # Reference harness: weaker self-verification -> some false completions,
    # churny repairs, fewer criteria met.
    return [
        {
            "task": "t1",
            "claimed_done": True,
            "verification_passed": False,  # false completion
            "repairs": 2,
            "productive_repairs": 0,
            "criteria_met": 1,
            "criteria_total": 3,
        },
        {
            "task": "t2",
            "claimed_done": True,
            "verification_passed": True,
            "repairs": 2,
            "productive_repairs": 1,
            "criteria_met": 2,
            "criteria_total": 3,
        },
        {
            "task": "t3",
            "claimed_done": True,
            "verification_passed": False,  # false completion
            "repairs": 0,
            "productive_repairs": 0,
            "criteria_met": 1,
            "criteria_total": 3,
        },
        {
            "task": "t4",
            "claimed_done": False,
            "verification_passed": False,
            "repairs": 0,
            "productive_repairs": 0,
            "criteria_met": 0,
            "criteria_total": 3,
        },
    ]


def _loop_engineer_outcomes() -> list[dict]:
    # loop-engineer: deterministic gating -> no false completions, productive
    # repairs, more criteria met.
    return [
        {
            "task": "t1",
            "claimed_done": True,
            "verification_passed": True,
            "repairs": 1,
            "productive_repairs": 1,
            "criteria_met": 3,
            "criteria_total": 3,
        },
        {
            "task": "t2",
            "claimed_done": True,
            "verification_passed": True,
            "repairs": 2,
            "productive_repairs": 2,
            "criteria_met": 3,
            "criteria_total": 3,
        },
        {
            "task": "t3",
            "claimed_done": True,
            "verification_passed": True,
            "repairs": 1,
            "productive_repairs": 1,
            "criteria_met": 2,
            "criteria_total": 3,
        },
        {
            "task": "t4",
            "claimed_done": True,
            "verification_passed": True,
            "repairs": 0,
            "productive_repairs": 0,
            "criteria_met": 3,
            "criteria_total": 3,
        },
    ]


def test_per_harness_fcr_matches_definition():
    # Arrange
    ref = _reference_outcomes()
    le = _loop_engineer_outcomes()

    # Act
    m_ref = bh.harness_metrics(ref)
    m_le = bh.harness_metrics(le)

    # Assert: reference has 2 of 3 claimed-done that fail verify -> FCR 2/3.
    assert m_ref["false_completion_rate"] == 2 / 3
    # loop-engineer never false-completes.
    assert m_le["false_completion_rate"] == 0.0


def test_per_harness_repair_productivity_matches_definition():
    # Arrange
    ref = _reference_outcomes()
    le = _loop_engineer_outcomes()

    # Act
    m_ref = bh.harness_metrics(ref)
    m_le = bh.harness_metrics(le)

    # Assert: reference productive 1 of 4 repairs; LE productive 4 of 4.
    assert m_ref["repair_productivity"] == 1 / 4
    assert m_le["repair_productivity"] == 1.0


def test_per_harness_criteria_met_rate():
    # Arrange
    ref = _reference_outcomes()
    le = _loop_engineer_outcomes()

    # Act
    m_ref = bh.harness_metrics(ref)
    m_le = bh.harness_metrics(le)

    # Assert: reference met 4 of 12 criteria; LE met 11 of 12.
    assert m_ref["criteria_met_rate"] == 4 / 12
    assert m_le["criteria_met_rate"] == 11 / 12


def test_compare_emits_per_harness_and_deltas():
    # Arrange
    ref = _reference_outcomes()
    le = _loop_engineer_outcomes()

    # Act
    report = bh.compare(ref, le)

    # Assert: both per-harness blocks present.
    assert report["reference"]["false_completion_rate"] == 2 / 3
    assert report["loop_engineer"]["false_completion_rate"] == 0.0

    # The swing (loop_engineer - reference) is the comparative signal.
    delta = report["delta"]
    # LE shows LOWER false-completion (a negative swing).
    assert delta["false_completion_rate"] == 0.0 - (2 / 3)
    assert delta["false_completion_rate"] < 0
    # LE shows HIGHER repair-productivity (a positive swing).
    assert delta["repair_productivity"] == 1.0 - (1 / 4)
    assert delta["repair_productivity"] > 0
    # LE shows HIGHER criteria-met rate.
    assert delta["criteria_met_rate"] == (11 / 12) - (4 / 12)
    assert delta["criteria_met_rate"] > 0


def test_empty_denominators_are_zero_not_error():
    # Arrange: nothing claimed done, no repairs, no criteria.
    outcomes = [
        {
            "task": "x",
            "claimed_done": False,
            "verification_passed": False,
            "repairs": 0,
            "productive_repairs": 0,
            "criteria_met": 0,
            "criteria_total": 0,
        }
    ]

    # Act
    m = bh.harness_metrics(outcomes)

    # Assert: undefined ratios collapse to 0.0, never a ZeroDivisionError.
    assert m["false_completion_rate"] == 0.0
    assert m["repair_productivity"] == 0.0
    assert m["criteria_met_rate"] == 0.0
