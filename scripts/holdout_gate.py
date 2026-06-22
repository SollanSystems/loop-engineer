"""Held-out verifier split — the runnable core of *measured* false-completion.

A loop can game a verifier it can see. So acceptance checks are split:

  * visible  — the loop sees these and optimizes against them during the run.
  * holdout  — withheld until terminal verification by this independent gate.

A loop may declare ``Succeeded`` only if the HOLDOUT set passes. Passing the
visible set while failing the holdout set is the measurable *false-completion*
event (``false_completion: true``) — the signature of overfitting to the tests
the agent could see. Aggregated across runs, that flag IS the
false-completion-rate metric (no longer self-reported).

This ships as composable tooling, not a runtime: a loop calls it at its terminal
gate. Pair it with ``anticheat_scan.py`` for the trajectory sweep.

Manifest schema (JSON)::

    {
      "visible": [{"id": "unit", "cmd": "pytest tests/unit -q"}],
      "holdout": [{"id": "spec", "cmd": "pytest tests/holdout -q"}]
    }

The manifest is trusted, operator-authored config (like a Makefile target); its
commands run in a shell. Do not feed it untrusted input.

Run::

    python3 holdout_gate.py <manifest.json> [--cwd DIR]

Prints the verdict as JSON. Exit code 0 iff verdict == "Succeeded".
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SUCCEEDED = "Succeeded"
FAILED_UNVERIFIABLE = "FailedUnverifiable"
# Non-terminal: a precondition is unmet (keep working, or fix the gate config).
NOT_READY = "NotReady"


def _all_passed(results: list[dict]) -> bool:
    return all(r["passed"] for r in results)


def decide(visible: list[dict], holdout: list[dict]) -> dict:
    """Pure verdict from pre-computed check results — never executes anything.

    ``visible`` / ``holdout`` are lists of ``{"id": str, "passed": bool}``.

    Rules:
      * visible not all green        -> NotReady  (loop shouldn't certify yet)
      * holdout empty                -> NotReady  (cannot certify without holdout)
      * visible green + holdout green -> Succeeded
      * visible green + holdout red   -> FailedUnverifiable (false completion)
    """
    passed_visible = _all_passed(visible)
    passed_holdout = bool(holdout) and _all_passed(holdout)

    if not passed_visible:
        verdict, reason = NOT_READY, "visible gate not green — keep working or repair"
    elif not holdout:
        verdict, reason = NOT_READY, "no holdout checks defined — cannot certify Succeeded"
    elif passed_holdout:
        verdict, reason = SUCCEEDED, "visible and holdout gates both green"
    else:
        verdict, reason = (
            FAILED_UNVERIFIABLE,
            "visible passed but holdout failed — false completion",
        )

    return {
        "verdict": verdict,
        "reason": reason,
        "passed_visible": passed_visible,
        "passed_holdout": passed_holdout,
        "false_completion": passed_visible and bool(holdout) and not passed_holdout,
        "visible": visible,
        "holdout": holdout,
    }


def _run_one(check: dict, cwd: str | None) -> dict:
    proc = subprocess.run(
        check["cmd"], shell=True, cwd=cwd, capture_output=True, text=True
    )
    return {
        "id": check["id"],
        "passed": proc.returncode == 0,
        "returncode": proc.returncode,
    }


def run_manifest(manifest: dict, cwd: str | None = None) -> dict:
    """Execute a visible/holdout manifest and return the verdict dict."""
    visible = [_run_one(c, cwd) for c in manifest.get("visible", [])]
    holdout = [_run_one(c, cwd) for c in manifest.get("holdout", [])]
    return decide(visible, holdout)


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: holdout_gate.py <manifest.json> [--cwd DIR]", file=sys.stderr)
        return 2
    manifest = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    cwd = argv[argv.index("--cwd") + 1] if "--cwd" in argv else None
    result = run_manifest(manifest, cwd)
    print(json.dumps(result, indent=2))
    return 0 if result["verdict"] == SUCCEEDED else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
