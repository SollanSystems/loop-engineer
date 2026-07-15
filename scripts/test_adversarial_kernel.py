"""Property-based adversarial checks for the pure event-stream reducer."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("hypothesis")

from hypothesis import HealthCheck, given, settings, strategies as st

from loop import fsm
from loop.completion import criteria_satisfy_completion
from loop.contract import TERMINAL_STATES
from loop.emit import _ITERATION_OUTCOMES
from loop.events import EVENT_SCHEMA_ID
from loop.reducer import EventReplayError, reduce_events


_PROFILE = settings(max_examples=150, derandomize=True, deadline=None,
                    suppress_health_check=[HealthCheck.too_slow])
_FLAGSHIP_PROFILE = settings(max_examples=300, derandomize=True, deadline=None,
                             suppress_health_check=[HealthCheck.too_slow])


def _base_event(**overrides):
    event = {"schema": EVENT_SCHEMA_ID, "run_id": "adv", "actor": "adversarial",
             "causation_id": None, "correlation_id": None}
    event.update(overrides)
    return event


@st.composite
def _legal_walk(draw, *, min_steps=0, max_steps=6):
    events = [_base_event(event_id="e0", sequence=0, type="contract_opened",
                          ts="t0", payload={"workspace": "w"})]
    state = "intake"
    for _ in range(draw(st.integers(min_value=min_steps, max_value=max_steps))):
        targets = [target for target in fsm.legal_targets(state)
                   if target != fsm.TERMINAL_MARKER]
        if not targets:
            break
        target = draw(st.sampled_from(sorted(targets)))
        sequence = len(events)
        events.append(_base_event(
            event_id=f"e{sequence}", sequence=sequence, type="iteration_appended",
            ts=f"t{sequence}", payload={
                "iteration_id": sequence,
                "outcome": draw(st.sampled_from(sorted(_ITERATION_OUTCOMES))),
                "state": target,
            }))
        state = target
    return events, state


_CRITERIA = st.dictionaries(st.sampled_from(("a", "b", "c")),
                            st.one_of(st.booleans(), st.integers(-1, 2),
                                      st.sampled_from(("yes", None))), max_size=3)
_EVIDENCE = st.lists(st.text(max_size=8), max_size=3)
_POLICY = st.one_of(st.none(), st.just("all_required"),
                    st.just({"mode": "all_required"}))


def _terminal_payload(state, criteria_met, evidence, false_completion, policy):
    return {"state": state, "criteria_met": criteria_met, "evidence": evidence,
            "false_completion": false_completion, "completion_policy": policy}


def _expected_g1_ok(state, criteria_met, evidence, false_completion, policy):
    if state != "Succeeded":
        return True
    if false_completion is True:
        return False
    if not criteria_satisfy_completion(criteria_met, policy):
        return False
    return isinstance(evidence, list) and len(evidence) > 0


def _terminal_event(*, event_id, sequence, payload, event_type="terminal_written",
                    causation_id=None):
    return _base_event(event_id=event_id, sequence=sequence, type=event_type,
                       ts=f"t{sequence}", causation_id=causation_id, payload=payload)


def _correction_payload(state="FailedBlocked"):
    return {**_terminal_payload(state, {}, [], False, None),
            "justification": "audit correction",
            "authority": {"by": "ops", "at": "now"}}


@_PROFILE
@given(_legal_walk())
def test_property_legal_random_walks_always_replay_cleanly(walk):
    events, expected_state = walk
    assert reduce_events(events)["state"] == expected_state


@_PROFILE
@given(data=st.data(), walk=_legal_walk(min_steps=1))
def test_property_fsm_illegal_jump_is_always_rejected(data, walk):
    events, _ = walk
    position = data.draw(st.integers(min_value=1, max_value=len(events) - 1))
    state_before = "intake" if position == 1 else events[position - 1]["payload"]["state"]
    illegal = next(candidate for candidate in fsm.ALL_STATES
                   if candidate != state_before
                   and candidate not in fsm.legal_targets(state_before))
    corrupted = [*events]
    corrupted[position] = {**events[position],
                           "payload": {**events[position]["payload"], "state": illegal}}
    with pytest.raises(EventReplayError, match="illegal FSM transition"):
        reduce_events(corrupted)


@_PROFILE
@given(data=st.data(), walk=_legal_walk(min_steps=1))
def test_property_duplicate_delivery_is_always_rejected(data, walk):
    events, _ = walk
    position = data.draw(st.integers(min_value=1, max_value=len(events) - 1))
    with pytest.raises(EventReplayError, match="non-monotonic"):
        reduce_events(events[:position + 1] + [events[position]] + events[position + 1:])


@_PROFILE
@given(data=st.data(), walk=_legal_walk(min_steps=2))
def test_property_reordered_sequence_numbers_is_always_rejected(data, walk):
    events, _ = walk
    position = data.draw(st.integers(min_value=1, max_value=len(events) - 2))
    reordered = [*events]
    reordered[position] = {**events[position], "sequence": events[position + 1]["sequence"]}
    reordered[position + 1] = {**events[position + 1], "sequence": events[position]["sequence"]}
    with pytest.raises(EventReplayError, match="non-monotonic"):
        reduce_events(reordered)


@_FLAGSHIP_PROFILE
@given(state=st.sampled_from(TERMINAL_STATES), criteria_met=_CRITERIA,
       evidence=_EVIDENCE, false_completion=st.booleans(), policy=_POLICY)
def test_property_target_invariant_succeeded_requires_g1(state, criteria_met, evidence,
                                                          false_completion, policy):
    events = [_base_event(event_id="e0", sequence=0, type="contract_opened",
                          ts="t0", payload={"workspace": "w"}),
              _terminal_event(event_id="terminal", sequence=1,
                              payload=_terminal_payload(state, criteria_met, evidence,
                                                        false_completion, policy))]
    if _expected_g1_ok(state, criteria_met, evidence, false_completion, policy):
        assert reduce_events(events)["terminal"]["state"] == state
    else:
        with pytest.raises(EventReplayError):
            reduce_events(events)


@_FLAGSHIP_PROFILE
@given(state=st.sampled_from(TERMINAL_STATES), criteria_met=_CRITERIA,
       evidence=_EVIDENCE, false_completion=st.booleans(), policy=_POLICY)
def test_property_supersession_cannot_launder_succeeded_without_g1(state, criteria_met,
                                                                    evidence, false_completion, policy):
    events = [
        _base_event(event_id="e0", sequence=0, type="contract_opened", ts="t0",
                    payload={"workspace": "w"}),
        _terminal_event(event_id="prior", sequence=1,
                        payload=_terminal_payload("FailedBlocked", {}, [], False, None)),
        _terminal_event(event_id="corrected", sequence=2, event_type="terminal_superseded",
                        causation_id="prior", payload={
                            **_terminal_payload(state, criteria_met, evidence,
                                                false_completion, policy),
                            "justification": "audit correction",
                            "authority": {"by": "ops", "at": "now"},
                        }),
    ]
    if _expected_g1_ok(state, criteria_met, evidence, false_completion, policy):
        assert reduce_events(events)["terminal"]["state"] == state
    else:
        with pytest.raises(EventReplayError):
            reduce_events(events)


@_PROFILE
@given(depth=st.integers(min_value=0, max_value=4),
       correctness=st.lists(st.booleans(), min_size=4, max_size=4))
def test_property_causation_chain_admission_is_exact_match_at_any_depth(depth, correctness):
    events = [_base_event(event_id="e0", sequence=0, type="contract_opened", ts="t0",
                          payload={"workspace": "w"}),
              _terminal_event(event_id="terminal", sequence=1,
                              payload=_terminal_payload("FailedBlocked", {}, [], False, None))]
    current_id = "terminal"
    for index in range(depth):
        causation_id = current_id if correctness[index] else f"forged-{index}"
        event_id = f"correction-{index}"
        events.append(_terminal_event(event_id=event_id, sequence=index + 2,
                                      event_type="terminal_superseded", causation_id=causation_id,
                                      payload=_correction_payload()))
        if correctness[index]:
            current_id = event_id
    if all(correctness[:depth]):
        assert reduce_events(events)["terminal"]["event_id"] == current_id
    else:
        with pytest.raises(EventReplayError, match="causation_id"):
            reduce_events(events)


@_PROFILE
@given(depth=st.integers(min_value=0, max_value=5))
def test_property_superseded_history_preserves_order_at_any_chain_depth(depth):
    events = [_base_event(event_id="e0", sequence=0, type="contract_opened", ts="t0",
                          payload={"workspace": "w"}),
              _terminal_event(event_id="terminal", sequence=1,
                              payload=_terminal_payload("FailedBlocked", {}, [], False, None))]
    current_id = "terminal"
    for index in range(depth):
        event_id = f"correction-{index}"
        events.append(_terminal_event(event_id=event_id, sequence=index + 2,
                                      event_type="terminal_superseded", causation_id=current_id,
                                      payload=_correction_payload()))
        current_id = event_id
    history = reduce_events(events)["superseded_history"]
    expected_ids = (["terminal", *[f"correction-{index}" for index in range(depth - 1)]] if depth else [])
    assert [entry["event_id"] for entry in history] == expected_ids
    assert [entry["superseded_by"] for entry in history] == [f"correction-{index}" for index in range(depth)]


@_PROFILE
@given(data=st.data(), walk=_legal_walk(), depth=st.integers(min_value=0, max_value=4))
def test_property_replay_is_deterministic_at_any_split_point(data, walk, depth):
    events, _ = walk
    terminal_id = f"e{len(events)}"
    stream = [*events, _terminal_event(event_id=terminal_id, sequence=len(events),
                                       payload=_terminal_payload("FailedBlocked", {}, [], False, None))]
    for index in range(depth):
        event_id = f"correction-{index}"
        stream.append(_terminal_event(event_id=event_id, sequence=len(stream),
                                      event_type="terminal_superseded", causation_id=terminal_id,
                                      payload=_correction_payload()))
        terminal_id = event_id
    split = data.draw(st.integers(min_value=0, max_value=len(stream)))
    whole = reduce_events(stream)
    assert json.dumps(whole, sort_keys=True) == json.dumps(reduce_events(stream), sort_keys=True)
    assert json.dumps(whole, sort_keys=True) == json.dumps(
        reduce_events(stream[split:], initial=reduce_events(stream[:split])), sort_keys=True)


def test_duplicate_event_id_elsewhere_in_history_does_not_confuse_causation():
    base = [_base_event(event_id="e0", sequence=0, type="contract_opened", ts="t0",
                        payload={"workspace": "w"})]
    historical = _base_event(event_id="historical", sequence=1, type="iteration_appended",
                             ts="t1", payload={"iteration_id": 1,
                                                "outcome": "task_passed", "state": "plan"})
    terminal = _terminal_event(event_id="terminal", sequence=2,
                               payload=_terminal_payload("FailedBlocked", {}, [], False, None))
    wrong = _terminal_event(event_id="bad", sequence=3, event_type="terminal_superseded",
                            causation_id="historical", payload=_correction_payload())
    with pytest.raises(EventReplayError, match="causation_id"):
        reduce_events(base + [historical, terminal, wrong])

    duplicate_label = _base_event(event_id="terminal", sequence=1,
                                  type="iteration_appended", ts="t1",
                                  payload={"iteration_id": 1, "outcome": "task_passed",
                                           "state": "plan"})
    admitted = _terminal_event(event_id="terminal", sequence=2,
                               payload=_terminal_payload("FailedBlocked", {}, [], False, None))
    correction = _terminal_event(event_id="good", sequence=3,
                                 event_type="terminal_superseded", causation_id="terminal",
                                 payload=_correction_payload())
    assert reduce_events(base + [duplicate_label, admitted, correction])["terminal"]["event_id"] == "good"
