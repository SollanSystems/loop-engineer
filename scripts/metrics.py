"""Derive false-completion-rate (FCR) and repair-productivity (RP) from a loop.

The runnable core of ST1: point it at a loop dir and it computes the two
first-class metrics (`reference/eval-suite.md` §2) from that loop's *real* on-disk
evidence — RUNLOG success claims, deterministic verify bundles, the held-out gate
verdict, the canonical repair records, and receipts — never from the agent's
narration. Every headline number ships with a `provenance` block so a skeptic can
re-derive it by hand.

Two honesty invariants distinguish this from a self-report:

  * **`productive` is recomputed, never trusted.** RP is aggregated only over
    repair records whose stored `productive` agrees with the value recomputed from
    `verification_before`/`verification_after.score` (`recheck_productive`). A
    record that disagrees, or cannot demonstrate a score delta, is *rejected* and
    excluded — reported under `provenance.rejected_records`, not silently coerced.
  * **FCR is derived two ways and disagreement is surfaced.** (a) the RUNLOG
    success-claim × verify-bundle cross-join (the deterministic anchor, per §3),
    and (b) the aggregated held-out-gate `false_completion` flag. An unmatched
    success-claim counts as a false completion (fail-closed, §8). A success claim
    is clean only if EVERY verify bundle attached to its iteration is green, or a
    red one's own task later reached green (an honestly-repaired intermediate) —
    an unrelated green bundle can never launder the claimed task's red gate.

The `### Outcome` token contract: a claim counts toward the FCR denominator only
when its outcome token is a recognized SUCCESS token (`task_passed`, `terminal`,
`succeeded`, `advanced`); `repair_triggered` / `task_failed` and peers are honest
reds. Any token in neither set is surfaced under `provenance.unrecognized_outcomes`
so a synonym (`shipped`, `done`, …) is visible rather than silently escaping the
denominator — it never widens the recognized-success set on its own.

A committed held-out verdict is validated structurally (it must carry the per-check
`visible`/`holdout` arrays and internally-consistent flags a real `holdout_gate`
run emits, not a hand-set 4-field stub) and its sha256 is recorded in provenance.
That committed verdict is *evidence, not proof*: it demonstrates a gate ran, but
tamper detection of the artifact itself belongs to the anti-cheat layer
(`anticheat_scan.py`) — this command does not, and does not claim to, make the
verdict tamper-proof.

`--baseline` writes a checked-in scorecard, but only over a genuinely gate-backed
run: it refuses (non-zero, writes nothing) if the run is not `evidence_backed`, if
any record was rejected, if the two FCR methods disagree, if no iteration claims
success (a vacuous 0/0 is not a publishable 0.0), or if any counted repair record
is unanchored. Baselining a self-asserted run would itself be a false completion of
ST1.

Pure stdlib, offline, deterministic: the same loop dir yields a byte-identical
scorecard.

Run::

    python3 metrics.py <loop-dir>
    python3 metrics.py --baseline <loop-dir>
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from loop.paths import LoopPaths, resolve_loop_paths  # noqa: E402

import re  # noqa: E402

METRICS_SCHEMA = "loop-engineer/metrics@1"
BASELINE_OUTPUT = "docs/metrics-baseline.json"

# A RUNLOG iteration whose outcome declares a task/loop reached "done". A
# repair_triggered / task_failed outcome is an honest red, NOT a success claim.
_SUCCESS_OUTCOME_TOKENS = ("task_passed", "terminal", "succeeded", "advanced")

# Recognized honest-red outcome tokens: not a success claim, but a known outcome
# (so they are not surfaced as an "unrecognized" synonym). Any outcome token in
# neither set is surfaced under provenance.unrecognized_outcomes.
_HONEST_RED_OUTCOME_TOKENS = (
    "repair_triggered", "task_failed", "replan", "reverted", "revert",
    "blocked", "terminated", "aborted", "failed",
)
_KNOWN_OUTCOME_TOKENS = frozenset(_SUCCESS_OUTCOME_TOKENS) | frozenset(_HONEST_RED_OUTCOME_TOKENS)

# Gate tokens (mirrors inspect_loop._GATE_TOKENS): a real held-out / anti-cheat
# gate invocation writes one of these into the execution trail.
_GATE_TOKENS = ("holdout_gate", "anticheat_scan", "anti_cheat")
# Gate script filenames (mirrors inspect_loop._GATE_SCRIPTS): the file a real
# invocation runs. evidence_backed via a verify script requires one to exist.
_GATE_SCRIPTS = ("holdout_gate.py", "anticheat_scan.py", "anti_cheat.py")

_ITER_HEADER_RE = re.compile(r"(?m)^##\s+Iteration\s+(\S+)")
# "outcome" declaration followed (within a little markup/whitespace) by its token.
_OUTCOME_RE = re.compile(r"outcome[^A-Za-z0-9]{0,40}?([A-Za-z][A-Za-z_]{2,})", re.IGNORECASE | re.DOTALL)
_VERIFY_REF_RE = re.compile(r"(verify-[\w.-]+?\.json)")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_json_object(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _num(value) -> float | None:
    """A real number, or None. ``bool`` is not a number (True is not a score)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _norm_iter(value) -> str:
    return str(value).strip()


