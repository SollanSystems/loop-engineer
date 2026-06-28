"""Comparative A/B benchmark harness (M5 / G5) — measurement tool, not a bake-off.

Given TWO result inputs — a reference-harness run and a loop-engineer run, each a
JSON list of per-task outcome dicts — compute per-harness:

  * false-completion-rate (FCR)
  * repair-productivity (RP)
  * criteria-met rate

and the DELTA (swing, loop_engineer - reference) between the two harnesses.

The metric definitions are the EXISTING ones from ``reference/eval-suite.md`` §2:

  FCR = (iterations claiming success AND failing deterministic verify)
        / (iterations claiming success)

  RP  = (repair passes that measurably improved the score)
        / (total repair passes attempted)

This ships the *measurement* only. Live numbers are the operator's to run; the
harness asserts nothing about which system is better — it reports the swing and
lets the operator read it. See the "Comparative A/B Protocol" section of
``reference/eval-suite.md``.

Per-task outcome schema (the fields this harness reads; extra keys ignored)::

    {
      "task": "t1",
      "claimed_done": true,            # the loop self-asserted done
      "verification_passed": true,     # deterministic verify agreed
      "repairs": 2,                    # repair passes attempted
      "productive_repairs": 1,         # passes where after > before
      "criteria_met": 2,               # success_criteria satisfied
      "criteria_total": 3              # success_criteria total
    }

Run::

    python3 benchmark_harness.py <reference.json> <loop_engineer.json>

Prints the comparative report as JSON. Exit code is always 0 — this is a
measurement tool, not a gate; it makes no pass/fail claim.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _ratio(numerator: int, denominator: int) -> float:
    """Safe ratio: an undefined (0-denominator) rate is 0.0, never an error."""
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _validate_outcome(outcome: dict) -> None:
    """Reject malformed per-task outcomes at the data boundary.

    Bool flags must be real bools (a JSON string ``"false"`` is truthy and would
    silently corrupt the FCR); productive repairs and met criteria cannot exceed
    their denominators (a rate > 1.0 is impossible, not a data point).
    """
    task = outcome.get("task", "<unknown>")
    for flag in ("claimed_done", "verification_passed"):
        if flag in outcome and not isinstance(outcome[flag], bool):
            raise ValueError(
                f"task {task!r}: {flag} must be a bool, got "
                f"{type(outcome[flag]).__name__}"
            )

    repairs = int(outcome.get("repairs", 0))
    productive = int(outcome.get("productive_repairs", 0))
    if productive > repairs:
        raise ValueError(
            f"task {task!r}: productive_repairs ({productive}) exceeds "
            f"repairs ({repairs})"
        )

    criteria_met = int(outcome.get("criteria_met", 0))
    criteria_total = int(outcome.get("criteria_total", 0))
    if criteria_met > criteria_total:
        raise ValueError(
            f"task {task!r}: criteria_met ({criteria_met}) exceeds "
            f"criteria_total ({criteria_total})"
        )


def harness_metrics(outcomes: list[dict]) -> dict:
    """Per-harness FCR, repair-productivity, and criteria-met rate.

    Pure aggregation over a list of per-task outcome dicts. Uses the eval-suite
    definitions: FCR is over CLAIMED-done tasks, RP is over attempted repairs,
    criteria-met is over total declared criteria.
    """
    for o in outcomes:
        _validate_outcome(o)

    claimed = [o for o in outcomes if o.get("claimed_done")]
    false_completions = sum(
        1 for o in claimed if not o.get("verification_passed")
    )

    total_repairs = sum(int(o.get("repairs", 0)) for o in outcomes)
    productive_repairs = sum(int(o.get("productive_repairs", 0)) for o in outcomes)

    criteria_met = sum(int(o.get("criteria_met", 0)) for o in outcomes)
    criteria_total = sum(int(o.get("criteria_total", 0)) for o in outcomes)

    return {
        "tasks": len(outcomes),
        "claimed_done": len(claimed),
        "false_completions": false_completions,
        "false_completion_rate": _ratio(false_completions, len(claimed)),
        "repairs": total_repairs,
        "productive_repairs": productive_repairs,
        "repair_productivity": _ratio(productive_repairs, total_repairs),
        "criteria_met": criteria_met,
        "criteria_total": criteria_total,
        "criteria_met_rate": _ratio(criteria_met, criteria_total),
    }


_COMPARED_METRICS = (
    "false_completion_rate",
    "repair_productivity",
    "criteria_met_rate",
)


def compare(reference: list[dict], loop_engineer: list[dict]) -> dict:
    """Compare two harness runs; report per-harness metrics + the swing.

    The delta is ``loop_engineer - reference`` for each compared metric. A
    negative FCR swing means loop-engineer false-completes less; a positive
    repair-productivity / criteria-met swing means it does better on those.
    No verdict is rendered — the swing is the signal.

    The A/B protocol requires both runs to cover the IDENTICAL task set; a
    mismatch is operator error (the runs aren't comparable), so it raises
    rather than reporting a meaningless delta.
    """
    ref_tasks = {o.get("task") for o in reference}
    le_tasks = {o.get("task") for o in loop_engineer}
    if ref_tasks != le_tasks:
        raise ValueError(
            "task sets differ between the two harness runs; the A/B protocol "
            f"requires identical task sets (only in reference: "
            f"{sorted(ref_tasks - le_tasks)}; only in loop_engineer: "
            f"{sorted(le_tasks - ref_tasks)})"
        )

    m_ref = harness_metrics(reference)
    m_le = harness_metrics(loop_engineer)
    delta = {k: m_le[k] - m_ref[k] for k in _COMPARED_METRICS}
    return {
        "reference": m_ref,
        "loop_engineer": m_le,
        "delta": delta,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: benchmark_harness.py <reference.json> <loop_engineer.json>",
            file=sys.stderr,
        )
        return 2
    reference = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    loop_engineer = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    report = compare(reference, loop_engineer)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
