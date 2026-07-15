"""event@1 EventStore protocol and SQLite/WAL implementation (ADR 0001)."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .contract import ContractIssue, _resolve_requested_mode, _schemas_dir
from .emit import _ITERATION_OUTCOMES, _RECEIPT_OUTCOMES, _RECEIPT_ROLES

EVENT_SCHEMA_ID = "loop-engineer/event@1"
EVENT_TYPES = ("contract_opened", "iteration_appended", "receipt_appended", "terminal_written", "terminal_superseded")

_PAYLOAD_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "contract_opened": ("workspace",),
    "iteration_appended": ("iteration_id", "outcome"),
    "receipt_appended": ("iteration_id", "role", "model", "outcome"),
    "terminal_written": ("state", "criteria_met", "evidence", "false_completion"),
    "terminal_superseded": ("state", "criteria_met", "evidence", "false_completion", "justification", "authority"),
}

_CREATE_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_id TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,
    actor TEXT NOT NULL,
    causation_id TEXT,
    correlation_id TEXT,
    ts TEXT NOT NULL,
    payload TEXT NOT NULL,
    artifact_hashes TEXT NOT NULL,
    PRIMARY KEY (run_id, sequence)
)
"""
_CREATE_NO_UPDATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events table is append-only: UPDATE is forbidden'); END
"""
_CREATE_NO_DELETE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events table is append-only: DELETE is forbidden'); END
"""


class EventValidationError(ValueError):
    """A candidate event failed event@1 validation and was refused before write."""


class DuplicateEventError(ValueError):
    """An event_id already exists in the store; callers may treat this as a retry."""


class SequenceConflictError(ValueError):
    """expected_sequence differed from the atomically assigned next sequence."""


@runtime_checkable
class EventStore(Protocol):
    def append(self, run_id: str, event_type: str, payload: Mapping[str, Any], *, actor: str,
               event_id: str | None = None, causation_id: str | None = None,
               correlation_id: str | None = None,
               artifact_hashes: Sequence[Mapping[str, Any]] | None = None,
               expected_sequence: int | None = None, ts: str | None = None) -> dict[str, Any]: ...

    def read(self, run_id: str, *, since_sequence: int | None = None) -> list[dict[str, Any]]: ...

    def latest_sequence(self, run_id: str) -> int | None: ...


def _load_event_schema() -> dict[str, Any]:
    return json.loads((_schemas_dir() / "event.schema.json").read_text(encoding="utf-8"))


