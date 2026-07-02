from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .contract import doctor_report

_PROG = "python3 -m loop"

_COMMANDS = ("scaffold", "doctor", "validate", "verify", "inspect")

# Read commands operate on an EXISTING contract dir; scaffold CREATES one, so it
# is exempt from the "target must exist" guard.
_READ_COMMANDS = ("doctor", "validate", "verify", "inspect")

_USAGE = f"usage: {_PROG} <scaffold|doctor|validate|verify|inspect> <workspace-or-.loop>"

_HELP = f"""{_PROG} — validate and inspect a portable repo-OS loop contract.

{_USAGE}

commands:
  scaffold   Write a fresh, doctor-clean loop contract into <target>.
  doctor     Validate the contract objects (manifest, state, tasks, terminal).
  validate   Alias for doctor.
  verify     Alias for doctor — check the contract's state.
  inspect    Score an existing loop against the prime-directive checklist
             (emits a weak/strong verdict and a gap report).

arguments:
  <target>   A workspace root or its .loop/ directory.

options:
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

    if not argv:
        print(f"{command}: missing target argument", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 2
    target = Path(argv[0])

    if command in _READ_COMMANDS and not target.exists():
        print(
            f"{command}: target path does not exist: {target}\n"
            f"       pass an existing workspace root or its .loop/ directory "
            f"(run `{_PROG} scaffold {target}` to create a new contract).",
            file=sys.stderr,
        )
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
        return _print_json(doctor_report(target))

    # command == "inspect": keep the historical inspector script as the scoring
    # UI over the same contract artifacts; import lazily to avoid making
    # scripts/ a package.
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    import inspect_loop  # type: ignore

    report = inspect_loop.inspect_loop(str(target))
    print(json.dumps(report, indent=2))
    return 0 if report.get("verdict") != "weak" else 1


if __name__ == "__main__":
    sys.exit(main())
