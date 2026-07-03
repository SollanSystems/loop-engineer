"""Append-only JSONL rollout ledger — the durable record of loop candidates (G8).

A rollout/repair loop produces a stream of *candidates*: each is a proposed
change (a repair, a harden, a config mutation) that the loop scored and
adjudicated against the prior winner. This ledger is where that stream lands —
one JSON object per line, appended and never rewritten, so the lineage survives
compaction and session loss.

Each record carries EXACTLY these 7 fields:

  * ``id``                          — the candidate's id.
  * ``parent``                      — parent candidate id, or ``None`` for a root.
  * ``verdict``                     — the loop's adjudication of this candidate.
  * ``score``                       — the candidate's measured score (or ``None``).
  * ``score_delta``                 — score vs the parent / prior winner.
  * ``coherent_with_prior_winner``  — does it preserve the prior winner's gains?
  * ``productive``                  — did it *measurably* improve the score?

``productive`` is the per-candidate signal behind the suite's
repair-productivity metric: a repair that does not move the score is churn, not
progress. ``summarize`` aggregates that signal into the productive fraction.

This ships as composable tooling, not a runtime: a loop calls ``append`` at each
adjudication and ``summarize`` when it wants the repair-productivity readout.

Run::

    python3 rollout_ledger.py <ledger.jsonl>

Prints the summary as JSON.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _warn(message: str) -> None:
    print(f"rollout_ledger: {message}", file=sys.stderr)

RECORD_FIELDS = (
    "id",
    "parent",
    "verdict",
    "score",
    "score_delta",
    "coherent_with_prior_winner",
    "productive",
)


def _normalize(record: dict) -> dict:
    """Project a record onto exactly the 7 ledger fields, in canonical order."""
    missing = [f for f in RECORD_FIELDS if f not in record]
    if missing:
        raise KeyError(f"rollout record missing fields: {missing}")
    return {field: record[field] for field in RECORD_FIELDS}


def append(record: dict, path: str | Path) -> dict:
    """Append one candidate record as a single JSONL line. Returns the written record."""
    written = _normalize(record)
    line = json.dumps(written, ensure_ascii=False)
    with Path(path).open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return written


def _read_with_stats(path: str | Path) -> tuple[list[dict], int]:
    """Read the ledger, tolerating corruption. Returns ``(records, malformed)``.

    A ledger is append-only JSONL that may have been truncated mid-write or hand-
    edited, so a single bad line must not lose the whole lineage. A line that is
    not a JSON object (unparseable, or valid JSON that is not a dict) is skipped
    with a stderr warning and counted, never raised.
    """
    p = Path(path)
    if not p.exists():
        return [], 0
    records: list[dict] = []
    malformed = 0
    for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            malformed += 1
            _warn(f"skipping malformed ledger line {lineno}: {exc}")
            continue
        if not isinstance(record, dict):
            malformed += 1
            _warn(f"skipping malformed ledger line {lineno}: not a JSON object")
            continue
        records.append(record)
    return records, malformed


def read(path: str | Path) -> list[dict]:
    """Return every valid record in the ledger, in append order. Empty if absent.

    Malformed lines are skipped (with a stderr warning), never fatal.
    """
    records, _ = _read_with_stats(path)
    return records


def summarize(path: str | Path) -> dict:
    """Compute repair-productivity (productive fraction), the candidate count, and
    the number of malformed lines skipped."""
    records, malformed = _read_with_stats(path)
    count = len(records)
    productive = sum(1 for r in records if r.get("productive"))
    repair_productivity = productive / count if count else 0.0
    return {
        "count": count,
        "productive": productive,
        "repair_productivity": repair_productivity,
        "malformed": malformed,
    }


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: rollout_ledger.py <ledger.jsonl>", file=sys.stderr)
        return 2
    print(json.dumps(summarize(argv[0]), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
