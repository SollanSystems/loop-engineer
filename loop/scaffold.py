from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from ._resources import templates_dir


def _templates_dir() -> Path:
    return templates_dir()


_PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")

# Files copied verbatim (executable), keyed by template name -> destination.
_VERIFY_SCRIPTS = {
    "verify-fast.sh": "scripts/verify-fast",
    "verify-full.sh": "scripts/verify-full",
}

# Template -> destination for the filled contract files. terminal_state.json is
# intentionally absent: it is written once, at loop end, by loop-run.
_FILLED_FILES = {
    "AGENTS.md.tmpl": "AGENTS.md",
    "SPEC.md.tmpl": "SPEC.md",
    "WORKFLOW.md.tmpl": "WORKFLOW.md",
    "TASKS.json.tmpl": "TASKS.json",
    "RUNLOG.md.tmpl": "RUNLOG.md",
    "manifest.yaml.tmpl": ".loop/manifest.yaml",
    "state.json.tmpl": ".loop/state.json",
}

# Existing-contract markers: any of these means the target already holds a loop
# contract and must not be silently overwritten.
_CONTRACT_MARKERS = ("SPEC.md", "WORKFLOW.md", "TASKS.json", ".loop/state.json")


def _substitutions(project: str) -> dict[str, str]:
    """Honest, valid-by-construction defaults for every {{PLACEHOLDER}}.

    Numeric/boolean/null slots (unquoted in the templates) map to bare JSON
    tokens; everything else maps to a string. A fresh scaffold is a valid
    in-flight contract, not a fake completed one.
    """

    return {
        "PROJECT_NAME": project,
        "LOOP_NAME": project,
        "ITERATION_ID": "0",
        "PLAN_VERSION": "1",
        "ACTIVE_TASK_ID": "",
        "STATE": "intake",
        "BEST_SCORE": "null",
        "FAILURE_MODE": "",
        "PENDING_APPROVAL": "null",
        "TIME_REMAINING": "",
        "COST_REMAINING": "",
        "CHECKPOINT_PATH": "",
        "GOAL_DESCRIPTION": "REPLACE: one-line goal",
        "CRITERION_1": "REPLACE: first success criterion",
        "CONSTRAINT_1": "REPLACE: first constraint",
        "WORKSPACE_PATH": ".",
        "ALLOWED_TOOL_1": "Read",
        "ALLOWED_TOOLS": "",
        "RISK_PROFILE": "low",
        "TIME_BUDGET": "",
        "COST_BUDGET": "",
        "APPROVAL_POLICY": "on_side_effects",
        "REPAIR_ATTEMPTS": "0",
        "REPAIR_CAP": "2",
        "LAST_VERIFY_CMD": "",
        "LAST_VERIFY_OUTCOME": "",
        "LAST_SCORE": "null",
        "EVIDENCE_PATH": "",
        "SHORT_TERM_SUMMARY": "",
        "LESSONS_PATH": "",
        "PERMISSION_1": "read-only",
        "APPROVAL_GATE_1": "on_side_effects",
        "PLAN_THEN_EXECUTE": "true",
        "TASK_ID": "T1",
        "TASK_TITLE": "REPLACE: first task",
        "TASK_STATUS": "pending",
        "TASK_CRITERION_REF": "1",
        "TASK_VERIFY": "scripts/verify-fast",
        "CREATED_AT": "",
        "UPDATED_AT": "",
    }


def _fill(text: str, mapping: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        token = match.group(0)[2:-2]
        return mapping.get(token, "REPLACE")

    return _PLACEHOLDER_RE.sub(repl, text)


def _has_existing_contract(target: Path) -> bool:
    return any((target / marker).exists() for marker in _CONTRACT_MARKERS)


def scaffold(target: str | Path) -> dict[str, Any]:
    """Write a fresh, doctor-clean repo-OS contract into ``target``.

    Refuses to overwrite an existing contract dir (a live loop owns its state).
    """

    target = Path(target)
    if target.exists() and _has_existing_contract(target):
        raise FileExistsError(f"contract already exists at {target}")

    mapping = _substitutions(target.name)
    written: list[str] = []

    for template_name, rel in _FILLED_FILES.items():
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = (_templates_dir() / template_name).read_text(encoding="utf-8")
        dest.write_text(_fill(text, mapping), encoding="utf-8")
        written.append(rel)

    for template_name, rel in _VERIFY_SCRIPTS.items():
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_templates_dir() / template_name, dest)
        dest.chmod(0o755)
        written.append(rel)

    return {"ok": True, "target": str(target), "written": written}
