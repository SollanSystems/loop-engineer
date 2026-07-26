"""Project a loop run into a loop-engineer/verdict@1 predicate body.

This module builds a document. It NEVER signs one, never verifies a signature,
never constructs an in-toto Statement, and never reads an environment variable.
The signer lane (action.yml -> actions/attest) owns the envelope, the subject,
and every cryptographic operation. See docs/adr/0002-ci-attested-verdict.md.
"""

from __future__ import annotations

import json
from importlib import metadata
from pathlib import Path
from typing import Any

from ._resources import schemas_dir
from .contract import doctor_report
from .paths import LoopPaths, resolve_loop_paths

VERDICT_SCHEMA_ID = "loop-engineer/verdict@1"
PREDICATE_TYPE = "urn:loop-engineer:verdict:1"


class VerdictError(ValueError):
    """A verdict cannot be projected from this workspace."""


def _load_verdict_schema() -> dict[str, Any]:
    return json.loads((schemas_dir() / "verdict.schema.json").read_text(encoding="utf-8"))


def _tool_version() -> str | None:
    try:
        return metadata.version("loop-engineer")
    except metadata.PackageNotFoundError:
        return None


def _terminal_record(paths: LoopPaths) -> dict[str, Any]:
    path = paths.loop_dir / "terminal_state.json"
    if not path.is_file():
        raise VerdictError(
            "no terminal record: a verdict projects a finished run "
            f"({path.name} is absent)"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerdictError(f"terminal record is unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise VerdictError("terminal record is not an object")
    if "false_completion" not in data:
        raise VerdictError("terminal record is missing required false_completion")
    if not isinstance(data["false_completion"], bool):
        raise VerdictError("terminal record false_completion must be a boolean")
    return data


def build_verdict(target: str | Path, *, mode: str | None = None) -> dict[str, Any]:
    """Project local run state into a ``verdict@1`` predicate body.

    Pure over the workspace: no environment, network, signing, or verification.
    """
    try:
        paths = resolve_loop_paths(target)
        report = doctor_report(paths.workspace, mode=mode)
    except (OSError, ValueError, RuntimeError) as exc:
        # RuntimeError is pathlib's symlink-loop signal on Python <= 3.12.
        raise VerdictError(f"cannot resolve a loop workspace at {target}: {exc}") from exc

    terminal = _terminal_record(paths)
    store = report.get("event_store") or {}
    chain = store.get("chain") or {}
    head = chain.get("head") or {}
    policy = terminal.get("completion_policy")
    policy_mode = policy.get("mode") if isinstance(policy, dict) else None

    return {
        "schema": VERDICT_SCHEMA_ID,
        "run_id": str(store.get("run_id") or paths.workspace.name),
        "tool": {"name": "loop-engineer", "version": _tool_version()},
        "doctor": {
            "ok": bool(report.get("ok")),
            "validation_mode": str(report.get("validation_mode") or "unknown"),
            "issue_codes": sorted({
                str(issue.get("code"))
                for issue in report.get("issues", [])
                if isinstance(issue, dict) and issue.get("code")
            }),
            "schemas_checked": sorted(
                str(schema) for schema in report.get("schemas_checked", [])
            ),
        },
        "chain": {
            "head": head.get("event_hash"),
            "sequence": head.get("sequence"),
            "unchained_prefix": int(chain.get("unchained_prefix") or 0),
        },
        "terminal": {
            "state": terminal.get("state"),
            "completion_policy": policy_mode,
            "false_completion": terminal["false_completion"],
        },
        "evidence": [],
    }
