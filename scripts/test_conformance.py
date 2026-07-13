"""ST2 acceptance #8 — the runnable conformance checklist.

One test per ratified checklist item ID (A1–E1); each runs against TWO fixtures:

  * ``terminated`` — the tracked flagship ``examples/coverage-repair`` (a real,
    Succeeded contract that ships a terminal file and a repair record);
  * ``inflight``   — a fresh scaffold built here in a tmp dir from ``templates/``
    (``terminal_state: null``, no terminal file — B1's first arm).

C-items are checked-when-present: a fixture that genuinely ships no receipt /
rollout trail is skipped-with-reason for that item, and the trail the fixture
DOES ship is asserted on. Schema conformance is exercised in BOTH validation
modes where meaningful (the jsonschema path when the library is installed, and
the stdlib structural path — forced by hiding ``jsonschema``).

The scaffold helper is intentionally local to this module. S2 writes a similar
helper in ``test_template_roundtrip.py``; duplication between the two modules is
accepted for this slice — this test does not import from S2's module.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import loop.contract as C  # noqa: E402
from loop.contract import TERMINAL_STATES, validate_contract  # noqa: E402
from loop.paths import resolve_loop_paths  # noqa: E402

TEMPLATES = ROOT / "templates"
EXAMPLE = ROOT / "examples" / "coverage-repair"

CHECKLIST_IDS = ("A1", "A2", "A3", "A4", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1")


# --------------------------------------------------------------------------- #
# Local scaffold helper — fill templates/ into a fresh in-flight contract.
# --------------------------------------------------------------------------- #

_STATE_FILL = {
    "PROJECT_NAME": "conformance-inflight",
    "ITERATION_ID": "0",  # quoted in the template -> string "0" -> lifecycle "planned"
    "PLAN_VERSION": "0",
    "ACTIVE_TASK_ID": "T1",
    "STATE": "intake",
    "BEST_SCORE": "null",
    "FAILURE_MODE": "",
    "PENDING_APPROVAL": "null",
    "TIME_REMAINING": "30m",
    "COST_REMAINING": "1.00usd",
    "CHECKPOINT_PATH": ".loop/checkpoints/none",
    "GOAL_DESCRIPTION": "In-flight conformance scaffold",
    "CRITERION_1": "criterion one is proven by pytest -q",
    "CONSTRAINT_1": "no external side effects",
    "WORKSPACE_PATH": "./",
    "ALLOWED_TOOL_1": "read",
    "RISK_PROFILE": "low",
    "TIME_BUDGET": "30m",
    "COST_BUDGET": "1.00usd",
    "APPROVAL_POLICY": "on_side_effects",
    "REPAIR_ATTEMPTS": "0",
    "REPAIR_CAP": "2",
    "LAST_VERIFY_CMD": "pytest -q",
    "LAST_VERIFY_OUTCOME": "PENDING",
    "LAST_SCORE": "null",
    "EVIDENCE_PATH": ".loop/artifacts/",
    "SHORT_TERM_SUMMARY": "scaffolded, not yet run",
    "LESSONS_PATH": ".loop/memory/lessons.md",
}

_MANIFEST_FILL = {
    "LOOP_NAME": "conformance-inflight",
    "GOAL_DESCRIPTION": "In-flight conformance scaffold",
    "CRITERION_1": "criterion one is proven by pytest -q",
    "CONSTRAINT_1": "no external side effects",
    "WORKSPACE_PATH": "./",
    "ALLOWED_TOOLS": "read, workspace-write",
    "RISK_PROFILE": "low",
    "TIME_BUDGET": "30m",
    "COST_BUDGET": "1.00usd",
    "APPROVAL_POLICY": "on_side_effects",
    "PERMISSION_1": "read-only",
    "APPROVAL_GATE_1": "destructive_commands",
    "REPAIR_CAP": "2",
    "PLAN_THEN_EXECUTE": "false",
}

_TASKS_FILL = {
    "PROJECT_NAME": "conformance-inflight",
    "TASK_ID": "T1",
    "TASK_TITLE": "Do the bounded task",
    "TASK_STATUS": "pending",
    "TASK_CRITERION_REF": "1",
    "TASK_VERIFY": "pytest -q",  # a plain command: a verify surface, not a path.
    "CREATED_AT": "2026-01-01T00:00:00Z",
    "UPDATED_AT": "2026-01-01T00:00:00Z",
}


def _fill(template_name: str, mapping: dict[str, str]) -> str:
    text = (TEMPLATES / template_name).read_text(encoding="utf-8")
    for key, value in mapping.items():
        text = text.replace("{{" + key + "}}", value)
    # `{{PLACEHOLDER}}` is a literal doc token in a manifest YAML comment, not a
    # fillable field; every real placeholder must be substituted.
    remaining = [p for p in re.findall(r"{{(\w+)}}", text) if p != "PLACEHOLDER"]
    assert not remaining, f"unfilled placeholders in {template_name}: {remaining}"
    return text


def _scaffold_inflight(target: Path) -> Path:
    """Write a fresh, in-flight (terminal_state: null, no terminal file) contract
    filled from the shipped templates/ into ``target``."""
    loop_dir = target / ".loop"
    loop_dir.mkdir(parents=True)

    state_text = _fill("state.json.tmpl", _STATE_FILL)
    tasks_text = _fill("TASKS.json.tmpl", _TASKS_FILL)
    # Fail loudly here (not at validate time) if a fill produced invalid JSON.
    json.loads(state_text)
    json.loads(tasks_text)

    (loop_dir / "state.json").write_text(state_text, encoding="utf-8")
    (loop_dir / "manifest.yaml").write_text(_fill("manifest.yaml.tmpl", _MANIFEST_FILL), encoding="utf-8")
    (target / "TASKS.json").write_text(tasks_text, encoding="utf-8")
    (target / "RUNLOG.md").write_text(
        (TEMPLATES / "RUNLOG.md.tmpl").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return target


@pytest.fixture()
def contracts(tmp_path) -> dict[str, Path]:
    """The two fixtures every checklist item is exercised against."""
    return {
        "terminated": EXAMPLE,
        "inflight": _scaffold_inflight(tmp_path / "inflight"),
    }


# --------------------------------------------------------------------------- #
# Shared validation helpers — drive loop.contract's own validators, both modes.
# --------------------------------------------------------------------------- #

def _has_jsonschema() -> bool:
    try:
        import jsonschema  # noqa: F401
        return True
    except Exception:
        return False


_STRUCTURAL = {
    "manifest": C._validate_manifest,
    "state": C._validate_state,
    "tasks": C._validate_tasks,
    "terminal": C._validate_terminal,
}


def _artifact_issues_both_modes(name: str, data: dict, path: Path) -> None:
    """Assert ``data`` validates against ``loop-engineer/<name>@1`` in the stdlib
    structural mode AND (when installed) the real jsonschema mode."""
    structural: list[dict] = []
    _STRUCTURAL[name](data, path, structural)
    assert structural == [], f"{name} structural issues: {structural}"
    if _has_jsonschema():
        js: list[dict] = []
        C._jsonschema_validate(data, name, path, js)
        assert js == [], f"{name} jsonschema issues: {js}"


def _record_issues_both_modes(data: dict, schema_key: str, path: Path) -> None:
    structural: list[dict] = []
    C._validate_record(data, schema_key, path, "structural-fallback", structural)
    assert structural == [], f"{schema_key} structural issues: {structural}"
    if _has_jsonschema():
        js: list[dict] = []
        C._validate_record(data, schema_key, path, "jsonschema", js)
        assert js == [], f"{schema_key} jsonschema issues: {js}"


def _jsonl_issues_both_modes(path: Path, schema_key: str) -> None:
    structural: list[dict] = []
    C._validate_jsonl(path, schema_key, "structural-fallback", structural)
    assert structural == [], f"{path.name} structural issues: {structural}"
    if _has_jsonschema():
        js: list[dict] = []
        C._validate_jsonl(path, schema_key, "jsonschema", js)
        assert js == [], f"{path.name} jsonschema issues: {js}"


def _published_schema_ids() -> set[str]:
    ids: set[str] = set()
    for schema_file in sorted((ROOT / "schemas").glob("*.schema.json")):
        ids.add(json.loads(schema_file.read_text(encoding="utf-8"))["$id"])
    return ids


# --------------------------------------------------------------------------- #
# A. Artifacts present & well-formed.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_a1_manifest_schema(contracts, kind):
    paths = resolve_loop_paths(contracts[kind])
    data = C.read_manifest(paths.manifest)
    assert isinstance(data, dict) and data, "manifest did not parse to a mapping"
    assert data.get("schema") == "loop-engineer/manifest@1"
    # The canonical 7 terminal_states, verbatim and in order.
    assert list(data.get("terminal_states") or []) == list(TERMINAL_STATES)
    _artifact_issues_both_modes("manifest", data, paths.manifest)


@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_a2_state_schema(contracts, kind):
    paths = resolve_loop_paths(contracts[kind])
    data = json.loads(paths.state.read_text(encoding="utf-8"))
    assert data.get("schema") == "loop-engineer/state@1"
    _artifact_issues_both_modes("state", data, paths.state)


@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_a3_tasks_schema(contracts, kind):
    paths = resolve_loop_paths(contracts[kind])
    data = json.loads(paths.tasks.read_text(encoding="utf-8"))
    assert data.get("schema") == "loop-engineer/tasks@1"
    _artifact_issues_both_modes("tasks", data, paths.tasks)
    # Cross-task rules JSON Schema cannot express: id uniqueness, evidence-before-done.
    semantics: list[dict] = []
    C._check_tasks_semantics(data, paths.tasks, semantics)
    assert semantics == [], semantics


@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_a4_runlog_present(contracts, kind):
    paths = resolve_loop_paths(contracts[kind])
    assert paths.runlog.name == "RUNLOG.md"
    assert paths.runlog.is_file(), f"RUNLOG.md missing for {kind}"


# --------------------------------------------------------------------------- #
# B. Lifecycle honesty.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_b1_terminal_pair_exclusivity(contracts, kind):
    paths = resolve_loop_paths(contracts[kind])
    state = json.loads(paths.state.read_text(encoding="utf-8"))
    terminal_state = state.get("terminal_state")
    terminal_present = paths.terminal.exists()

    arm_inflight = terminal_state is None and not terminal_present
    terminal_valid = False
    if terminal_present:
        term_issues: list[dict] = []
        C._validate_terminal(
            json.loads(paths.terminal.read_text(encoding="utf-8")), paths.terminal, term_issues
        )
        terminal_valid = not term_issues
    arm_terminated = terminal_state in TERMINAL_STATES and terminal_present and terminal_valid

    assert arm_inflight ^ arm_terminated, (
        f"B1 requires exactly one arm: inflight={arm_inflight} terminated={arm_terminated}"
    )
    # And the contract as a whole must pass — no contradictory lifecycle issue.
    assert validate_contract(contracts[kind])["ok"] is True


@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_b2_terminal_proof_surface(contracts, kind):
    paths = resolve_loop_paths(contracts[kind])
    if not paths.terminal.exists():
        pytest.skip(f"{kind}: no terminal_state.json — B2 is checked-when-present")
    data = json.loads(paths.terminal.read_text(encoding="utf-8"))
    _artifact_issues_both_modes("terminal", data, paths.terminal)
    assert isinstance(data.get("criteria_met"), dict)
    assert isinstance(data.get("evidence"), list)
    assert isinstance(data.get("false_completion"), bool)
    if data.get("state") == "Succeeded":
        assert data["false_completion"] is False
        assert any(v is True for v in data["criteria_met"].values())
        assert data["evidence"], "Succeeded terminal must carry non-empty evidence"


# --------------------------------------------------------------------------- #
# C. Evidentiary trail (checked when present).
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_c1_receipts_trail(contracts, kind):
    paths = resolve_loop_paths(contracts[kind])
    receipts_dir = paths.loop_dir / "receipts"
    receipts = sorted(receipts_dir.glob("*.jsonl")) if receipts_dir.is_dir() else []
    if not receipts:
        pytest.skip(f"{kind}: no .loop/receipts/*.jsonl trail — C1 is checked-when-present")
    for receipt in receipts:
        _jsonl_issues_both_modes(receipt, "receipt")


@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_c2_repair_trail(contracts, kind):
    paths = resolve_loop_paths(contracts[kind])
    repair_dir = paths.loop_dir / "repair"
    records = sorted(repair_dir.glob("*.json")) if repair_dir.is_dir() else []
    if not records:
        pytest.skip(f"{kind}: no .loop/repair/*.json trail — C2 is checked-when-present")
    for record_path in records:
        data = json.loads(record_path.read_text(encoding="utf-8"))
        assert data.get("schema") == "loop-engineer/repair@1"
        _record_issues_both_modes(data, "repair", record_path)


@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_c3_rollout_trail(contracts, kind):
    paths = resolve_loop_paths(contracts[kind])
    rollout = paths.loop_dir / "rollout.jsonl"
    if not rollout.is_file():
        pytest.skip(f"{kind}: no .loop/rollout.jsonl ledger — C3 is checked-when-present")
    _jsonl_issues_both_modes(rollout, "rollout")


# --------------------------------------------------------------------------- #
# D. Versioning.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_d1_schema_ids_are_published(contracts, kind):
    published = _published_schema_ids()
    paths = resolve_loop_paths(contracts[kind])

    manifest = C.read_manifest(paths.manifest)
    assert manifest.get("schema") in published

    for path in (paths.state, paths.tasks):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("schema") in published, (path.name, data.get("schema"))

    if paths.terminal.exists():
        terminal = json.loads(paths.terminal.read_text(encoding="utf-8"))
        assert terminal.get("schema") in published

    repair_dir = paths.loop_dir / "repair"
    if repair_dir.is_dir():
        for record_path in sorted(repair_dir.glob("*.json")):
            record = json.loads(record_path.read_text(encoding="utf-8"))
            assert record.get("schema") in published, (record_path.name, record.get("schema"))


@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_d2_additive_keys_are_tolerated(contracts, kind, tmp_path, monkeypatch):
    # Copy the whole contract, inject an unknown additive key into every artifact,
    # and assert validation still passes in BOTH modes (a v1 validator never
    # rejects a newer emitter's additive fields).
    dest = tmp_path / f"copy_{kind}"
    shutil.copytree(contracts[kind], dest)
    paths = resolve_loop_paths(dest)

    def _inject_json(path: Path, extra: dict) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update(extra)
        path.write_text(json.dumps(data), encoding="utf-8")

    _inject_json(paths.state, {"x_unknown_additive": {"nested": [1, 2]}})
    tasks = json.loads(paths.tasks.read_text(encoding="utf-8"))
    tasks["x_unknown_additive"] = "additive"
    if tasks.get("tasks"):
        tasks["tasks"][0]["x_unknown_task_key"] = "additive"
    paths.tasks.write_text(json.dumps(tasks), encoding="utf-8")
    if paths.terminal.exists():
        _inject_json(paths.terminal, {"x_unknown_additive": True})
    paths.manifest.write_text(
        paths.manifest.read_text(encoding="utf-8") + "\nx_unknown_additive_key: additive\n",
        encoding="utf-8",
    )

    # Pass 1: whatever mode is installed (jsonschema when present).
    report_default = validate_contract(dest)
    assert report_default["ok"] is True, report_default["issues"]

    # Pass 2: force the stdlib structural mode by hiding jsonschema.
    monkeypatch.setitem(sys.modules, "jsonschema", None)
    report_structural = validate_contract(dest)
    assert report_structural["validation_mode"] == "structural-fallback"
    assert report_structural["ok"] is True, report_structural["issues"]


# --------------------------------------------------------------------------- #
# E. Lifecycle report.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_e1_doctor_lifecycle_consistent_with_b1(contracts, kind):
    report = validate_contract(contracts[kind])
    expected = "terminated:Succeeded" if kind == "terminated" else "planned"
    assert report["lifecycle"] == expected


# --------------------------------------------------------------------------- #
# Doc-parity guard — the normative doc must publish every checklist ID.
# --------------------------------------------------------------------------- #

def test_conformance_checklist_documented():
    doc = ROOT / "reference" / "repo-os-contract.md"
    text = doc.read_text(encoding="utf-8")
    assert "conformance checklist" in text.lower(), "normative doc lacks a conformance-checklist section"
    for cid in CHECKLIST_IDS:
        assert cid in text, f"checklist ID {cid} missing from normative doc"
