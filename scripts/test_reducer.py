from __future__ import annotations

import json

import pytest

from loop.events import EVENT_SCHEMA_ID, SQLiteEventStore
from loop.reducer import EventReplayError, reduce_events


def stream(run_id: str = "run") -> list[dict[str, object]]:
    base = {"schema": EVENT_SCHEMA_ID, "run_id": run_id, "actor": "t", "causation_id": None, "correlation_id": None}
    return [
        {**base, "event_id": "e0", "sequence": 0, "type": "contract_opened", "ts": "2026-01-01T00:00:00+00:00", "payload": {"workspace": "w"}},
        {**base, "event_id": "e1", "sequence": 1, "type": "iteration_appended", "ts": "2026-01-01T00:00:01+00:00", "payload": {"iteration_id": 1, "outcome": "task_passed", "state": "plan"}},
        {**base, "event_id": "e2", "sequence": 2, "type": "iteration_appended", "ts": "2026-01-01T00:00:02+00:00", "payload": {"iteration_id": 2, "outcome": "task_passed", "state": "critique-plan"}},
        {**base, "event_id": "e3", "sequence": 3, "type": "receipt_appended", "ts": "2026-01-01T00:00:03+00:00", "payload": {"iteration_id": 2, "role": "read", "model": "m", "outcome": "ok"}},
        {**base, "event_id": "e4", "sequence": 4, "type": "terminal_written", "ts": "2026-01-01T00:00:04+00:00", "payload": {"state": "Succeeded", "criteria_met": {"done": True}, "evidence": ["proof"], "false_completion": False}},
    ]


def test_reducer_is_deterministic_and_resumable() -> None:
    events = stream()
    whole = reduce_events(events)
    assert json.dumps(whole, sort_keys=True) == json.dumps(reduce_events(events), sort_keys=True)
    assert reduce_events(events[2:], initial=reduce_events(events[:2])) == whole
    assert reduce_events([])["event_count"] == 0


def test_reducer_is_deterministic_after_store_round_trip(tmp_path) -> None:
    store = SQLiteEventStore(tmp_path / "events.db")
    for item in stream():
        store.append(item["run_id"], item["type"], item["payload"], actor=item["actor"], event_id=item["event_id"], ts=item["ts"])
    assert json.dumps(reduce_events(store.read("run")), sort_keys=True) == json.dumps(reduce_events(store.read("run")), sort_keys=True)


def test_reducer_resumes_from_an_explicit_sequence_zero_cursor(tmp_path) -> None:
    store = SQLiteEventStore(tmp_path / "events.db")
    for item in stream():
        store.append(item["run_id"], item["type"], item["payload"], actor=item["actor"], event_id=item["event_id"], ts=item["ts"])
    whole = reduce_events(store.read("run"))
    prior = reduce_events([store.read("run")[0]])
    resumed = reduce_events(store.read("run", since_sequence=0), initial=prior)
    assert json.dumps(resumed, sort_keys=True) == json.dumps(whole, sort_keys=True)


@pytest.mark.parametrize("mutate, message", [
    (lambda events: events.__setitem__(1, {**events[1], "sequence": 2}), "non-monotonic"),
    (lambda events: events.__setitem__(1, {**events[1], "run_id": "other"}), "mixed run_id"),
    (lambda events: events.__setitem__(0, {**events[0], "type": "iteration_appended", "payload": {"iteration_id": 0, "outcome": "task_passed"}}), "before contract_opened"),
    (lambda events: events.__setitem__(1, {**events[1], "type": "contract_opened", "payload": {"workspace": "w"}}), "contract_opened must be the first"),
    (lambda events: events.__setitem__(1, {**events[1], "payload": {"iteration_id": 1, "outcome": "task_passed", "state": "verify"}}), "illegal FSM transition"),
    (lambda events: events.__setitem__(4, {**events[4], "payload": {"state": "Succeeded", "criteria_met": {"done": True}, "evidence": [], "false_completion": False}}), "empty evidence"),
    (lambda events: events.__setitem__(4, {**events[4], "payload": {"state": "Succeeded", "criteria_met": {"done": True}, "evidence": ["proof"], "false_completion": True}}), "false_completion"),
    (lambda events: events.__setitem__(4, {**events[4], "payload": {"state": "Succeeded", "criteria_met": {"done": False}, "evidence": ["proof"], "false_completion": False}}), "completion policy"),
    (lambda events: events.__setitem__(4, {**events[4], "payload": {"state": "succeeded", "criteria_met": {"done": True}, "evidence": ["proof"], "false_completion": False}}), "non-canonical state"),
])
def test_reducer_rejects_tampered_streams(mutate, message: str) -> None:
    events = stream()
    mutate(events)
    with pytest.raises(EventReplayError, match=message):
        reduce_events(events)


def test_reducer_rejects_event_after_terminal() -> None:
    events = stream()
    events.append({**events[-1], "event_id": "later", "sequence": 5, "type": "receipt_appended", "payload": {"iteration_id": 2, "role": "read", "model": "m", "outcome": "ok"}})
    with pytest.raises(EventReplayError, match="immutable"):
        reduce_events(events)
