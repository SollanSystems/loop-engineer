"""Acceptance for the ruflo recipe (issue #38): a host-side supervisor around
ruflo's blocking swarm CLI replaces the swarm's self-report with a real gate.

Deterministic and credential-free: every test replays the committed
``examples/ruflo-gate/fixture/`` tree, so no Node, no ``npx ruflo``, no
``claude`` binary and no model spend are involved. The gate, the projection,
``loop.emit``, ``loop doctor`` and ``loop metrics`` all execute for real —
only the swarm is recorded.

The three traps this pins (all from the live API dossier):

* ruflo exits **0** on Ctrl-C, so ``AbortedByHuman`` must come from the
  supervisor's own signal flag and never be inferred from the exit code;
* ``ruflo verify`` is install-integrity, not a run verdict, so it is never
  wired as the gate;
* ``sparc-gates`` holds the swarm's SELF-asserted verdicts, which the gate
  replaces rather than trusts.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "ruflo-gate" / "swarm_example.py"
FIXTURE = REPO_ROOT / "examples" / "ruflo-gate" / "fixture"
RECIPE_DOC = REPO_ROOT / "docs" / "integrations" / "ruflo.md"


def _load_example():
    spec = importlib.util.spec_from_file_location("ruflo_swarm_example", EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve annotations through sys.modules[cls.__module__]
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_example(workspace: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
    return subprocess.run(
        [sys.executable, "-B", str(EXAMPLE), str(workspace), *args],
        cwd=workspace.parent, env=env, capture_output=True, text=True,
    )


def _cli(cmd: str, workspace: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", "-m", "loop", cmd, str(workspace)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )


def _terminal(workspace: Path) -> dict:
    return json.loads((workspace / ".loop" / "terminal_state.json").read_text(encoding="utf-8"))


def _gate_verdict(workspace: Path) -> dict:
    return json.loads(
        (workspace / ".loop" / "artifacts" / "holdout-verdict.json").read_text(encoding="utf-8")
    )


def test_happy_path_is_doctor_clean_and_metrics_clean(tmp_path):
    ws = tmp_path / "swarm-run"
    proc = _run_example(ws)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    doctored = _cli("doctor", ws)
    assert doctored.returncode == 0, doctored.stdout
    assert json.loads(doctored.stdout)["ok"] is True

    terminal = _terminal(ws)
    assert terminal["state"] == "Succeeded"
    assert terminal["false_completion"] is False
    assert terminal["evidence"]
    # criteria ids come from the swarm's OWN declared acceptanceCriteria
    assert set(terminal["criteria_met"]) == {"AC-1", "AC-2", "AC-3"}
    assert all(terminal["criteria_met"].values())

    metrics = _cli("metrics", ws)
    assert metrics.returncode == 0, metrics.stdout + metrics.stderr
    card = json.loads(metrics.stdout)
    assert card["false_completion_rate"] == 0.0
    assert card["false_completions"] == 0
    assert card["iterations_claiming_success"] >= 1
    assert card["evidence_backed"] is True
    prov = card["provenance"]
    assert prov["unmatched_verify"] == []
    assert prov["unrecognized_outcomes"] == []
    assert prov["fcr_methods_agree"] is True


def test_sabotage_holdout_is_false_completion_never_succeeded(tmp_path):
    ws = tmp_path / "swarm-run-sabotaged"
    proc = _run_example(ws, "--sabotage-holdout")

    terminal = _terminal(ws)
    assert terminal["state"] == "FailedUnverifiable"
    assert terminal["state"] != "Succeeded"
    assert terminal["false_completion"] is True, (terminal, proc.stdout, proc.stderr)

    doctored = _cli("doctor", ws)
    assert json.loads(doctored.stdout)["ok"] is True  # an honest failure is a valid contract


def test_swarm_self_report_stays_green_while_the_gate_refuses(tmp_path):
    """The sparc-gates namespace is the swarm's SELF-asserted verdict. Under
    sabotage it still reads all-pass — and is replaced, not trusted."""
    ws = tmp_path / "swarm-run-self-report"
    _run_example(ws, "--sabotage-holdout")

    example = _load_example()
    export = example.observe(ws)["export"]
    self_report = example.swarm_self_report(export)
    assert self_report["all_gates_pass"] is True
    assert self_report["truth_score"] == 0.97

    assert _terminal(ws)["state"] == "FailedUnverifiable"


def test_interrupt_is_aborted_by_human_despite_exit_code_zero(tmp_path):
    """ruflo's SIGINT path calls process.exit(0), so an interrupted run is
    indistinguishable from success by exit code. The terminal must come from
    the supervisor's own interrupt flag."""
    ws = tmp_path / "swarm-run-interrupted"
    _run_example(ws, "--simulate-interrupt")

    observation = json.loads(
        (ws / ".loop" / "artifacts" / "swarm-observation.json").read_text(encoding="utf-8")
    )
    assert observation["returncode"] == 0  # the trap: ruflo reports success
    assert _gate_verdict(ws)["verdict"] == "Succeeded"  # and the gate is green

    terminal = _terminal(ws)
    assert terminal["state"] == "AbortedByHuman"
    assert terminal["state"] != "Succeeded"


