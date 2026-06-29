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
