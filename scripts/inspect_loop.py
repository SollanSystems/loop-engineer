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

**False-completion defense is graded on invocation evidence, not claims.** A
self-asserted ``false_completion: false`` flag, a ``verifier_gaming`` manifest
key, or the phrase "false-completion" in prose earns *nothing* — those are
assertions the loop makes about itself. The three grades are:

  * **invoked** (full credit) — a ``scripts/verify-*`` gate invokes a holdout /
    anti-cheat gate on an executable (non-comment) line, OR ``RUNLOG.md`` /
    ``.loop/receipts/*.jsonl`` records an actual run (a ``holdout_gate`` verdict
    / anti-cheat scan result).
  * **wired** (partial credit, half the weight) — a gate script file exists
    (``scripts/holdout_gate.py`` / ``anticheat_scan.py`` / ``anti_cheat.py``)
    and is referenced from the contract's verify surface (SPEC / WORKFLOW /
    verify-* scripts), but no run is recorded yet.
  * **none** (zero) — only a self-asserted terminal flag, a prose mention, or an
    unreferenced script file.

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

# When run as a documented standalone script (`python3 scripts/inspect_loop.py
# <loop>`), sys.path[0] is scripts/ — not the repo root — so the sibling `loop`
# package is not importable and we would silently use the degraded fallbacks
# below (read_manifest -> None, root-only path resolution). Put the repo root on
# sys.path first so the real loop.contract / loop.paths are used when the package
# ships alongside.
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

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
            spec = Path(target) / "SPEC.md"
            workflow = Path(target) / "WORKFLOW.md"
            contract = Path(target) / "loop-contract.md"

        return _Paths()

# Bound the read of any single target file: the corpus is substring-matched
# against fixed signals, so the head of a file is enough and an oversized file
# can never exhaust memory.
_MAX_READ_BYTES = 256 * 1024

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
    ("false_completion_defense", "false-completion defense", 14,
     "no false-completion defense: no recorded holdout/anti-cheat invocation "
     "(a self-asserted false_completion flag or prose mention earns no credit)"),
    ("plan_then_execute", "plan-then-execute for untrusted input", 10,
     "no plan-then-execute discipline for untrusted/web reads (prompt-injection surface)"),
)

_TERMINAL_WEIGHT = 40  # points for full 7-of-7 terminal-state coverage

# False-completion-defense evidence signals. Gate scripts are matched by name;
# their tokens (underscored, script-specific) discriminate a real invocation /
# recorded run from mere prose ("anti-cheat", "false-completion").
_GATE_TOKENS = ("holdout_gate", "anticheat_scan", "anti_cheat")
_GATE_SCRIPTS = ("holdout_gate.py", "anticheat_scan.py", "anti_cheat.py")
_GATE_RUN_WORDS = ("verdict", "scan", "result", "passed", "failed", "ran", "clean", "flagged")
_FALSE_COMPLETION_PARTIAL_DIVISOR = 2  # wired-but-unrun earns half the weight


def _read_text(path: Path) -> str:
    try:
        with path.open("rb") as fh:
            raw = fh.read(_MAX_READ_BYTES)
    except OSError:
        return ""
    return raw.decode("utf-8", errors="ignore")


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
        for path in (paths.workflow, paths.manifest, paths.contract)
        if path.exists()
    )
    return sum(1 for state in TERMINAL_STATES if state.lower() in contract_text)


def _verify_scripts(workspace: Path) -> list[Path]:
    scripts = workspace / "scripts"
    if not scripts.is_dir():
        return []
    return sorted(p for p in scripts.glob("verify-*") if p.is_file())


def _gate_invoked_in_verify(workspace: Path) -> bool:
    """A verify-* script runs a holdout/anti-cheat gate on an executable line."""
    for script in _verify_scripts(workspace):
        for line in _read_text(script).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if any(token in stripped for token in _GATE_TOKENS):
                return True
    return False


def _gate_run_recorded(paths) -> bool:
    """RUNLOG.md / .loop/receipts/*.jsonl record an actual gate run."""
    texts = [_read_text(paths.runlog)]
    receipts = paths.loop_dir / "receipts"
    if receipts.is_dir():
        texts.extend(_read_text(p) for p in sorted(receipts.glob("*.jsonl")))
    for text in texts:
        for line in text.splitlines():
            low = line.lower()
            if any(token in low for token in _GATE_TOKENS):
                return True
            if ("holdout" in low or "anticheat" in low or "anti-cheat" in low) and any(
                word in low for word in _GATE_RUN_WORDS
            ):
                return True
    return False


def _gate_script_referenced(paths) -> bool:
    """A gate script file exists and is named from the contract's verify surface."""
    if not _script_exists(paths.workspace, *_GATE_SCRIPTS):
        return False
    surface = _read_text(paths.spec).lower() + "\n" + _read_text(paths.workflow).lower()
    for script in _verify_scripts(paths.workspace):
        surface += "\n" + _read_text(script).lower()
    return any(token in surface for token in _GATE_TOKENS)


def _false_completion_credit(paths) -> str:
    """Graded false-completion-defense credit (see module docstring).

    Returns "invoked" (full), "wired" (partial), or "none" (zero).
    """
    if _gate_invoked_in_verify(paths.workspace) or _gate_run_recorded(paths):
        return "invoked"
    if _gate_script_referenced(paths):
        return "wired"
    return "none"


def _evaluate_contract_checks(loop: Path) -> dict[str, object]:
    """Evaluate the checklist against typed/owned contract artifacts.

    Positive credit comes from SPEC/WORKFLOW/TASKS/scripts/.loop, not broad
    README prose, so keyword stuffing cannot satisfy the loop contract.
    """

    paths = resolve_loop_paths(loop)
    # SPEC/WORKFLOW resolve dual-location (.loop/ ∪ root) via resolve_loop_paths;
    # a committed single-file loop-contract.md is folded in as a contract-owned
    # source for the same signals.
    contract = _read_text(paths.contract).lower()
    spec = _read_text(paths.spec).lower() + "\n" + contract
    workflow = _read_text(paths.workflow).lower() + "\n" + contract
    tasks = _read_json_object(paths.tasks)
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
    if manifest_declares_plan:
        has_plan_then_execute = policies.get("plan_then_execute") is True
    else:
        has_plan_then_execute = "plan-then-execute" in workflow or "plan_then_execute: true" in workflow

    return {
        "defines_success": has_spec_criteria,
        "independent_verification": has_verify,
        "approval_gates": has_approval,
        "false_completion_defense": _false_completion_credit(paths),
        "plan_then_execute": has_plan_then_execute,
    }


def _grade_false_completion(grade, weight, label, none_gap, present, gaps) -> int:
    if grade == "invoked":
        present.append(f"{label} (invoked)")
        return weight
    if grade == "wired":
        present.append(f"{label} (wired, no recorded run)")
        gaps.append(
            "false-completion gate wired but never run — no recorded "
            "holdout/anti-cheat invocation yet (RUNLOG.md / .loop/receipts)"
        )
        return round(weight / _FALSE_COMPLETION_PARTIAL_DIVISOR)
    gaps.append(none_gap)
    return 0


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
        value = results[key]
        if key == "false_completion_defense":
            score += _grade_false_completion(value, weight, label, gap_msg, present, gaps)
            continue
        if value:
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
                for path in (paths.workflow, paths.manifest, paths.contract)
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
