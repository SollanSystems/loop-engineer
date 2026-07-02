"""Regression tests for the deterministic `scaffold` command (Cluster E).

The scaffold command must emit a repo-OS contract that passes the product's own
doctor unedited — a stranger's first `python -m loop scaffold` then `doctor`
must be green, or the credibility slice fails at the front door.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_scaffolded_contract_passes_doctor_unedited(tmp_path):
    from loop.contract import validate_contract
    from loop.scaffold import scaffold

    target = tmp_path / "my-first-loop"
    scaffold(target)

    report = validate_contract(target)

    assert report["ok"] is True, report["issues"]


def test_scaffold_writes_standard_layout_and_skips_terminal(tmp_path):
    from loop.scaffold import scaffold

    target = tmp_path / "layout-loop"
    scaffold(target)

    for rel in (
        "AGENTS.md",
        "SPEC.md",
        "WORKFLOW.md",
        "TASKS.json",
        "RUNLOG.md",
        ".loop/manifest.yaml",
        ".loop/state.json",
        "scripts/verify-fast",
        "scripts/verify-full",
    ):
        assert (target / rel).is_file(), f"missing scaffolded file {rel}"

    # terminal_state.json is written once, at loop end — never by scaffold.
    assert not (target / ".loop" / "terminal_state.json").exists()

    # Exec bits on the verify scripts.
    import os

    for rel in ("scripts/verify-fast", "scripts/verify-full"):
        mode = (target / rel).stat().st_mode
        assert mode & 0o111, f"{rel} is not executable"


def test_scaffolded_json_is_valid_and_placeholder_free(tmp_path):
    from loop.scaffold import scaffold

    target = tmp_path / "clean-loop"
    scaffold(target)

    state = json.loads((target / ".loop" / "state.json").read_text(encoding="utf-8"))
    tasks = json.loads((target / "TASKS.json").read_text(encoding="utf-8"))

    assert state["schema"] == "loop-engineer/state@1"
    assert state["terminal_state"] is None
    assert state["project"] == "clean-loop"
    assert tasks["schema"] == "loop-engineer/tasks@1"

    for rel in (".loop/state.json", "TASKS.json"):
        assert "{{" not in (target / rel).read_text(encoding="utf-8")


def test_scaffold_refuses_to_overwrite_existing_contract(tmp_path):
    from loop.scaffold import scaffold

    target = tmp_path / "existing-loop"
    scaffold(target)

    with pytest.raises(FileExistsError):
        scaffold(target)


def test_missing_terminal_is_in_flight_when_state_terminal_is_null(tmp_path):
    from loop.contract import validate_contract
    from loop.scaffold import scaffold

    target = tmp_path / "inflight-loop"
    scaffold(target)

    # Sanity: the fresh scaffold has no terminal file and state.terminal_state null.
    assert not (target / ".loop" / "terminal_state.json").exists()

    report = validate_contract(target)

    assert report["ok"] is True, report["issues"]
    assert not any(
        issue["code"] == "missing_file" and "terminal" in issue["message"]
        for issue in report["issues"]
    )


def test_missing_terminal_is_an_issue_when_state_declares_a_terminal(tmp_path):
    from loop.contract import validate_contract
    from loop.scaffold import scaffold

    target = tmp_path / "terminated-loop"
    scaffold(target)

    state_path = target / ".loop" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["terminal_state"] = "Succeeded"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    report = validate_contract(target)

    assert report["ok"] is False
    assert any(
        issue["code"] == "missing_file" and "terminal" in issue["message"]
        for issue in report["issues"]
    )


def test_scaffold_cli_subcommand(tmp_path):
    target = tmp_path / "cli-loop"
    result = subprocess.run(
        [sys.executable, "-m", "loop", "scaffold", str(target)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (target / ".loop" / "state.json").is_file()
