"""CLI contract tests for the read-only ``loop verdict`` projection."""

import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest


@pytest.fixture
def repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent


def _run(repo_root: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", "-m", "loop", *args],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )


def test_verdict_emits_canonical_json_and_exits_zero(repo_root: pathlib.Path):
    result = _run(repo_root, "verdict", "examples/flaky-test-triage")
    assert result.returncode == 0, result.stderr
    doc = json.loads(result.stdout)
    assert doc["schema"] == "loop-engineer/verdict@1"


def test_verdict_output_is_byte_stable(repo_root: pathlib.Path):
    first = _run(repo_root, "verdict", "examples/flaky-test-triage")
    second = _run(repo_root, "verdict", "examples/flaky-test-triage")
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout


def test_verdict_emits_no_statement_envelope(repo_root: pathlib.Path):
    result = _run(repo_root, "verdict", "examples/flaky-test-triage")
    assert result.returncode == 0, result.stderr
    doc = json.loads(result.stdout)
    assert not {"_type", "subject", "predicateType", "predicate"} & doc.keys()


def test_verdict_fails_loud_without_a_terminal_record(repo_root: pathlib.Path, tmp_path: pathlib.Path):
    workspace = tmp_path / "workspace"
    scaffolded = _run(repo_root, "scaffold", str(workspace))
    assert scaffolded.returncode == 0, scaffolded.stderr
    result = _run(repo_root, "verdict", str(workspace))
    assert result.returncode == 2
    assert result.stdout == ""
    assert "Traceback" not in result.stderr
    assert "no terminal record" in result.stderr
    assert result.stderr.startswith("verdict:")


def test_verdict_reports_a_typed_error_when_the_document_cannot_be_canonicalized(
    repo_root: pathlib.Path, tmp_path: pathlib.Path
):
    workspace = tmp_path / "workspace"
    scaffolded = _run(repo_root, "scaffold", str(workspace))
    assert scaffolded.returncode == 0, scaffolded.stderr
    terminal = json.dumps({"state": "Succeeded", "false_completion": False})
    (workspace / ".loop" / "terminal_state.json").write_text(
        terminal.replace('"Succeeded"', "NaN"), encoding="utf-8"
    )
    result = _run(repo_root, "verdict", str(workspace))
    assert result.returncode == 2
    assert result.stdout == ""
    assert "Traceback" not in result.stderr
    assert result.stderr.startswith("verdict:")


def test_verdict_appears_in_usage_and_help(repo_root: pathlib.Path):
    help_result = _run(repo_root, "--help")
    assert "verdict" in help_result.stdout
    assert "Never signs and never verifies" in help_result.stdout
    missing_target = _run(repo_root, "verdict")
    assert missing_target.returncode == 2
    assert "verdict" in missing_target.stderr


def test_verdict_stdout_is_the_canonical_json_of_build_verdict(repo_root: pathlib.Path):
    from loop.chain import canonical_json
    from loop.verdict import build_verdict

    result = _run(repo_root, "verdict", "examples/flaky-test-triage")
    assert result.returncode == 0, result.stderr
    assert result.stdout == canonical_json(build_verdict("examples/flaky-test-triage")) + "\n"


def test_verdict_missing_target_exits_2_with_the_read_command_hint(repo_root: pathlib.Path, tmp_path: pathlib.Path):
    result = _run(repo_root, "verdict", str(tmp_path / "missing"))
    assert result.returncode == 2
    assert "target path does not exist" in result.stderr


def test_verdict_rejects_an_invalid_mode_value(repo_root: pathlib.Path):
    result = _run(repo_root, "verdict", "--mode", "bogus", "examples/flaky-test-triage")
    assert result.returncode == 2
    assert "invalid --mode value" in result.stderr


def test_verdict_mode_flag_reaches_the_projection(repo_root: pathlib.Path):
    basic = _run(repo_root, "verdict", "--mode", "basic", "examples/flaky-test-triage")
    assert basic.returncode == 0, basic.stderr
    basic_doc = json.loads(basic.stdout)
    assert basic_doc["doctor"]["validation_mode"] == "structural-fallback"

    default = _run(repo_root, "verdict", "examples/flaky-test-triage")
    assert default.returncode == 0, default.stderr
    default_doc = json.loads(default.stdout)
    has_jsonschema = importlib.util.find_spec("jsonschema") is not None
    if has_jsonschema:
        assert basic_doc["doctor"]["validation_mode"] != default_doc["doctor"]["validation_mode"]


def test_verdict_rejects_expect_chain_head(repo_root: pathlib.Path):
    result = _run(
        repo_root,
        "verdict",
        "--expect-chain-head",
        "a" * 64,
        "examples/flaky-test-triage",
    )
    assert result.returncode == 2
    assert "only valid for doctor/validate/verify" in result.stderr
