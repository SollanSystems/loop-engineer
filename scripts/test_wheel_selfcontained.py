# scripts/test_wheel_selfcontained.py
"""S0 acceptance: a built wheel must be self-contained. Build the wheel, install
it into a fresh venv, and run scaffold/doctor/inspect from a temp cwd where the
repo checkout is not importable. Env-guarded: building needs pip + network for
the hatchling backend, so this skips in offline/pip-less local envs; in CI a
wheel build failure fails the test rather than skipping it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import venv
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _pip_available() -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "--version"], capture_output=True, text=True
    )
    return proc.returncode == 0


pytestmark = pytest.mark.skipif(
    not _pip_available(), reason="pip unavailable in this interpreter (wheel build env guard)"
)


@pytest.fixture(scope="module")
def wheel_env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("wheel")
    build = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", str(tmp), str(REPO_ROOT)],
        capture_output=True, text=True,
    )
    if build.returncode != 0:
        if os.environ.get("CI"):
            pytest.fail(f"wheel build failed in CI: {build.stderr[-1500:]}")
        pytest.skip(f"wheel build unavailable here (offline?): {build.stderr[-400:]}")
    wheel = next(tmp.glob("loop_engineer-*.whl"))

    names = zipfile.ZipFile(wheel).namelist()
    for expected in (
        "loop/_bundle/schemas/",
        "loop/_bundle/templates/",
        "loop/_bundle/tools/",
    ):
        assert any(n.startswith(expected) for n in names), f"wheel missing {expected}"

    venv_dir = tmp / "venv"
    venv.EnvBuilder(with_pip=True).create(venv_dir)
    py = venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    install = subprocess.run(
        [str(py), "-m", "pip", "install", "--no-index", str(wheel)],
        capture_output=True, text=True,
    )
    assert install.returncode == 0, install.stderr
    return py


def _run(py: Path, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    # cwd is OUTSIDE the repo, so the checkout is absent from sys.path.
    return subprocess.run([str(py), "-m", "loop", *args], cwd=cwd, capture_output=True, text=True)


def test_scaffold_doctor_inspect_from_wheel_only(wheel_env, tmp_path):
    workspace = tmp_path / "fresh-loop"

    scaffolded = _run(wheel_env, ["scaffold", str(workspace)], cwd=tmp_path)
    assert scaffolded.returncode == 0, scaffolded.stderr

    doctored = _run(wheel_env, ["doctor", str(workspace)], cwd=tmp_path)
    assert doctored.returncode == 0, doctored.stdout + doctored.stderr
    assert json.loads(doctored.stdout)["ok"] is True

    inspected = _run(wheel_env, ["inspect", str(workspace)], cwd=tmp_path)
    report = json.loads(inspected.stdout)
    assert report["verdict"] in ("weak", "ok", "strong")


def test_both_console_scripts_are_installed(wheel_env, tmp_path):
    bindir = wheel_env.parent
    for name in ("loop", "loop-engineer"):
        exe = bindir / name
        proc = subprocess.run([str(exe), "--version"], cwd=tmp_path, capture_output=True, text=True)
        assert proc.returncode == 0, f"{name}: {proc.stderr}"
        assert proc.stdout.strip()


def test_plan_lint_from_wheel_only(wheel_env, tmp_path):
    # No jsonschema in this venv (pip wheel --no-deps): proves plan-lint's
    # structural-fallback mode genuinely runs from a repo-checkout-free install.
    plan_file = REPO_ROOT / "examples" / "plans" / "coverage-repair.plan.json"
    result = _run(wheel_env, ["plan-lint", str(plan_file)], cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["validation_mode"] == "structural-fallback"
