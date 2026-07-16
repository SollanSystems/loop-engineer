from __future__ import annotations

import json

import pytest

from loop.events import EVENT_SCHEMA_ID, SQLiteEventStore, validate_event
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


def superseded_event(*, event_id: str = "e5", sequence: int = 5, causation_id: str | None = "e4",
                     payload: dict[str, object] | None = None) -> dict[str, object]:
    terminal = stream()[-1]
    return {**terminal, "event_id": event_id, "sequence": sequence, "type": "terminal_superseded",
            "ts": f"2026-01-01T00:00:{sequence:02d}+00:00", "causation_id": causation_id,
            "payload": payload if payload is not None else {
                "state": "FailedSafety", "criteria_met": {"done": True}, "evidence": ["proof"],
                "false_completion": False, "justification": "audit correction",
                "authority": {"by": "ops", "at": "2026-01-01T00:00:05+00:00"},
            }}


def test_reducer_admits_terminal_superseded_after_terminal() -> None:
    result = reduce_events(stream() + [superseded_event()])
    assert result["terminal"]["event_id"] == "e5"
    assert [entry["event_id"] for entry in result["superseded_history"]] == ["e4"]


@pytest.mark.parametrize("event_type, payload", [
    ("contract_opened", {"workspace": "w"}),
    ("iteration_appended", {"iteration_id": 3, "outcome": "task_passed"}),
    ("receipt_appended", {"iteration_id": 2, "role": "read", "model": "m", "outcome": "ok"}),
    ("terminal_written", {"state": "FailedSafety", "criteria_met": {}, "evidence": [], "false_completion": False}),
])
def test_reducer_rejects_every_other_event_type_after_terminal(event_type: str, payload: dict[str, object]) -> None:
    terminal = stream()[-1]
    events = stream() + [{**terminal, "event_id": "later", "sequence": 5, "type": event_type, "payload": payload}]
    with pytest.raises(EventReplayError, match="event appended after terminal — terminal is immutable"):
        reduce_events(events)


def test_reducer_rejects_terminal_superseded_before_any_terminal() -> None:
    event = superseded_event(event_id="e0", sequence=0, causation_id=None)
    with pytest.raises(EventReplayError, match="nothing to supersede"):
        reduce_events([event])


@pytest.mark.parametrize("causation_id", ["wrong", None])
def test_reducer_rejects_terminal_superseded_with_mismatched_causation_id(causation_id: str | None) -> None:
    with pytest.raises(EventReplayError, match="causation_id"):
        reduce_events(stream() + [superseded_event(causation_id=causation_id)])


def test_reducer_rejects_terminal_superseded_citing_a_stale_superseded_record() -> None:
    events = stream() + [superseded_event(), superseded_event(event_id="e6", sequence=6, causation_id="e4")]
    with pytest.raises(EventReplayError, match="causation_id"):
        reduce_events(events)


def test_reducer_chains_multiple_terminal_supersessions_preserving_history_order() -> None:
    result = reduce_events(stream() + [superseded_event(), superseded_event(event_id="e6", sequence=6, causation_id="e5")])
    assert [entry["event_id"] for entry in result["superseded_history"]] == ["e4", "e5"]
    assert [entry["superseded_by"] for entry in result["superseded_history"]] == ["e5", "e6"]
    assert result["terminal"]["event_id"] == "e6"


@pytest.mark.parametrize("payload, message", [
    ({"state": "succeeded", "criteria_met": {"done": True}, "evidence": ["proof"], "false_completion": False, "justification": "j", "authority": {"by": "a", "at": "t"}}, "non-canonical state"),
    ({"state": "Succeeded", "criteria_met": {"done": True}, "evidence": ["proof"], "false_completion": True, "justification": "j", "authority": {"by": "a", "at": "t"}}, "false_completion"),
    ({"state": "Succeeded", "criteria_met": {"done": False}, "evidence": ["proof"], "false_completion": False, "justification": "j", "authority": {"by": "a", "at": "t"}}, "completion policy"),
    ({"state": "Succeeded", "criteria_met": {"done": True}, "evidence": [], "false_completion": False, "justification": "j", "authority": {"by": "a", "at": "t"}}, "empty evidence"),
])
def test_reducer_terminal_superseded_enforces_g1_when_correcting_to_succeeded(payload: dict[str, object], message: str) -> None:
    with pytest.raises(EventReplayError, match=message):
        reduce_events(stream() + [superseded_event(payload=payload)])


