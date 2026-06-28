"""Loop Contract Core for loop-engineer.

This package is intentionally small and stdlib-first: it validates the portable
repo-OS loop contract that the Claude Code plugin scaffolds and the verifier
scripts consume.
"""

from .paths import LoopPaths, resolve_loop_paths
from .contract import TERMINAL_STATES, doctor_report, validate_contract

__all__ = [
    "LoopPaths",
    "TERMINAL_STATES",
    "doctor_report",
    "resolve_loop_paths",
    "validate_contract",
]
