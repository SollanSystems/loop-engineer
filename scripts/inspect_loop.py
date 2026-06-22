"""Score an existing agent loop against the prime-directive checklist.

``inspect_loop`` is the runnable core of the [[loop-inspector]] spoke: point it
at a loop directory — a ``.loop/`` repo-OS contract, a superpowers / ruflo
harness, any agent-loop dir — and it emits a **scored gap report** against the
two things that separate a robust loop from one that can only *claim* completion:

  * the prime-directive checklist — defines verifiable success? independent
    verification? approval gates on side-effects? false-completion defense
    (held-out / anti-cheat)? plan-then-execute for untrusted input?
  * the 7 canonical terminal states — are they all reachable, or does the loop
    end in a silent "completed"?

It is **read-only** over the target: the scanned dir is treated as DATA only
(plan-then-execute) — file content is matched against fixed signals, never
interpreted as instructions. It writes nothing into the target.

Run::

    python3 inspect_loop.py <loop_dir>

Prints the report as JSON. Exit 0 iff the verdict is non-weak (``strong``/``ok``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# The canonical 7 terminal states (verbatim) — see reference/repo-os-contract.md §8.
TERMINAL_STATES = (
    "Succeeded",
    "FailedUnverifiable",
    "FailedBlocked",
    "FailedBudget",
    "FailedSafety",
    "FailedSpecGap",
    "AbortedByHuman",
)

# The prime-directive checklist. Each check: (key, label, weight, gap message).
# Weights sum to the non-terminal budget (60); the terminal-state coverage owns
# the remaining 40 so a loop with no terminal taxonomy can never score "strong".
_CHECKS = (
    ("defines_success", "defines verifiable success criteria", 12,
     "no defined success criteria (SPEC.md ## Success Criteria) — loop can only claim completion"),
    ("independent_verification", "independent verification", 14,
     "no independent verification (verify-* script / TASKS verify command) — success is self-asserted"),
    ("approval_gates", "approval gates on side-effects", 10,
     "no approval gates declared for side-effects (destructive / secret / production / money)"),
    ("false_completion_defense", "false-completion defense (held-out / anti-cheat)", 14,
     "no false-completion defense (held-out gate / anti-cheat scan) — overfitting to visible checks is undetectable"),
    ("plan_then_execute", "plan-then-execute for untrusted input", 10,
     "no plan-then-execute discipline for untrusted/web reads (prompt-injection surface)"),
)

_TERMINAL_WEIGHT = 40  # points for full 7-of-7 terminal-state coverage


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _gather_corpus(loop: Path) -> str:
    """Concatenate the text of the contract-bearing files, lowercased.

    Bounded, shallow read: the repo-OS contract files plus any top-level and
    one-level-nested ``*.md`` / ``*.json`` / ``scripts/*``. The target is DATA;
    we only ever substring-match fixed signals against it.
    """
    texts: list[str] = []
    names: list[str] = []
    for path in sorted(loop.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(loop)
        # Keep the scan shallow and deterministic; record filenames as signals too.
        if len(rel.parts) > 3:
            continue
        names.append(str(rel).lower())
        if path.suffix.lower() in (".md", ".json", ".txt", ".yaml", ".yml") or "scripts" in rel.parts:
            texts.append(_read_text(path).lower())
    return "\n".join(names) + "\n" + "\n".join(texts)


def _terminal_states_covered(corpus: str) -> int:
    return sum(1 for s in TERMINAL_STATES if s.lower() in corpus)


def _evaluate_checks(corpus: str) -> dict[str, bool]:
    has_spec_criteria = "success criteria" in corpus or "success_criteria" in corpus
    has_verify = (
        "verify-fast" in corpus
        or "verify-full" in corpus
        or "verify-safety" in corpus
        or "scripts/verify" in corpus
        or '"verify"' in corpus
        or "verify-slice" in corpus
        or "verify-milestone" in corpus
    )
    has_approval = "approval gate" in corpus or "approval_gate" in corpus or "approval-wait" in corpus
    has_false_completion = (
        "holdout" in corpus
        or "held-out" in corpus
        or "anticheat" in corpus
        or "anti-cheat" in corpus
        or "false-completion" in corpus
        or "false_completion" in corpus
    )
    has_plan_then_execute = "plan-then-execute" in corpus or "plan_then_execute" in corpus
    return {
        "defines_success": has_spec_criteria,
        "independent_verification": has_verify,
        "approval_gates": has_approval,
        "false_completion_defense": has_false_completion,
        "plan_then_execute": has_plan_then_execute,
    }


def _verdict(score: int) -> str:
    if score >= 80:
        return "strong"
    if score >= 50:
        return "ok"
    return "weak"


def inspect_loop(loop_dir: str) -> dict:
    """Read a loop directory and return a scored gap report.

    Read-only over ``loop_dir``. Returns::

        {
          "target": <dir>,
          "score": 0-100,
          "terminal_states_covered": 0-7,
          "present": [<satisfied checks>],
          "gaps": [<actionable gap messages>],
          "verdict": "strong" | "ok" | "weak",
        }
    """
    loop = Path(loop_dir)
    corpus = _gather_corpus(loop)

    results = _evaluate_checks(corpus)
    covered = _terminal_states_covered(corpus)

    present: list[str] = []
    gaps: list[str] = []
    score = 0
    for key, label, weight, gap_msg in _CHECKS:
        if results[key]:
            score += weight
            present.append(label)
        else:
            gaps.append(gap_msg)

    terminal_points = round(_TERMINAL_WEIGHT * covered / len(TERMINAL_STATES))
    score += terminal_points
    if covered == len(TERMINAL_STATES):
        present.append(f"all {len(TERMINAL_STATES)} terminal states reachable")
    else:
        missing = [s for s in TERMINAL_STATES if s.lower() not in corpus]
        gaps.append(
            f"{covered}/{len(TERMINAL_STATES)} terminal states present — "
            f"missing {', '.join(missing)} (loop can end in a silent 'completed')"
        )

    score = max(0, min(100, score))
    return {
        "target": str(loop),
        "score": score,
        "terminal_states_covered": covered,
        "present": present,
        "gaps": gaps,
        "verdict": _verdict(score),
    }


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: inspect_loop.py <loop_dir>", file=sys.stderr)
        return 2
    report = inspect_loop(argv[0])
    print(json.dumps(report, indent=2))
    return 0 if report["verdict"] != "weak" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