def test_reducer_terminal_superseded_allows_correcting_succeeded_to_a_failed_state() -> None:
    events = stream() + [superseded_event(), superseded_event(event_id="e6", sequence=6, causation_id="e5", payload={
        "state": "FailedBlocked", "criteria_met": {}, "evidence": [], "false_completion": False,
        "justification": "blocker confirmed", "authority": {"by": "ops", "at": "t"},
    })]
    assert reduce_events(events)["terminal"]["state"] == "FailedBlocked"


@pytest.mark.parametrize("payload, message", [
    ({"state": "FailedSafety", "criteria_met": {}, "evidence": [], "false_completion": False, "authority": {"by": "a", "at": "t"}}, "justification"),
    ({"state": "FailedSafety", "criteria_met": {}, "evidence": [], "false_completion": False, "justification": " " , "authority": {"by": "a", "at": "t"}}, "justification"),
    ({"state": "FailedSafety", "criteria_met": {}, "evidence": [], "false_completion": False, "justification": "j"}, "authority"),
    ({"state": "FailedSafety", "criteria_met": {}, "evidence": [], "false_completion": False, "justification": "j", "authority": {"by": "", "at": "t"}}, "authority"),
])
def test_reducer_rejects_terminal_superseded_missing_justification_or_authority(payload: dict[str, object], message: str) -> None:
    with pytest.raises(EventReplayError, match=message):
        reduce_events(stream() + [superseded_event(payload=payload)])


def test_reducer_terminal_superseded_is_deterministic_and_resumable() -> None:
    events = stream() + [superseded_event(), superseded_event(event_id="e6", sequence=6, causation_id="e5")]
    whole = reduce_events(events)
    assert json.dumps(whole, sort_keys=True) == json.dumps(reduce_events(events), sort_keys=True)
    assert reduce_events(events[3:], initial=reduce_events(events[:3])) == whole


def run_control_event(event_type: str, sequence: int, *, event_id: str | None = None,
                      causation_id: str | None = None, payload: dict[str, object] | None = None) -> dict[str, object]:
    payloads = {
        "approval_requested": {"iteration_id": 2, "request": "Approve the plan"},
        "approval_resolved": {"iteration_id": 2, "decision": "approved", "resume_target": "execute-task"},
        "run_paused": {"iteration_id": 2, "reason": "operator break"},
        "run_resumed": {"iteration_id": 2, "note": "operator returned"},
    }
    base = stream()[0]
    return {**base, "event_id": event_id or f"rc-{sequence}", "sequence": sequence,
            "type": event_type, "causation_id": causation_id,
            "ts": f"2026-01-01T00:01:{sequence:02d}+00:00",
            "payload": payload if payload is not None else payloads[event_type]}


def approval_ready_stream() -> list[dict[str, object]]:
    return stream()[:2]


def test_reducer_projects_approval_requested_into_approval_wait_with_pending_request() -> None:
    result = reduce_events(approval_ready_stream() + [run_control_event("approval_requested", 2, event_id="request-1")])
    assert result["state"] == "approval-wait"
    assert result["pending_approval"] == {"event_id": "request-1", "request": "Approve the plan"}


def test_reducer_rejects_approval_requested_from_intake() -> None:
    with pytest.raises(EventReplayError, match="illegal FSM transition"):
        reduce_events(stream()[:1] + [run_control_event("approval_requested", 1)])


def test_reducer_projects_approval_resolved_approved_to_resume_target() -> None:
    events = approval_ready_stream() + [run_control_event("approval_requested", 2, event_id="request-1"),
                                         run_control_event("approval_resolved", 3, causation_id="request-1")]
    result = reduce_events(events)
    assert result["state"] == "execute-task" and result["pending_approval"] is None


def test_reducer_projects_approval_resolved_denied_clears_pending_without_changing_state() -> None:
    events = approval_ready_stream() + [run_control_event("approval_requested", 2, event_id="request-1"),
                                         run_control_event("approval_resolved", 3, causation_id="request-1", payload={"iteration_id": 2, "decision": "denied"})]
    result = reduce_events(events)
    assert result["state"] == "approval-wait" and result["pending_approval"] is None


def test_reducer_rejects_approval_resolved_outside_approval_wait() -> None:
    with pytest.raises(EventReplayError, match="only legal from approval-wait"):
        reduce_events(approval_ready_stream() + [run_control_event("approval_resolved", 2)])


@pytest.mark.parametrize("causation_id", ["wrong", None])
def test_reducer_rejects_approval_resolved_with_mismatched_causation_id(causation_id: str | None) -> None:
    events = approval_ready_stream() + [run_control_event("approval_requested", 2, event_id="request-1"),
                                         run_control_event("approval_resolved", 3, causation_id=causation_id)]
    with pytest.raises(EventReplayError, match="causation_id"):
        reduce_events(events)


