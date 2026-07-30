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


# --- slice 4b: --compare and --emit-subject ----------------------------------
#
# The exit-code contract is normative: 0 agreement, 1 disagreement, 2 refusal. Exit 1
# in this CLI MEANS "a report said not-ok", so an unreadable --compare input must never
# land there — it would read as a genuine disagreement.

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ci_anchor_probe import seed as _seed_chained                            # noqa: E402

from loop.verdict import subject_bytes as _subject_bytes                     # noqa: E402

_SIGNATURE_FLAGS = ("--verify-signature", "--signature", "--signer-workflow")


def _run_stdin(repo_root: pathlib.Path, stdin: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-B", "-m", "loop", *args],
                          capture_output=True, text=True, cwd=repo_root, input=stdin)


def _chained_terminal(tmp_path: pathlib.Path) -> tuple[pathlib.Path, str]:
    """A chained workspace with a terminal record, so a verdict carries a real head."""
    workspace = tmp_path / "ws"
    head = _seed_chained(workspace)
    (workspace / ".loop" / "terminal_state.json").write_text(json.dumps({
        "schema": "loop-engineer/terminal@1", "state": "Succeeded",
        "completion_policy": {"mode": "all_required"}, "criteria_met": {"T1": True},
        "evidence": [], "false_completion": False,
    }), encoding="utf-8")
    return workspace, head


def test_compare_exits_zero_on_agreement(repo_root: pathlib.Path, tmp_path: pathlib.Path):
    workspace, _head = _chained_terminal(tmp_path)
    projected = _run(repo_root, "verdict", str(workspace))
    assert projected.returncode == 0, projected.stderr
    document = tmp_path / "attested.json"
    document.write_text(projected.stdout, encoding="utf-8")
    result = _run(repo_root, "verdict", "--compare", str(document), str(workspace))
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is True and report["signature_checked"] is False


def test_compare_exits_one_on_disagreement(repo_root: pathlib.Path, tmp_path: pathlib.Path):
    workspace, _head = _chained_terminal(tmp_path)
    projected = json.loads(_run(repo_root, "verdict", str(workspace)).stdout)
    projected["chain"]["head"] = "b" * 64
    document = tmp_path / "attested.json"
    document.write_text(json.dumps(projected), encoding="utf-8")
    result = _run(repo_root, "verdict", "--compare", str(document), str(workspace))
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert {issue["code"] for issue in report["issues"]} == {"verdict_head_disagreement"}


def test_compare_exits_two_on_a_wrapper_shape(repo_root: pathlib.Path, tmp_path: pathlib.Path):
    workspace, _head = _chained_terminal(tmp_path)
    document = tmp_path / "wrapped.json"
    document.write_text(json.dumps([{"verificationResult": {"statement": {}}}]), encoding="utf-8")
    result = _run(repo_root, "verdict", "--compare", str(document), str(workspace))
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("verdict:")
    assert "Traceback" not in result.stderr


def test_compare_reads_stdin_with_a_dash(repo_root: pathlib.Path, tmp_path: pathlib.Path):
    workspace, _head = _chained_terminal(tmp_path)
    projected = _run(repo_root, "verdict", str(workspace)).stdout
    result = _run_stdin(repo_root, projected, "verdict", "--compare", "-", str(workspace))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True


def test_compare_missing_value_is_a_usage_error(repo_root: pathlib.Path, tmp_path: pathlib.Path):
    workspace, _head = _chained_terminal(tmp_path)
    result = _run(repo_root, "verdict", str(workspace), "--compare")
    assert result.returncode == 2
    assert result.stdout == ""


def test_compare_refuses_a_nonexistent_file(repo_root: pathlib.Path, tmp_path: pathlib.Path):
    """Exit 1 here would read as a genuine disagreement, so it must be exit 2."""
    workspace, _head = _chained_terminal(tmp_path)
    result = _run(repo_root, "verdict", "--compare", str(tmp_path / "absent.json"), str(workspace))
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("verdict:")
    assert "Traceback" not in result.stderr


