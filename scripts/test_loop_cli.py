"""CLI/UX contract tests for the `python3 -m loop` entry point (M4-CLI / S6).

Each test pins one behavior from the launch-criterion CLI polish batch. They run
the real entry point as a subprocess so STDOUT vs STDERR and the process exit
code are exercised exactly as a user sees them.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "loop", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def _pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    assert match, "pyproject.toml has no version field"
    return match.group(1)


# --- item 1: --help / -h to STDOUT, exit 0, per-command descriptions ---------


def test_help_flag_exits_zero_and_prints_usage_to_stdout():
    result = _run("--help")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), "help must print to stdout"
    assert result.stderr == "", "help must not go to stderr"
    assert "usage" in result.stdout.lower()


def test_short_help_flag_matches_long_help():
    long = _run("--help")
    short = _run("-h")
    assert short.returncode == 0
    assert short.stdout == long.stdout


def test_help_lists_every_command_with_a_description():
    out = _run("--help").stdout
    for command in ("scaffold", "doctor", "validate", "verify", "inspect"):
        assert command in out, f"help omits command {command!r}"
    # Per-command descriptions, not a bare command list.
    assert "Validate" in out or "validate the contract" in out.lower()
    assert "Score" in out or "score" in out.lower()


# --- item 2: --version prints the package version (single source: pyproject) --


def test_version_flag_prints_package_version_and_exits_zero():
    result = _run("--version")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == _pyproject_version()
    assert result.stderr == ""


# --- item 3: usage/help text says `python3 -m loop`, never `python -m loop` ---


def test_usage_text_uses_python3_invocation():
    help_out = _run("--help").stdout
    assert "python3 -m loop" in help_out
    assert "python -m loop" not in help_out
    # The bare usage (no args -> stderr) must also use python3.
    no_args = _run()
    assert "python3 -m loop" in no_args.stderr
    assert "python -m loop" not in no_args.stderr


# --- item 5: missing target argument -> usage + nonzero (no traceback) --------


def test_missing_target_argument_prints_usage_and_exits_nonzero():
    result = _run("doctor")
    assert result.returncode != 0
    assert "usage" in result.stderr.lower()
    assert "Traceback" not in result.stderr


def test_missing_target_for_inspect_does_not_default_to_cwd():
    result = _run("inspect")
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    # Must NOT silently inspect the current directory and emit a JSON report.
    assert not result.stdout.strip().startswith("{")


# --- item 4: nonexistent target -> distinct actionable error ------------------


def test_nonexistent_target_gives_distinct_actionable_error(tmp_path):
    missing = tmp_path / "does-not-exist"
    result = _run("doctor", str(missing))
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    # Distinct from a malformed/empty contract: names the missing path on stderr,
    # not a JSON `missing_file` issues report on stdout.
    assert "does not exist" in result.stderr.lower()
    assert str(missing) in result.stderr
    assert result.stdout.strip() == ""


def test_nonexistent_target_differs_from_malformed_contract(tmp_path):
    # An existing-but-empty dir is a malformed contract: JSON issues on stdout,
    # exit 1. A nonexistent path is a different failure: message on stderr, and
    # the two must not produce the same output.
    empty = tmp_path / "empty"
    empty.mkdir()
    missing = tmp_path / "missing"

    malformed = _run("doctor", str(empty))
    nonexistent = _run("doctor", str(missing))

    assert malformed.stdout.strip().startswith("{")  # JSON issues report
    assert nonexistent.stdout.strip() == ""  # no JSON report
    assert malformed.stdout != nonexistent.stdout
    assert malformed.stderr != nonexistent.stderr


# --- item 6: `verify` alias is wired and reconciled with docs -----------------


def test_verify_is_a_wired_doctor_alias(tmp_path):
    empty = tmp_path / "ws"
    empty.mkdir()
    doctor = _run("doctor", str(empty))
    verify = _run("verify", str(empty))
    assert verify.returncode == doctor.returncode
    assert verify.stdout == doctor.stdout
    # And a valid JSON report either way.
    json.loads(verify.stdout)


def test_help_describes_verify_and_validate_as_aliases():
    out = _run("--help").stdout.lower()
    assert "alias" in out, "help must reconcile verify/validate as doctor aliases"


# S2: explicit validation mode CLI ------------------------------------------------


def test_help_documents_validation_modes():
    out = _run("--help").stdout
    assert "--mode" in out
    for value in ("basic", "strict", "release"):
        assert value in out


def test_doctor_mode_release_and_basic_echo_requested_mode():
    import importlib.util

    strict = _run("doctor", "--mode=release", "examples/coverage-repair")
    if importlib.util.find_spec("jsonschema") is not None:
        assert strict.returncode == 0, strict.stderr
        assert json.loads(strict.stdout)["requested_mode"] == "release"
        assert json.loads(strict.stdout)["validation_mode"] == "jsonschema"
    else:
        assert strict.returncode == 2
        assert strict.stdout == ""
        assert "jsonschema" in strict.stderr
        assert "--mode basic" in strict.stderr

    basic = _run("doctor", "--mode", "basic", "examples/coverage-repair")
    assert basic.returncode == 0, basic.stderr
    assert json.loads(basic.stdout)["requested_mode"] == "basic"
    assert json.loads(basic.stdout)["validation_mode"] == "structural-fallback"


def test_doctor_default_mode_reports_auto():
    result = _run("doctor", "examples/coverage-repair")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["requested_mode"] == "auto"


def test_strict_mode_fails_loudly_without_jsonschema(tmp_path):
    import os

    blocker = tmp_path / "blocker"
    blocker.mkdir()
    (blocker / "jsonschema.py").write_text("raise ImportError('blocked for test')\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(blocker), str(ROOT)))}
    result = subprocess.run(
        [sys.executable, "-m", "loop", "doctor", "--mode", "strict", "examples/coverage-repair"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "jsonschema" in result.stderr
    assert "Traceback" not in result.stderr


def test_invalid_or_missing_mode_is_a_usage_error():
    for args in (("doctor", "--mode", "bogus", "examples/coverage-repair"), ("doctor", "--mode")):
        result = _run(*args)
        assert result.returncode == 2
        assert result.stdout == ""
        assert "usage" in result.stderr.lower()
        assert "Traceback" not in result.stderr
    assert all(value in _run("doctor", "--mode", "bogus", "examples/coverage-repair").stderr for value in ("basic", "strict", "release"))


def test_validate_and_verify_accept_mode_as_doctor_aliases():
    doctor = _run("doctor", "--mode", "basic", "examples/coverage-repair")
    for command in ("validate", "verify"):
        result = _run(command, "--mode", "basic", "examples/coverage-repair")
        assert result.returncode == doctor.returncode
        assert result.stdout == doctor.stdout


def test_mode_is_not_consumed_by_other_commands(tmp_path):
    import os

    target = tmp_path / "target"
    for command in ("inspect", "metrics"):
        result = _run(command, "--mode", str(target))
        assert result.returncode != 0

    result = subprocess.run(
        [sys.executable, "-m", "loop", "scaffold", "--mode", str(target)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    assert result.returncode == 0
    assert (tmp_path / "--mode").is_dir()


def test_help_lists_plan_lint_command():
    assert "plan-lint" in _run("--help").stdout


def test_help_documents_plan_lint_mode_flag():
    assert "plan-lint [--mode basic|strict|release] <plan-file>" in _run("--help").stdout


def test_plan_lint_missing_target_argument_prints_usage_and_exits_nonzero():
    result = _run("plan-lint")
    assert result.returncode != 0
    assert "usage" in result.stderr.lower()
    assert "Traceback" not in result.stderr


def test_plan_lint_nonexistent_file_gives_distinct_actionable_error(tmp_path):
    missing = tmp_path / "does-not-exist.plan.json"
    result = _run("plan-lint", str(missing))
    assert result.returncode != 0
    assert "loop-engineer/plan@1 JSON file" in result.stderr
    assert "scaffold" not in result.stderr


def test_plan_lint_valid_golden_example_exits_zero():
    import importlib.util

    mode = "release" if importlib.util.find_spec("jsonschema") is not None else "basic"
    result = _run("plan-lint", "--mode", mode, "examples/plans/coverage-repair.plan.json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True


def test_plan_lint_cyclic_example_exits_nonzero():
    result = _run("plan-lint", "examples/plans/invalid/cyclic-dependency.plan.json")
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["ok"] is False
    assert any(issue["code"] == "cyclic_dependency" for issue in report["issues"])


def test_plan_lint_basic_mode_also_catches_cycle():
    result = _run("plan-lint", "--mode", "basic", "examples/plans/invalid/cyclic-dependency.plan.json")
    assert result.returncode == 1
    assert any(issue["code"] == "cyclic_dependency" for issue in json.loads(result.stdout)["issues"])


def test_plan_lint_reports_plan_schema_id():
    result = _run("plan-lint", "--mode", "basic", "examples/plans/coverage-repair.plan.json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["schemas_checked"] == ["loop-engineer/plan@1"]


def test_plan_lint_accepts_mode_flag_like_doctor():
    result = _run("plan-lint", "--mode", "bogus", "examples/plans/coverage-repair.plan.json")
    assert result.returncode == 2
    assert "usage" in result.stderr.lower()
    assert "Traceback" not in result.stderr
