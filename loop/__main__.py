from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .contract import VALIDATION_MODES, ValidationModeError, doctor_report
from .plan import validate_plan

_PROG = "python3 -m loop"

_COMMANDS = ("scaffold", "doctor", "validate", "verify", "inspect", "metrics", "plan-lint")

# Read commands operate on an EXISTING contract dir; scaffold CREATES one, so it
# is exempt from the "target must exist" guard.
_READ_COMMANDS = ("doctor", "validate", "verify", "inspect", "metrics", "plan-lint")

_USAGE = f"usage: {_PROG} <scaffold|doctor|validate|verify|inspect|metrics|plan-lint> <target>"

_HELP = f"""{_PROG} — validate, inspect, and measure a portable repo-OS loop contract.

{_USAGE}
       {_PROG} metrics [--baseline] <workspace-or-.loop>
       {_PROG} doctor|validate|verify [--mode basic|strict|release] <workspace-or-.loop>
       {_PROG} plan-lint [--mode basic|strict|release] <plan-file>

commands:
  scaffold   Write a fresh, doctor-clean loop contract into <target>.
  doctor     Validate the contract objects; --mode selects validation strength.
  validate   Alias for doctor.
  verify     Alias for doctor — check the contract's state.
  inspect    Score an existing loop against the prime-directive checklist
             (emits a weak/strong verdict and a gap report).
  metrics    Derive false-completion-rate + repair-productivity from the loop's
             real .loop/ evidence (RUNLOG, verify bundles, held-out gate, repair
             records) and emit a JSON scorecard. With --baseline, write a
             checked-in baseline scorecard — refused unless the run is gate-backed.
  plan-lint  Validate a loop-engineer/plan@1 Loop Plan IR document: task-kind
             fields, dependency-graph acyclicity, and the terminal-state
             mapping. --mode selects validation strength, same as doctor.

arguments:
  <target>     A workspace root or its .loop/ directory (all commands except plan-lint).
  <plan-file>  A single loop-engineer/plan@1 JSON file (plan-lint only).

options:
  --mode {{basic,strict,release}}
                (doctor/validate/verify/plan-lint only) basic forces structural
                checks; strict/release require jsonschema. Default: auto-detect.
  --baseline    (metrics only) write docs/metrics-baseline.json over a gate-backed
                run; exits non-zero and writes nothing otherwise.
  -h, --help    Show this help and exit.
  --version     Show the version and exit.
"""


def _version() -> str:
    """Return the package version. Single source of truth is pyproject.toml.

    Prefer installed metadata (which is itself generated from pyproject); fall
    back to reading pyproject.toml at the repo root so `--version` still works
    from an uninstalled/editable checkout.
    """
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("loop-engineer")
        except PackageNotFoundError:
            pass
    except Exception:  # pragma: no cover - importlib.metadata ships on 3.10+
        pass
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - repo layout guarantees this file
        return "unknown"
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else "unknown"


def _print_json(report: dict) -> int:
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


def _extract_mode_flag(argv: list[str]) -> tuple[str | None, list[str]]:
    """Extract the doctor-family validation mode without changing positional argv."""
    mode: str | None = None
    remaining: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--mode":
            if index + 1 >= len(argv):
                raise ValueError("--mode requires a value")
            value = argv[index + 1]
            index += 2
        elif arg.startswith("--mode="):
            value = arg.split("=", 1)[1]
            index += 1
        else:
            remaining.append(arg)
            index += 1
            continue
        if value not in VALIDATION_MODES:
            valid = ", ".join(VALIDATION_MODES)
            raise ValueError(f"invalid --mode value {value!r}; expected one of: {valid}")
        mode = value
    return mode, remaining


def _run_metrics(argv: list[str]) -> int:
    """`metrics [--baseline] <target>` — parses its own flag, then delegates to
    scripts/metrics.py (resolved bundle-first, repo-relative fallback)."""
    unknown = [a for a in argv if a.startswith("-") and a != "--baseline"]
    if unknown:
        print(f"metrics: unknown option: {unknown[0]}", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 2
    positional = [a for a in argv if not a.startswith("-")]
    if not positional:
        print("metrics: missing target argument", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 2
    target = Path(positional[0])
    if not target.exists():
        print(
            f"metrics: target path does not exist: {target}\n"
            f"       pass an existing loop workspace or its .loop/ directory.",
            file=sys.stderr,
        )
        return 2
    from ._resources import tools_dir

    scripts_dir = tools_dir()
    sys.path.insert(0, str(scripts_dir))
    import metrics  # type: ignore

    return metrics.run(argv)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv:
        print(_USAGE, file=sys.stderr)
        return 2
    if argv[0] in {"-h", "--help"}:
        print(_HELP)
        return 0
    if argv[0] == "--version":
        print(_version())
        return 0

    command = argv.pop(0)
    if command not in _COMMANDS:
        print(f"unknown loop command: {command}", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 2

    mode = None
    if command in {"doctor", "validate", "verify", "plan-lint"}:
        try:
            mode, argv = _extract_mode_flag(argv)
        except ValueError as exc:
            print(f"{command}: {exc}", file=sys.stderr)
            print(_USAGE, file=sys.stderr)
            return 2

    # metrics carries its own optional --baseline flag, so it parses its own args
    # before the generic single-target guards below.
    if command == "metrics":
        return _run_metrics(argv)

    if not argv:
        print(f"{command}: missing target argument", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 2
    target = Path(argv[0])

    if command in _READ_COMMANDS and not target.exists():
        if command == "plan-lint":
            hint = "pass an existing loop-engineer/plan@1 JSON file"
        else:
            hint = (
                f"pass an existing workspace root or its .loop/ directory "
                f"(run `{_PROG} scaffold {target}` to create a new contract)"
            )
        print(f"{command}: target path does not exist: {target}\n       {hint}.", file=sys.stderr)
        return 2

    if command == "scaffold":
        from .scaffold import scaffold

        try:
            report = scaffold(target)
        except FileExistsError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps(report, indent=2))
        return 0

    if command in {"doctor", "validate", "verify"}:
        try:
            return _print_json(doctor_report(target, mode=mode))
        except ValidationModeError as exc:
            print(f"{command}: {exc}", file=sys.stderr)
            return 2

    if command == "plan-lint":
        try:
            return _print_json(validate_plan(target, mode=mode))
        except ValidationModeError as exc:
            print(f"{command}: {exc}", file=sys.stderr)
            return 2

    # command == "inspect": keep the historical inspector script as the scoring
    # UI over the same contract artifacts; import lazily to avoid making
    # scripts/ a package.
    from ._resources import tools_dir

    scripts_dir = tools_dir()
    sys.path.insert(0, str(scripts_dir))
    import inspect_loop  # type: ignore

    report = inspect_loop.inspect_loop(str(target))
    print(json.dumps(report, indent=2))
    return 0 if report.get("verdict") != "weak" else 1


if __name__ == "__main__":
    sys.exit(main())
