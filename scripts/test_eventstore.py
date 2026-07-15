from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from loop.events import (
    EVENT_SCHEMA_ID,
    DuplicateEventError,
    EventStore,
    EventValidationError,
    SQLiteEventStore,
    SequenceConflictError,
    validate_event,
)


def event(event_type: str = "contract_opened", **overrides: object) -> dict[str, object]:
    payloads = {
        "contract_opened": {"workspace": "demo"},
        "iteration_appended": {"iteration_id": 0, "outcome": "task_passed"},
        "receipt_appended": {"iteration_id": 0, "role": "read", "model": "test", "outcome": "ok"},
        "terminal_written": {"state": "Succeeded", "criteria_met": {"done": True}, "evidence": ["proof"], "false_completion": False},
    }
    result: dict[str, object] = {
        "schema": EVENT_SCHEMA_ID, "event_id": "event-1", "run_id": "run-1", "sequence": 0,
        "type": event_type, "actor": "test", "ts": "2026-01-01T00:00:00+00:00", "payload": payloads[event_type],
    }
    result.update(overrides)
    return result


@pytest.mark.parametrize("event_type", ["contract_opened", "iteration_appended", "receipt_appended", "terminal_written"])
def test_basic_validation_accepts_all_event_types(event_type: str) -> None:
    report = validate_event(event(event_type), mode="basic")
    assert report["ok"] is True
    assert report["issues"] == []


@pytest.mark.parametrize("event_type", ["contract_opened", "iteration_appended", "receipt_appended", "terminal_written"])
def test_release_validation_accepts_event_when_jsonschema_is_available(event_type: str) -> None:
    pytest.importorskip("jsonschema")
    assert validate_event(event(event_type), mode="release")["ok"] is True


def test_structural_validation_type_checks_required_surface() -> None:
    report = validate_event(event(sequence="0", payload="not-an-object", artifact_hashes=[{"path": 1, "sha256": 1}]), mode="basic")
    messages = " ".join(issue["message"] for issue in report["issues"])
    assert report["ok"] is False
    assert "sequence" in messages and "payload" in messages and "artifact_hashes" in messages


@pytest.mark.parametrize("mode", ["basic", "release"])
@pytest.mark.parametrize("iteration_id", [None, True, -1])
def test_receipt_validation_requires_a_non_negative_integer_iteration_id(mode: str, iteration_id: int | bool | None) -> None:
    if mode == "release":
        pytest.importorskip("jsonschema")
    payload = {"role": "read", "model": "test", "outcome": "ok"}
    if iteration_id is not None:
        payload["iteration_id"] = iteration_id
    assert validate_event(event("receipt_appended", payload=payload), mode=mode)["ok"] is False


def test_store_assigns_sequences_round_trips_and_is_a_protocol(tmp_path) -> None:
    store = SQLiteEventStore(tmp_path / "events.db")
    assert isinstance(store, EventStore)
    assert store.latest_sequence("run") is None
    records = [store.append("run", "contract_opened", {"workspace": "w"}, actor="t"),
               store.append("run", "iteration_appended", {"iteration_id": 0, "outcome": "task_passed"}, actor="t"),
               store.append("run", "receipt_appended", {"iteration_id": 0, "role": "read", "model": "m", "outcome": "ok"}, actor="t", artifact_hashes=[{"path": "a", "sha256": "a" * 64}])]
    assert [record["sequence"] for record in records] == [0, 1, 2]
    assert [record["sequence"] for record in store.read("run")] == [0, 1, 2]
    assert [record["sequence"] for record in store.read("run", since_sequence=0)] == [1, 2]
    assert store.read("run", since_sequence=1)[0]["sequence"] == 2
    assert store.read("run")[2]["artifact_hashes"] == [{"path": "a", "sha256": "a" * 64}]


def test_store_rejects_duplicates_conflicts_and_malformed_events(tmp_path) -> None:
    store = SQLiteEventStore(tmp_path / "events.db")
    store.append("run", "contract_opened", {"workspace": "w"}, actor="t", event_id="same")
    with pytest.raises(DuplicateEventError):
        store.append("other", "contract_opened", {"workspace": "w"}, actor="t", event_id="same")
    with pytest.raises(SequenceConflictError):
        store.append("run", "iteration_appended", {"iteration_id": 0, "outcome": "task_passed"}, actor="t", expected_sequence=0)
    appended = store.append("run", "iteration_appended", {"iteration_id": 0, "outcome": "task_passed"}, actor="t", expected_sequence=1)
    assert appended["sequence"] == 1
    with pytest.raises(EventValidationError):
        store.append("run", "bogus", {}, actor="t")
    assert store.latest_sequence("run") == 1


def test_store_is_wal_and_raw_sql_cannot_mutate_rows(tmp_path) -> None:
    path = tmp_path / "events.db"
    store = SQLiteEventStore(path)
    store.append("run", "contract_opened", {"workspace": "w"}, actor="t")
    raw = store._connect()
    try:
        assert raw.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert raw.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert raw.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="append-only"):
            raw.execute("UPDATE events SET type = 'x'")
        with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="append-only"):
            raw.execute("DELETE FROM events")
    finally:
        raw.close()