# --- recheck_productive: the shared, never-trust-the-flag validator (§4.3) -----


def recheck_productive(record: dict) -> dict:
    """Recompute a record's ``productive`` from its own evidence and compare.

    Returns a verdict dict — ``kind`` (``repair``/``rollout``/``unknown``),
    ``stored``, ``expected``, ``valid`` (stored agrees with a computable
    expected), and ``reason``. Both the metrics command (RP) and
    ``rollout_ledger.summarize`` consume it; neither ever sums a caller-supplied
    boolean verbatim.
    """

    stored = record.get("productive")
    stored_is_bool = isinstance(stored, bool)

    has_before_after = isinstance(record.get("verification_before"), dict) and isinstance(
        record.get("verification_after"), dict
    )

    if has_before_after:
        kind = "repair"
        before = _num(record["verification_before"].get("score"))
        after = _num(record["verification_after"].get("score"))
        if before is None or after is None:
            return {
                "kind": kind,
                "stored": stored if stored_is_bool else None,
                "expected": None,
                "valid": False,
                "reason": "missing numeric verification_before/after score",
            }
        expected = after > before
    elif "score_delta" in record:
        kind = "rollout"
        delta = _num(record.get("score_delta"))
        expected = delta is not None and delta > 0
    else:
        return {
            "kind": "unknown",
            "stored": stored if stored_is_bool else None,
            "expected": None,
            "valid": False,
            "reason": "unrecognized record shape (no verification_before/after or score_delta)",
        }

    if not stored_is_bool:
        return {
            "kind": kind,
            "stored": None,
            "expected": expected,
            "valid": False,
            "reason": "productive is missing or not a boolean",
        }
    if stored != expected:
        return {
            "kind": kind,
            "stored": stored,
            "expected": expected,
            "valid": False,
            "reason": f"stored productive={stored} disagrees with recomputed {expected}",
        }
    return {"kind": kind, "stored": stored, "expected": expected, "valid": True, "reason": "ok"}


# --- RUNLOG / verify-bundle parsing (deterministic, evidence-only) -------------


def _runlog_blocks(runlog_text: str) -> list[tuple[str, str]]:
    """Split RUNLOG.md into (iteration_id, block_text) pairs, in file order."""
    matches = list(_ITER_HEADER_RE.finditer(runlog_text))
    blocks: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(runlog_text)
        blocks.append((_norm_iter(m.group(1)), runlog_text[m.start():end]))
    return blocks


def _block_outcome_tokens(block_text: str) -> list[str]:
    return [t.lower() for t in _OUTCOME_RE.findall(block_text)]


def _block_claims_success(block_text: str) -> bool:
    return any(t in _SUCCESS_OUTCOME_TOKENS for t in _block_outcome_tokens(block_text))


