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
        # The manifest may come from an untrusted/foreign loop dir; a malformed
        # document must fail safe to {} (parseable-as-empty), mirroring the
        # json.JSONDecodeError guard in _read_json — never propagate a traceback.
        try:
            loaded = yaml.safe_load(text)
        except yaml.YAMLError:
            loaded = None
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


def _check_tasks_semantics(data: dict[str, Any] | None, path: Path, issues: list[dict]) -> None:
    """Cross-task rules JSON Schema cannot express: id uniqueness and the
    evidence-before-done invariant. Runs in both validation modes."""

    if not isinstance(data, dict):
        return
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        return
    seen: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = task.get("id")
        if isinstance(task_id, str) and task_id:
            if task_id in seen:
                issues.append(ContractIssue("duplicate_task", f"duplicate task id {task_id!r}", path))
            seen.add(task_id)
        if task.get("status") == "done" and not task.get("evidence"):
            issues.append(ContractIssue("done_without_evidence", f"task {task_id!r} done without evidence", path))


def _validate_tasks(data: dict[str, Any] | None, path: Path, issues: list[dict]) -> None:
    _require_schema(data, "loop-engineer/tasks@1", path, issues)
    if data is None:
        return
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        issues.append(ContractIssue("invalid_tasks", "tasks must be a list", path))
        return
    for task in tasks:
        if not isinstance(task, dict):
            issues.append(ContractIssue("invalid_task", "task must be an object", path))
            continue
        task_id = task.get("id")
        if not isinstance(task_id, str) or not task_id:
            issues.append(ContractIssue("invalid_task", "task id must be a non-empty string", path))
    _check_tasks_semantics(data, path, issues)


def _check_terminal_contradiction(data: dict[str, Any] | None, path: Path, issues: list[dict]) -> None:
    """G1: a Succeeded terminal must not contradict its own evidence.

    Runs in both validation modes because JSON Schema cannot express the
    cross-field rule that a success claim requires false_completion=false AND at
    least one met criterion.
    """

    if not isinstance(data, dict) or data.get("state") != "Succeeded":
        return
    if data.get("false_completion") is True:
        issues.append(
            ContractIssue("contradictory_terminal", "Succeeded terminal declares false_completion=true", path)
        )
    criteria = data.get("criteria_met")
    if not isinstance(criteria, dict) or not any(v is True for v in criteria.values()):
        issues.append(
            ContractIssue("contradictory_terminal", "Succeeded terminal has no met (true) entry in criteria_met", path)
        )


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
    _check_terminal_contradiction(data, path, issues)


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


_SCHEMA_FILES = {
    "manifest": "manifest.schema.json",
    "state": "state.schema.json",
    "tasks": "tasks.schema.json",
    "terminal": "terminal.schema.json",
}


def _schemas_dir() -> Path:
    # Bundle-first (wheel package data), repo-relative editable-install fallback.
    from ._resources import schemas_dir

    return schemas_dir()


def _load_schema(name: str) -> dict[str, Any]:
    return json.loads((_schemas_dir() / _SCHEMA_FILES[name]).read_text(encoding="utf-8"))


def _validation_mode() -> str:
    try:
        import jsonschema  # type: ignore  # noqa: F401
    except Exception:
        return "structural-fallback"
    return "jsonschema"


def _jsonschema_validate(data: dict[str, Any], name: str, path: Path, issues: list[dict]) -> None:
    import jsonschema  # type: ignore

    validator = jsonschema.Draft202012Validator(_load_schema(name))
    for err in validator.iter_errors(data):
        location = "/".join(str(p) for p in err.absolute_path) or "<root>"
        issues.append(ContractIssue("schema_violation", f"{path.name}: {location}: {err.message}", path))


# The FCR/RP evidentiary trail (M5): repair records and receipt/rollout ledgers.
# Validated OPTIONALLY — only when the files exist — so an in-flight loop that has
# not emitted them yet still passes, while a loop that ships malformed metric
# inputs can no longer pass validation with them unchecked.
_RECORD_SCHEMA_FILES = {
    "repair": "repair-record.schema.json",
    "rollout": "rollout-record.schema.json",
    "receipt": "receipt.schema.json",
}

# The $id each record schema publishes, reported under schemas_checked when the
# corresponding record files were present and validated (deterministic order).
_RECORD_SCHEMA_IDS = (
    ("repair", "loop-engineer/repair@1"),
    ("rollout", "loop-engineer/rollout@1"),
    ("receipt", "loop-engineer/receipt@1"),
)


def _load_schema_file(filename: str) -> dict[str, Any]:
    return json.loads((_schemas_dir() / filename).read_text(encoding="utf-8"))


