import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location(
    "se", pathlib.Path(__file__).parent / "self_eval.py"
)
se = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(se)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_run_checks_returns_schema():
    r = se.run_checks(REPO_ROOT)
    assert set(r) >= {"checks", "structural_pass_rate", "passed"}
    assert len(r["checks"]) == 10
    for c in r["checks"]:
        assert set(c) >= {"name", "ok", "detail"}
        assert isinstance(c["name"], str) and c["name"]
        assert isinstance(c["ok"], bool)
        assert isinstance(c["detail"], str)
    assert isinstance(r["structural_pass_rate"], float)
    assert 0.0 <= r["structural_pass_rate"] <= 1.0
    assert isinstance(r["passed"], bool)


def test_pass_rate_matches_checks():
    r = se.run_checks(REPO_ROOT)
    ok = sum(1 for c in r["checks"] if c["ok"])
    assert r["structural_pass_rate"] == ok / len(r["checks"])
    assert r["passed"] == (ok == len(r["checks"]))


def test_check_names_are_unique():
    r = se.run_checks(REPO_ROOT)
    names = [c["name"] for c in r["checks"]]
    assert len(names) == len(set(names))


def test_all_pass_on_real_repo():
    r = se.run_checks(REPO_ROOT)
    failed = [c["name"] for c in r["checks"] if not c["ok"]]
    assert r["passed"], f"failing checks: {failed}"


def test_cli_runs_by_path_from_foreign_cwd(tmp_path):
    """Regression: self_eval.py must resolve the repo root from __file__,
    not the current working directory. Exec the CLI by absolute path from an
    unrelated CWD with no PYTHONPATH (the real path-invoked runtime)."""
    import os
    import subprocess
    import sys

    script = pathlib.Path(__file__).resolve().parent / "self_eval.py"
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "structural_pass_rate: 1.000" in proc.stdout