def test_compare_refuses_a_directory_path(repo_root: pathlib.Path, tmp_path: pathlib.Path):
    workspace, _head = _chained_terminal(tmp_path)
    result = _run(repo_root, "verdict", "--compare", str(tmp_path), str(workspace))
    assert result.returncode == 2
    assert result.stdout == ""
    assert "Traceback" not in result.stderr


def test_compare_refuses_empty_stdin(repo_root: pathlib.Path, tmp_path: pathlib.Path):
    """The pipeline whose upstream jq produced nothing deserves a message that says so,
    never a comparison against None."""
    workspace, _head = _chained_terminal(tmp_path)
    result = _run_stdin(repo_root, "", "verdict", "--compare", "-", str(workspace))
    assert result.returncode == 2
    assert result.stdout == ""
    assert "empty" in result.stderr


@pytest.mark.parametrize("command", ["scaffold", "doctor", "status"])
def test_compare_rejected_for_non_verdict_commands(repo_root: pathlib.Path,
                                                   tmp_path: pathlib.Path, command: str):
    target = tmp_path / f"{command}-target"
    result = _run(repo_root, command, "--compare", str(tmp_path / "x.json"), str(target))
    assert result.returncode == 2
    assert "--compare is only valid for verdict" in result.stderr
    # An unguarded flag makes scaffold CREATE a directory named after it, in its CWD.
    assert not (repo_root / "--compare").exists()


def test_emit_subject_writes_exactly_64_bytes_no_newline(repo_root: pathlib.Path,
                                                        tmp_path: pathlib.Path):
    workspace, head = _chained_terminal(tmp_path)
    result = subprocess.run([sys.executable, "-B", "-m", "loop", "verdict", "--emit-subject",
                             str(workspace)], capture_output=True, cwd=repo_root)
    assert result.returncode == 0, result.stderr
    assert len(result.stdout) == 64
    assert not result.stdout.endswith(b"\n")
    assert result.stdout == head.encode("ascii")


def test_emit_subject_bytes_equal_subject_bytes_of_the_projected_head(repo_root: pathlib.Path,
                                                                     tmp_path: pathlib.Path):
    """The CLI and loop.verdict.subject_bytes cannot drift: one writer, one byte form."""
    workspace, _head = _chained_terminal(tmp_path)
    projected = json.loads(_run(repo_root, "verdict", str(workspace)).stdout)
    result = subprocess.run([sys.executable, "-B", "-m", "loop", "verdict", "--emit-subject",
                             str(workspace)], capture_output=True, cwd=repo_root)
    assert result.stdout == _subject_bytes(projected["chain"]["head"])


def test_emit_subject_refuses_a_null_head(repo_root: pathlib.Path):
    """A store-less workspace has no subject to attest."""
    result = subprocess.run([sys.executable, "-B", "-m", "loop", "verdict", "--emit-subject",
                             "examples/flaky-test-triage"], capture_output=True, cwd=repo_root)
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.decode().startswith("verdict:")


def test_compare_and_emit_subject_are_mutually_exclusive(repo_root: pathlib.Path,
                                                         tmp_path: pathlib.Path):
    workspace, _head = _chained_terminal(tmp_path)
    result = _run(repo_root, "verdict", "--compare", "-", "--emit-subject", str(workspace))
    assert result.returncode == 2
    assert result.stdout == ""
    assert "mutually exclusive" in result.stderr


def test_help_documents_compare_and_emit_subject(repo_root: pathlib.Path):
    result = _run(repo_root, "--help")
    assert result.returncode == 0
    assert "--compare" in result.stdout and "--emit-subject" in result.stdout
    assert "never verifies a signature" in result.stdout


@pytest.mark.parametrize("flag", _SIGNATURE_FLAGS)
def test_verdict_never_advertises_a_signature_flag(repo_root: pathlib.Path, flag: str):
    """D10.1's third leg: there is no flag to flip."""
    result = _run(repo_root, "verdict", flag, "x", "examples/flaky-test-triage")
    assert result.returncode == 2
    assert result.stdout == ""
