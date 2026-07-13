"""Writer API for foreign runtimes (B1). A writer, never a runtime: it renders
contract artifacts and refuses dishonest ones — no orchestration, no execution.

The G1 cross-check (a Succeeded terminal needs evidence and every required
criterion) is enforced HERE, at write time, before doctor ever sees the file.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from . import fsm
from .completion import (
    CompletionPolicyError,
    criteria_satisfy_completion,
    normalize_completion_policy,
    unmet_required_criteria,
)
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
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _atomic_create_text(path: Path, text: str) -> None:
    """Create ``path`` exactly once from a fully-written same-directory temp file.

    The hard-link step is atomic and refuses an existing destination, closing the
    check-then-replace race that would otherwise let concurrent terminators
    overwrite one another.  The destination never names a partially-written file.
    """
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.link(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def _require_iteration_id(value: object, *, optional: bool = False) -> int | None:
    if optional and value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise EmitError("iteration_id must be a non-negative integer")
    return value


def _write_state(paths, state: dict[str, Any]) -> None:
    _atomic_write_text(paths.state, json.dumps(state, indent=2) + "\n")


def append_iteration(
    target: str | Path,
    *,
    iteration_id: int,
    outcome: str,
    state: str | None = None,
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
    if state is not None and (not isinstance(state, str) or not state.strip()):
        raise EmitError("state must be a non-empty string when provided")
    _require_iteration_id(iteration_id)
    paths = _require_contract(target)
    current = _read_state(paths)
    if state is not None:
        if not fsm.is_legal_transition(current.get("state"), state):
            raise EmitError(f"illegal FSM transition {current.get('state')!r} -> {state!r}")
        current["state"] = state
    current["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

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

    current["iteration_id"] = iteration_id
    if task_id:
        current["active_task"] = task_id
    _write_state(paths, current)
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
    completion_policy: object | None = None,
    force: bool = False,
) -> Path:
    """Write an immutable ``.loop/terminal_state.json`` and stamp state.json.

    ``Succeeded`` requires non-empty evidence, ``false_completion=False``, and
    every declared criterion to satisfy the explicit completion policy.  The
    compatibility default is ``{"mode": "all_required"}``, and new records
    always persist it.

    ``force`` remains temporarily in the signature so older callers receive an
    actionable error instead of silently overwriting an audit record.  It never
    permits replacement.
    """
    if state not in TERMINAL_STATES:
        raise EmitError(f"unknown terminal state {state!r}; expected one of {TERMINAL_STATES}")
    if force:
        raise EmitError(
            "force=True is no longer supported: terminal records are immutable; "
            "record any correction as a separate administrative event"
        )
    if not isinstance(criteria_met, dict):
        raise EmitError("criteria_met must be an object")
    if not all(isinstance(key, str) and key.strip() for key in criteria_met):
        raise EmitError("criteria_met keys must be non-empty strings")
    if not all(isinstance(value, bool) for value in criteria_met.values()):
        raise EmitError("criteria_met values must be booleans")
    if not isinstance(evidence, list):
        raise EmitError("evidence must be a list")
    if any(not isinstance(item, str) or not item.strip() for item in evidence):
        raise EmitError("evidence entries must be non-empty strings")
    if len(set(evidence)) != len(evidence):
        raise EmitError("evidence entries must be unique")
    try:
        normalized_policy = normalize_completion_policy(completion_policy)
    except CompletionPolicyError as exc:
        raise EmitError(str(exc)) from exc
    _require_iteration_id(iteration_id, optional=True)

    if state == "Succeeded":
        if false_completion:
            raise EmitError("refusing Succeeded with false_completion=True (G1 contradiction)")
        if not evidence:
            raise EmitError("refusing evidence-free Succeeded: evidence[] is empty (G1)")
        if not criteria_satisfy_completion(criteria_met, normalized_policy):
            unmet = unmet_required_criteria(criteria_met)
            detail = ", ".join(unmet) if unmet else "no criteria were declared"
            raise EmitError(
                "refusing Succeeded because not all required criteria are proven true: " + detail
            )

    paths = _require_contract(target)
    terminal_path = paths.loop_dir / "terminal_state.json"
    if terminal_path.is_file():
        raise EmitError(f"terminal already written at {terminal_path} — terminal records are immutable")
    current = _read_state(paths)

    terminal: dict[str, Any] = {
        "schema": "loop-engineer/terminal@1",
        "project": paths.workspace.name,
        "state": state,
        "criteria_met": dict(criteria_met),
        "completion_policy": normalized_policy,
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

    try:
        _atomic_create_text(terminal_path, json.dumps(terminal, indent=2) + "\n")
    except FileExistsError as exc:
        raise EmitError(
            f"terminal already written at {terminal_path} — terminal records are immutable"
        ) from exc
    except OSError as exc:
        raise EmitError(f"terminal write failed at {terminal_path}: {exc}") from exc
    if not fsm.is_legal_transition(current.get("state"), fsm.TERMINAL_MARKER):
        raise EmitError(
            f"terminal written at {terminal_path} but state.json has no legal transition "
            f"from {current.get('state')!r} to {fsm.TERMINAL_MARKER!r}"
        )
    current["state"] = fsm.TERMINAL_MARKER
    current["terminal_state"] = state
    current["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        _write_state(paths, current)
    except OSError as exc:
        raise EmitError(
            f"terminal written at {terminal_path} but state.json was not stamped: {exc} — "
            "call emit.sync_state_to_terminal() to reconcile"
        ) from exc
    return terminal_path


def sync_state_to_terminal(target: str | Path) -> Path:
    """Reconcile state.json's FSM marker and terminal verdict from its end record.

    The narrow repair for a crash or failed write between the immutable
    ``terminal_state.json`` creation and the state.json stamp — the two files
    are not one transaction.  Reads the terminal record and reconciles
    state.json to it; never creates, alters, or removes the terminal file.
    """
    paths = _require_contract(target)
    terminal_path = paths.loop_dir / "terminal_state.json"
    if not terminal_path.is_file():
        raise EmitError(f"no terminal record at {terminal_path} — nothing to sync")
    try:
        terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EmitError(f"unreadable terminal_state.json: {exc}") from exc
    if not isinstance(terminal, dict) or terminal.get("state") not in TERMINAL_STATES:
        raise EmitError(f"terminal_state.json at {terminal_path} does not hold a valid terminal record")
    current = _read_state(paths)
    changed = False
    if current.get("terminal_state") != terminal["state"]:
        current["terminal_state"] = terminal["state"]
        changed = True
    if current.get("state") != fsm.TERMINAL_MARKER:
        current["state"] = fsm.TERMINAL_MARKER
        changed = True
    if changed:
        current["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _write_state(paths, current)
    return paths.state