def test_concurrent_appends_are_serialized(tmp_path) -> None:
    path = tmp_path / "events.db"

    def append(index: int) -> int:
        return SQLiteEventStore(path).append("run", "iteration_appended", {"iteration_id": index, "outcome": "task_passed"}, actor="t")["sequence"]

    SQLiteEventStore(path).append("run", "contract_opened", {"workspace": "w"}, actor="t")
    with ThreadPoolExecutor(max_workers=8) as pool:
        sequences = list(pool.map(append, range(8)))
    assert set(sequences) == set(range(1, 9))


def terminal_superseded_event(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "schema": EVENT_SCHEMA_ID, "event_id": "superseded-1", "run_id": "run-1", "sequence": 1,
        "type": "terminal_superseded", "actor": "test", "causation_id": "terminal-1",
        "correlation_id": None, "ts": "2026-01-01T00:00:01+00:00",
        "payload": {"state": "FailedSafety", "criteria_met": {"done": True}, "evidence": ["proof"],
                    "false_completion": False, "justification": "audit correction",
                    "authority": {"by": "ops", "at": "2026-01-01T00:00:01+00:00"}},
    }
    result.update(overrides)
    return result


def test_event_types_include_terminal_superseded_and_match_schema_enum() -> None:
    schema = __import__("json").load(open("schemas/event.schema.json", encoding="utf-8"))
    from loop.events import EVENT_TYPES

    assert "terminal_superseded" in EVENT_TYPES
    assert "terminal_superseded" in schema["properties"]["type"]["enum"]
    assert set(EVENT_TYPES) == set(schema["properties"]["type"]["enum"])


@pytest.mark.parametrize("mode", ["basic", "release"])
def test_terminal_superseded_validates_in_basic_and_release_modes(mode: str) -> None:
    if mode == "release":
        pytest.importorskip("jsonschema")
    assert validate_event(terminal_superseded_event(), mode=mode)["ok"] is True


@pytest.mark.parametrize("mode", ["basic", "release"])
@pytest.mark.parametrize("payload", [
    {"criteria_met": {}, "evidence": [], "false_completion": False, "justification": "j", "authority": {"by": "a", "at": "t"}},
    {"state": 1, "criteria_met": {}, "evidence": [], "false_completion": False, "justification": "j", "authority": {"by": "a", "at": "t"}},
    {"state": "FailedSafety", "evidence": [], "false_completion": False, "justification": "j", "authority": {"by": "a", "at": "t"}},
    {"state": "FailedSafety", "criteria_met": [], "evidence": [], "false_completion": False, "justification": "j", "authority": {"by": "a", "at": "t"}},
    {"state": "FailedSafety", "criteria_met": {}, "false_completion": False, "justification": "j", "authority": {"by": "a", "at": "t"}},
    {"state": "FailedSafety", "criteria_met": {}, "evidence": "proof", "false_completion": False, "justification": "j", "authority": {"by": "a", "at": "t"}},
    {"state": "FailedSafety", "criteria_met": {}, "evidence": [], "justification": "j", "authority": {"by": "a", "at": "t"}},
    {"state": "FailedSafety", "criteria_met": {}, "evidence": [], "false_completion": 0, "justification": "j", "authority": {"by": "a", "at": "t"}},
    {"state": "FailedSafety", "criteria_met": {}, "evidence": [], "false_completion": False, "authority": {"by": "a", "at": "t"}},
    {"state": "FailedSafety", "criteria_met": {}, "evidence": [], "false_completion": False, "justification": " ", "authority": {"by": "a", "at": "t"}},
    {"state": "FailedSafety", "criteria_met": {}, "evidence": [], "false_completion": False, "justification": "j"},
    {"state": "FailedSafety", "criteria_met": {}, "evidence": [], "false_completion": False, "justification": "j", "authority": {"by": "", "at": "t"}},
])
def test_terminal_superseded_rejects_malformed_payload_fields(mode: str, payload: dict[str, object]) -> None:
    if mode == "release":
        pytest.importorskip("jsonschema")
    assert validate_event(terminal_superseded_event(payload=payload), mode=mode)["ok"] is False
    with pytest.raises(EventValidationError):
        SQLiteEventStore(":memory:").append("run", "terminal_superseded", payload, actor="test")


def test_store_appends_well_formed_terminal_superseded(tmp_path) -> None:
    store = SQLiteEventStore(tmp_path / "events.db")
    store.append("run", "contract_opened", {"workspace": "w"}, actor="test")
    terminal = store.append("run", "terminal_written", {"state": "Succeeded", "criteria_met": {"done": True},
                             "evidence": ["proof"], "false_completion": False}, actor="test")
    correction = store.append("run", "terminal_superseded", terminal_superseded_event()["payload"], actor="test",
                              causation_id=terminal["event_id"])
    assert correction["type"] == "terminal_superseded"
    assert correction["causation_id"] == terminal["event_id"]
