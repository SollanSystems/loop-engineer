# scripts/runtime_monitor.py
"""Observe a RUNNING agent loop and surface an intervention recommendation.

Importable (`health_report`) + CLI: given a path to a `.loop/` directory, read
`state.json` + `RUNLOG.md` and emit a JSON health report:

    {stalled, repair_churn, budget_overrun, recommendation, evidence}

This is a read-only observer over an in-flight loop's externalized state — the
companion to loop-run (which advances the machine) and loop-repair (which
reacts to a red gate). It never mutates the loop; it recommends.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

# Detection thresholds (see skills/loop-runtime-monitor/reference/patterns.md).
STALL_MIN_ITERS = 3          # same active_task, no score progress, this many iters
CHURN_MIN_ATTEMPTS = 3       # repair attempts with no score improvement
SCORE_EPSILON = 1e-9         # smallest score move counted as "progress"

_ITER_RE = re.compile(
    r"active_task\s*=\s*(?P<task>\S+).*?best_score\s*=\s*(?P<score>[0-9.]+)",
    re.IGNORECASE,
)
_ATTEMPT_RE = re.compile(r"attempt\s*=\s*(?P<n>\d+)", re.IGNORECASE)
_PRODUCTIVE_RE = re.compile(r"productive\s*=\s*(?P<v>true|false)", re.IGNORECASE)


def _parse_runlog(text: str) -> list[dict]:
    """Extract per-iteration facts from RUNLOG.md lines. Facts only — no judgment."""
    rows: list[dict] = []
    for line in text.splitlines():
        m = _ITER_RE.search(line)
        if not m:
            continue
        attempt = _ATTEMPT_RE.search(line)
        productive = _PRODUCTIVE_RE.search(line)
        rows.append(
            {
                "task": m.group("task"),
                "score": float(m.group("score")),
                "attempt": int(attempt.group("n")) if attempt else None,
                "productive": (
                    productive.group("v").lower() == "true" if productive else None
                ),
            }
        )
    return rows


def _detect_stall(rows: list[dict]) -> tuple[bool, str]:
    if len(rows) < STALL_MIN_ITERS:
        return False, ""
    tail = rows[-STALL_MIN_ITERS:]
    same_task = len({r["task"] for r in tail}) == 1
    score_span = max(r["score"] for r in tail) - min(r["score"] for r in tail)
    if same_task and score_span <= SCORE_EPSILON:
        return True, (
            f"active_task '{tail[-1]['task']}' unchanged across "
            f"{STALL_MIN_ITERS} iterations with best_score flat at {tail[-1]['score']}"
        )
    return False, ""


def _detect_repair_churn(rows: list[dict]) -> tuple[bool, str]:
    repairs = [r for r in rows if r["attempt"] is not None]
    if len(repairs) < CHURN_MIN_ATTEMPTS:
        return False, ""
    tail = repairs[-CHURN_MIN_ATTEMPTS:]
    none_productive = all(r["productive"] is False for r in tail)
    score_span = max(r["score"] for r in tail) - min(r["score"] for r in tail)
    if none_productive and score_span <= SCORE_EPSILON:
        return True, (
            f"{len(tail)} consecutive repair attempts on '{tail[-1]['task']}' with "
            f"productive=false and best_score flat at {tail[-1]['score']}"
        )
    return False, ""


def _detect_budget_overrun(state: dict) -> tuple[bool, str]:
    budget = state.get("budget_remaining")
    if not isinstance(budget, dict):
        return False, ""
    exhausted = [
        k
        for k, v in budget.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v <= 0
    ]
    if exhausted:
        return True, f"budget_remaining exhausted: {', '.join(sorted(exhausted))} <= 0"
    return False, ""


def _recommend(stalled: bool, churn: bool, overrun: bool) -> str:
    """Map the worst active signal to an intervention rung (loop-run's ladder)."""
    if overrun:
        return "approval"   # only a human can extend budget
    if churn:
        return "revert"     # stop stacking bad patches; restore best-known-good
    if stalled:
        return "replan"     # the execution graph, not the same patch
    return "continue"


def health_report(loop_dir) -> dict:
    """Read a `.loop/` dir's state.json + RUNLOG.md → a JSON health report."""
    loop_dir = pathlib.Path(loop_dir)
    state_raw = (loop_dir / "state.json").read_text(encoding="utf-8")
    state = json.loads(state_raw)
    runlog = (loop_dir / "RUNLOG.md").read_text(encoding="utf-8")
    rows = _parse_runlog(runlog)

    stalled, stall_ev = _detect_stall(rows)
    churn, churn_ev = _detect_repair_churn(rows)
    overrun, overrun_ev = _detect_budget_overrun(state)

    evidence = [e for e in (stall_ev, churn_ev, overrun_ev) if e]
    return {
        "active_task": state.get("active_task"),
        "iterations_observed": len(rows),
        "stalled": stalled,
        "repair_churn": churn,
        "budget_overrun": overrun,
        "recommendation": _recommend(stalled, churn, overrun),
        "evidence": evidence,
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: runtime_monitor.py <path-to-.loop-dir>", file=sys.stderr)
        return 2
    report = health_report(argv[0])
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
