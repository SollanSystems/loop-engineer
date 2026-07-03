"""CLI contract for `python3 -m loop metrics` (Rider A) + the editable-install
console-script / repo-relative scripts resolution (Rider B / QW8). Runs the real
entry point as a subprocess so exit codes and STDOUT/STDERR match what a user sees.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "loop", *args], cwd=ROOT, text=True, capture_output=True
    )


# --- Rider A: metrics subcommand ---------------------------------------------


def test_metrics_emits_scorecard_for_flagship_example():
    result = _run("metrics", "examples/coverage-repair")
    assert result.returncode == 0, result.stderr
    scorecard = json.loads(result.stdout)
    assert scorecard["schema"] == "loop-engineer/metrics@1"
    assert scorecard["evidence_backed"] is True
    assert scorecard["false_completion_rate"] == 0.0
    assert scorecard["repair_productivity"] == 1.0
    assert "provenance" in scorecard


def test_metrics_missing_target_prints_usage_and_exits_nonzero():
    result = _run("metrics")
    assert result.returncode != 0
    assert "usage" in result.stderr.lower()
    assert "Traceback" not in result.stderr
    assert result.stdout.strip() == ""


def test_metrics_nonexistent_target_gives_distinct_error(tmp_path):
    missing = tmp_path / "nope"
    result = _run("metrics", str(missing))
    assert result.returncode != 0
    assert "does not exist" in result.stderr.lower()
    assert str(missing) in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout.strip() == ""


def test_metrics_help_is_listed():
    out = _run("--help").stdout
    assert "metrics" in out
    assert "--baseline" in out


def test_metrics_baseline_refuses_non_evidence_backed_and_writes_nothing(tmp_path):
    # A bare loop with a success claim but no gate is not evidence_backed → refuse.
    ws = tmp_path / "ws"
    (ws / ".loop").mkdir(parents=True)
    (ws / "RUNLOG.md").write_text(
        "## Iteration 1 — t\n### Outcome\n`task_passed`\n", encoding="utf-8"
    )
    baseline_path = ROOT / "docs" / "metrics-baseline.json"
    before = baseline_path.read_bytes() if baseline_path.exists() else None

    result = _run("metrics", "--baseline", str(ws))

    assert result.returncode != 0
    assert "refused" in result.stderr.lower()
    # The committed baseline (if any) is untouched by a refused run.
    after = baseline_path.read_bytes() if baseline_path.exists() else None
    assert after == before


# --- Rider B: editable-install console script + repo-relative scripts (QW8) ---


def test_pyproject_declares_loop_console_script():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r"(?m)^\[project\.scripts\]", text), "missing [project.scripts]"
    assert re.search(r'(?m)^loop\s*=\s*"loop\.__main__:main"', text)


def test_entrypoint_resolves_repo_relative_scripts_dir():
    # The QW8 constraint: loop.__main__ resolves the bundled scripts/ dir from its
    # own __file__, so an editable install runs `inspect`/`metrics` from any dir.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import loop.__main__ as entry

    scripts_dir = Path(entry.__file__).resolve().parent.parent / "scripts"
    assert (scripts_dir / "metrics.py").exists()
    assert (scripts_dir / "inspect_loop.py").exists()


def test_metrics_runs_from_a_foreign_cwd(tmp_path):
    # Proves scripts/ resolution is repo-relative, not cwd-relative: invoke from an
    # unrelated cwd with an absolute target.
    result = subprocess.run(
        [sys.executable, "-m", "loop", "metrics", str(ROOT / "examples" / "coverage-repair")],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["schema"] == "loop-engineer/metrics@1"
