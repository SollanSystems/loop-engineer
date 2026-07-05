"""Regression tests for Loop Contract Core (Slice 1/2).

These tests pin the protocol-first slice: shared path resolution, schema-aware
contract validation, and a doctor CLI that reports actionable release/loop
contract issues instead of relying on prose keyword matching.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


TERMINAL_STATES = [
    "Succeeded",
    "FailedUnverifiable",
    "FailedBlocked",
    "FailedBudget",
    "FailedSafety",
    "FailedSpecGap",
    "AbortedByHuman",
]


def _write_valid_loop(root: pathlib.Path) -> pathlib.Path:
    workspace = root / "workspace"
    loop_dir = workspace / ".loop"
    scripts = workspace / "scripts"
    loop_dir.mkdir(parents=True)
    scripts.mkdir()

    (workspace / "SPEC.md").write_text(
        "# SPEC\n## Goal\nShip safely.\n## Success Criteria\n"
        "1. fast gate passes (scripts/verify-fast)\n"
        "## Evidence Rules\nCriterion 1 is proven by scripts/verify-fast.\n",
        encoding="utf-8",
    )
    (workspace / "WORKFLOW.md").write_text(
        "# WORKFLOW\n## Approval Gates\napproval gate on side-effects\n"
        "## Plan-then-execute\nPlan before untrusted reads.\n"
        "## Terminal States\n" + ", ".join(TERMINAL_STATES) + "\n",
        encoding="utf-8",
    )
    (workspace / "TASKS.json").write_text(
        json.dumps(
            {
                "schema": "loop-engineer/tasks@1",
                "tasks": [
                    {
                        "id": "T1",
                        "title": "Run fast gate",
                        "status": "done",
                        "criterion_ref": "1",
                        "verify": "scripts/verify-fast",
                        "depends_on": [],
                        "attempts": 1,
                        "evidence": ".loop/artifacts/verify-T1.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (workspace / "RUNLOG.md").write_text(
        "# RUNLOG\n\n- iter 1: active_task=T1 verify=PASS best_score=1.0\n",
        encoding="utf-8",
    )
    (scripts / "verify-fast").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (scripts / "verify-full").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (scripts / "holdout_gate.py").write_text("# anti-cheat holdout gate\n", encoding="utf-8")
    (loop_dir / "state.json").write_text(
        json.dumps(
            {
                "schema": "loop-engineer/state@1",
                "iteration_id": 1,
                "state": "terminal",
                "plan_version": 1,
                "active_task": "T1",
                "best_score": 1.0,
                "failure_mode": None,
                "pending_approval": None,
                "budget_remaining": {"time": "1m", "cost": "0.01usd"},
                "checkpoint_path": None,
                "terminal_state": "Succeeded",
            }
        ),
        encoding="utf-8",
    )
    (loop_dir / "terminal_state.json").write_text(
        json.dumps(
            {
                "schema": "loop-engineer/terminal@1",
                "state": "Succeeded",
                "iteration_id": 1,
                "criteria_met": {"1": True},
                "evidence": [".loop/artifacts/verify-T1.json"],
                "false_completion": False,
                "reason": "fast gate passed",
                "lessons_ref": None,
            }
        ),
        encoding="utf-8",
    )
    (loop_dir / "manifest.yaml").write_text(
        "schema: loop-engineer/manifest@1\n"
        "loop: valid-loop\n"
        "inputs:\n"
        "  workspace_path: ./\n"
        "outputs:\n"
        "  current_state: .loop/state.json\n"
        "  terminal_state: .loop/terminal_state.json\n"
        "  task_queue: TASKS.json\n"
        "policies:\n"
        "  plan_then_execute: true\n"
        "  verifier_gaming: hard_terminate_as_security_failure\n"
        "terminal_states:\n"
        + "\n".join(f"  - {s}" for s in TERMINAL_STATES)
        + "\n",
        encoding="utf-8",
    )
    return workspace


def _run_loop_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "loop", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def test_loop_doctor_accepts_valid_contract_from_workspace_root(tmp_path):
    workspace = _write_valid_loop(tmp_path)

    result = _run_loop_cli("doctor", str(workspace))

    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["paths"]["workspace"] == str(workspace)
    assert report["schemas_checked"] >= [
        "loop-engineer/manifest@1",
        "loop-engineer/state@1",
        "loop-engineer/tasks@1",
        "loop-engineer/terminal@1",
    ]
    # schemas_checked names the schemas; validation_mode reports what actually
    # ran — real jsonschema validation when the library is present, the stdlib
    # structural hand checks otherwise. It must never imply validation that did
    # not happen.
    assert report["validation_mode"] in {"jsonschema", "structural-fallback"}


def test_loop_doctor_resolves_same_contract_from_dot_loop_dir(tmp_path):
    workspace = _write_valid_loop(tmp_path)

    result = _run_loop_cli("doctor", str(workspace / ".loop"))

    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["paths"]["runlog"] == str(workspace / "RUNLOG.md")
    assert report["paths"]["state"] == str(workspace / ".loop" / "state.json")


def test_read_manifest_returns_dict_on_malformed_yaml(tmp_path):
    # F1 (root cause): read_manifest feeds inspect_loop, validate_contract, and
    # doctor_report. Its yaml.safe_load was the one read path without the guard
    # every JSON read already has — a malformed manifest in an untrusted loop dir
    # crashed with a YAMLError instead of returning an (empty) report.
    from loop.contract import read_manifest

    bad = tmp_path / "manifest.yaml"
    bad.write_text(
        "schema: loop-engineer/manifest@1\n"
        "policies:\n"
        "  - id: ci-change      ; trigger: edit .github/workflows/*\n",
        encoding="utf-8",
    )

    result = read_manifest(bad)  # must not raise

    assert isinstance(result, dict)


def test_f6_fallback_yaml_keeps_hash_inside_quotes():
    # F6: the fallback parser stripped everything after the first '#' before it
    # ever looked at quotes, so goal: "reach #1" truncated to '"reach'. A '#'
    # inside a quoted scalar is data, not a comment.
    from loop.contract import _fallback_yaml

    assert _fallback_yaml('goal: "reach #1"\n') == {"goal": "reach #1"}
    assert _fallback_yaml("goal: 'reach #1'\n") == {"goal": "reach #1"}
    # A genuine unquoted trailing comment is still stripped.
    assert _fallback_yaml("goal: ship  # real comment\n") == {"goal": "ship"}
    # And a nested (one-level) mapping value keeps its quoted '#' too.
    assert _fallback_yaml('policies:\n  note: "see #3"\n') == {"policies": {"note": "see #3"}}


def test_f6_both_manifest_parse_paths_agree_on_quoted_hash(tmp_path, monkeypatch):
    # F6: PyYAML and the fallback subset parser must agree that a '#' inside a
    # quoted value survives. Pin both paths — the real library, and the fallback
    # forced by hiding the yaml module (import yaml -> ImportError -> fallback).
    import sys

    from loop.contract import read_manifest

    manifest = tmp_path / "manifest.yaml"
    manifest.write_text('schema: loop-engineer/manifest@1\ngoal: "reach #1"\n', encoding="utf-8")

    yaml = pytest.importorskip("yaml")
    real = read_manifest(manifest)
    assert real["goal"] == "reach #1"

    monkeypatch.setitem(sys.modules, "yaml", None)  # import yaml now raises ImportError
    fallback = read_manifest(manifest)
    assert fallback["goal"] == "reach #1"
    assert fallback["goal"] == real["goal"]


def test_doctor_does_not_crash_on_malformed_manifest(tmp_path):
    # F1 (blast radius): the doctor CLI validates a foreign contract via the same
    # read_manifest; a malformed manifest must produce an actionable report, not a
    # traceback.
    workspace = _write_valid_loop(tmp_path)
    (workspace / ".loop" / "manifest.yaml").write_text(
        "schema: loop-engineer/manifest@1\n"
        "policies:\n"
        "  - id: ci-change      ; trigger: edit .github/workflows/*\n",
        encoding="utf-8",
    )

    result = _run_loop_cli("doctor", str(workspace))

    assert result.returncode in (0, 1), result.stderr + result.stdout
    report = json.loads(result.stdout)  # raises if it crashed
    assert "ok" in report


def _terminal_issues(data):
    from loop.contract import _validate_terminal

    issues: list[dict] = []
    _validate_terminal(data, pathlib.Path("terminal_state.json"), issues)
    return issues


def test_g1_contradictory_succeeded_terminal_emits_issue():
    # G1: a Succeeded terminal is the loop's strongest claim. The validator must
    # reject the two ways it can outrun its evidence — a self-declared false
    # completion, or no criterion actually met — instead of validating clean.
    from loop.contract import _validate_terminal  # noqa: F401

    base = {"schema": "loop-engineer/terminal@1", "state": "Succeeded", "evidence": []}

    false_completion_issues = _terminal_issues(
        {**base, "criteria_met": {"1": True}, "false_completion": True}
    )
    assert any(i["code"] == "contradictory_terminal" for i in false_completion_issues)
    assert any(
        "false_completion" in i["message"]
        for i in false_completion_issues
        if i["code"] == "contradictory_terminal"
    )

    empty_criteria_issues = _terminal_issues(
        {**base, "criteria_met": {}, "false_completion": False}
    )
    assert any(i["code"] == "contradictory_terminal" for i in empty_criteria_issues)
    assert any(
        "criteria_met" in i["message"]
        for i in empty_criteria_issues
        if i["code"] == "contradictory_terminal"
    )

    all_false_issues = _terminal_issues(
        {**base, "criteria_met": {"1": False, "2": False}, "false_completion": False}
    )
    assert any(i["code"] == "contradictory_terminal" for i in all_false_issues)

    happy_issues = _terminal_issues(
        {**base, "criteria_met": {"1": True}, "false_completion": False, "evidence": ["e.json"]}
    )
    assert not any(i["code"] == "contradictory_terminal" for i in happy_issues)
    assert happy_issues == []


def _write_valid_succeeded_contract(root: pathlib.Path, evidence) -> pathlib.Path:
    """A doctor-clean scaffold mutated into a Succeeded terminal with the given
    evidence list. Used to pin F1 end-to-end (both validation modes)."""
    from loop.scaffold import scaffold

    target = root / "loop"
    scaffold(target)
    state_path = target / ".loop" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["terminal_state"] = "Succeeded"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    (target / ".loop" / "terminal_state.json").write_text(
        json.dumps(
            {
                "schema": "loop-engineer/terminal@1",
                "project": "loop",
                "state": "Succeeded",
                "iteration_id": 1,
                "criteria_met": {"c1": True},
                "evidence": evidence,
                "false_completion": False,
                "terminated_at": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    return target


def test_g1_empty_evidence_succeeded_terminal_is_flagged_unit():
    # F1: a Succeeded terminal with no evidence outruns its own claim exactly like
    # false_completion=true or an unmet criterion. _validate_terminal runs the
    # cross-field check in BOTH validation modes, so this unit assertion covers both.
    empty_evidence_issues = _terminal_issues(
        {
            "schema": "loop-engineer/terminal@1",
            "state": "Succeeded",
            "criteria_met": {"c1": True},
            "false_completion": False,
            "evidence": [],
        }
    )
    assert any(i["code"] == "contradictory_terminal" for i in empty_evidence_issues)
    assert any(
        "evidence" in i["message"]
        for i in empty_evidence_issues
        if i["code"] == "contradictory_terminal"
    )


def test_f1_empty_evidence_succeeded_fails_doctor_end_to_end(tmp_path):
    # F1 repro: a schema-valid contract whose terminal declares Succeeded with an
    # empty evidence[] must NOT pass doctor. Runs under whichever validation mode
    # is installed; the two suite invocations exercise both.
    from loop.contract import doctor_report

    target = _write_valid_succeeded_contract(tmp_path, evidence=[])
    report = doctor_report(target)
    assert report["ok"] is False, report["issues"]
    assert any(
        i["code"] == "contradictory_terminal" and "evidence" in i["message"]
        for i in report["issues"]
    )


def test_f1_non_empty_evidence_succeeded_still_passes_doctor(tmp_path):
    # The fix must not over-fire: a Succeeded terminal that DOES carry evidence
    # stays doctor-clean.
    from loop.contract import doctor_report

    target = _write_valid_succeeded_contract(tmp_path, evidence=[".loop/artifacts/verify-T1.json"])
    report = doctor_report(target)
    assert report["ok"] is True, report["issues"]


def test_jsonschema_mode_rejects_schema_violating_artifact(tmp_path):
    # M1-SCHEMAS: when jsonschema is installed the doctor must run REAL schema
    # validation, not just the weaker structural hand checks — a state.json
    # missing a schema-required field must be rejected.
    pytest.importorskip("jsonschema")
    from loop.contract import doctor_report

    workspace = _write_valid_loop(tmp_path)
    clean = doctor_report(str(workspace))
    assert clean["validation_mode"] == "jsonschema"
    assert clean["ok"] is True, clean["issues"]

    state_path = workspace / ".loop" / "state.json"
    data = json.loads(state_path.read_text(encoding="utf-8"))
    del data["iteration_id"]
    state_path.write_text(json.dumps(data), encoding="utf-8")

    report = doctor_report(str(workspace))
    assert report["validation_mode"] == "jsonschema"
    assert report["ok"] is False
    assert any(issue["code"] == "schema_violation" for issue in report["issues"])


def test_jsonschema_mode_enforces_every_schema_required_field(tmp_path):
    # Field-agreement: for every required field the schemas/*.json files declare,
    # jsonschema-mode doctor must reject an artifact that omits it. This is the
    # honesty guarantee behind validation_mode == "jsonschema".
    pytest.importorskip("jsonschema")
    yaml = pytest.importorskip("yaml")
    from loop.contract import _load_schema, doctor_report

    locators = {
        "state": lambda ws: ws / ".loop" / "state.json",
        "tasks": lambda ws: ws / "TASKS.json",
        "terminal": lambda ws: ws / ".loop" / "terminal_state.json",
        "manifest": lambda ws: ws / ".loop" / "manifest.yaml",
    }

    case = 0
    for name, locate in locators.items():
        for field in _load_schema(name).get("required", []):
            case += 1
            workspace = _write_valid_loop(tmp_path / f"case_{case}")
            path = locate(workspace)
            if path.suffix == ".yaml":
                doc = yaml.safe_load(path.read_text(encoding="utf-8"))
                doc.pop(field, None)
                path.write_text(yaml.safe_dump(doc), encoding="utf-8")
            else:
                doc = json.loads(path.read_text(encoding="utf-8"))
                doc.pop(field, None)
                path.write_text(json.dumps(doc), encoding="utf-8")
            report = doctor_report(str(workspace))
            assert report["validation_mode"] == "jsonschema"
            assert report["ok"] is False, f"{name} missing {field!r} should fail"
            assert any(i["code"] == "schema_violation" for i in report["issues"]), (name, field)

    task_item_required = _load_schema("tasks")["properties"]["tasks"]["items"]["required"]
    for field in task_item_required:
        case += 1
        workspace = _write_valid_loop(tmp_path / f"case_{case}")
        path = workspace / "TASKS.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["tasks"][0].pop(field, None)
        path.write_text(json.dumps(doc), encoding="utf-8")
        report = doctor_report(str(workspace))
        assert report["validation_mode"] == "jsonschema"
        assert report["ok"] is False, f"task missing {field!r} should fail"
        assert any(i["code"] == "schema_violation" for i in report["issues"]), field


def _scaffold(tmp_path: pathlib.Path, name: str) -> pathlib.Path:
    from loop.scaffold import scaffold

    target = tmp_path / name
    scaffold(target)
    return target


def _set_task_verify(target: pathlib.Path, value) -> None:
    tasks_path = target / "TASKS.json"
    tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
    tasks["tasks"][0]["verify"] = value
    tasks_path.write_text(json.dumps(tasks), encoding="utf-8")


def test_f2_no_verify_surface_is_flagged(tmp_path):
    # F2(a): a contract with no verify-* script AND no task declaring a verify
    # command has no verification surface at all — doctor must say so.
    from loop.contract import doctor_report

    target = _scaffold(tmp_path, "no-surface")
    (target / "scripts" / "verify-fast").unlink()
    (target / "scripts" / "verify-full").unlink()
    _set_task_verify(target, "")

    report = doctor_report(target)
    assert report["ok"] is False
    assert any(i["code"] == "missing_verify_surface" for i in report["issues"]), report["issues"]


def test_f2_scaffold_with_deleted_verify_scripts_is_flagged(tmp_path):
    # F2(b) repro: deleting scripts/verify-* from a scaffold left doctor green
    # even though every task still points at the now-missing script.
    from loop.contract import doctor_report

    target = _scaffold(tmp_path, "deleted-scripts")
    (target / "scripts" / "verify-fast").unlink()
    (target / "scripts" / "verify-full").unlink()

    report = doctor_report(target)
    assert report["ok"] is False
    assert any(i["code"] == "unresolved_task_verify" for i in report["issues"]), report["issues"]


def test_f2_unresolvable_path_shaped_task_verify_is_flagged(tmp_path):
    # F2(b): a path-shaped task.verify that does not resolve relative to the
    # workspace is flagged, even when the verify-* scripts exist.
    from loop.contract import doctor_report

    target = _scaffold(tmp_path, "bad-path")
    _set_task_verify(target, "scripts/does-not-exist")

    report = doctor_report(target)
    assert report["ok"] is False
    assert any(i["code"] == "unresolved_task_verify" for i in report["issues"]), report["issues"]
    assert not any(i["code"] == "missing_verify_surface" for i in report["issues"])


def test_f2_plain_command_task_verify_is_not_path_checked(tmp_path):
    # F2: a plain command (first token has no "/") is not a path and is not
    # existence-checked — "pytest -q" must stay clean.
    from loop.contract import doctor_report

    target = _scaffold(tmp_path, "plain-cmd")
    _set_task_verify(target, "pytest -q")

    report = doctor_report(target)
    assert report["ok"] is True, report["issues"]


def test_f2_fresh_scaffold_stays_clean(tmp_path):
    # F2 must not over-fire: a fresh scaffold has verify scripts and a resolving
    # task verify, so it stays doctor-clean.
    from loop.contract import doctor_report

    target = _scaffold(tmp_path, "fresh")
    report = doctor_report(target)
    assert report["ok"] is True, report["issues"]


def test_f7_file_target_resolves_to_owning_workspace(tmp_path):
    # F7: a FILE target (loop doctor .loop/state.json or TASKS.json) resolved the
    # workspace to the file itself, so every path underneath was garbage. A file
    # target must resolve from its parent to the SAME paths as the dir target.
    from loop.paths import resolve_loop_paths

    target = _scaffold(tmp_path, "file-target")
    from_dir = resolve_loop_paths(target)

    from_state_file = resolve_loop_paths(target / ".loop" / "state.json")
    assert from_state_file.workspace == from_dir.workspace
    assert from_state_file.state == from_dir.state
    assert from_state_file.loop_dir == from_dir.loop_dir

    from_tasks_file = resolve_loop_paths(target / "TASKS.json")
    assert from_tasks_file.workspace == from_dir.workspace
    assert from_tasks_file.tasks == from_dir.tasks


def test_f7_doctor_on_file_target_matches_dir_target(tmp_path):
    # F7 at the CLI level: `doctor <ws>/.loop/state.json` must produce the same
    # report as `doctor <ws>` instead of a wall of garbage-path issues.
    target = _scaffold(tmp_path, "file-cli")

    from_dir = _run_loop_cli("doctor", str(target))
    from_file = _run_loop_cli("doctor", str(target / ".loop" / "state.json"))

    assert from_dir.returncode == 0, from_dir.stderr + from_dir.stdout
    assert from_file.returncode == 0, from_file.stderr + from_file.stdout
    dir_report = json.loads(from_dir.stdout)
    file_report = json.loads(from_file.stdout)
    assert file_report["ok"] is True
    assert file_report["paths"] == dir_report["paths"]


def test_loop_doctor_flags_stub_verify_scripts(tmp_path):
    workspace = _write_valid_loop(tmp_path)
    (workspace / "scripts" / "verify-fast").write_text(
        "#!/bin/sh\necho '[verify-fast] STUB: replace with real command'\nexit 0\n",
        encoding="utf-8",
    )

    result = _run_loop_cli("doctor", str(workspace))

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["ok"] is False
    assert any(issue["code"] == "stub_verify_script" for issue in report["issues"])