def _payload_issues(event_type: str, payload: Any) -> list[str]:
    """Cross-field payload validation shared by jsonschema and structural modes."""
    if not isinstance(payload, dict):
        return [f"payload must be an object for type {event_type!r}"]
    issues: list[str] = []
    for field in _PAYLOAD_REQUIRED_FIELDS.get(event_type, ()):
        if field not in payload:
            issues.append(f"{event_type} payload missing {field!r}")
    if event_type == "contract_opened":
        if "workspace" in payload and (not isinstance(payload["workspace"], str) or not payload["workspace"]):
            issues.append("contract_opened.workspace must be a non-empty string")
    elif event_type == "iteration_appended":
        value = payload.get("iteration_id")
        if "iteration_id" in payload and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            issues.append("iteration_appended.iteration_id must be a non-negative integer")
        if payload.get("outcome") not in _ITERATION_OUTCOMES:
            issues.append(f"iteration_appended.outcome must be one of {_ITERATION_OUTCOMES}")
        if "state" in payload and payload["state"] is not None and not isinstance(payload["state"], str):
            issues.append("iteration_appended.state must be a string or null")
    elif event_type == "receipt_appended":
        value = payload.get("iteration_id")
        if "iteration_id" in payload and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            issues.append("receipt_appended.iteration_id must be a non-negative integer")
        if payload.get("role") not in _RECEIPT_ROLES:
            issues.append(f"receipt_appended.role must be one of {_RECEIPT_ROLES}")
        if "model" in payload and (not isinstance(payload["model"], str) or not payload["model"]):
            issues.append("receipt_appended.model must be a non-empty string")
        if payload.get("outcome") not in _RECEIPT_OUTCOMES:
            issues.append(f"receipt_appended.outcome must be one of {_RECEIPT_OUTCOMES}")
    elif event_type == "terminal_written":
        if "state" in payload and not isinstance(payload["state"], str):
            issues.append("terminal_written.state must be a string")
        if "criteria_met" in payload and not isinstance(payload["criteria_met"], dict):
            issues.append("terminal_written.criteria_met must be an object")
        if "evidence" in payload and not isinstance(payload["evidence"], list):
            issues.append("terminal_written.evidence must be an array")
        if "false_completion" in payload and not isinstance(payload["false_completion"], bool):
            issues.append("terminal_written.false_completion must be a boolean")
    elif event_type == "terminal_superseded":
        if "state" in payload and not isinstance(payload["state"], str):
            issues.append("terminal_superseded.state must be a string")
        if "criteria_met" in payload and not isinstance(payload["criteria_met"], dict):
            issues.append("terminal_superseded.criteria_met must be an object")
        if "evidence" in payload and not isinstance(payload["evidence"], list):
            issues.append("terminal_superseded.evidence must be an array")
        if "false_completion" in payload and not isinstance(payload["false_completion"], bool):
            issues.append("terminal_superseded.false_completion must be a boolean")
        if "justification" in payload and (not isinstance(payload["justification"], str)
                                            or not payload["justification"].strip()):
            issues.append("terminal_superseded.justification must be a non-empty string")
        if "authority" in payload:
            authority = payload["authority"]
            if (not isinstance(authority, dict)
                    or not isinstance(authority.get("by"), str) or not authority.get("by", "").strip()
                    or not isinstance(authority.get("at"), str) or not authority.get("at", "").strip()):
                issues.append("terminal_superseded.authority must be an object with non-empty by/at strings")
    return issues


def _structural_validate_event(data: dict[str, Any]) -> list[str]:
    """Stdlib fallback equivalent to the schema's required envelope surface."""
    issues: list[str] = []
    if data.get("schema") != EVENT_SCHEMA_ID:
        issues.append(f"expected schema {EVENT_SCHEMA_ID!r}, got {data.get('schema')!r}")
    for field in ("event_id", "run_id", "actor", "ts"):
        if not isinstance(data.get(field), str) or not data[field]:
            issues.append(f"{field} must be a non-empty string")
    sequence = data.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        issues.append("sequence must be a non-negative integer")
    if not isinstance(data.get("type"), str) or data["type"] not in EVENT_TYPES:
        issues.append(f"type must be one of {EVENT_TYPES}")
    for field in ("causation_id", "correlation_id"):
        if field in data and data[field] is not None and not isinstance(data[field], str):
            issues.append(f"{field} must be a string or null")
    hashes = data.get("artifact_hashes", [])
    if not isinstance(hashes, list):
        issues.append("artifact_hashes must be an array")
    else:
        for item in hashes:
            path = item.get("path") if isinstance(item, dict) else None
            digest = item.get("sha256") if isinstance(item, dict) else None
            if not isinstance(path, str) or not path or not isinstance(digest, str) or re.search(r"^[0-9a-f]{64}$", digest) is None:
                issues.append("artifact_hashes entries need non-empty string path + 64-character lowercase hex sha256")
                break
    if isinstance(data.get("type"), str):
        issues.extend(_payload_issues(data["type"], data.get("payload")))
    return issues


def _jsonschema_validate_event(data: dict[str, Any]) -> list[str]:
    import jsonschema  # type: ignore

    validator = jsonschema.Draft202012Validator(_load_event_schema())
    issues = [f"{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}" for error in validator.iter_errors(data)]
    if isinstance(data.get("type"), str):
        issues.extend(_payload_issues(data["type"], data.get("payload")))
    return issues


def _validate_event_dict(data: Any, *, mode: str | None = None) -> dict[str, Any]:
    requested_mode, resolved_mode = _resolve_requested_mode(mode)
    if not isinstance(data, dict):
        issues = ["event record must be an object"]
    elif resolved_mode == "jsonschema":
        issues = _jsonschema_validate_event(data)
    else:
        issues = _structural_validate_event(data)
    return {"ok": not issues, "validation_mode": resolved_mode, "requested_mode": requested_mode,
            "schemas_checked": [EVENT_SCHEMA_ID],
            "issues": [ContractIssue("invalid_event", issue) for issue in issues]}


