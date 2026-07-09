"""Engine-outcome -> typed-terminal projection (ST3).

A pure projection, never a runtime: recipes adapt their engine's native result
into an ``EngineOutcome``, pass the holdout-gate and anticheat results through
as plain dicts (``scripts/holdout_gate.py decide(...)`` / ``scripts/
anticheat_scan.py scan(...)`` JSON), and this module assembles the
``terminal@1`` body. Every disk write stays in ``loop.emit``.

The fixed precedence — safety -> human -> blocked -> budget -> spec-gap ->
gate verdict — means a gamed (FailedSafety) or human-killed (AbortedByHuman)
run can never launder itself into Succeeded. ``Succeeded`` is reachable ONLY
via a green gate verdict + anticheat clean of HIGH/CRITICAL findings + at
least one met criterion + non-empty evidence. ``false_completion`` is
copied out of the gate result, never synthesized. A missing or
structurally-empty gate/anticheat input fails closed to
``FailedUnverifiable`` — the same posture as ``holdout_gate`` on an empty
holdout set.

Pure stdlib; imports no engine package and nothing from ``scripts/`` — so
installing this helper never pulls LangGraph/Temporal/etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

TERMINAL_SCHEMA = "loop-engineer/terminal@1"


@dataclass(frozen=True)
class EngineOutcome:
    """Engine-agnostic description of how a host run ended."""

    reached_end: bool
    external_error: str | None = None
    budget_exhausted: bool = False
    human_abort: bool = False
    artifacts: Sequence[str] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifacts", tuple(str(a) for a in self.artifacts))


def _valid_checks(checks: object) -> bool:
    return (
        isinstance(checks, list)
        and bool(checks)
        and all(isinstance(c, dict) and "id" in c and isinstance(c.get("passed"), bool) for c in checks)
    )


def _valid_gate(gate: dict) -> bool:
    """Structurally a ``holdout_gate.decide`` result: verdict + flag + the
    per-check ``visible``/``holdout`` evidence arrays. A hand-typed stub with
    no check evidence is not a gate run."""
    return (
        isinstance(gate.get("verdict"), str)
        and isinstance(gate.get("false_completion"), bool)
        and _valid_checks(gate.get("visible"))
        and _valid_checks(gate.get("holdout"))
    )


def _valid_anticheat(anticheat: dict) -> bool:
    return isinstance(anticheat.get("findings"), list) and "downgrade_to" in anticheat


def to_terminal_state(
    outcome: EngineOutcome,
    gate_verdict: dict | None,
    anticheat: dict | None,
    criteria_met: dict[str, bool | None],
) -> dict:
    """Project an engine terminal + gate/anticheat evidence into a terminal@1 body.

    ``criteria_met`` maps each SPEC criterion id to the pass/fail of its mapped
    check; ``None`` means the criterion has no mapped check at all ->
    ``FailedSpecGap``. In the returned body ``None`` coerces to ``False``
    (unproven is not met).
    """
    gate = gate_verdict if isinstance(gate_verdict, dict) else {}
    ac = anticheat if isinstance(anticheat, dict) else {}
    false_completion = gate.get("false_completion") is True

    def body(state: str, reason: str) -> dict:
        return {
            "schema": TERMINAL_SCHEMA,
            "state": state,
            "criteria_met": {str(k): v is True for k, v in criteria_met.items()},
            "evidence": list(outcome.artifacts),
            "false_completion": false_completion,
            "reason": reason,
        }

    if _valid_anticheat(ac) and ac.get("downgrade_to") == "FailedSafety":
        return body("FailedSafety", "anticheat: critical gate-tampering finding")
    if outcome.human_abort:
        return body("AbortedByHuman", "operator interrupt / human abort signal")
    if outcome.external_error:
        return body("FailedBlocked", f"unrecoverable external block: {outcome.external_error}")
    if outcome.budget_exhausted:
        return body("FailedBudget", "engine budget cap hit (steps/tokens/wall-clock/cost)")
    unmapped = sorted(str(k) for k, v in criteria_met.items() if v is None)
    if unmapped:
        return body("FailedSpecGap", "criteria with no mapped check: " + ", ".join(unmapped))
    if not _valid_anticheat(ac):
        return body("FailedUnverifiable", "no anticheat result — cannot certify (fail closed)")
    if not _valid_gate(gate):
        return body("FailedUnverifiable", "no holdout gate result — cannot certify (fail closed)")
    if ac.get("downgrade_to") == "FailedUnverifiable":
        return body("FailedUnverifiable", "anticheat: high-severity finding")
    if gate["verdict"] != "Succeeded":
        if false_completion:
            return body("FailedUnverifiable", "visible passed but holdout failed — false completion")
        return body("FailedUnverifiable", f"gate verdict {gate['verdict']!r} — cannot certify Succeeded")
    if false_completion:
        return body("FailedUnverifiable", "gate flags false_completion — refusing Succeeded")
    if not any(v is True for v in criteria_met.values()):
        return body("FailedUnverifiable", "green gate but no met criterion — cannot certify")
    if not outcome.artifacts:
        return body("FailedUnverifiable", "green gate but no evidence artifacts — cannot certify")
    if not outcome.reached_end:
        return body("FailedUnverifiable", "engine did not reach its own terminal signal")
    return body("Succeeded", "holdout gate green, anticheat clean, criteria met with evidence")
