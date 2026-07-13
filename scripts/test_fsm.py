from __future__ import annotations

import pytest

from loop import fsm


def test_all_states_has_exactly_ten_canonical_names_in_order():
    assert fsm.ALL_STATES == (
        "intake",
        "plan",
        "critique-plan",
        "queue-tasks",
        "execute-task",
        "verify",
        "repair",
        "replan",
        "approval-wait",
        "terminal",
    )


def test_non_terminal_states_excludes_terminal_and_has_nine_members():
    assert len(fsm.NON_TERMINAL_STATES) == 9
    assert fsm.TERMINAL_MARKER not in fsm.NON_TERMINAL_STATES


def test_happy_path_sequence_is_all_legal():
    sequence = ("intake", "plan", "critique-plan", "queue-tasks", "execute-task", "verify")
    assert all(fsm.is_legal_transition(old, new) for old, new in zip(sequence, sequence[1:]))


def test_verify_pass_cycles_back_to_execute_task():
    assert fsm.is_legal_transition("verify", "execute-task")


def test_verify_fail_routes_to_repair():
    assert fsm.is_legal_transition("verify", "repair")


def test_repair_fixed_returns_to_verify():
    assert fsm.is_legal_transition("repair", "verify")


def test_repair_cap_exceeded_may_replan():
    assert fsm.is_legal_transition("repair", "replan")


def test_replan_requeues_tasks():
    assert fsm.is_legal_transition("replan", "queue-tasks")


def test_verify_cannot_skip_repair_to_replan():
    assert not fsm.is_legal_transition("verify", "replan")


def test_queue_tasks_cannot_jump_to_verify():
    assert not fsm.is_legal_transition("queue-tasks", "verify")


@pytest.mark.parametrize("state", fsm.NON_TERMINAL_STATES)
def test_every_non_terminal_state_can_terminate(state):
    assert fsm.is_legal_transition(state, fsm.TERMINAL_MARKER)


@pytest.mark.parametrize("target", fsm.NON_TERMINAL_STATES)
def test_terminal_is_absorbing(target):
    assert not fsm.is_legal_transition(fsm.TERMINAL_MARKER, target)
    assert not fsm.legal_targets(fsm.TERMINAL_MARKER)


def test_intake_cannot_reach_approval_wait():
    assert not fsm.is_legal_transition("intake", "approval-wait")


@pytest.mark.parametrize("state", fsm.NON_TERMINAL_STATES[1:])
def test_every_other_active_state_can_reach_approval_wait(state):
    assert fsm.is_legal_transition(state, "approval-wait")


@pytest.mark.parametrize(
    ("target", "expected"),
    (("intake", False),) + tuple((state, True) for state in fsm.NON_TERMINAL_STATES[1:]),
)
def test_approval_wait_resumes_into_any_non_intake_active_state(target, expected):
    assert fsm.is_legal_transition("approval-wait", target) is expected


@pytest.mark.parametrize("state", fsm.ALL_STATES)
def test_self_stay_is_always_legal(state):
    assert fsm.is_legal_transition(state, state)


def test_unknown_state_names_fail_open():
    assert fsm.is_legal_transition("domain-extra", "verify")
    assert fsm.is_legal_transition("verify", "domain-extra")


def test_legal_targets_of_unknown_state_is_empty():
    assert not fsm.legal_targets("domain-extra")
