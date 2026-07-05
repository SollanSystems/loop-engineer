"""C1 acceptance: the pre-commit hook definition is sound (always), and it runs
from a consumer-side .pre-commit-config.yaml fixture (env-guarded on the
pre-commit tool; the CI dogfood job installs it and runs this for real)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT))
from loop.scaffold import scaffold  # noqa: E402


def _hooks() -> list[dict]:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load((REPO_ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))


def test_hook_definition_is_sound():
    (hook,) = _hooks()
    assert hook["id"] == "loop-doctor"
    assert hook["entry"] == "loop doctor ."
    assert hook["language"] == "python"
    assert hook["pass_filenames"] is False
    assert hook["always_run"] is True


def test_hook_installs_the_schema_extras_so_it_runs_the_strict_gate():
    # The CLI's pure-stdlib structural default is deliberate, but the pre-commit
    # gate must run real JSON-Schema validation — otherwise a type-invalid
    # contract passes the shipped hook. pre-commit installs additional_dependencies
    # into the hook's isolated env.
    (hook,) = _hooks()
    deps = hook.get("additional_dependencies", [])
    joined = " ".join(deps).lower()
    assert "jsonschema" in joined, (
        "loop-doctor hook must install jsonschema so validation runs in strict mode"
    )
    assert "pyyaml" in joined or "yaml" in joined, (
        "loop-doctor hook must install pyyaml so the manifest parses via PyYAML"
    )


def test_entry_command_matches_a_declared_console_script():
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'loop = "loop.__main__:main"' in text


@pytest.mark.skipif(shutil.which("pre-commit") is None, reason="pre-commit tool not installed")
def test_hook_runs_from_a_consumer_fixture(tmp_path):
    consumer = tmp_path / "consumer"
    scaffold(consumer)
    subprocess.run(["git", "init", "-q"], cwd=consumer, check=True)
    subprocess.run(["git", "add", "-A"], cwd=consumer, check=True)
    proc = subprocess.run(
        ["pre-commit", "try-repo", str(REPO_ROOT), "loop-doctor", "--all-files"],
        cwd=consumer, capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
