# scripts/test_action_scorecard.py
"""Gate-strictness acceptance for the shipped GitHub Action.

F3 — the composite action must install loop-engineer WITH its schema extras on
both install paths, so `loop doctor` runs real JSON-Schema validation (not the
pure-stdlib structural fallback) and asserts as much. F8 — the scorecard logic
is extracted into scripts/action_scorecard.py so it validates fail-under as an
integer instead of tracebacking on non-numeric input, and the PR comment is
sticky (edit-in-place, never a fresh comment per run)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ACTION_YML = REPO_ROOT / "action.yml"


def _action() -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(ACTION_YML.read_text(encoding="utf-8"))


def _steps() -> list[dict]:
    return _action()["runs"]["steps"]


def _step(name_fragment: str) -> dict:
    for step in _steps():
        if name_fragment.lower() in str(step.get("name", "")).lower():
            return step
    raise AssertionError(f"no action step whose name contains {name_fragment!r}")


def test_action_yml_is_valid_yaml():
    action = _action()
    assert action["runs"]["using"] == "composite"


# --- F3: strict-by-install on the action gate surface ------------------------


def test_both_install_paths_carry_the_schema_extras():
    run = _step("Install loop-engineer")["run"]
    # PyPI-pinned path and the action-checkout path must both request the extras.
    assert 'loop-engineer[schemas,yaml]==' in run, (
        "the versioned PyPI install must request the [schemas,yaml] extras"
    )
    assert '}}[schemas,yaml]' in run or 'github.action_path }}[schemas,yaml]' in run, (
        "the action-checkout install must request the [schemas,yaml] extras"
    )


def test_bare_install_without_extras_is_gone():
    run = _step("Install loop-engineer")["run"]
    assert '"loop-engineer==' not in run, "bare (extras-free) PyPI install path lingers"
    # the action-path install must not appear without the extras suffix
    assert '"${{ github.action_path }}"' not in run, (
        "bare (extras-free) action-checkout install path lingers"
    )


def test_doctor_step_asserts_jsonschema_validation_mode():
    run = _step("loop doctor")["run"]
    assert "validation_mode" in run, (
        "the doctor step should assert the report's validation_mode is jsonschema "
        "so a packaging regression that drops the extras fails loudly"
    )
    assert "jsonschema" in run
