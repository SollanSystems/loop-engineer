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
    success-claim counts as a false completion (fail-closed, §8).

`--baseline` writes a checked-in scorecard, but only over a genuinely gate-backed
run: it refuses (non-zero, writes nothing) if the run is not `evidence_backed` or
if any record was rejected. Baselining a self-asserted run would itself be a false
completion of ST1.

Pure stdlib, offline, deterministic: the same loop dir yields a byte-identical
scorecard.

Run::

    python3 metrics.py <loop-dir>
    python3 metrics.py --baseline <loop-dir>
"""

from __future__ import annotations

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

# Gate tokens (mirrors inspect_loop._GATE_TOKENS): a real held-out / anti-cheat
# gate invocation writes one of these into the execution trail.
_GATE_TOKENS = ("holdout_gate", "anticheat_scan", "anti_cheat")

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


def _block_claims_success(block_text: str) -> bool:
    tokens = [t.lower() for t in _OUTCOME_RE.findall(block_text)]
    return any(t in _SUCCESS_OUTCOME_TOKENS for t in tokens)


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
        bundles.append(
            {
                "path": path,
                "name": path.name,
                "green": green,
                "iter": _norm_iter(it) if it is not None else None,
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


def _load_gate_verdicts(loop_dir: Path) -> list[dict]:
    """Held-out / anti-cheat gate verdict artifacts (holdout_gate.decide output)."""
    verdicts: list[dict] = []
    for path in sorted(loop_dir.rglob("*.json")):
        if "archive" in path.parts:
            continue
        data = _read_json_object(path)
        if "false_completion" in data and ("verdict" in data or "passed_visible" in data):
            verdicts.append({"path": path, "data": data})
    return verdicts


def _gate_invoked(paths: LoopPaths, gate_verdicts: list[dict]) -> bool:
    """Is a real gate invocation detectable — a recorded verdict artifact, or a
    gate token in the RUNLOG / verify scripts / task verify commands? Mirrors the
    inspector's invocation-evidence rule (HI4)."""
    if gate_verdicts:
        return True
    haystacks = [_read_text(paths.runlog)]
    scripts_dir = paths.workspace / "scripts"
    for name in ("verify-fast", "verify-fast.sh", "verify-full", "verify-full.sh",
                 "verify-safety", "verify-safety.sh"):
        haystacks.append(_read_text(scripts_dir / name))
    tasks = _read_json_object(paths.tasks).get("tasks")
    if isinstance(tasks, list):
        haystacks.extend(str(row.get("verify", "")) for row in tasks if isinstance(row, dict))
    blob = "\n".join(haystacks).lower()
    return any(tok in blob for tok in _GATE_TOKENS)


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

    # FCR-A: a success claim with no green deterministic verify is a false
    # completion (unmatched claims fail closed, §8).
    false_completions = sum(
        1 for iid in claim_iters if not any(b["green"] for b in verify_by_iter.get(iid, []))
    )
    n_claims = len(claim_iters)
    fcr_a = (false_completions / n_claims) if n_claims else 0.0

    # FCR-B: aggregated held-out-gate false_completion flag.
    gate_verdicts = _load_gate_verdicts(loop_dir_path)
    fc_flagged = sum(1 for v in gate_verdicts if v["data"].get("false_completion") is True)
    fcr_b = (fc_flagged / len(gate_verdicts)) if gate_verdicts else None
    fcr_methods_agree = None if fcr_b is None else (fcr_a == fcr_b)

    evidence_backed = _gate_invoked(paths, gate_verdicts)

    # RP: over recomputed-and-agreed repair records only.
    validated = 0
    productive = 0
    rejected: list[dict] = []
    rp_source: list[str] = []
    for path in sorted((loop_dir_path / "repair").glob("*.json")):
        record = _read_json_object(path)
        verdict = recheck_productive(record)
        rel = _rel(path, workspace)
        if verdict["valid"]:
            validated += 1
            rp_source.append(rel)
            if verdict["expected"]:
                productive += 1
        else:
            rejected.append({"record": rel, "reason": verdict["reason"]})
    repair_productivity = (productive / validated) if validated else None

    # Cost-per-success (layer 7): total receipt cost over true completions.
    total_cost, _receipt_count = _load_receipt_costs(loop_dir_path)
    successes = n_claims - false_completions
    cost_per_success = (total_cost / successes) if (total_cost is not None and successes > 0) else None

    fcr_source = sorted({_rel(paths.runlog, workspace)} | {_rel(b["path"], workspace) for b in bundles})
    holdout_source = sorted(_rel(v["path"], workspace) for v in gate_verdicts)
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
            "false_completion_rate_holdout": fcr_b,
            "fcr_methods_agree": fcr_methods_agree,
            "holdout_source": holdout_source,
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

    Returns ``(ok, scorecard, refusal_reasons)``. ``ok`` is False iff the run is
    not evidence-backed or contains rejected records.
    """
    scorecard = compute_metrics(loop_dir, loop_label)
    reasons: list[str] = []
    if not scorecard["evidence_backed"]:
        reasons.append(
            "run is not evidence_backed — no held-out / anti-cheat gate invocation "
            "detectable in the verify trail or RUNLOG"
        )
    rejected = scorecard["provenance"]["rejected_records"]
    if rejected:
        reasons.append(
            f"{len(rejected)} rejected record(s) present (productive disagrees with its own evidence)"
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
