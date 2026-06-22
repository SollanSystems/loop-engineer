"""Tests for the append-only rollout ledger (G8)."""

from __future__ import annotations

import rollout_ledger

RECORD_FIELDS = {
    "id",
    "parent",
    "verdict",
    "score",
    "score_delta",
    "coherent_with_prior_winner",
    "productive",
}


def _candidate(**overrides) -> dict:
    base = {
        "id": "cand-1",
        "parent": None,
        "verdict": "Succeeded",
        "score": 0.80,
        "score_delta": 0.0,
        "coherent_with_prior_winner": True,
        "productive": False,
    }
    base.update(overrides)
    return base


def test_append_then_read_round_trips_records(tmp_path):
    # Arrange
    ledger = tmp_path / "rollout.jsonl"
    first = _candidate(id="cand-1", parent=None, score=0.80, productive=False)
    second = _candidate(
        id="cand-2", parent="cand-1", score=0.90, score_delta=0.10, productive=True
    )

    # Act
    rollout_ledger.append(first, ledger)
    rollout_ledger.append(second, ledger)
    records = rollout_ledger.read(ledger)

    # Assert
    assert len(records) == 2
    assert records[0]["id"] == "cand-1"
    assert records[1]["id"] == "cand-2"
    assert records[1]["parent"] == "cand-1"


def test_every_record_has_exactly_the_seven_fields(tmp_path):
    # Arrange
    ledger = tmp_path / "rollout.jsonl"
    rollout_ledger.append(_candidate(id="cand-1"), ledger)
    rollout_ledger.append(_candidate(id="cand-2", parent="cand-1"), ledger)

    # Act
    records = rollout_ledger.read(ledger)

    # Assert
    for record in records:
        assert set(record.keys()) == RECORD_FIELDS


def test_summarize_computes_productive_fraction_and_count(tmp_path):
    # Arrange
    ledger = tmp_path / "rollout.jsonl"
    rollout_ledger.append(_candidate(id="cand-1", productive=False), ledger)
    rollout_ledger.append(_candidate(id="cand-2", productive=True), ledger)
    rollout_ledger.append(_candidate(id="cand-3", productive=True), ledger)

    # Act
    summary = rollout_ledger.summarize(ledger)

    # Assert
    assert summary["count"] == 3
    assert summary["repair_productivity"] == 2 / 3


def test_append_is_append_only_and_preserves_prior_lines(tmp_path):
    # Arrange
    ledger = tmp_path / "rollout.jsonl"
    rollout_ledger.append(_candidate(id="cand-1"), ledger)

    # Act
    rollout_ledger.append(_candidate(id="cand-2", parent="cand-1"), ledger)

    # Assert
    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_summarize_of_empty_ledger_is_zero(tmp_path):
    # Arrange
    ledger = tmp_path / "rollout.jsonl"

    # Act
    summary = rollout_ledger.summarize(ledger)

    # Assert
    assert summary["count"] == 0
    assert summary["repair_productivity"] == 0.0