def _structural_record_check(data: dict[str, Any], schema: dict[str, Any], path: Path, issues: list[dict]) -> None:
    props = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in data:
            issues.append(ContractIssue("invalid_record", f"{path.name}: missing {key}", path))
    for key, sub in props.items():
        if key in data and isinstance(sub, dict) and "const" in sub and data[key] != sub["const"]:
            issues.append(ContractIssue("schema_mismatch", f"{path.name}: {key} != {sub['const']!r}", path))
    for vk in ("verification_before", "verification_after"):
        sub = props.get(vk)
        if isinstance(sub, dict) and "score" in sub.get("required", []) and vk in data:
            value = data[vk]
            score = value.get("score") if isinstance(value, dict) else None
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                issues.append(ContractIssue("invalid_record", f"{path.name}: {vk}.score must be numeric", path))


def _validate_record(data: dict[str, Any], schema_key: str, path: Path, mode: str, issues: list[dict]) -> None:
    filename = _RECORD_SCHEMA_FILES[schema_key]
    if mode == "jsonschema":
        import jsonschema  # type: ignore

        validator = jsonschema.Draft202012Validator(_load_schema_file(filename))
        for err in validator.iter_errors(data):
            location = "/".join(str(p) for p in err.absolute_path) or "<root>"
            issues.append(ContractIssue("schema_violation", f"{path.name}: {location}: {err.message}", path))
    else:
        _structural_record_check(data, _load_schema_file(filename), path, issues)


def _validate_jsonl(path: Path, schema_key: str, mode: str, issues: list[dict]) -> None:
    for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append(ContractIssue("invalid_json", f"{path.name}:{lineno}: {exc}", path))
            continue
        if not isinstance(data, dict):
            issues.append(ContractIssue("invalid_record", f"{path.name}:{lineno}: expected object", path))
            continue
        _validate_record(data, schema_key, path, mode, issues)


def _validate_optional_records(paths: LoopPaths, mode: str, issues: list[dict]) -> set[str]:
    """Validate record files that are present; return the set of record schema
    keys actually checked (``repair``/``rollout``/``receipt``) so ``doctor`` can
    report them under ``schemas_checked`` instead of under-counting its coverage."""
    checked: set[str] = set()
    repair_dir = paths.loop_dir / "repair"
    if repair_dir.is_dir():
        for record_path in sorted(repair_dir.glob("*.json")):
            data = _read_json(record_path, issues)
            if data is not None:
                _validate_record(data, "repair", record_path, mode, issues)
                checked.add("repair")
    for ledger_path in sorted(paths.loop_dir.glob("*.jsonl")):
        _validate_jsonl(ledger_path, "rollout", mode, issues)
        checked.add("rollout")
    receipts_dir = paths.loop_dir / "receipts"
    if receipts_dir.is_dir():
        for receipt_path in sorted(receipts_dir.glob("*.jsonl")):
            _validate_jsonl(receipt_path, "receipt", mode, issues)
            checked.add("receipt")
    return checked


def validate_contract(target: str | Path) -> dict[str, Any]:
    paths = resolve_loop_paths(target)
    issues: list[dict] = []
    manifest = read_manifest(paths.manifest)
    state = _read_json(paths.state, issues)
    tasks = _read_json(paths.tasks, issues)
    if not paths.terminal.exists() and isinstance(state, dict) and state.get("terminal_state") is None:
        # In-flight loop: terminal_state.json is written once, at loop end. Its
        # absence is valid while state.json still declares terminal_state: null.
        terminal = None
    else:
        terminal = _read_json(paths.terminal, issues)

    mode = _validation_mode()
    if mode == "jsonschema":
        if manifest is None:
            issues.append(ContractIssue("missing_file", "missing manifest.yaml", paths.manifest))
        else:
            _jsonschema_validate(manifest, "manifest", paths.manifest, issues)
        for data, name, path in (
            (state, "state", paths.state),
            (tasks, "tasks", paths.tasks),
            (terminal, "terminal", paths.terminal),
        ):
            if data is not None:
                _jsonschema_validate(data, name, path, issues)
        # Cross-field rules JSON Schema cannot express, run in both modes.
        _check_tasks_semantics(tasks, paths.tasks, issues)
        _check_terminal_contradiction(terminal, paths.terminal, issues)
    else:
        _validate_manifest(manifest, paths.manifest, issues)
        _validate_state(state, paths.state, issues)
        _validate_tasks(tasks, paths.tasks, issues)
        _validate_terminal(terminal, paths.terminal, issues)

    if not paths.runlog.exists():
        issues.append(ContractIssue("missing_file", "missing RUNLOG.md", paths.runlog))
    _check_stub_verify_scripts(paths, issues)
    records_checked = _validate_optional_records(paths, mode, issues)

    schemas_checked = list(SCHEMA_IDS) + [
        schema_id for key, schema_id in _RECORD_SCHEMA_IDS if key in records_checked
    ]

    return {
        "ok": not issues,
        "paths": paths.to_json(),
        "validation_mode": mode,
        "schemas_checked": schemas_checked,
        "issues": issues,
    }


def doctor_report(target: str | Path) -> dict[str, Any]:
    return validate_contract(target)
