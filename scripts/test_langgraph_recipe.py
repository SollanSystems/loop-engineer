"""B1 acceptance: the LangGraph recipe example runs end-to-end and its emitted
contract passes doctor. Env-guarded: langgraph is a dev dependency of the
example only — the package stays zero-dependency."""

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


def test_recipe_runs_end_to_end_and_passes_doctor(tmp_path):
    workspace = tmp_path / "graph-run"
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
    proc = subprocess.run(
        [sys.executable, "-B", str(EXAMPLE), str(workspace)],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    doctored = subprocess.run(
        [sys.executable, "-B", "-m", "loop", "doctor", str(workspace)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert doctored.returncode == 0, doctored.stdout
    assert json.loads(doctored.stdout)["ok"] is True

    terminal = json.loads((workspace / ".loop" / "terminal_state.json").read_text())
    assert terminal["state"] == "Succeeded"
    assert terminal["evidence"], "Succeeded must carry evidence"
