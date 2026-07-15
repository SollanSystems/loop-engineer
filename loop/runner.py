"""One event-sourced, crash-resumable execute-task dispatch step."""

from __future__ import annotations

import json
import shlex
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import emit
from .events import EVENT_SCHEMA_ID, SQLiteEventStore, validate_event
from .paths import resolve_loop_paths
from .reducer import reduce_events
from .runtime import RuntimeStoreError


class RunnerError(RuntimeError):
    """A dispatch request could not be attempted."""


class NotReadyError(RunnerError):
    """The event projection has not reached execute-task."""


class VerifierNotImplementedError(RunnerError):
    """A selected task has no declared verification command."""


class VerifierExecutionError(RunnerError):
    """The declared verifier command could not be launched."""


class RunModeNotImplementedError(RunnerError):
    """A requested run mode is not implemented."""


@dataclass(frozen=True)
class VerifyOutcome:
    passed: bool
    summary: str = ""


Verifier = Callable[[dict[str, Any], Path], VerifyOutcome]

_VERIFY_TIMEOUT_SECONDS = 300


def done_task_ids(tasks: list[dict], projection: dict) -> set[str]:
    """Return declaratively done tasks plus durable successful dispatches."""
    done = {task["id"] for task in tasks if task.get("status") == "done"}
    done.update(
        entry["task_id"]
        for entry in projection.get("runlog_entries", [])
        if entry.get("outcome") == "task_passed" and isinstance(entry.get("task_id"), str)
    )
    return done


def select_next_task(tasks: list[dict], projection: dict) -> dict | None:
    """Select the first pending task whose declared dependencies are done."""
    done = done_task_ids(tasks, projection)
    for task in tasks:
        if task.get("status") != "pending" or task.get("id") in done:
            continue
        if all(dependency in done for dependency in task.get("depends_on", [])):
            return task
    return None


def _default_verifier(task: dict[str, Any], workspace: Path) -> VerifyOutcome:
    return _subprocess_verifier(task, workspace)


def _subprocess_verifier(task: dict[str, Any], workspace: Path) -> VerifyOutcome:
    """Run the task's declared verifier in a separate, bounded process."""
    cmd = task.get("verify")
    if not isinstance(cmd, str) or not cmd.strip():
        raise VerifierNotImplementedError(
            f"no verify command declared for task {task.get('id')!r}; "
            "add a non-empty TASKS.json `verify` field"
        )
    try:
        argv = shlex.split(cmd, posix=True)
    except ValueError as exc:
        raise VerifierExecutionError(f"cannot parse verify command {cmd!r}: {exc}") from exc
    try:
        proc = subprocess.run(
            argv, cwd=str(workspace), shell=False, timeout=_VERIFY_TIMEOUT_SECONDS,
            capture_output=True, text=True, errors="replace",
        )
    except subprocess.TimeoutExpired:
        return VerifyOutcome(False, summary=f"verify command timed out after {_VERIFY_TIMEOUT_SECONDS}s")
    except OSError as exc:
        raise VerifierExecutionError(f"cannot execute verify command {cmd!r}: {exc}") from exc
    return VerifyOutcome(proc.returncode == 0, summary=(proc.stdout + proc.stderr)[-2000:])


