"""Read-only runtime reports over the append-only event store."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .completion import CompletionPolicyError, criteria_satisfy_completion
from .contract import ContractIssue
from .events import EVENT_SCHEMA_ID, EVENT_TYPES, validate_event
from .paths import resolve_loop_paths
from .reducer import EventReplayError, reduce_events


class RuntimeStoreError(RuntimeError):
    """The runtime store cannot be read well enough to construct a report."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _store_path(target: str | Path) -> Path:
    return resolve_loop_paths(target).loop_dir / "events.db"


def _read_events_readonly(path: Path, run_id: str) -> list[dict[str, Any]]:
    """Read the EventStore row shape without invoking its write-capable connector."""
    try:
        conn = sqlite3.connect(f"{path.absolute().as_uri()}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT run_id, sequence, event_id, type, actor, causation_id, "
                "correlation_id, ts, payload, artifact_hashes FROM events "
                "WHERE run_id = ? ORDER BY sequence ASC",
                (run_id,),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise RuntimeStoreError("corrupt_store", f"cannot read event store: {exc}") from exc
    try:
        return [
            {
                "schema": EVENT_SCHEMA_ID, "run_id": row[0], "sequence": row[1],
                "event_id": row[2], "type": row[3], "actor": row[4],
                "causation_id": row[5], "correlation_id": row[6], "ts": row[7],
                "payload": json.loads(row[8]), "artifact_hashes": json.loads(row[9]),
            }
            for row in rows
        ]
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeStoreError("corrupt_store", f"cannot read event store: {exc}") from exc


def _discover_run_id(path: Path) -> str:
    if not path.exists():
        raise RuntimeStoreError("missing_store", f"event store does not exist: {path}")
    try:
        conn = sqlite3.connect(f"{path.absolute().as_uri()}?mode=ro", uri=True)
        try:
            rows = conn.execute("SELECT DISTINCT run_id FROM events ORDER BY run_id ASC").fetchall()
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise RuntimeStoreError("corrupt_store", f"cannot read event store: {exc}") from exc
    if not rows:
        raise RuntimeStoreError("empty_store", f"event store is empty: {path}")
    if len(rows) != 1:
        raise RuntimeStoreError("ambiguous_run_id", f"event store has ambiguous run_id values: {path}")
    run_id = rows[0][0]
    if not isinstance(run_id, str):
        raise RuntimeStoreError("corrupt_store", f"event store has invalid run_id: {path}")
    return run_id


def _events(target: str | Path, mode: str | None) -> tuple[Path, str, list[dict[str, Any]], dict[str, Any]]:
    path = _store_path(target)
    run_id = _discover_run_id(path)
    events = _read_events_readonly(path, run_id)
    validation: dict[str, Any] | None = None
    for event in events:
        validation = validate_event(event, mode=mode)
    assert validation is not None
    return path, run_id, events, validation


def _state_divergence(paths: Any, projection: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        state = json.loads(paths.state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = None
    if not isinstance(state, dict):
        return [ContractIssue("state_field_mismatch", "state.json is missing or is not an object")]
    expected = {
        "state": projection["state"],
        "iteration_id": projection["iteration_id"],
        "active_task": projection["active_task"],
        "terminal_state": projection["terminal"].get("state") if projection["terminal"] else None,
        "paused": projection["paused"],
        "pause_reason": projection["pause_reason"],
        "pending_approval": projection["pending_approval"],
    }
    issues: list[dict[str, Any]] = []
    for field, value in expected.items():
        if state.get(field, False if field == "paused" else None) != value:
            issues.append(ContractIssue("state_field_mismatch", f"state.json {field!r} differs from event projection"))
    return issues


def _completion_satisfied(terminal: dict[str, Any] | None) -> bool | None:
    if terminal is None:
        return None
    if terminal.get("state") != "Succeeded":
        return False
    try:
        return criteria_satisfy_completion(terminal.get("criteria_met", {}), terminal.get("completion_policy"))
    except CompletionPolicyError:
        return False


def status_report(target: str | Path, *, mode: str | None = None) -> dict[str, Any]:
    """Project a single event stream and reconcile it with live state.json."""
    _, run_id, events, validation = _events(target, mode)
    paths = resolve_loop_paths(target)
    try:
        projection = reduce_events(events)
        divergence = _state_divergence(paths, projection)
    except EventReplayError as exc:
        projection = {"state": None, "iteration_id": None, "active_task": None, "terminal": None}
        divergence = [ContractIssue("illegal_event_sequence", str(exc))]
    return {
        "ok": not divergence,
        "validation_mode": validation["validation_mode"], "requested_mode": validation["requested_mode"],
        "schemas_checked": [EVENT_SCHEMA_ID], "run_id": run_id, "event_count": len(events),
        "state": projection["state"], "iteration_id": projection["iteration_id"],
        "active_task": projection["active_task"], "terminal": projection["terminal"],
        "completion_satisfied": _completion_satisfied(projection["terminal"]),
        "state_json_agrees": not divergence, "divergence": divergence,
    }


def _terminal_desync(paths: Any, projection: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    event_terminal = projection["terminal"]
    try:
        disk_terminal = json.loads(paths.terminal.read_text(encoding="utf-8")) if paths.terminal.exists() else None
    except (OSError, json.JSONDecodeError):
        disk_terminal = None
    if event_terminal is None and disk_terminal is None:
        return None, []
    if event_terminal is None or disk_terminal is None:
        return {"event": event_terminal, "file": disk_terminal}, [
            ContractIssue("desynced_terminal_window", "terminal event and terminal_state.json disagree on presence")
        ]
    if not isinstance(disk_terminal, dict) or disk_terminal.get("state") != event_terminal.get("state"):
        return {"event": event_terminal, "file": disk_terminal}, [
            ContractIssue("desynced_terminal_window", "terminal_state.json differs from event projection")
        ]
    for field in ("criteria_met", "evidence", "false_completion", "completion_policy"):
        if field in disk_terminal and disk_terminal.get(field) != event_terminal.get(field):
            return {"event": event_terminal, "file": disk_terminal}, [
                ContractIssue("terminal_state_mismatch", f"terminal_state.json {field!r} differs from event projection")
            ]
    return None, []


def replay_report(target: str | Path, *, mode: str | None = None) -> dict[str, Any]:
    """Double-fold an event stream and check terminal-window synchronization."""
    _, run_id, events, validation = _events(target, mode)
    paths = resolve_loop_paths(target)
    findings: list[dict[str, Any]] = []
    deterministic = True
    legal_sequence = True
    projection: dict[str, Any] | None = None
    try:
        first = reduce_events(events)
        second = reduce_events(events)
        deterministic = first == second
        projection = first
        if not deterministic:
            findings.append(ContractIssue("nondeterministic_replay", "two event folds produced different projections"))
    except EventReplayError as exc:
        legal_sequence = False
        findings.append(ContractIssue("illegal_event_sequence", str(exc)))
    terminal_desync = None
    if projection is not None:
        terminal_desync, terminal_findings = _terminal_desync(paths, projection)
        findings.extend(terminal_findings)
    return {
        "ok": not findings,
        "validation_mode": validation["validation_mode"], "requested_mode": validation["requested_mode"],
        "schemas_checked": [EVENT_SCHEMA_ID], "run_id": run_id, "event_count": len(events),
        "deterministic": deterministic, "legal_sequence": legal_sequence,
        "terminal_desync": terminal_desync, "findings": findings,
    }
