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
import os
import sys
from pathlib import Path

try:
    from loop.contract import TERMINAL_STATES, read_manifest
    from loop.paths import resolve_loop_paths
except ImportError:  # pragma: no cover - direct script copy outside repo root
    TERMINAL_STATES = (
        "Succeeded",
        "FailedUnverifiable",
        "FailedBlocked",
        "FailedBudget",
        "FailedSafety",
        "FailedSpecGap",
        "AbortedByHuman",
    )

    def read_manifest(_path):
        return None

    def resolve_loop_paths(target):
        class _Paths:
            workspace = Path(target)
            loop_dir = Path(target) / ".loop"
            manifest = loop_dir / "manifest.yaml"
            state = loop_dir / "state.json"
            tasks = Path(target) / "TASKS.json"
            runlog = Path(target) / "RUNLOG.md"
            terminal = loop_dir / "terminal_state.json"

        return _Paths()

# Bound the read of any single target file: the corpus is substring-matched
# against fixed signals, so the head of a file is enough and an oversized file
# can never exhaust memory. The deepest a walk descends is _MAX_DEPTH parts.
_MAX_READ_BYTES = 256 * 1024
_MAX_DEPTH = 3

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
        with path.open("rb") as fh:
            raw = fh.read(_MAX_READ_BYTES)
    except OSError:
        return ""
    return raw.decode("utf-8", errors="ignore")


def _gather_corpus(loop: Path) -> str:
    """Concatenate the text of the contract-bearing files, lowercased.

    Bounded, shallow read: the repo-OS contract files plus any top-level and
    one-level-nested ``*.md`` / ``*.json`` / ``scripts/*``. The target is DATA;
    we only ever substring-match fixed signals against it.
    """
    texts: list[str] = []
    names: list[str] = []
    for path in _walk_bounded(loop):
        rel = path.relative_to(loop)
        names.append(str(rel).lower())
        if path.suffix.lower() in (".md", ".json", ".txt", ".yaml", ".yml") or "scripts" in rel.parts:
            texts.append(_read_text(path).lower())
    return "\n".join(names) + "\n" + "\n".join(texts)



def _read_json_object(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _script_exists(workspace: Path, *names: str) -> bool:
    scripts = workspace / "scripts"
    return any((scripts / name).exists() for name in names)


def _task_verify_declared(tasks: dict) -> bool:
    rows = tasks.get("tasks")
    if not isinstance(rows, list):
        return False
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("verify"), str) and row["verify"].strip():
            return True
    return False


def _terminal_states_covered_from_contract(loop: Path) -> int:
    """Count terminal taxonomy coverage from contract-owned files only."""

    paths = resolve_loop_paths(loop)
    manifest = read_manifest(paths.manifest) or {}
    states = manifest.get("terminal_states") if isinstance(manifest, dict) else None
    if isinstance(states, list):
        return sum(1 for state in TERMINAL_STATES if state in states)

    contract_text = "\n".join(
        _read_text(path).lower()
        for path in (paths.workspace / "WORKFLOW.md", paths.manifest)
        if path.exists()
    )
    return sum(1 for state in TERMINAL_STATES if state.lower() in contract_text)


def _evaluate_contract_checks(loop: Path) -> dict[str, bool]:
    """Evaluate the checklist against typed/owned contract artifacts.

    Positive credit comes from SPEC/WORKFLOW/TASKS/scripts/.loop, not broad
    README prose, so keyword stuffing cannot satisfy the loop contract.
    """

    paths = resolve_loop_paths(loop)
    spec = _read_text(paths.workspace / "SPEC.md").lower()
    workflow = _read_text(paths.workspace / "WORKFLOW.md").lower()
    tasks = _read_json_object(paths.tasks)
    terminal = _read_json_object(paths.terminal)
    manifest = read_manifest(paths.manifest) or {}

    policies = manifest.get("policies") if isinstance(manifest, dict) else None
    manifest_declares_plan = isinstance(policies, dict) and "plan_then_execute" in policies

    has_spec_criteria = "success criteria" in spec or "success_criteria" in spec
    has_verify = (
        _task_verify_declared(tasks)
        or _script_exists(
            paths.workspace,
            "verify-fast",
            "verify-fast.sh",
            "verify-full",
            "verify-full.sh",
            "verify-safety",
            "verify-safety.sh",
        )
        or "scripts/verify" in spec
    )
    has_approval = (
        "approval gate" in workflow
        or "approval gates" in workflow
        or "approval_policy" in str(manifest).lower()
        or "approval_gates" in str(manifest).lower()
    )
    has_false_completion = (
        _script_exists(paths.workspace, "holdout_gate.py", "anticheat_scan.py", "anti_cheat.py")
        or terminal.get("false_completion") is False
        or "verifier_gaming" in str(manifest).lower()
        or "false-completion" in workflow
        or "false_completion" in workflow
    )
    if manifest_declares_plan:
        has_plan_then_execute = policies.get("plan_then_execute") is True
    else:
        has_plan_then_execute = "plan-then-execute" in workflow or "plan_then_execute: true" in workflow

    return {
        "defines_success": has_spec_criteria,
        "independent_verification": has_verify,
        "approval_gates": has_approval,
        "false_completion_defense": has_false_completion,
        "plan_then_execute": has_plan_then_execute,
    }


def _walk_bounded(loop: Path):
    """Yield files within ``_MAX_DEPTH`` parts of ``loop``, sorted, descending
    no deeper at iteration time.

    A file with N path parts lives in a directory of N-1 parts; pruning
    directories at depth ``_MAX_DEPTH - 1`` means deeper subtrees are never
    enumerated (not enumerated-then-discarded). Deterministic order matches the
    prior ``sorted(rglob)`` walk.
    """
    for dirpath, dirnames, filenames in os.walk(loop):
        here = Path(dirpath)
        depth = len(here.relative_to(loop).parts)
        if depth >= _MAX_DEPTH - 1:
            dirnames[:] = []
        else:
            dirnames.sort()
        for name in sorted(filenames):
            path = here / name
            if path.is_file():
                yield path


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

    results = _evaluate_contract_checks(loop)
    covered = _terminal_states_covered_from_contract(loop)

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
        paths = resolve_loop_paths(loop)
        manifest = read_manifest(paths.manifest) or {}
        states = manifest.get("terminal_states") if isinstance(manifest, dict) else None
        if isinstance(states, list):
            missing = [s for s in TERMINAL_STATES if s not in states]
        else:
            contract_text = "\n".join(
                _read_text(path).lower()
                for path in (paths.workspace / "WORKFLOW.md", paths.manifest)
                if path.exists()
            )
            missing = [s for s in TERMINAL_STATES if s.lower() not in contract_text]
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