def _load_tasks(paths: Any) -> list[dict]:
    try:
        raw = json.loads(paths.tasks.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunnerError(f"cannot read TASKS.json: {exc}") from exc
    tasks = raw.get("tasks") if isinstance(raw, dict) else None
    if not isinstance(tasks, list) or not all(isinstance(task, dict) for task in tasks):
        raise RunnerError("TASKS.json must contain a tasks array of objects")
    return tasks


def _projection(target: str | Path, mode: str | None) -> tuple[str, dict[str, Any]]:
    """Read with SQLite's immutable URI so failed attempts create no WAL files."""
    path = resolve_loop_paths(target).loop_dir / "events.db"
    if not path.exists():
        raise RuntimeStoreError("missing_store", f"event store does not exist: {path}")
    # A clean, closed WAL store can be read immutable without creating SQLite
    # sidecars.  A post-COMMIT crash deliberately leaves a WAL sidecar, which
    # must be read in ordinary read-only mode so its durable frames are replayed.
    query = "mode=ro" if path.with_name(path.name + "-wal").exists() else "mode=ro&immutable=1"
    try:
        conn = sqlite3.connect(f"{path.absolute().as_uri()}?{query}", uri=True)
        try:
            run_ids = conn.execute("SELECT DISTINCT run_id FROM events ORDER BY run_id ASC").fetchall()
            if not run_ids:
                raise RuntimeStoreError("empty_store", f"event store is empty: {path}")
            if len(run_ids) != 1:
                raise RuntimeStoreError("ambiguous_run_id", f"event store has ambiguous run_id values: {path}")
            run_id = run_ids[0][0]
            rows = conn.execute("SELECT run_id, sequence, event_id, type, actor, causation_id, correlation_id, ts, payload, artifact_hashes FROM events WHERE run_id = ? ORDER BY sequence ASC", (run_id,)).fetchall()
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise RuntimeStoreError("corrupt_store", f"cannot read event store: {exc}") from exc
    try:
        events = [{"schema": EVENT_SCHEMA_ID, "run_id": row[0], "sequence": row[1], "event_id": row[2], "type": row[3], "actor": row[4], "causation_id": row[5], "correlation_id": row[6], "ts": row[7], "payload": json.loads(row[8]), "artifact_hashes": json.loads(row[9])} for row in rows]
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeStoreError("corrupt_store", f"cannot read event store: {exc}") from exc
    for event in events:
        report = validate_event(event, mode=mode)
        if not report["ok"]:
            raise RuntimeStoreError("invalid_event", f"event store contains invalid event: {report['issues']}")
    try:
        return run_id, reduce_events(events)
    except ValueError as exc:
        raise RuntimeStoreError("invalid_event_stream", str(exc)) from exc


def _reconcile_legacy_iteration(target: str | Path, projection: dict[str, Any]) -> None:
    """Materialize every event-log iteration not yet reflected in state.json."""
    paths = resolve_loop_paths(target)
    try:
        state = json.loads(paths.state.read_text(encoding="utf-8"))
        current_id = state.get("iteration_id") if isinstance(state, dict) else None
    except (OSError, json.JSONDecodeError) as exc:
        raise RunnerError(f"cannot read state.json: {exc}") from exc
    if not isinstance(current_id, int):
        raise RunnerError("state.json iteration_id must be an integer")
    for entry in projection["runlog_entries"]:
        iteration_id = entry.get("iteration_id")
        if isinstance(iteration_id, int) and iteration_id > current_id:
            emit.append_iteration(
                target,
                iteration_id=iteration_id,
                outcome=entry["outcome"],
                state=entry.get("state"),
                task_id=entry.get("task_id", ""),
                notes=entry.get("summary", ""),
            )
            current_id = iteration_id


def _reconcile_legacy_terminal(target: str | Path, projection: dict[str, Any]) -> None:
    """Replay the terminal's already-recorded payload into existing emit APIs."""
    terminal = projection.get("terminal")
    if terminal is None:
        return
    paths = resolve_loop_paths(target)
    if not paths.terminal.exists():
        emit.terminate(
            target,
            state=terminal["state"],
            criteria_met=terminal["criteria_met"],
            evidence=terminal["evidence"],
            false_completion=terminal["false_completion"],
            iteration_id=terminal.get("iteration_id"),
            completion_policy=terminal.get("completion_policy"),
        )
    try:
        state = json.loads(paths.state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunnerError(f"cannot read state.json: {exc}") from exc
    if not isinstance(state, dict) or state.get("state") != "terminal" or state.get("terminal_state") != terminal["state"]:
        emit.sync_state_to_terminal(target)


def dispatch_once(
    target: str | Path, *, verifier: Verifier | None = None, mode: str | None = None,
) -> dict[str, Any]:
    """Run at most one durable selection/verification/recording dispatch."""
    run_id, projection = _projection(target, mode)
    # Safe only because each dispatch_once invocation appends at most one event.
    if projection.get("terminal") is not None:
        _reconcile_legacy_terminal(target, projection)
        return {"ok": True, "action": "noop_terminal", "run_id": run_id}
    if projection.get("state") != "execute-task":
        raise NotReadyError(f"dispatch requires state 'execute-task', got {projection.get('state')!r}")

    _reconcile_legacy_iteration(target, projection)
    paths = resolve_loop_paths(target)
    tasks = _load_tasks(paths)
    task = select_next_task(tasks, projection)
    if task is None:
        done = done_task_ids(tasks, projection)
        if all(task.get("id") in done for task in tasks):
            iteration_id = projection["iteration_id"]
            payload = {
                "state": "Succeeded", "criteria_met": {task["id"]: True for task in tasks},
                "evidence": ["RUNLOG.md"], "false_completion": False,
                "completion_policy": {"mode": "all_required"}, "iteration_id": iteration_id,
            }
            store = SQLiteEventStore(paths.loop_dir / "events.db")
            store.append(run_id, "terminal_written", payload, actor="loop.run",
                         expected_sequence=projection["last_sequence"] + 1)
            _reconcile_legacy_terminal(target, {**projection, "terminal": payload})
            return {"ok": True, "action": "terminal_written", "iteration_id": iteration_id, "run_id": run_id}
        return {"ok": False, "action": "blocked", "run_id": run_id}

    outcome = (verifier or _default_verifier)(task, paths.workspace)
    if not isinstance(outcome, VerifyOutcome):
        raise RunnerError("verifier must return VerifyOutcome")
    iteration_id = projection["iteration_id"] + 1
    payload = {
        "iteration_id": iteration_id,
        "outcome": "task_passed" if outcome.passed else "task_failed",
        "task_id": task["id"],
        "summary": outcome.summary,
    }
    store = SQLiteEventStore(paths.loop_dir / "events.db")
    store.append(run_id, "iteration_appended", payload, actor="loop.run",
                 expected_sequence=projection["last_sequence"] + 1)
    emit.append_iteration(target, iteration_id=iteration_id, outcome=payload["outcome"],
                          task_id=payload["task_id"], notes=payload["summary"])
    return {"ok": True, "action": "dispatched", "task_id": task["id"],
            "outcome": payload["outcome"], "iteration_id": iteration_id, "run_id": run_id}