def _load_verify_bundles(loop_dir: Path) -> list[dict]:
    bundles: list[dict] = []
    for path in sorted(loop_dir.rglob("verify-*.json")):
        if "archive" in path.parts:
            continue
        data = _read_json_object(path)
        if not data:
            continue
        outcome = str(data.get("outcome", "")).upper()
        green = outcome == "PASS" or data.get("passed") is True
        it = data.get("iteration_id", data.get("iteration"))
        task = data.get("task")
        bundles.append(
            {
                "path": path,
                "name": path.name,
                "green": green,
                "iter": _norm_iter(it) if it is not None else None,
                "task": str(task) if task is not None else None,
                "score": _num(data.get("score")),
            }
        )
    return bundles


def _assign_bundles_to_iters(bundles: list[dict], blocks: list[tuple[str, str]]) -> tuple[dict, list[str]]:
    """Key each verify bundle to an iteration_id: its own iteration field first,
    else the RUNLOG block that references its filename. Unassignable bundles are
    returned separately (surfaced under provenance)."""
    refs_by_iter = {iid: set(_VERIFY_REF_RE.findall(text)) for iid, text in blocks}
    by_iter: dict[str, list[dict]] = {}
    unmatched: list[str] = []
    for b in bundles:
        target = b["iter"]
        if target is None:
            target = next((iid for iid, refs in refs_by_iter.items() if b["name"] in refs), None)
        if target is None:
            unmatched.append(b["name"])
        else:
            by_iter.setdefault(target, []).append(b)
    return by_iter, sorted(unmatched)


def _valid_check_list(checks) -> bool:
    """A non-empty list of ``{"id": ..., "passed": bool}`` per-check results."""
    return (
        isinstance(checks, list)
        and bool(checks)
        and all(isinstance(c, dict) and "id" in c and isinstance(c.get("passed"), bool) for c in checks)
    )


def _is_valid_gate_verdict(data: dict) -> bool:
    """Structurally validate a held-out verdict against ``holdout_gate.decide``'s
    output shape. A real run carries the per-check ``visible``/``holdout`` arrays
    plus flags RE-DERIVABLE from them; a hand-typed
    ``{verdict, passed_visible, passed_holdout, false_completion}`` stub carries no
    check evidence and is rejected — a self-asserted flag is not a gate run."""
    if not isinstance(data.get("verdict"), str):
        return False
    for key in ("passed_visible", "passed_holdout", "false_completion"):
        if not isinstance(data.get(key), bool):
            return False
    visible, holdout = data.get("visible"), data.get("holdout")
    if not _valid_check_list(visible) or not _valid_check_list(holdout):
        return False
    passed_visible = all(c["passed"] for c in visible)
    passed_holdout = all(c["passed"] for c in holdout)
    if data["passed_visible"] != passed_visible or data["passed_holdout"] != passed_holdout:
        return False
    return data["false_completion"] == (passed_visible and not passed_holdout)


def _load_gate_verdicts(loop_dir: Path) -> list[dict]:
    """Held-out / anti-cheat gate verdict artifacts (holdout_gate.decide output).

    Only structurally-valid verdicts are returned; a fabricated 4-field stub is
    not counted as gate evidence.
    """
    verdicts: list[dict] = []
    for path in sorted(loop_dir.rglob("*.json")):
        if "archive" in path.parts:
            continue
        data = _read_json_object(path)
        if "false_completion" in data and _is_valid_gate_verdict(data):
            verdicts.append({"path": path, "data": data})
    return verdicts


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _verify_scripts(workspace: Path) -> list[Path]:
    scripts = workspace / "scripts"
    if not scripts.is_dir():
        return []
    return sorted(p for p in scripts.glob("verify-*") if p.is_file())


def _gate_script_present(workspace: Path) -> bool:
    """A gate script the verify surface can actually invoke exists — either bundled
    with the loop or in the loop-engineer toolkit it composes with."""
    for base in (workspace / "scripts", _REPO_ROOT / "scripts"):
        if any((base / name).exists() for name in _GATE_SCRIPTS):
            return True
    return False


