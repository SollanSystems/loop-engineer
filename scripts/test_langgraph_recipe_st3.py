"""ST3 acceptance for the LangGraph recipe: the certify node routes through
EngineOutcome + to_terminal_state (gate + anticheat wired), the emitted
contract passes doctor, `loop metrics` scores the run clean (closes the
FCR-1.0 follow-up), and the false-completion invariant holds under sabotage.
Env-guarded: langgraph is a dev dependency of the example only."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("langgraph")

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "langgraph-emit" / "graph_example.py"


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


def test_happy_path_is_doctor_clean_and_metrics_clean(tmp_path):
    ws = tmp_path / "graph-run"
    proc = _run_example(ws)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    doctored = _cli("doctor", ws)
    assert doctored.returncode == 0, doctored.stdout
    assert json.loads(doctored.stdout)["ok"] is True

    terminal = json.loads((ws / ".loop" / "terminal_state.json").read_text())
    assert terminal["state"] == "Succeeded"
    assert terminal["false_completion"] is False
    assert terminal["evidence"]

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
    ws = tmp_path / "graph-run-sabotaged"
    proc = _run_example(ws, "--sabotage-holdout")
    # the recipe exits non-zero on a non-Succeeded terminal, but still emits it
    terminal = json.loads((ws / ".loop" / "terminal_state.json").read_text())
    assert terminal["state"] == "FailedUnverifiable"
    assert terminal["state"] != "Succeeded"
    assert terminal["false_completion"] is True, (terminal, proc.stdout, proc.stderr)

    doctored = _cli("doctor", ws)
    assert json.loads(doctored.stdout)["ok"] is True  # an honest failure is a valid contract
