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


# --- M4-CLI item 9: malformed ledger lines are tolerated, not fatal ----------


def test_read_skips_malformed_line_without_crashing(tmp_path):
    ledger = tmp_path / "rollout.jsonl"
    rollout_ledger.append(_candidate(id="cand-1", productive=True), ledger)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write("this is not json\n")
    rollout_ledger.append(_candidate(id="cand-2", productive=False), ledger)

    # Must not raise on the corrupt middle line.
    records = rollout_ledger.read(ledger)

    ids = [r["id"] for r in records]
    assert ids == ["cand-1", "cand-2"]


def test_read_skips_valid_json_that_is_not_an_object(tmp_path):
    ledger = tmp_path / "rollout.jsonl"
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write("[1, 2, 3]\n")  # valid JSON, but not a ledger record object

    records = rollout_ledger.read(ledger)

    assert records == []


def test_read_warns_to_stderr_on_malformed_line(tmp_path, capsys):
    ledger = tmp_path / "rollout.jsonl"
    rollout_ledger.append(_candidate(id="cand-1"), ledger)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write("{broken\n")

    rollout_ledger.read(ledger)

    err = capsys.readouterr().err
    assert err.strip(), "a malformed line must warn to stderr"
    assert "malformed" in err.lower() or "skip" in err.lower()


def test_summarize_counts_malformed_lines(tmp_path):
    ledger = tmp_path / "rollout.jsonl"
    rollout_ledger.append(_candidate(id="cand-1", productive=True), ledger)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write("garbage line\n")
        fh.write("also not json {,,}\n")
    rollout_ledger.append(_candidate(id="cand-2", productive=True), ledger)

    summary = rollout_ledger.summarize(ledger)

    # Valid candidates are summarized; malformed lines are counted separately.
    assert summary["count"] == 2
    assert summary["malformed"] == 2
    assert summary["repair_productivity"] == 1.0
