"""Dependency-free line-coverage gate for pricing.py (criterion 1).

Runs the full regression suite (visible + held-out) under ``sys.settrace``,
records which executable lines of ``pricing.py`` execute, and asserts line
coverage ``>= THRESHOLD``. Pure stdlib — no coverage.py, no pytest — so it runs
under a bare ``python3`` with zero installs.

Executable lines are taken from the module's own bytecode line table
(``code.co_lines()``, recursively through nested function/class code objects):
the honest denominator, not a hand-maintained count. Exit 0 iff the gate holds.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

THRESHOLD = 0.80
HERE = Path(__file__).resolve().parent
MODULE = "pricing"
SOURCE = HERE / "pricing.py"


def executable_lines(source_path: Path) -> set[int]:
    """Every source line carrying bytecode — module level + every nested code."""
    code = compile(source_path.read_text(encoding="utf-8"), str(source_path), "exec")
    lines: set[int] = set()
    stack = [code]
    code_type = type(code)
    while stack:
        current = stack.pop()
        for _, _, lineno in current.co_lines():
            if lineno is not None:
                lines.add(lineno)
        for const in current.co_consts:
            if isinstance(const, code_type):
                stack.append(const)
    return lines


def _run_suite() -> None:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for name in ("test_visible", "test_holdout"):
        suite.addTests(loader.loadTestsFromName(name))
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=0).run(suite)
    if not result.wasSuccessful():
        raise SystemExit("coverage gate: underlying test suite failed")


def measure() -> tuple[set[int], set[int]]:
    executed: set[int] = set()

    def _tracer(frame, event, arg):
        if event == "line" and frame.f_globals.get("__name__") == MODULE:
            executed.add(frame.f_lineno)
        return _tracer

    sys.modules.pop(MODULE, None)
    sys.settrace(_tracer)
    try:
        __import__(MODULE)   # capture module-level lines under the tracer
        _run_suite()
    finally:
        sys.settrace(None)
    return executable_lines(SOURCE), executed


def main() -> int:
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    executable, executed = measure()
    covered = executable & executed
    ratio = len(covered) / len(executable) if executable else 0.0
    ok = ratio >= THRESHOLD
    print(
        f"line_coverage {ratio:.2f} "
        f"(covered {len(covered)}/{len(executable)} executable lines of pricing.py) "
        f"— {'PASS' if ok else 'FAIL'} (gate >= {THRESHOLD:.2f})"
    )
    if not ok:
        missing = sorted(executable - executed)
        print(f"uncovered pricing.py lines: {missing}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