@pytest.mark.parametrize("target", ["intake", "terminal"])
def test_reducer_rejects_approval_resolved_with_non_resumable_target(target: str) -> None:
    events = approval_ready_stream() + [run_control_event("approval_requested", 2, event_id="request-1"),
                                         run_control_event("approval_resolved", 3, causation_id="request-1", payload={"iteration_id": 2, "decision": "approved", "resume_target": target})]
    with pytest.raises(EventReplayError, match="legal non-terminal resume target"):
        reduce_events(events)


@pytest.mark.parametrize("target", ["banana-not-a-real-state", ""])
def test_reducer_rejects_approval_resolved_with_unknown_resume_target(target: str) -> None:
    prefix = approval_ready_stream() + [run_control_event("approval_requested", 2, event_id="request-1")]
    event = run_control_event(
        "approval_resolved", 3, causation_id="request-1",
        payload={"iteration_id": 2, "decision": "approved", "resume_target": target},
    )
    with pytest.raises(EventReplayError) as error:
        reduce_events(prefix + [event])
    assert str(error.value) == (
        f"approval_resolved.resume_target {target!r} is not a legal non-terminal resume target from approval-wait"
    )
    assert reduce_events(prefix)["state"] == "approval-wait"


def test_validation_rejects_explicit_null_resume_target_when_approved() -> None:
    report = validate_event(run_control_event(
        "approval_resolved", 2,
        payload={"iteration_id": 2, "decision": "approved", "resume_target": None},
    ))
    assert report["ok"] is False
    assert any("resume_target" in issue["message"] for issue in report["issues"])


def test_reducer_rejects_approval_resolved_after_legacy_iteration_appended_entered_approval_wait() -> None:
    legacy = {**approval_ready_stream()[-1], "event_id": "legacy", "sequence": 2,
              "type": "iteration_appended", "payload": {"iteration_id": 2, "outcome": "approval_requested", "state": "approval-wait"}}
    with pytest.raises(EventReplayError, match="no pending approval_requested"):
        reduce_events(approval_ready_stream() + [legacy, run_control_event("approval_resolved", 3, causation_id="legacy")])


@pytest.mark.parametrize("event_type, payload", [
    ("approval_requested", {"iteration_id": 2}),
    ("approval_resolved", {"iteration_id": 2, "decision": "approved"}),
    ("run_paused", {"iteration_id": 2}),
    ("run_resumed", {"iteration_id": 2, "note": None}),
])
def test_reducer_rejects_run_control_events_with_malformed_payloads(event_type: str, payload: dict[str, object]) -> None:
    with pytest.raises(EventReplayError, match="malformed event"):
        reduce_events(approval_ready_stream() + [run_control_event(event_type, 2, payload=payload)])


def test_reducer_projects_run_paused_and_run_resumed_round_trip_preserving_state() -> None:
    events = approval_ready_stream() + [run_control_event("run_paused", 2), run_control_event("run_resumed", 3)]
    result = reduce_events(events)
    assert result["state"] == "plan" and result["paused"] is False and result["pause_reason"] is None


def test_reducer_rejects_double_pause() -> None:
    with pytest.raises(EventReplayError, match="already paused"):
        reduce_events(approval_ready_stream() + [run_control_event("run_paused", 2), run_control_event("run_paused", 3)])


def test_reducer_rejects_resume_without_pause() -> None:
    with pytest.raises(EventReplayError, match="not paused"):
        reduce_events(approval_ready_stream() + [run_control_event("run_resumed", 2)])


@pytest.mark.parametrize("event_type, payload", [
    ("approval_requested", {"iteration_id": 2, "request": "approve"}),
    ("approval_resolved", {"iteration_id": 2, "decision": "denied"}),
    ("run_paused", {"iteration_id": 2, "reason": "stop"}),
    ("run_resumed", {"iteration_id": 2}),
])
def test_reducer_rejects_run_control_events_after_terminal(event_type: str, payload: dict[str, object]) -> None:
    terminal = stream()[-1]
    with pytest.raises(EventReplayError, match="event appended after terminal — terminal is immutable"):
        reduce_events(stream() + [run_control_event(event_type, 5, payload=payload)])


def test_reducer_is_deterministic_and_resumable_across_run_control_events() -> None:
    events = approval_ready_stream() + [run_control_event("approval_requested", 2, event_id="request-1"),
                                         run_control_event("run_paused", 3), run_control_event("run_resumed", 4),
                                         run_control_event("approval_resolved", 5, causation_id="request-1")]
    whole = reduce_events(events)
    assert json.dumps(whole, sort_keys=True) == json.dumps(reduce_events(events), sort_keys=True)
    assert reduce_events(events[3:], initial=reduce_events(events[:3])) == whole
