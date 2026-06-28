from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import LoopPaths, resolve_loop_paths

TERMINAL_STATES = (
    "Succeeded",
    "FailedUnverifiable",
    "FailedBlocked",
    "FailedBudget",
    "FailedSafety",
    "FailedSpecGap",
    "AbortedByHuman",
)

SCHEMA_IDS = (
    "loop-engineer/manifest@1",
    "loop-engineer/state@1",
    "loop-engineer/tasks@1",
    "loop-engineer/terminal@1",
)


class ContractIssue(dict):
    def __init__(self, code: str, message: str, path: Path | None = None):
        super().__init__(code=code, message=message)
        if path is not None:
            self["path"] = str(path)


def _read_json(path: Path, issues: list[dict]) -> dict[str, Any] | None:
    if not path.exists():
        issues.append(ContractIssue("missing_file", f"missing {path.name}", path))
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        issues.append(ContractIssue("invalid_json", f"{path.name}: {exc}", path))
        return None
    if not isinstance(data, dict):
        issues.append(ContractIssue("invalid_json", f"{path.name}: expected object", path))
        return None
    return data


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "null":
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def _fallback_yaml(text: str) -> dict[str, Any]:
    """Small YAML subset parser for the manifest shapes this project emits.

    It supports top-level scalars, one-level mappings, and one-level lists. When
    PyYAML is available, `read_manifest` uses it instead.
    """

    root: dict[str, Any] = {}
    current_key: str | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line:
            continue
        if not line.startswith(" ") and ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value:
                root[key] = _parse_scalar(value)
                current_key = None
            else:
                root[key] = {}
                current_key = key
            continue
        if current_key is None:
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            if not isinstance(root[current_key], list):
                root[current_key] = []
            root[current_key].append(_parse_scalar(stripped[2:]))
        elif ":" in stripped:
            if not isinstance(root[current_key], dict):
                root[current_key] = {}
            key, value = stripped.split(":", 1)
            root[current_key][key.strip()] = _parse_scalar(value)
    return root


def read_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except Exception:
        data = _fallback_yaml(text)
    else:
        loaded = yaml.safe_load(text)
        data = loaded if isinstance(loaded, dict) else {}
    return data


def _require_schema(data: dict[str, Any] | None, expected: str, path: Path, issues: list[dict]) -> None:
    if data is None:
        return
    if data.get("schema") != expected:
        issues.append(
            ContractIssue(
                "schema_mismatch",
                f"{path.name}: expected schema {expected!r}, got {data.get('schema')!r}",
                path,
            )
        )


def _validate_state(data: dict[str, Any] | None, path: Path, issues: list[dict]) -> None:
    _require_schema(data, "loop-engineer/state@1", path, issues)
    if data is None:
        return
    for key in ("iteration_id", "state", "plan_version", "budget_remaining"):
        if key not in data:
            issues.append(ContractIssue("missing_state_field", f"state missing {key}", path))
    terminal = data.get("terminal_state")
    if terminal is not None and terminal not in TERMINAL_STATES:
        issues.append(ContractIssue("invalid_terminal_state", f"invalid terminal_state {terminal!r}", path))


def _validate_tasks(data: dict[str, Any] | None, path: Path, issues: list[dict]) -> None:
    _require_schema(data, "loop-engineer/tasks@1", path, issues)
    if data is None:
        return
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        issues.append(ContractIssue("invalid_tasks", "tasks must be a list", path))
        return
    seen: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict):
            issues.append(ContractIssue("invalid_task", "task must be an object", path))
            continue
        task_id = task.get("id")
        if not isinstance(task_id, str) or not task_id:
            issues.append(ContractIssue("invalid_task", "task id must be a non-empty string", path))
        elif task_id in seen:
            issues.append(ContractIssue("duplicate_task", f"duplicate task id {task_id!r}", path))
        seen.add(str(task_id))
        if task.get("status") == "done" and not task.get("evidence"):
            issues.append(ContractIssue("done_without_evidence", f"task {task_id!r} done without evidence", path))


def _validate_terminal(data: dict[str, Any] | None, path: Path, issues: list[dict]) -> None:
    _require_schema(data, "loop-engineer/terminal@1", path, issues)
    if data is None:
        return
    if data.get("state") not in TERMINAL_STATES:
        issues.append(ContractIssue("invalid_terminal_state", f"invalid state {data.get('state')!r}", path))
    if not isinstance(data.get("criteria_met"), dict):
        issues.append(ContractIssue("invalid_terminal", "criteria_met must be an object", path))
    if not isinstance(data.get("evidence"), list):
        issues.append(ContractIssue("invalid_terminal", "evidence must be a list", path))
    if not isinstance(data.get("false_completion"), bool):
        issues.append(ContractIssue("invalid_terminal", "false_completion must be bool", path))


def _validate_manifest(data: dict[str, Any] | None, path: Path, issues: list[dict]) -> None:
    if data is None:
        issues.append(ContractIssue("missing_file", "missing manifest.yaml", path))
        return
    if data.get("schema") != "loop-engineer/manifest@1":
        issues.append(
            ContractIssue(
                "schema_mismatch",
                f"manifest.yaml: expected schema 'loop-engineer/manifest@1', got {data.get('schema')!r}",
                path,
            )
        )
    policies = data.get("policies")
    if not isinstance(policies, dict):
        issues.append(ContractIssue("invalid_manifest", "policies must be an object", path))
    elif not isinstance(policies.get("plan_then_execute"), bool):
        issues.append(ContractIssue("invalid_manifest", "policies.plan_then_execute must be bool", path))
    states = data.get("terminal_states")
    if states is not None and list(states) != list(TERMINAL_STATES):
        issues.append(ContractIssue("invalid_terminal_states", "terminal_states must match canonical 7", path))


def _verify_script_paths(paths: LoopPaths) -> list[Path]:
    scripts = paths.workspace / "scripts"
    return [scripts / "verify-fast", scripts / "verify-fast.sh", scripts / "verify-full", scripts / "verify-full.sh"]


def _check_stub_verify_scripts(paths: LoopPaths, issues: list[dict]) -> None:
    for script in _verify_script_paths(paths):
        if not script.exists() or not script.is_file():
            continue
        text = script.read_text(encoding="utf-8", errors="ignore").lower()
        if "stub:" in text or "replace with real command" in text:
            issues.append(ContractIssue("stub_verify_script", f"{script.name} still contains stub markers", script))


def validate_contract(target: str | Path) -> dict[str, Any]:
    paths = resolve_loop_paths(target)
    issues: list[dict] = []
    manifest = read_manifest(paths.manifest)
    state = _read_json(paths.state, issues)
    tasks = _read_json(paths.tasks, issues)
    terminal = _read_json(paths.terminal, issues)

    _validate_manifest(manifest, paths.manifest, issues)
    _validate_state(state, paths.state, issues)
    _validate_tasks(tasks, paths.tasks, issues)
    _validate_terminal(terminal, paths.terminal, issues)
    if not paths.runlog.exists():
        issues.append(ContractIssue("missing_file", "missing RUNLOG.md", paths.runlog))
    _check_stub_verify_scripts(paths, issues)

    return {
        "ok": not issues,
        "paths": paths.to_json(),
        "schemas_checked": list(SCHEMA_IDS),
        "issues": issues,
    }


def doctor_report(target: str | Path) -> dict[str, Any]:
    return validate_contract(target)
