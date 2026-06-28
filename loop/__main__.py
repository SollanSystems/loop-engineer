from __future__ import annotations

import json
import sys
from pathlib import Path

from .contract import doctor_report


def _print_json(report: dict) -> int:
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        print("usage: python -m loop <doctor|validate|verify|inspect> <workspace-or-.loop>", file=sys.stderr)
        return 2

    command = argv.pop(0)
    target = Path(argv[0]) if argv else Path.cwd()

    if command in {"doctor", "validate", "verify"}:
        return _print_json(doctor_report(target))

    if command == "inspect":
        # Keep the historical inspector script as the scoring UI over the same
        # contract artifacts; import lazily to avoid making scripts/ a package.
        scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
        sys.path.insert(0, str(scripts_dir))
        import inspect_loop  # type: ignore

        report = inspect_loop.inspect_loop(str(target))
        print(json.dumps(report, indent=2))
        return 0 if report.get("verdict") != "weak" else 1

    print(f"unknown loop command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
