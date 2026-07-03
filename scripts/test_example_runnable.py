"""Pin the coverage-repair example as a *runnable* loop, not a frozen story.

Two guards, both fail-before if the toy target or the gate wiring is removed:

  1. ``run-example`` executes end to end (from a foreign cwd, proving
     path-independence) and reaches an independent ``holdout_gate`` verdict of
     ``Succeeded`` with ``false_completion: false`` — the same claim the
     committed ``terminal_state.json`` makes.
  2. ``inspect`` grades the example's false-completion defense as *invoked*
     (full credit), with no "no false-completion defense" gap.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_EXAMPLE = _REPO / "examples" / "coverage-repair"
_RUN = _EXAMPLE / "scripts" / "run-example"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_example_end_to_end_from_foreign_cwd(tmp_path):
    """The scripted run reproduces the real holdout gate and backs the terminal claim."""
    proc = subprocess.run(
        ["bash", str(_RUN)],
        cwd=tmp_path,                      # foreign cwd → path-independence
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"run-example failed:\n{proc.stdout}\n{proc.stderr}"

    verdict = json.loads((_EXAMPLE / ".loop" / "artifacts" / "holdout-verdict.json").read_text())
    assert verdict["verdict"] == "Succeeded", verdict
    assert verdict["false_completion"] is False, verdict

    terminal = json.loads((_EXAMPLE / "terminal_state.json").read_text())
    assert terminal["false_completion"] is False
    # The committed claim is now BACKED by an independent gate run, not asserted.
    assert "BACKED by an independent" in proc.stdout


def test_inspect_grants_full_false_completion_credit():
    inspect_loop = _load("inspect_loop")
    report = inspect_loop.inspect_loop(str(_EXAMPLE))

    assert "false-completion defense (invoked)" in report["present"], report
    assert not any("no false-completion defense" in g for g in report["gaps"]), report["gaps"]
    assert report["verdict"] == "strong", report


def test_holdout_gate_is_really_invoked_by_the_verify_surface():
    """Guard the grade's *source*: a verify-* script invokes the gate on a real
    (non-comment) line — deleting the wiring drops the credit and fails here."""
    inspect_loop = _load("inspect_loop")
    paths = inspect_loop.resolve_loop_paths(str(_EXAMPLE))
    assert inspect_loop._gate_invoked_in_verify(paths.workspace) is True


if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", __file__]))
