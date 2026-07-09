"""ST3 adapter contract: the projection from an engine outcome + gate/anticheat
evidence to one of the 7 typed terminal states. Pins the fixed precedence
(safety -> human -> blocked -> budget -> spec-gap -> gate verdict), the
false-completion invariant, and the structural unreachability of Succeeded
without a green gate + clean anticheat + a met criterion + evidence."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from loop import emit  # noqa: E402
from loop.integrations import EngineOutcome, to_terminal_state  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _gate(visible_pass: bool, holdout_pass: bool) -> dict:
    """A REAL holdout_gate.decide(...) verdict — never a hand-typed stub."""
    holdout_gate = _load("holdout_gate")
    return holdout_gate.decide(
        visible=[{"id": "v1", "passed": visible_pass}],
        holdout=[{"id": "h1", "passed": holdout_pass}],
    )


_CLEAN_AC = {"findings": [], "clean": True, "downgrade_to": None}
_HIGH_AC = {
    "findings": [{"signature": "hidden-answer-read", "severity": "high", "evidence": "x"}],
    "clean": False,
    "downgrade_to": "FailedUnverifiable",
}
_CRITICAL_AC = {
    "findings": [{"signature": "gate-tampering", "severity": "critical", "evidence": "x"}],
    "clean": False,
    "downgrade_to": "FailedSafety",
}
_ENDED = dict(reached_end=True, artifacts=["a.txt"])


def test_succeeded_via_green_gate_clean_anticheat_met_criterion():
    body = to_terminal_state(EngineOutcome(**_ENDED), _gate(True, True), _CLEAN_AC, {"1": True})
    assert body["state"] == "Succeeded"
    assert body["false_completion"] is False
    assert body["schema"] == "loop-engineer/terminal@1"
    assert body["evidence"] == ["a.txt"]


def test_false_completion_invariant_visible_green_holdout_red():
    gate = _gate(True, False)
    assert gate["false_completion"] is True  # the real decide() flag
    body = to_terminal_state(EngineOutcome(**_ENDED), gate, _CLEAN_AC, {"1": True})
    assert body["state"] == "FailedUnverifiable"
    assert body["state"] != "Succeeded"
    assert body["false_completion"] is True  # copied from the gate, not synthesized


def test_anticheat_critical_beats_green_gate():
    body = to_terminal_state(EngineOutcome(**_ENDED), _gate(True, True), _CRITICAL_AC, {"1": True})
    assert body["state"] == "FailedSafety"


def test_human_abort_beats_green_gate():
    body = to_terminal_state(
        EngineOutcome(reached_end=True, human_abort=True, artifacts=["a"]),
        _gate(True, True), _CLEAN_AC, {"1": True},
    )
    assert body["state"] == "AbortedByHuman"


def test_external_error_maps_to_failed_blocked():
    body = to_terminal_state(
        EngineOutcome(reached_end=False, external_error="credential missing"),
        {}, {}, {"1": False},
    )
    assert body["state"] == "FailedBlocked"
    assert "credential missing" in body["reason"]


def test_budget_exhausted_maps_to_failed_budget():
    body = to_terminal_state(
        EngineOutcome(reached_end=False, budget_exhausted=True), {}, {}, {"1": False},
    )
    assert body["state"] == "FailedBudget"


def test_unmapped_criterion_maps_to_failed_spec_gap():
    body = to_terminal_state(EngineOutcome(**_ENDED), _gate(True, True), _CLEAN_AC, {"1": True, "2": None})
    assert body["state"] == "FailedSpecGap"
    assert body["criteria_met"] == {"1": True, "2": False}  # None coerces to False


def test_all_seven_states_reachable():
    reached = {
        to_terminal_state(EngineOutcome(**_ENDED), _gate(True, True), _CLEAN_AC, {"1": True})["state"],
        to_terminal_state(EngineOutcome(**_ENDED), _gate(True, False), _CLEAN_AC, {"1": True})["state"],
        to_terminal_state(EngineOutcome(reached_end=False, external_error="x"), {}, {}, {"1": False})["state"],
        to_terminal_state(EngineOutcome(reached_end=False, budget_exhausted=True), {}, {}, {"1": False})["state"],
        to_terminal_state(EngineOutcome(**_ENDED), _gate(True, True), _CRITICAL_AC, {"1": True})["state"],
        to_terminal_state(EngineOutcome(**_ENDED), _gate(True, True), _CLEAN_AC, {"1": None})["state"],
        to_terminal_state(EngineOutcome(reached_end=False, human_abort=True), {}, {}, {"1": False})["state"],
    }
    assert reached == {
        "Succeeded", "FailedUnverifiable", "FailedBlocked", "FailedBudget",
        "FailedSafety", "FailedSpecGap", "AbortedByHuman",
    }


def test_missing_gate_or_anticheat_fails_closed():
    assert to_terminal_state(EngineOutcome(**_ENDED), None, _CLEAN_AC, {"1": True})["state"] == "FailedUnverifiable"
    assert to_terminal_state(EngineOutcome(**_ENDED), {}, _CLEAN_AC, {"1": True})["state"] == "FailedUnverifiable"
    assert to_terminal_state(EngineOutcome(**_ENDED), _gate(True, True), None, {"1": True})["state"] == "FailedUnverifiable"
    assert to_terminal_state(EngineOutcome(**_ENDED), _gate(True, True), {}, {"1": True})["state"] == "FailedUnverifiable"


def test_succeeded_unreachable_without_met_criterion_or_evidence():
    no_criterion = to_terminal_state(EngineOutcome(**_ENDED), _gate(True, True), _CLEAN_AC, {"1": False})
    assert no_criterion["state"] == "FailedUnverifiable"
    no_evidence = to_terminal_state(
        EngineOutcome(reached_end=True, artifacts=[]), _gate(True, True), _CLEAN_AC, {"1": True},
    )
    assert no_evidence["state"] == "FailedUnverifiable"
    not_ended = to_terminal_state(
        EngineOutcome(reached_end=False, artifacts=["a"]), _gate(True, True), _CLEAN_AC, {"1": True},
    )
    assert not_ended["state"] == "FailedUnverifiable"


def test_anticheat_high_downgrades_a_green_gate():
    body = to_terminal_state(EngineOutcome(**_ENDED), _gate(True, True), _HIGH_AC, {"1": True})
    assert body["state"] == "FailedUnverifiable"


def test_not_ready_gate_cannot_certify():
    holdout_gate = _load("holdout_gate")
    gate = holdout_gate.decide(visible=[], holdout=[])  # NotReady
    body = to_terminal_state(EngineOutcome(**_ENDED), gate, _CLEAN_AC, {"1": True})
    assert body["state"] == "FailedUnverifiable"


def test_body_feeds_emit_terminate_round_trip(tmp_path):
    ws = tmp_path / "run"
    emit.open_contract(ws)
    body = to_terminal_state(EngineOutcome(**_ENDED), _gate(True, True), _CLEAN_AC, {"1": True})
    path = emit.terminate(
        ws, state=body["state"], criteria_met=body["criteria_met"], evidence=body["evidence"],
        false_completion=body["false_completion"], reason=body["reason"], iteration_id=1,
    )
    assert path.is_file()


def test_module_imports_no_engine_and_no_scripts():
    source = (_REPO / "loop" / "integrations.py").read_text(encoding="utf-8")
    imports = [l for l in source.splitlines() if re.match(r"\s*(import|from)\s", l)]
    for line in imports:
        assert "langgraph" not in line and "temporalio" not in line and "scripts" not in line, line
    # pure stdlib: the only allowed import roots
    for line in imports:
        assert re.match(r"\s*(from\s+(__future__|dataclasses|typing)\s+import|import\s+(dataclasses|typing))", line), line
