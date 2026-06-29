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

# When run as a documented standalone script (`python3 scripts/runtime_monitor.py
# <loop>`), sys.path[0] is scripts/ — not the repo root — so the sibling `loop`
# package is not importable and we would silently use the degraded fallback
# resolver below (which only finds a root RUNLOG.md, missing the canonical
# `.loop/RUNLOG.md` layout). Put the repo root on sys.path first so the real
# dual-location resolver is used whenever the package ships alongside.
_REPO_ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    from loop.paths import resolve_loop_paths
except ImportError:  # pragma: no cover - direct script copy outside repo root
    def resolve_loop_paths(target):
        class _Paths:
            def __init__(self, target):
                loop_dir = pathlib.Path(target)
                workspace = loop_dir.parent if loop_dir.name == ".loop" else loop_dir
                self.workspace = workspace
                self.loop_dir = workspace / ".loop"
                self.state = self.loop_dir / "state.json"
                self.runlog = workspace / "RUNLOG.md"

        return _Paths(target)

# Detection thresholds (see skills/loop-runtime-monitor/reference/patterns.md).
STALL_MIN_ITERS = 3          # same active_task, no score progress, this many iters
CHURN_MIN_ATTEMPTS = 3       # repair attempts with no score improvement
SCORE_EPSILON = 1e-9         # smallest score move counted as "progress"

_ITER_RE = re.compile(
    r"active_task\s*=\s*(?P<task>\S+).*?best_score\s*=\s*(?P<score>\S+)",
    re.IGNORECASE,
)


def _parse_score(token: str) -> float | None:
    """Parse a best_score token as a float. Malformed tokens (e.g. '1.2.3')
    fail safe to None — the row is dropped, never a crash. Handles signs and
    scientific notation (`-0.5`, `1e-3`) that the prior `[0-9.]+` capture lost."""
    try:
        value = float(token)
    except ValueError:
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return value
_ATTEMPT_RE = re.compile(r"attempt\s*=\s*(?P<n>\d+)", re.IGNORECASE)
_PRODUCTIVE_RE = re.compile(r"productive\s*=\s*(?P<v>true|false)", re.IGNORECASE)


def _parse_runlog(text: str) -> list[dict]:
    """Extract per-iteration facts from RUNLOG.md lines. Facts only — no judgment."""
    rows: list[dict] = []
    for line in text.splitlines():
        m = _ITER_RE.search(line)
        if not m:
            continue
        score = _parse_score(m.group("score"))
        if score is None:
            continue
        attempt = _ATTEMPT_RE.search(line)
        productive = _PRODUCTIVE_RE.search(line)
        rows.append(
            {
                "task": m.group("task"),
                "score": score,
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
    same_task = len({r["task"] for r in tail}) == 1
    none_productive = all(r["productive"] is False for r in tail)
    score_span = max(r["score"] for r in tail) - min(r["score"] for r in tail)
    if same_task and none_productive and score_span <= SCORE_EPSILON:
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


def _missing_report(paths, missing: list[str]) -> dict:
    return {
        "status": "error",
        "error": "missing_loop_state" if any(m.endswith("state.json") for m in missing) else "missing_loop_artifact",
        "missing": missing,
        "active_task": None,
        "iterations_observed": 0,
        "stalled": False,
        "repair_churn": False,
        "budget_overrun": False,
        "recommendation": "replan",
        "evidence": [f"missing {m}" for m in missing],
        "paths": {"state": str(paths.state), "runlog": str(paths.runlog)},
    }


def health_report(loop_dir) -> dict:
    """Read loop state + RUNLOG.md → a JSON health report.

    Accepts either the workspace root or the `.loop/` directory. Canonical
    repo-OS layout stores RUNLOG.md at workspace root and state under `.loop/`.
    Missing/partial state returns an actionable structured report, not a
    traceback.
    """
    paths = resolve_loop_paths(loop_dir)
    missing = [str(p.name) for p in (paths.state, paths.runlog) if not p.exists()]
    if missing:
        return _missing_report(paths, missing)

    try:
        state = json.loads(paths.state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "error",
            "error": "invalid_loop_state",
            "active_task": None,
            "iterations_observed": 0,
            "stalled": False,
            "repair_churn": False,
            "budget_overrun": False,
            "recommendation": "replan",
            "evidence": [f"invalid state.json: {exc}"],
            "paths": {"state": str(paths.state), "runlog": str(paths.runlog)},
        }
    if not isinstance(state, dict):
        return {
            "status": "error",
            "error": "invalid_loop_state",
            "active_task": None,
            "iterations_observed": 0,
            "stalled": False,
            "repair_churn": False,
            "budget_overrun": False,
            "recommendation": "replan",
            "evidence": ["state.json is not an object"],
            "paths": {"state": str(paths.state), "runlog": str(paths.runlog)},
        }

    runlog = paths.runlog.read_text(encoding="utf-8")
    rows = _parse_runlog(runlog)

    stalled, stall_ev = _detect_stall(rows)
    churn, churn_ev = _detect_repair_churn(rows)
    overrun, overrun_ev = _detect_budget_overrun(state)

    evidence = [e for e in (stall_ev, churn_ev, overrun_ev) if e]
    return {
        "status": "ok",
        "active_task": state.get("active_task"),
        "iterations_observed": len(rows),
        "stalled": stalled,
        "repair_churn": churn,
        "budget_overrun": overrun,
        "recommendation": _recommend(stalled, churn, overrun),
        "evidence": evidence,
        "paths": {"state": str(paths.state), "runlog": str(paths.runlog)},
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