def validate_event(data: dict[str, Any], *, mode: str | None = None) -> dict[str, Any]:
    """Validate a standalone event@1 record in the requested validation mode."""
    return _validate_event_dict(data, mode=mode)


class SQLiteEventStore:
    """A transactional SQLite/WAL event store with DB-enforced append-only rows."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), isolation_level=None, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute(_CREATE_EVENTS_TABLE)
        conn.execute(_CREATE_NO_UPDATE_TRIGGER)
        conn.execute(_CREATE_NO_DELETE_TRIGGER)
        return conn

    def append(self, run_id: str, event_type: str, payload: Mapping[str, Any], *, actor: str,
               event_id: str | None = None, causation_id: str | None = None,
               correlation_id: str | None = None,
               artifact_hashes: Sequence[Mapping[str, Any]] | None = None,
               expected_sequence: int | None = None, ts: str | None = None) -> dict[str, Any]:
        normalized_payload: Any = dict(payload) if isinstance(payload, Mapping) else payload
        normalized_hashes: Any = [] if artifact_hashes is None else [
            dict(item) if isinstance(item, Mapping) else item for item in artifact_hashes
        ]
        record = {"schema": EVENT_SCHEMA_ID, "event_id": event_id if event_id is not None else uuid.uuid4().hex, "run_id": run_id,
                  "sequence": 0, "type": event_type, "actor": actor, "causation_id": causation_id,
                  "correlation_id": correlation_id, "ts": ts if ts is not None else datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "payload": normalized_payload, "artifact_hashes": normalized_hashes}
        report = _validate_event_dict(record)
        if not report["ok"]:
            raise EventValidationError(f"event failed validation: {report['issues']}")
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT MAX(sequence) FROM events WHERE run_id = ?", (run_id,)).fetchone()
            next_sequence = 0 if row[0] is None else row[0] + 1
            if expected_sequence is not None and expected_sequence != next_sequence:
                conn.execute("ROLLBACK")
                raise SequenceConflictError(f"expected next sequence {next_sequence} for run_id {run_id!r}, caller supplied {expected_sequence}")
            record["sequence"] = next_sequence
            payload_json = json.dumps(record["payload"], sort_keys=True)
            hashes_json = json.dumps([dict(item) for item in record["artifact_hashes"]], sort_keys=True)
            try:
                conn.execute("INSERT INTO events (run_id, sequence, event_id, type, actor, causation_id, correlation_id, ts, payload, artifact_hashes) VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (record["run_id"], record["sequence"], record["event_id"], record["type"], record["actor"], record["causation_id"], record["correlation_id"], record["ts"], payload_json, hashes_json))
            except sqlite3.IntegrityError as exc:
                conn.execute("ROLLBACK")
                raise DuplicateEventError(record["event_id"]) from exc
            conn.execute("COMMIT")
        finally:
            conn.close()
        return record

    def read(self, run_id: str, *, since_sequence: int | None = None) -> list[dict[str, Any]]:
        """Read the full stream for None, or events strictly after an integer cursor."""
        conn = self._connect()
        try:
            operator, cursor = (">=", 0) if since_sequence is None else (">", since_sequence)
            rows = conn.execute(f"SELECT run_id, sequence, event_id, type, actor, causation_id, correlation_id, ts, payload, artifact_hashes FROM events WHERE run_id = ? AND sequence {operator} ? ORDER BY sequence ASC", (run_id, cursor)).fetchall()
        finally:
            conn.close()
        return [{"schema": EVENT_SCHEMA_ID, "run_id": row[0], "sequence": row[1], "event_id": row[2], "type": row[3], "actor": row[4], "causation_id": row[5], "correlation_id": row[6], "ts": row[7], "payload": json.loads(row[8]), "artifact_hashes": json.loads(row[9])} for row in rows]

    def latest_sequence(self, run_id: str) -> int | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT MAX(sequence) FROM events WHERE run_id = ?", (run_id,)).fetchone()
        finally:
            conn.close()
        return row[0]