def _gate_invoked(paths: LoopPaths, gate_verdicts: list[dict]) -> bool:
    """Is a real gate invocation detectable? Mirrors the inspector's
    invocation-evidence rule (HI4), NOT looser prose matching:

      (a) a recorded, structurally-valid gate VERDICT artifact, or
      (b) a NON-COMMENT gate-token line in a verify-* script whose gate script
          file actually exists.

    A bare TASKS.json verify *declaration* or a RUNLOG prose mention is NOT an
    invocation (a ``# TODO: call holdout_gate.py`` comment earns nothing)."""
    if gate_verdicts:
        return True
    if not _gate_script_present(paths.workspace):
        return False
    for script in _verify_scripts(paths.workspace):
        for line in _read_text(script).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if any(tok in stripped for tok in _GATE_TOKENS):
                return True
    return False


def _load_receipt_costs(loop_dir: Path) -> tuple[float | None, int]:
    """Sum ``cost_usd`` across receipts; None if no receipt carries a cost."""
    total: float | None = None
    count = 0
    for path in sorted((loop_dir / "receipts").glob("*.jsonl")):
        for line in _read_text(path).splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            count += 1
            cost = _num(rec.get("cost_usd"))
            if cost is not None:
                total = cost if total is None else total + cost
    return total, count


def _anchor_repair(record: dict, bundle_scores: set[float]) -> dict:
    """Cross-check a repair record's self-reported before/after scores against the
    deterministic verify bundles (§4.3, RP anchoring).

    Returns ``status`` one of ``anchored`` (both scores corroborated),
    ``unanchored`` (no verify bundle carries a score to anchor against), or
    ``rejected`` (a score is present but no verify bundle corroborates it — a
    fabricated delta). ``recheck_productive`` runs first, so by here a repair
    record's before/after scores are already numeric.
    """
    before = record.get("verification_before")
    after = record.get("verification_after")
    before = _num(before.get("score")) if isinstance(before, dict) else None
    after = _num(after.get("score")) if isinstance(after, dict) else None
    if before is None and after is None:
        return {"status": "unanchored", "reason": "no before/after score to anchor"}
    if not bundle_scores:
        return {"status": "unanchored", "reason": "no verify bundle scores to anchor against"}
    missing = [
        label
        for label, value in (("verification_before", before), ("verification_after", after))
        if value is not None and value not in bundle_scores
    ]
    if missing:
        return {
            "status": "rejected",
            "reason": f"self-reported {', '.join(missing)}.score not corroborated by any verify bundle",
        }
    return {"status": "anchored", "reason": "ok"}


