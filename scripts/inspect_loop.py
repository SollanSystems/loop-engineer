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

  * **invoked** (full credit) — a ``scripts/verify-*`` gate *executes* a holdout
    / anti-cheat gate script: an interpreter (``python``/``python3``/``python3.N``/
    ``uv run``/``bash``/``sh``/``exec``, optionally behind a transparent wrapper
    like ``env``/``time``/``nohup``) runs a gate script named in its arguments
    (``python3 scripts/holdout_gate.py``), or the gate script is invoked directly
    by path (``./scripts/holdout_gate.py``). A command that only *references* the
    file — ``echo``/``printf`` printing it, ``grep``/``cat``/``ls``/``test``/
    ``head``/``wc``/``find`` reading it, a trailing ``# comment`` naming it, or a
    redirection using it as a sink — earns *nothing*. A workspace-relative gate
    path must exist on disk; only unresolvable paths (``$VAR``/absolute) earn
    shape-only credit. OR ``RUNLOG.md`` / ``.loop/receipts/*.jsonl`` records an
    actual run (the gate ``.py`` path AND a whole-word verdict token on one line,
    with a gate script present on disk — not a bare token in stuffed prose;
    ordinary English like "ran"/"result"/"cleanup"/"passphrase" never counts).
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
import re
import shlex
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
    from loop.foreign import detect_foreign_layout, map_foreign_paths
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

    def detect_foreign_layout(_target):
        return None

    def map_foreign_paths(_target):
        return None


def _resolve_paths(target):
    """The path-resolution seam: a recognized foreign layout maps onto the
    same LoopPaths surface; everything else resolves natively. The scoring
    logic below is layout-blind — signals, weights, and credit tiers are
    identical for native and foreign targets."""
    mapped = map_foreign_paths(target)
    return mapped if mapped is not None else resolve_loop_paths(target)


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
# Verdict vocabulary, matched on WORD BOUNDARIES: "cleanup"/"passphrase"/
# "surpassed" must never satisfy the bar the way "clean"/"pass" do.
_GATE_RUN_WORDS_RE = re.compile(
    r"\b(?:verdict|pass|passed|fail|failed|flagged|clean)\b|\bexit 0\b"
)
_FALSE_COMPLETION_PARTIAL_DIVISOR = 2  # wired-but-unrun earns half the weight

# A gate script referenced as a *.py path — the invocation shape a real verify
# gate uses (`python3 scripts/holdout_gate.py`, `./scripts/anticheat_scan.py`).
# The bare token ("holdout_gate") without .py is prose, not an invocation.
_GATE_SCRIPT_RE = re.compile(r"\b(?:holdout_gate|anticheat_scan|anti_cheat)\.py\b")
# Genuine-invocation ALLOWLIST: "invoked" credit requires an executable line that
# actually *runs* a gate script. Either an interpreter leads the command and a
# gate script is named in its arguments, or the gate script is invoked directly
# by path. Everything else — a reference via echo/printf/grep/cat/ls/test/head/
# wc/find, or any other non-interpreter command — earns nothing. `uv` executes
# only through its `run` subcommand (pip install / add merely reference).
_GATE_INTERPRETERS = frozenset({"python", "python3", "bash", "sh", "exec"})
_VERSIONED_PYTHON_RE = re.compile(r"^python3\.\d+$")
# Wrapper commands that transparently run their argument command.
_TRANSPARENT_PREFIXES = frozenset({"env", "time", "nohup", "nice", "command"})
# A token that is (or opens) a shell redirection: everything after it is a file
# operand, not part of the executed command (`python3 x.py > holdout_gate.py`).
_REDIRECTION_RE = re.compile(r"^\d*(>>?|<)")
# Strip whole redirection expressions (operator + file operand) from a line
# BEFORE segment splitting: compound operators (`>&`, `>|`, `&>`) contain the
# very characters the segment splitter cuts on, so a redirect sink would
# otherwise be severed into its own segment and read as a bare-path invocation.
_REDIRECTION_STRIP_RE = re.compile(
    r"(?:\d*(?:>>|>\||>&|>|<<-|<<|<&|<)|&>>?)\s*\S*"
)
# Split a shell line into command segments so a real invocation chained after an
# inert emitter (`echo x && python3 ...holdout_gate.py`) is still discovered.
_SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[;|()&]")
# A verify-* line is "inert" (no verification substance) when its leading command
# only prints or no-ops. A body of nothing but these plus comments is not proof.
_INERT_LINE_COMMANDS = frozenset({"echo", "printf", "exit", "true", "false", ":"})


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


# Scaffold placeholder convention: an unfilled slot is the literal "REPLACE"
# marker (loop/scaffold.py `_substitutions`: "REPLACE: <hint>" for filled tokens,
# a bare "REPLACE" for the extra CRITERION_2/3 slots).
_PLACEHOLDER_MSG = (
    "unfilled scaffold placeholders ('REPLACE: ...') — replace them with "
    "concrete, verifiable text before this loop can claim to define {what}"
)
_SECTION_HEADING_RE = re.compile(r"\s*#{1,6}\s+(?P<title>.*\S)\s*$")
_LIST_ITEM_RE = re.compile(r"\s*(?:\d+[.)]|[-*+])\s+(?P<item>.*\S)\s*$")


def _is_placeholder(text: str) -> bool:
    """True iff ``text`` is an unfilled scaffold slot ('REPLACE' / 'REPLACE:…')."""
    upper = text.strip().upper()
    return upper == "REPLACE" or upper.startswith("REPLACE:")


def _section_body(text: str, heading: str) -> str | None:
    """Return the body of the first ``## <heading>`` section (case-insensitive)."""
    lines = text.splitlines()
    target = heading.strip().lower()
    start = None
    for i, line in enumerate(lines):
        match = _SECTION_HEADING_RE.match(line)
        if match and match.group("title").strip().lower().rstrip(":") == target:
            start = i + 1
            break
    if start is None:
        return None
    body: list[str] = []
    for line in lines[start:]:
        if _SECTION_HEADING_RE.match(line):
            break
        body.append(line)
    return "\n".join(body)


def _success_criteria_all_placeholder(spec_text: str) -> bool:
    """True iff the SPEC's Success-criteria list has items and all are unfilled."""
    body = _section_body(spec_text, "success criteria")
    if body is None:
        return False
    items = [m.group("item") for line in body.splitlines() if (m := _LIST_ITEM_RE.match(line))]
    return bool(items) and all(_is_placeholder(item) for item in items)


def _task_titles_all_placeholder(tasks: dict) -> bool:
    """True iff every declared task carries an unfilled 'REPLACE' title."""
    rows = tasks.get("tasks")
    if not isinstance(rows, list) or not rows:
        return False
    titles = [row.get("title") for row in rows if isinstance(row, dict)]
    titles = [t for t in titles if isinstance(t, str) and t.strip()]
    return bool(titles) and all(_is_placeholder(title) for title in titles)


def _terminal_states_covered_from_contract(loop: Path) -> int:
    """Count terminal taxonomy coverage from contract-owned files only."""

    paths = _resolve_paths(loop)
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


def _leading_command(segment: str) -> str:
    """The command word of a shell segment (past subshell/group openers)."""
    stripped = segment.lstrip("({ \t")
    parts = stripped.split(None, 1)
    return parts[0] if parts else ""


def _shell_tokens(segment: str) -> list[str]:
    """Tokenize a shell segment (subshell openers stripped, quotes removed).

    Unquoted ``#`` starts a comment — everything after it is prose, not command
    content, so a gate named only in a trailing comment never tokenizes.
    """
    seg = segment.lstrip("({ \t")
    try:
        return shlex.split(seg, posix=True, comments=True)
    except ValueError:
        tokens: list[str] = []
        for tok in seg.split():
            if tok.startswith("#"):
                break
            tokens.append(tok)
        return tokens


def _basename(token: str) -> str:
    """The trailing path component of a shell token (posix `/` separator)."""
    return token.rsplit("/", 1)[-1]


def _is_gate_interpreter(token: str) -> bool:
    return token in _GATE_INTERPRETERS or bool(_VERSIONED_PYTHON_RE.match(token))


def _statically_resolvable(token: str) -> bool:
    """A gate path we can check on disk: workspace-relative, no expansion."""
    return not (token.startswith(("/", "~")) or "$" in token or "`" in token)


def _gate_on_disk(workspace: Path, token: str) -> bool:
    rel = token[2:] if token.startswith("./") else token
    if (workspace / rel).is_file():
        return True
    return "/" not in rel and (workspace / "scripts" / rel).is_file()


def _gate_arg_credits(workspace: Path, token: str) -> bool:
    """A token earns gate credit: names a gate script that plausibly exists.

    A workspace-relative path must exist on disk — an invocation SHAPE of a
    non-existent gate is stolen valor ("invoked" full credit must not have a
    weaker precondition than "wired" half credit, which checks existence).
    Unresolvable paths ($VAR / absolute / backticks) keep shape-only credit:
    the flagship's gate lives outside the example workspace behind ``$REPO``.
    """
    if _basename(token) not in _GATE_SCRIPTS:
        return False
    if not _statically_resolvable(token):
        return True
    return _gate_on_disk(workspace, token)


def _segment_runs_gate(segment: str, workspace: Path) -> bool:
    """True iff this shell segment genuinely *executes* a gate script.

    Allowlisted shapes only: an interpreter (python/python3/python3.N/uv run/
    bash/sh/exec, optionally behind env/time/nohup/nice/command) whose arguments
    name a gate script, or the gate script invoked directly by path
    (`./scripts/holdout_gate.py`). A leading grep/cat/ls/test/head/wc/find — or
    echo/printf — that merely references the file is not an execution; neither
    is a gate path that appears only as a redirection sink.
    """
    tokens = _shell_tokens(segment)
    for i, tok in enumerate(tokens):
        if _REDIRECTION_RE.match(tok):
            tokens = tokens[:i]
            break
    while tokens and tokens[0] in _TRANSPARENT_PREFIXES:
        tokens = tokens[1:]
    if not tokens:
        return False
    lead, args = tokens[0], tokens[1:]
    if _basename(lead) in _GATE_SCRIPTS:
        return _gate_arg_credits(workspace, lead)
    if lead == "uv":
        if not args or args[0] != "run":
            return False
        args = args[1:]
    elif not _is_gate_interpreter(lead):
        return False
    return any(_gate_arg_credits(workspace, arg) for arg in args)


def _gate_invoked_in_verify(workspace: Path) -> bool:
    """A verify-* script genuinely *executes* a holdout/anti-cheat gate.

    Credit requires the gate script (`holdout_gate.py` / `anticheat_scan.py` /
    `anti_cheat.py`) to be *run* — an interpreter invocation or a direct
    by-path call. A command that only prints, reads, lists, or searches the file
    (echo/printf/grep/cat/ls/test/head/wc/find) earns nothing.
    """
    for script in _verify_scripts(workspace):
        for line in _read_text(script).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Redirection expressions go first: `>&`/`>|` contain segment-split
            # characters, so a sink severed into its own segment would read as
            # a bare-path invocation of a file the command never executes.
            stripped = _REDIRECTION_STRIP_RE.sub(" ", stripped)
            for segment in _SEGMENT_SPLIT_RE.split(stripped):
                segment = segment.strip()
                if not segment or not _GATE_SCRIPT_RE.search(segment):
                    continue
                if _segment_runs_gate(segment, workspace):
                    return True
    return False


def _verify_script_has_substance(workspace: Path) -> bool:
    """A verify-* script exists whose body has ≥1 non-inert executable line.

    A body of nothing but comments and printing/no-op commands (echo/printf/exit/
    true/false/`:`) is not verification — a file merely *named* ``verify-fast``
    earns no independent-verification credit. The shipped scaffold's verify-fast
    keeps credit: its contract-file existence ``for``/``if`` loop is substantive.
    """
    for script in _verify_scripts(workspace):
        for line in _read_text(script).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            lead = _leading_command(stripped)
            if lead and lead not in _INERT_LINE_COMMANDS:
                return True
    return False


def _records_gate_run(low: str, require_script_path: bool = False) -> bool:
    """A gate token AND an independent verdict word share one lowered line.

    The verdict word is checked against the residue *after* the gate tokens are
    removed, so a token that itself contains one cannot self-satisfy — a bare
    token earns nothing. The word list is verdict vocabulary only: ordinary
    English ("ran", "result", "the deadline passed") is narration, not a record.
    With ``require_script_path`` (the RUNLOG bar) the line must name the actual
    gate ``.py`` path, not just the bare token.
    """
    if require_script_path:
        if not _GATE_SCRIPT_RE.search(low):
            return False
    elif not any(token in low for token in _GATE_TOKENS):
        return False
    residue = low
    for token in _GATE_TOKENS:
        residue = residue.replace(token, " ")
    return bool(_GATE_RUN_WORDS_RE.search(residue))


def _receipt_records_gate(line: str) -> bool:
    """A receipt line is a real gate record: parseable JSON with gate+run fields."""
    line = line.strip()
    if not line:
        return False
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return False
    return _records_gate_run(json.dumps(obj).lower())


def _gate_run_recorded(paths) -> bool:
    """RUNLOG.md / .loop/receipts/*.jsonl record an actual gate run.

    A record of a run implies a gate that can run: with no gate script anywhere
    on disk, record-shaped prose is a claim about a tool that does not exist.
    """
    if not _script_exists(paths.workspace, *_GATE_SCRIPTS):
        return False
    for line in _read_text(paths.runlog).splitlines():
        if _records_gate_run(line.lower(), require_script_path=True):
            return True
    receipts = paths.loop_dir / "receipts"
    if receipts.is_dir():
        for receipt in sorted(receipts.glob("*.jsonl")):
            for line in _read_text(receipt).splitlines():
                if _receipt_records_gate(line):
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

    paths = _resolve_paths(loop)
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

    # A fresh scaffold's Success-criteria list and task titles are the literal
    # "REPLACE:" placeholders. A structurally-present-but-unfilled criteria list
    # earns no defines_success credit — a shell is not a defined success.
    spec_raw = _read_text(paths.spec) + "\n" + _read_text(paths.contract)
    criteria_all_placeholder = _success_criteria_all_placeholder(spec_raw)
    task_titles_placeholder = _task_titles_all_placeholder(tasks)

    has_criteria_heading = "success criteria" in spec or "success_criteria" in spec
    has_spec_criteria = has_criteria_heading and not criteria_all_placeholder
    # A verify-* script earns credit only if it actually verifies — a body of
    # nothing but echo/printf/no-ops (a file merely *named* verify-fast) does not.
    has_verify = (
        _task_verify_declared(tasks)
        or _verify_script_has_substance(paths.workspace)
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
        "_success_criteria_placeholder": has_criteria_heading and criteria_all_placeholder,
        "_task_titles_placeholder": task_titles_placeholder,
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
        if key == "defines_success" and not value and results.get("_success_criteria_placeholder"):
            gaps.append("success criteria are " + _PLACEHOLDER_MSG.format(what="success"))
            continue
        if value:
            score += weight
            present.append(label)
        else:
            gaps.append(gap_msg)

    if results.get("_task_titles_placeholder"):
        gaps.append("TASKS.json titles are " + _PLACEHOLDER_MSG.format(what="its tasks"))

    terminal_points = round(_TERMINAL_WEIGHT * covered / len(TERMINAL_STATES))
    score += terminal_points
    if covered == len(TERMINAL_STATES):
        present.append(f"all {len(TERMINAL_STATES)} terminal states reachable")
    else:
        paths = _resolve_paths(loop)
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

    # False-completion defense is the anti-gaming keystone: a loop with NO real
    # holdout/anti-cheat gate (grade "none") must never reach "strong" or clear a
    # fail-under-80 CI gate on keyword stuffing alone. Cap it below the threshold.
    # "wired"/"invoked" grades — a gate that at least exists — are uncapped.
    if results["false_completion_defense"] == "none" and score >= 80:
        score = 79
        gaps.append(
            "no false-completion defense — score capped below 'strong'; "
            "wire a holdout/anti-cheat gate"
        )

    report = {
        "target": str(loop),
        "score": score,
        "terminal_states_covered": covered,
        "present": present,
        "gaps": gaps,
        "verdict": _verdict(score),
    }
    foreign = detect_foreign_layout(loop)
    if foreign:
        report["foreign_layout"] = foreign
        report["advisory"] = True
    return report


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: inspect_loop.py <loop_dir>", file=sys.stderr)
        return 2
    report = inspect_loop(argv[0])
    print(json.dumps(report, indent=2))
    return 0 if report["verdict"] != "weak" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
