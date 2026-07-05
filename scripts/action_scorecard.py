#!/usr/bin/env python3
"""Scorecard renderer for the loop-engineer GitHub Action.

Invoked by the composite action from its own checkout:

    python "${{ github.action_path }}/scripts/action_scorecard.py" <inspect.json> <fail-under>

The inspect score is an ADVISORY heuristic — a determined author can game it.
`loop doctor` is the hard gate; this only summarizes and optionally fails the job
when the score dips below an author-set floor.

Exit codes:
  0  scorecard rendered (verdict may be weak → a ::warning, still a pass)
  1  the inspect score is below <fail-under>
  2  bad input (non-integer/out-of-range fail-under, missing/malformed inspect.json,
     wrong argument count) — distinct from the fail-under-breach code
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

MARKER = "<!-- loop-engineer-scorecard -->"


def parse_fail_under(raw: str) -> int:
    """Parse the fail-under threshold as an integer in [0, 100].

    Raises ValueError on anything else (``"80.5"``, ``"abc"``, ``""``, ``"101"``)
    so the caller can emit one clear ::error instead of a raw traceback.
    """
    try:
        value = int(raw.strip())
    except (AttributeError, ValueError):
        raise ValueError(f"fail-under-score must be an integer 0-100, got {raw!r}")
    if not 0 <= value <= 100:
        raise ValueError(f"fail-under-score must be in [0, 100], got {value}")
    return value


def render_summary(report: dict[str, Any]) -> str:
    """Render the Markdown scorecard. The sticky marker leads the body so the
    PR-comment step can find-and-edit its own prior comment in place."""
    score = report.get("score", 0)
    verdict = report.get("verdict", "?")
    gaps = report.get("gaps", [])
    lines = [
        MARKER,
        "## loop-engineer scorecard",
        "",
        "| metric | value |",
        "|---|---|",
        f"| verdict | **{verdict}** |",
        f"| score | {score}/100 |",
        f"| gaps | {len(gaps)} |",
        "",
    ]
    for gap in gaps[:10]:
        lines.append(f"- {gap}")
    return "\n".join(lines) + "\n"


def _publish(summary: str) -> None:
    """Append to the job summary and drop scorecard.md for the PR-comment step.
    Both destinations come from the runner env; absent (e.g. in tests) → skipped."""
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write(summary)
    runner_temp = os.environ.get("RUNNER_TEMP")
    if runner_temp:
        (Path(runner_temp) / "scorecard.md").write_text(summary, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print("::error::action_scorecard.py expects <inspect.json> <fail-under>")
        return 2

    inspect_path, fail_under_raw = argv
    try:
        fail_under = parse_fail_under(fail_under_raw)
    except ValueError as exc:
        print(f"::error::{exc}")
        return 2

    try:
        report = json.loads(Path(inspect_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"::error::could not read inspect report {inspect_path!r}: {exc}")
        return 2
    if not isinstance(report, dict):
        print(f"::error::inspect report {inspect_path!r} is not a JSON object")
        return 2

    score = report.get("score", 0)
    verdict = report.get("verdict", "?")
    _publish(render_summary(report))

    if verdict == "weak":
        print(f"::warning::loop inspect verdict is weak (score {score}/100)")
    if fail_under and isinstance(score, (int, float)) and score < fail_under:
        print(f"::error::inspect score {score} < fail-under-score {fail_under}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
