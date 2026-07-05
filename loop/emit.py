"""Writer API for foreign runtimes (B1). A writer, never a runtime: it renders
contract artifacts and refuses dishonest ones — no orchestration, no execution.

The G1 cross-check (a Succeeded terminal needs evidence and a met criterion)
is enforced HERE, at write time, before doctor ever sees the file.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .contract import (
    TERMINAL_STATES,
    _validate_record,
    _validate_terminal,
    _validation_mode,
)
from .paths import resolve_loop_paths
from .scaffold import scaffold

_ITERATION_OUTCOMES = (
    "task_passed",
    "task_failed",
    "repair_triggered",
    "approval_requested",
    "replanned",
    "terminal",
)
_RECEIPT_ROLES = ("read", "reason", "write", "orchestrate")
_RECEIPT_OUTCOMES = ("ok", "fail", "escalated")


class EmitError(ValueError):
    """A write was refused: it would produce a dishonest or schema-invalid artifact."""


def open_contract(target: str | Path) -> dict[str, Any]:
    """Render a fresh, doctor-clean contract. Delegates to the scaffold renderer."""
    return scaffold(target)


def _require_contract(target: str | Path):
    paths = resolve_loop_paths(target)
    if not paths.state.is_file():
        raise EmitError(
            f"no loop contract at {paths.workspace} (missing .loop/state.json) — "
            f"call emit.open_contract() first"
        )
    return paths


def _read_state(paths) -> dict[str, Any]:
    try:
        data = json.loads(paths.state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EmitError(f"unreadable state.json: {exc}") from exc
    if not isinstance(data, dict):
        raise EmitError("state.json must hold a JSON object")
    return data


def _atomic_write_text(path: Path, text: str) -> None:
    """Whole-file write via a temp file in the SAME directory then os.replace, so a
    crash mid-write can never leave truncated JSON. The temp file is removed on any
    failure, leaving no litter."""
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _write_state(paths, state: dict[str, Any]) -> None:
    _atomic_write_text(paths.state, json.dumps(state, indent=2) + "\n")


def append_iteration(
    target: str | Path,
    *,
    iteration_id: int,
    outcome: str,
    task_id: str = "",
    actions: Sequence[str] = (),
    verify_cmd: str = "",
    verify_outcome: str = "",
    notes: str = "",
) -> Path:
    """Append one iteration block to RUNLOG.md (the shape scripts/metrics.py
    parses: `## Iteration <id>` header + a backticked outcome token) and advance
    .loop/state.json's iteration_id/active_task."""
    if outcome not in _ITERATION_OUTCOMES:
        raise EmitError(f"unknown iteration outcome {outcome!r}; expected one of {_ITERATION_OUTCOMES}")
    paths = _require_contract(target)

    lines = [
        "",
        f"## Iteration {iteration_id} — {datetime.now(timezone.utc).date().isoformat()}",
        "",
    ]
    if task_id:
        lines.append(f"**Active task:** `{task_id}`")
        lines.append("")
    if actions:
        lines.append("### Actions taken")
        lines.append("")
        lines.extend(f"- {a}" for a in actions)
        lines.append("")
    if verify_cmd or verify_outcome:
        lines.append("### Verification result")
        lines.append("")
        lines.append(f"- **Gate:** `{verify_cmd}` — {verify_outcome}")
        lines.append("")
    lines.append("### Outcome")
    lines.append("")
    lines.append(f"`{outcome}`")
    lines.append("")
    if notes:
        lines.append("### Notes")
        lines.append("")
        lines.append(notes)
        lines.append("")

    runlog = paths.runlog
    if not runlog.exists():
        runlog = paths.workspace / "RUNLOG.md"
        runlog.write_text(f"# RUNLOG.md — {paths.workspace.name}\n", encoding="utf-8")
    with runlog.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    state = _read_state(paths)
    state["iteration_id"] = str(iteration_id)
    if task_id:
        state["active_task"] = task_id
    _write_state(paths, state)
    return runlog