def test_unmapped_declared_criterion_is_spec_gap(tmp_path):
    """An acceptance criterion the swarm declared but no check covers is a
    FailedSpecGap — the failure a self-reporting coordinator hides."""
    ws = tmp_path / "swarm-run-specgap"
    _run_example(ws, "--declare-unmapped-criterion")

    terminal = _terminal(ws)
    assert terminal["state"] == "FailedSpecGap"
    assert terminal["criteria_met"]["AC-4"] is False
    assert json.loads(_cli("doctor", ws).stdout)["ok"] is True


def test_ruflo_verify_is_never_wired_as_the_gate():
    """`ruflo verify` checks the SHA-256/Ed25519 integrity of the INSTALLED
    artifact, not the run. A reader could plausibly mistake it for a verdict."""
    example = _load_example()
    assert "verify" not in example.LIVE_COMMAND
    assert "hive-mind" in example.LIVE_COMMAND and "spawn" in example.LIVE_COMMAND
    assert "install-integrity" in RECIPE_DOC.read_text(encoding="utf-8")


def test_fixture_replay_touches_no_network_tooling(tmp_path):
    """The shipped default replays a recording: the live command is never
    executed, so the recipe needs no Node, no npx and no credentials."""
    ws = tmp_path / "swarm-run-offline"
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT), PATH="")
    proc = subprocess.run(
        [sys.executable, "-B", str(EXAMPLE), str(ws)],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _terminal(ws)["state"] == "Succeeded"


@pytest.mark.skipif(
    not os.environ.get("LOOP_RUFLO_LIVE") or shutil.which("npx") is None,
    reason="live schema-drift alarm: needs npx + network; set LOOP_RUFLO_LIVE=1 to run",
)
def test_live_swarm_status_still_matches_the_recorded_layout(tmp_path):
    """Opt-in drift alarm. Runs the real CLI's cheapest state-writing verbs and
    asserts `.swarm/state.json` still carries the keys the fixture records."""
    example = _load_example()
    ws = tmp_path / "live-swarm"
    ws.mkdir()
    init = subprocess.run(
        ["npx", f"ruflo@{example.RUFLO_VERSION}", "swarm", "init"],
        cwd=ws, capture_output=True, text=True,
    )
    assert init.returncode == 0, init.stdout + init.stderr
    live_state = json.loads((ws / ".swarm" / "state.json").read_text(encoding="utf-8"))
    recorded = json.loads((FIXTURE / ".swarm" / "state.json").read_text(encoding="utf-8"))
    assert set(recorded) <= set(live_state), (recorded, live_state)