def _rel(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


# --- the scorecard -------------------------------------------------------------


def compute_metrics(loop_dir: str | Path, loop_label: str | None = None) -> dict:
    paths = resolve_loop_paths(loop_dir)
    workspace = paths.workspace
    loop_dir_path = paths.loop_dir
    label = loop_label if loop_label is not None else str(loop_dir)

    runlog_text = _read_text(paths.runlog)
    terminal = _read_json_object(paths.terminal)
    blocks = _runlog_blocks(runlog_text)

    bundles = _load_verify_bundles(loop_dir_path)
    verify_by_iter, unmatched_verify = _assign_bundles_to_iters(bundles, blocks)

    # Success claims: RUNLOG success-outcome iterations, plus the terminal claim.
    claim_iters: set[str] = {iid for iid, text in blocks if _block_claims_success(text)}
    if terminal.get("state") == "Succeeded":
        tid = _norm_iter(terminal.get("iteration_id"))
        claim_iters.add(tid)
        # The terminal names the verify bundles that back its success claim.
        evidence = terminal.get("evidence")
        if isinstance(evidence, list):
            wanted = {Path(str(e)).name for e in evidence}
            for b in bundles:
                if b["name"] in wanted:
                    verify_by_iter.setdefault(tid, [])
                    if b not in verify_by_iter[tid]:
                        verify_by_iter[tid].append(b)

    # FCR-A: a success claim is clean only if every verify bundle attached to its
    # iteration is green — with one honest exception: a red bundle whose OWN task
    # later reached green is a repaired intermediate, not a false completion (the
    # flagship's verify-T2-iter1 → verify-T2). An UNRELATED green bundle can never
    # launder a claimed task's still-red gate. Unmatched claims fail closed (§8).
    green_tasks = {b["task"] for b in bundles if b["green"] and b["task"]}

    def _claim_is_clean(iid: str) -> bool:
        attached = verify_by_iter.get(iid, [])
        if not attached or not any(b["green"] for b in attached):
            return False
        for b in attached:
            if not b["green"] and (not b["task"] or b["task"] not in green_tasks):
                return False
        return True

    false_completions = sum(1 for iid in claim_iters if not _claim_is_clean(iid))
    n_claims = len(claim_iters)
    fcr_a = (false_completions / n_claims) if n_claims else 0.0

    unrecognized_outcomes = sorted(
        {t for _iid, text in blocks for t in _block_outcome_tokens(text) if t not in _KNOWN_OUTCOME_TOKENS}
    )

    # FCR-B: aggregated held-out-gate false_completion flag.
    gate_verdicts = _load_gate_verdicts(loop_dir_path)
    fc_flagged = sum(1 for v in gate_verdicts if v["data"].get("false_completion") is True)
    fcr_b = (fc_flagged / len(gate_verdicts)) if gate_verdicts else None
    fcr_methods_agree = None if fcr_b is None else (fcr_a == fcr_b)

    evidence_backed = _gate_invoked(paths, gate_verdicts)

    # RP: over recomputed-and-agreed repair records only, whose before/after
    # scores are anchored to the deterministic verify bundles (§4.3). A record
    # whose stored productive lies (recheck) OR whose scores are not corroborated
    # by any verify bundle (anchor) is rejected; a record with no bundle to anchor
    # against is counted but flagged unanchored (a baseline refuses over those).
    bundle_scores = {b["score"] for b in bundles if b["score"] is not None}
    validated = 0
    productive = 0
    rejected: list[dict] = []
    unanchored: list[str] = []
    rp_source: list[str] = []
    for path in sorted((loop_dir_path / "repair").glob("*.json")):
        record = _read_json_object(path)
        rel = _rel(path, workspace)
        verdict = recheck_productive(record)
        if not verdict["valid"]:
            rejected.append({"record": rel, "reason": verdict["reason"]})
            continue
        anchor = _anchor_repair(record, bundle_scores)
        if anchor["status"] == "rejected":
            rejected.append({"record": rel, "reason": anchor["reason"]})
            continue
        if anchor["status"] == "unanchored":
            unanchored.append(rel)
        validated += 1
        rp_source.append(rel)
        if verdict["expected"]:
            productive += 1
    repair_productivity = (productive / validated) if validated else None

    # Cost-per-success (layer 7): total receipt cost over true completions.
    total_cost, _receipt_count = _load_receipt_costs(loop_dir_path)
    successes = n_claims - false_completions
    cost_per_success = (total_cost / successes) if (total_cost is not None and successes > 0) else None

    fcr_source = sorted({_rel(paths.runlog, workspace)} | {_rel(b["path"], workspace) for b in bundles})
    holdout_source = sorted(_rel(v["path"], workspace) for v in gate_verdicts)
    holdout_verdicts = sorted(
        ({"source": _rel(v["path"], workspace), "sha256": _sha256(v["path"])} for v in gate_verdicts),
        key=lambda e: e["source"],
    )
    rejected.sort(key=lambda r: r["record"])

    return {
        "schema": METRICS_SCHEMA,
        "loop": label,
        "false_completion_rate": fcr_a,
        "repair_productivity": repair_productivity,
        "iterations_claiming_success": n_claims,
        "false_completions": false_completions,
        "repair_passes": validated,
        "productive_repairs": productive,
        "cost_per_success_usd": cost_per_success,
        "evidence_backed": evidence_backed,
        "provenance": {
            "fcr_source": fcr_source,
            "rp_source": sorted(rp_source),
            "rejected_records": rejected,
            "unanchored_records": sorted(unanchored),
            "unrecognized_outcomes": unrecognized_outcomes,
            "false_completion_rate_holdout": fcr_b,
            "fcr_methods_agree": fcr_methods_agree,
            "holdout_source": holdout_source,
            "holdout_verdicts": holdout_verdicts,
            "unmatched_verify": unmatched_verify,
        },
    }


def _input_files(loop_dir: str | Path) -> list[str]:
    """The exact committed files the scorecard is derived from, repo-relative."""
    paths = resolve_loop_paths(loop_dir)
    loop_dir_path = paths.loop_dir
    candidates: list[Path] = [paths.runlog, paths.terminal, paths.tasks]
    candidates += sorted(loop_dir_path.rglob("verify-*.json"))
    candidates += [v["path"] for v in _load_gate_verdicts(loop_dir_path)]
    candidates += sorted((loop_dir_path / "repair").glob("*.json"))
    candidates += sorted((loop_dir_path / "receipts").glob("*.jsonl"))
    seen: list[str] = []
    for p in candidates:
        if "archive" in p.parts or not p.exists():
            continue
        rel = _rel(p, _REPO_ROOT)
        if rel not in seen:
            seen.append(rel)
    return sorted(seen)


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=_REPO_ROOT, capture_output=True, text=True
        )
    except OSError:
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def build_baseline(loop_dir: str | Path, loop_label: str | None = None) -> tuple[bool, dict, list[str]]:
    """Compute the scorecard and check the §4.5 baseline preconditions.

    Returns ``(ok, scorecard, refusal_reasons)``. ``ok`` is False when the run is
    not evidence-backed, contains a rejected record, has disagreeing FCR methods,
    claims no success (vacuous 0/0), or counts an unanchored repair record. Each
    refusal names the precondition that failed.
    """
    scorecard = compute_metrics(loop_dir, loop_label)
    prov = scorecard["provenance"]
    reasons: list[str] = []
    if not scorecard["evidence_backed"]:
        reasons.append(
            "run is not evidence_backed — no held-out / anti-cheat gate invocation "
            "detectable (a structurally-valid verdict artifact, or a non-comment gate "
            "line in a verify-* script whose gate script exists)"
        )
    rejected = prov["rejected_records"]
    if rejected:
        reasons.append(
            f"{len(rejected)} rejected record(s) present (productive disagrees with its own "
            "evidence, or before/after scores are not corroborated by any verify bundle)"
        )
    if prov["fcr_methods_agree"] is False:
        reasons.append(
            "fcr_methods_agree is False — the deterministic cross-join "
            f"(FCR {scorecard['false_completion_rate']}) and the held-out-gate flag "
            f"(FCR {prov['false_completion_rate_holdout']}) disagree; a baseline may not "
            "launder an inconsistent run into a clean number"
        )
    if scorecard["iterations_claiming_success"] == 0:
        reasons.append(
            "iterations_claiming_success == 0 — a vacuous 0/0 run yields no publishable "
            "false-completion-rate (an FCR 0.0 over no success claims is not a baseline)"
        )
    if prov["unanchored_records"]:
        reasons.append(
            f"{len(prov['unanchored_records'])} counted repair record(s) are unanchored — no "
            "verify bundle score corroborates their before/after; a baseline must anchor RP "
            "to deterministic evidence"
        )
    return (not reasons), scorecard, reasons


def write_baseline(loop_dir: str | Path, out_path: Path, loop_label: str | None = None) -> int:
    ok, scorecard, reasons = build_baseline(loop_dir, loop_label)
    if not ok:
        print(
            "metrics --baseline refused (writes nothing):\n  - " + "\n  - ".join(reasons),
            file=sys.stderr,
        )
        return 1
    baseline = dict(scorecard)
    baseline["baseline"] = {
        "source_example": scorecard["loop"],
        "commit": _git_commit(),
        "inputs": _input_files(loop_dir),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    print(f"wrote baseline -> {_rel(out_path, _REPO_ROOT)}")
    return 0


def run(argv: list[str]) -> int:
    baseline_mode = False
    positional: list[str] = []
    for arg in argv:
        if arg == "--baseline":
            baseline_mode = True
        else:
            positional.append(arg)
    if not positional:
        print("usage: metrics.py [--baseline] <loop-dir>", file=sys.stderr)
        return 2
    loop_dir = positional[0]
    if baseline_mode:
        return write_baseline(loop_dir, _REPO_ROOT / BASELINE_OUTPUT, loop_label=loop_dir)
    print(json.dumps(compute_metrics(loop_dir, loop_label=loop_dir), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    return run(list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
