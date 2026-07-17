"""`loop architect` is a permanent, typed fail-loud deferral.

Architecture classification and ADR authorship (choosing the loop's shape, its
Claude-Code realization, its risk profile, its terminal-state plan) is agentic
judgment the loop-architect Claude-Code skill performs. A deterministic CLI
cannot reproduce that judgment, and a placeholder ADR scaffold would risk being
mistaken for a real decision by whatever consumes it next (loop-contract's own
scaffold step). So this verb never writes, never reads, never branches:
architect_run always raises, for any input, which is the only way this verb
can be truthful about what it does not do.
"""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn

ARCHITECT_NOT_IMPLEMENTED_MESSAGE = (
    "loop architect is not implemented by this deterministic CLI: architecture "
    "classification and ADR authorship require agentic judgment; run the "
    "loop-architect Claude-Code skill (or equivalent LLM-driven analysis) to "
    "produce an architecture decision record, then use `loop scaffold` to "
    "operationalize the chosen contract"
)


class ArchitectNotImplementedError(RuntimeError):
    """`loop architect` cannot be performed by deterministic code."""


def architect_run(target: str | Path | None = None, *, mode: str | None = None) -> NoReturn:
    """Always raise ArchitectNotImplementedError, for any input.

    Accepts the same (target, mode) shape as every other verb's <verb>_run
    entry point for API symmetry with simulate_run/status_report/dispatch_once,
    but never inspects either argument: there is no deterministic path to a
    real architecture decision record.
    """
    raise ArchitectNotImplementedError(ARCHITECT_NOT_IMPLEMENTED_MESSAGE)
