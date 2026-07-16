"""Strictly read-only prediction of the next ``loop run`` dispatch step."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from . import runner, runtime
from .contract import _resolve_requested_mode
from .events import EVENT_SCHEMA_ID
from .paths import resolve_loop_paths


def _legacy_sync_would_write(paths: Any, projection: dict[str, Any]) -> bool | None:
    """Mirror ``dispatch_once`` reconciliation branching without reconciling."""
    terminal = projection.get("terminal")
    if terminal is not None:
        if not paths.terminal.exists():
            return True
        try:
            state = json.loads(paths.state.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return (
            not isinstance(state, dict)
            or state.get("state") != "terminal"
            or state.get("terminal_state") != terminal.get("state")
        )

    if projection["state"] != "execute-task":
        return False
    try:
        state = json.loads(paths.state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    current_id = state.get("iteration_id") if isinstance(state, dict) else None
    if not isinstance(current_id, int):
        return None
    return any(
        isinstance(entry.get("iteration_id"), int)
        and entry["iteration_id"] > current_id
        for entry in projection["runlog_entries"]
    )


def _empty_prediction() -> dict[str, Any]:
    return {
        "action": None, "task_id": None, "verify_command": None,
        "verify_argv": None, "predicted_terminal": None, "refusal_reason": None,
    }


def _predict(paths: Any, projection: dict[str, Any]) -> dict[str, Any]:
    """Predict dispatch_once's decision without executing its effects."""
    empty = _empty_prediction()
    if projection["terminal"] is not None:
        return {**empty, "action": "already_terminal"}
    if projection["state"] != "execute-task":
        reason = str(runner.NotReadyError(
            f"dispatch requires state 'execute-task', got {projection.get('state')!r}"))
        return {**empty, "action": "would_refuse", "refusal_reason": reason}

    tasks = runner._load_tasks(paths)
    task = runner.select_next_task(tasks, projection)
    if task is None:
        done = runner.done_task_ids(tasks, projection)
        if all(candidate.get("id") in done for candidate in tasks):
            payload = {
                "state": "Succeeded",
                "criteria_met": {candidate["id"]: True for candidate in tasks},
                "evidence": ["RUNLOG.md"], "false_completion": False,
                "completion_policy": {"mode": "all_required"},
                "iteration_id": projection["iteration_id"],
            }
            return {**empty, "action": "would_write_terminal", "predicted_terminal": payload}
        return {**empty, "action": "would_block"}

    command = task.get("verify")
    if not isinstance(command, str) or not command.strip():
        reason = str(runner.VerifierNotImplementedError(
            f"no verify command declared for task {task.get('id')!r}; "
            "add a non-empty TASKS.json `verify` field"))
        return {**empty, "action": "would_refuse", "task_id": task["id"], "refusal_reason": reason}
    try:
        argv = shlex.split(command, posix=True)
    except ValueError as exc:
        reason = str(runner.VerifierExecutionError(
            f"cannot parse verify command {command!r}: {exc}"))
        return {
            **empty, "action": "would_refuse", "task_id": task["id"],
            "verify_command": command, "refusal_reason": reason,
        }
    return {
        **empty, "action": "would_dispatch", "task_id": task["id"],
        "verify_command": command, "verify_argv": argv,
    }


def simulate_run(target: str | Path, *, mode: str | None = None) -> dict[str, Any]:
    """Report the next dispatch decision while leaving the workspace untouched."""
    run_id, projection = runner._projection(target, mode)
    paths = resolve_loop_paths(target)
    requested_mode, resolved_mode = _resolve_requested_mode(mode)
    divergence = runtime._state_divergence(paths, projection)
    terminal_desync, _ = runtime._terminal_desync(paths, projection)
    would = _predict(paths, projection)
    would["legacy_sync_would_write"] = _legacy_sync_would_write(paths, projection)
    return {
        "ok": not divergence and terminal_desync is None,
        "validation_mode": resolved_mode, "requested_mode": requested_mode,
        "schemas_checked": [EVENT_SCHEMA_ID], "run_id": run_id,
        "event_count": projection["event_count"], "state": projection["state"],
        "iteration_id": projection["iteration_id"], "active_task": projection["active_task"],
        "paused": projection["paused"], "pause_reason": projection["pause_reason"],
        "pending_approval": projection["pending_approval"], "terminal": projection["terminal"],
        "state_json_agrees": not divergence, "divergence": divergence,
        "terminal_desync": terminal_desync, "would": would,
    }