def append_receipt(
    target: str | Path,
    *,
    iteration_id: int,
    role: str,
    model: str,
    outcome: str,
    dispatch_id: str | None = None,
    tokens: int | None = None,
    cost_usd: float | None = None,
    ts: str | None = None,
) -> Path:
    """Append one loop-engineer/receipt@1 line to .loop/receipts/receipts.jsonl."""
    if role not in _RECEIPT_ROLES:
        raise EmitError(f"unknown receipt role {role!r}; expected one of {_RECEIPT_ROLES}")
    if outcome not in _RECEIPT_OUTCOMES:
        raise EmitError(f"unknown receipt outcome {outcome!r}; expected one of {_RECEIPT_OUTCOMES}")
    if not isinstance(iteration_id, int) or isinstance(iteration_id, bool) or iteration_id < 0:
        raise EmitError("iteration_id must be a non-negative integer")
    paths = _require_contract(target)

    record: dict[str, Any] = {
        "schema": "loop-engineer/receipt@1",
        "iteration_id": iteration_id,
        "dispatch_id": dispatch_id,
        "role": role,
        "model": model,
        "outcome": outcome,
        "tokens": tokens,
        "cost_usd": cost_usd,
        "ts": ts,
    }
    receipts = paths.loop_dir / "receipts" / "receipts.jsonl"
    issues: list[dict] = []
    _validate_record(record, "receipt", receipts, _validation_mode(), issues)
    if issues:
        raise EmitError(f"receipt failed schema validation: {issues}")
    receipts.parent.mkdir(parents=True, exist_ok=True)
    with receipts.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return receipts


def terminate(
    target: str | Path,
    *,
    state: str,
    criteria_met: dict[str, bool],
    evidence: list[str],
    reason: str = "",
    iteration_id: int | None = None,
    false_completion: bool = False,
    lessons_ref: str | None = None,
    force: bool = False,
) -> Path:
    """Write .loop/terminal_state.json (and stamp state.json.terminal_state).

    Refuses an evidence-free Succeeded — the G1 cross-check at write time:
    Succeeded requires non-empty evidence, at least one met criterion, and
    false_completion=False.

    The terminal record is written once: a second terminate on an existing
    terminal file is refused unless force=True (the deliberate-overwrite escape
    hatch).
    """
    if state not in TERMINAL_STATES:
        raise EmitError(f"unknown terminal state {state!r}; expected one of {TERMINAL_STATES}")
    if state == "Succeeded":
        if false_completion:
            raise EmitError("refusing Succeeded with false_completion=True (G1 contradiction)")
        if not evidence:
            raise EmitError("refusing evidence-free Succeeded: evidence[] is empty (G1)")
        if not any(v is True for v in criteria_met.values()):
            raise EmitError("refusing Succeeded with no met (true) entry in criteria_met (G1)")
    if not all(isinstance(v, bool) for v in criteria_met.values()):
        raise EmitError("criteria_met values must be booleans")
    paths = _require_contract(target)
    terminal_path = paths.loop_dir / "terminal_state.json"
    if terminal_path.is_file() and not force:
        raise EmitError(
            f"terminal already written at {terminal_path} — the terminal record is "
            f"written once; pass force=True to deliberately overwrite it"
        )
    current = _read_state(paths)

    terminal: dict[str, Any] = {
        "schema": "loop-engineer/terminal@1",
        "project": paths.workspace.name,
        "state": state,
        "criteria_met": dict(criteria_met),
        "evidence": list(evidence),
        "false_completion": false_completion,
        "terminated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if reason:
        terminal["reason"] = reason
    if iteration_id is not None:
        terminal["iteration_id"] = iteration_id
    if lessons_ref is not None:
        terminal["lessons_ref"] = lessons_ref

    issues: list[dict] = []
    _validate_terminal(terminal, terminal_path, issues)
    if issues:
        raise EmitError(f"terminal failed validation before write: {issues}")

    _atomic_write_text(terminal_path, json.dumps(terminal, indent=2) + "\n")
    current["terminal_state"] = state
    _write_state(paths, current)
    return terminal_path
