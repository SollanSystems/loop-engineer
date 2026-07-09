"""ST4 acceptance: the 2nd runnable example is doctor-clean and gate-backed,
and showcases the repair-record pillar — `loop metrics` derives a non-null RP
from a same-task red->green anchored repair. run-example re-derives the
committed gate verdict live from a foreign cwd."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_EXAMPLE = _REPO / "examples" / "flaky-test-triage"


def _cli(cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", "-m", "loop", cmd, str(_EXAMPLE)],
        cwd=_REPO, capture_output=True, text=True,
    )


def test_doctor_clean():
    proc = _cli("doctor")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["ok"] is True


def test_metrics_derives_non_null_rp_and_clean_fcr():
    proc = _cli("metrics")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    card = json.loads(proc.stdout)
    assert card["repair_productivity"] == 1.0
    assert card["repair_passes"] == 1
    assert card["productive_repairs"] == 1
    assert card["false_completion_rate"] == 0.0
    assert card["evidence_backed"] is True
    prov = card["provenance"]
    assert prov["fcr_methods_agree"] is True
    assert prov["rejected_records"] == []
    assert prov["unanchored_records"] == []
    assert prov["unmatched_verify"] == []


def test_run_example_reproduces_the_gate_verdict_from_foreign_cwd(tmp_path):
    proc = subprocess.run(
        ["bash", str(_EXAMPLE / "scripts" / "run-example")],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "BACKED by an independent" in proc.stdout
    verdict = json.loads((_EXAMPLE / ".loop" / "artifacts" / "holdout-verdict.json").read_text())
    assert verdict["verdict"] == "Succeeded"
    assert verdict["false_completion"] is False
