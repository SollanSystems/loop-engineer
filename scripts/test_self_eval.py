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
    assert len(r["checks"]) == 13
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


_LICENSE_FACTS = {
    "license": {
        "spdx": "MIT",
        "title": "MIT License",
        "holder": "Sollan Systems",
        "year": "2026",
        "body_marker": "Permission is hereby granted, free of charge",
    }
}
_DIFF_FACTS = {
    "readme_differentiation": {
        "section_heading_pattern": r"^#+\s+.*how (it|this) compares",
        "required_markers": ["false-completion-rate", "repair-productivity"],
    }
}
_MIT_BODY = (
    "MIT License\n\nCopyright (c) 2026 {holder}\n\n"
    "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
)


def test_license_check_missing_then_present(tmp_path):
    ok, _ = se.check_license_present(tmp_path, _LICENSE_FACTS)
    assert ok is False
    (tmp_path / "LICENSE").write_text(_MIT_BODY.format(holder="Sollan Systems"))
    ok, detail = se.check_license_present(tmp_path, _LICENSE_FACTS)
    assert ok is True, detail


def test_license_check_wrong_holder_fails(tmp_path):
    (tmp_path / "LICENSE").write_text(_MIT_BODY.format(holder="Someone Else"))
    ok, detail = se.check_license_present(tmp_path, _LICENSE_FACTS)
    assert ok is False and "holder" in detail


def test_readme_differentiation_requires_heading(tmp_path):
    (tmp_path / "README.md").write_text(
        "# loop-engineer\n\nfalse-completion-rate and repair-productivity\n"
    )
    ok, _ = se.check_readme_differentiation(tmp_path, _DIFF_FACTS)
    assert ok is False
    (tmp_path / "README.md").write_text(
        "# loop-engineer\n\n## How it compares\n\n"
        "Tracks false-completion-rate and repair-productivity.\n"
    )
    ok, detail = se.check_readme_differentiation(tmp_path, _DIFF_FACTS)
    assert ok is True, detail


def test_readme_differentiation_requires_markers(tmp_path):
    (tmp_path / "README.md").write_text(
        "## How it compares\n\nno metrics named here\n"
    )
    ok, detail = se.check_readme_differentiation(tmp_path, _DIFF_FACTS)
    assert ok is False and "markers" in detail
