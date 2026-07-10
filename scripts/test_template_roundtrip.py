"""ST2 acceptance #7/#9: every shipped ``templates/*`` artifact, filled with
schema-valid values and scaffolded into a real contract layout, passes
``validate_contract`` clean — in BOTH validation modes.

This is the DG-drift guard: if a template, a schema, or the validator drifts out
of agreement (a placeholder the map can't fill, a fill value the schema rejects,
a validator rule the templates violate), one of these tests goes red. The class
cannot silently return.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loop._resources import templates_dir  # noqa: E402
from loop.contract import _validation_mode, validate_contract  # noqa: E402

_PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")


def _fill_values() -> dict[str, str]:
    """A schema-valid fill for every ``{{PLACEHOLDER}}`` the templates declare.

    Values that land in an unquoted JSON/YAML slot (integers, booleans, null,
    canonical enums) are bare tokens; everything else is a plain string. These
    are drawn from the published schemas — plan_version/iteration_id integers,
    the terminal state from the canonical 7, task status from its enum — so the
    round trip proves the SHIPPED templates + schemas + validator agree.
    """

    return {
        # --- state.json / manifest / tasks / terminal: schema-typed slots ---
        "PROJECT_NAME": "roundtrip-fixture",
        "LOOP_NAME": "roundtrip-fixture",
        "ITERATION_ID": "1",          # quoted in state (string), bare in terminal (int)
        "PLAN_VERSION": "1",          # integer
        "ACTIVE_TASK_ID": "T1",
        "STATE": "running",
        "BEST_SCORE": "null",         # number | null
        "FAILURE_MODE": "",
        "PENDING_APPROVAL": "null",   # object | null
        "TIME_REMAINING": "30m",
        "COST_REMAINING": "1.00usd",
        "CHECKPOINT_PATH": "",
        "GOAL_DESCRIPTION": "prove the template round trip validates",
        "CRITERION_1": "the fast gate passes",
        "CRITERION_2": "the full gate passes",
        "CRITERION_3": "the safety gate passes",
        "CONSTRAINT_1": "read-only workspace",
        "CONSTRAINT_2": "no network",
        "WORKSPACE_PATH": ".",
        "ALLOWED_TOOLS": "Read",      # -> YAML list [Read]
        "ALLOWED_TOOL_1": "Read",     # -> JSON string
        "RISK_PROFILE": "low",
        "TIME_BUDGET": "1h",
        "COST_BUDGET": "5.00usd",
        "APPROVAL_POLICY": "on_side_effects",
        "REPAIR_ATTEMPTS": "0",       # integer
        "REPAIR_CAP": "2",            # integer
        "LAST_VERIFY_CMD": "scripts/verify-fast",
        "LAST_VERIFY_OUTCOME": "PASS",
        "LAST_SCORE": "null",         # number | null
        "EVIDENCE_PATH": ".loop/artifacts/",
        "SHORT_TERM_SUMMARY": "in flight",
        "LESSONS_PATH": ".loop/memory/lessons.md",
        "PERMISSION_1": "read-only",
        "APPROVAL_GATE_1": "on_side_effects",
        "PLAN_THEN_EXECUTE": "true",  # boolean
        "TASK_ID": "T1",
        "TASK_TITLE": "run the fast gate",
        "TASK_STATUS": "pending",     # enum member
        "TASK_CRITERION_REF": "1",
        "TASK_VERIFY": "scripts/verify-fast",
        "CREATED_AT": "2026-06-30T00:00:00Z",
        "UPDATED_AT": "2026-06-30T00:00:00Z",
        # --- terminal_state.json: schema-typed slots ---
        "TERMINAL_STATE": "Succeeded",   # canonical 7
        "TERMINATED_AT": "2026-06-30T01:00:00Z",
        "CRITERION_REF": "1",
        "CRITERION_STATUS": "true",      # boolean; >=1 true for a Succeeded terminal
        "ARTIFACT_PATH": ".loop/artifacts/verify-T1.json",
        "FALSE_COMPLETION": "false",     # boolean
        "TERMINAL_REASON": "fast gate passed with evidence",
        # RUNLOG.md seeds a reference-only preamble that declares only
        # {{PROJECT_NAME}}, so it needs no per-iteration prose fill.
        # --- SPEC / WORKFLOW / AGENTS / EVALS prose ---
        "NON_GOAL_1": "no production writes",
        "NON_GOAL_2": "no schema changes",
        "EVIDENCE_1": ".loop/artifacts/verify-T1.json",
        "EVIDENCE_2": ".loop/artifacts/verify-T2.json",
        "VERIFY_CMD_1": "scripts/verify-fast",
        "VERIFY_CMD_2": "scripts/verify-full",
        "NETWORK_POLICY": "off",
        "RUBRIC_TARGET": "9",
        "W_CORRECTNESS": "0.2",
        "W_COMPLETENESS": "0.15",
        "W_VERIFICATION": "0.15",
        "W_SAFETY": "0.15",
        "W_REPAIR": "0.1",
        "W_FC_RESISTANCE": "0.1",
        "W_BREVITY": "0.05",
        "W_EFFICIENCY": "0.05",
        "W_LOOP_BEHAVIOR": "0.05",
        "W_FLYWHEEL": "0.05",
        # literal reference to "{{PLACEHOLDER}}" in the manifest header comment
        "PLACEHOLDER": "example",
    }


def _fill_all_templates(mapping: dict[str, str]) -> dict[str, str]:
    """Fill every placeholder in every ``templates/*.tmpl`` file.

    Asserts (a) the map has a value for every token a template declares and
    (b) no ``{{`` survives the fill — the two ways a template could drift past
    an incomplete map. Returns ``{template_name: filled_text}``.
    """

    filled: dict[str, str] = {}
    tmpl_files = sorted(templates_dir().glob("*.tmpl"))
    assert tmpl_files, "no *.tmpl files found under templates/"
    for tmpl in tmpl_files:
        text = tmpl.read_text(encoding="utf-8")

        def repl(match: re.Match[str], _name: str = tmpl.name) -> str:
            token = match.group(0)[2:-2]
            assert token in mapping, f"{_name}: no fill value for {{{{{token}}}}}"
            return mapping[token]

        out = _PLACEHOLDER_RE.sub(repl, text)
        assert "{{" not in out, f"{tmpl.name}: unfilled placeholder remains:\n{out}"
        filled[tmpl.name] = out
    return filled


def _scaffold(root: Path, terminated: bool) -> Path:
    """Write a filled contract into ``root`` in the layout resolve_loop_paths wants.

    In-flight: state.terminal_state stays null and no terminal_state.json exists.
    Terminated: state.terminal_state becomes ``Succeeded`` and a matching, filled
    terminal_state.json is written (the B1 pair).
    """

    filled = _fill_all_templates(_fill_values())

    workspace = root
    loop_dir = workspace / ".loop"
    scripts = workspace / "scripts"
    loop_dir.mkdir(parents=True)
    scripts.mkdir()

    (workspace / "SPEC.md").write_text(filled["SPEC.md.tmpl"], encoding="utf-8")
    (workspace / "WORKFLOW.md").write_text(filled["WORKFLOW.md.tmpl"], encoding="utf-8")
    (workspace / "AGENTS.md").write_text(filled["AGENTS.md.tmpl"], encoding="utf-8")
    (workspace / "TASKS.json").write_text(filled["TASKS.json.tmpl"], encoding="utf-8")
    (workspace / "RUNLOG.md").write_text(filled["RUNLOG.md.tmpl"], encoding="utf-8")
    (workspace / "EVALS-rubric.md").write_text(filled["EVALS-rubric.md.tmpl"], encoding="utf-8")
    (loop_dir / "manifest.yaml").write_text(filled["manifest.yaml.tmpl"], encoding="utf-8")

    # Real, non-stub verify scripts (copied verbatim from the shipped templates,
    # which ship without the stub markers) so the verify surface resolves honestly.
    for src, dest in (("verify-fast.sh", "verify-fast"), ("verify-full.sh", "verify-full")):
        (scripts / dest).write_text(
            (templates_dir() / src).read_text(encoding="utf-8"), encoding="utf-8"
        )

    state = json.loads(filled["state.json.tmpl"])
    if terminated:
        state["terminal_state"] = "Succeeded"
        (loop_dir / "terminal_state.json").write_text(
            filled["terminal_state.json.tmpl"], encoding="utf-8"
        )
    (loop_dir / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

    return workspace


def _assert_lifecycle(report: dict, expected: str) -> None:
    """Assert the ratified lifecycle rule."""

    assert report["lifecycle"] == expected


# (iteration_id "1", no terminal) -> running; (terminal Succeeded) -> terminated:Succeeded
_CASES = [
    pytest.param(False, "running", id="in-flight"),
    pytest.param(True, "terminated:Succeeded", id="terminated"),
]


def test_every_template_fills_with_no_placeholder_remaining():
    # The core DG-drift guard: a template placeholder with no schema-valid fill
    # (or a new placeholder nobody mapped) fails here, loudly, by name.
    filled = _fill_all_templates(_fill_values())
    for name, text in filled.items():
        assert "{{" not in text, name


@pytest.mark.parametrize("terminated,expected_lifecycle", _CASES)
def test_roundtrip_validates_clean_jsonschema_mode(tmp_path, terminated, expected_lifecycle):
    pytest.importorskip("jsonschema")
    workspace = _scaffold(tmp_path / "ws", terminated)

    report = validate_contract(workspace)

    assert report["validation_mode"] == "jsonschema"
    assert report["ok"] is True, report["issues"]
    assert report["issues"] == [], report["issues"]
    _assert_lifecycle(report, expected_lifecycle)


@pytest.mark.parametrize("terminated,expected_lifecycle", _CASES)
def test_roundtrip_validates_clean_structural_fallback_mode(
    tmp_path, monkeypatch, terminated, expected_lifecycle
):
    # Force structural-fallback by hiding jsonschema (import jsonschema -> None in
    # sys.modules raises ImportError), mirroring the yaml-hiding pattern in
    # test_loop_contract_core.py. This proves the stdlib hand checks agree with
    # the shipped templates + schemas independently of the jsonschema library.
    monkeypatch.setitem(sys.modules, "jsonschema", None)
    assert _validation_mode() == "structural-fallback"

    workspace = _scaffold(tmp_path / "ws", terminated)

    report = validate_contract(workspace)

    assert report["validation_mode"] == "structural-fallback"
    assert report["ok"] is True, report["issues"]
    assert report["issues"] == [], report["issues"]
    _assert_lifecycle(report, expected_lifecycle)
