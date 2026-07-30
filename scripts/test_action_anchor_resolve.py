"""scripts/test_action_anchor_resolve.py — the resolve step, against a fake `gh`.

The highest-risk new module in the slice: it shells out and parses another program's
stdout. Every failure must land as a TYPED outcome naming which shape assumption failed
— never a traceback, never a silent pass, and never `corroborated`.

`gh`'s exit codes cannot tell D5's three outcomes apart (all arrive as exit 1), so the
classifier reads stderr. The 404 branch is therefore driven by a VERBATIM captured
vendor string, not a paraphrase: a remembered approximation is exactly the thing that
passes review and fails in production.
"""
from __future__ import annotations

import ast
import json
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "action_anchor_resolve.py"
FIXTURE_404 = ROOT / "scripts" / "fixtures" / "gh_attestation_verify" / "no_attestation_404.txt"

_HEAD = "a1" * 32
_REPO = "SollanSystems/loop-engineer"
_WORKFLOW = "SollanSystems/loop-engineer/.github/workflows/attest.yml"

_CERTIFICATE = {
    "subjectAlternativeName": f"https://github.com/{_WORKFLOW}@refs/heads/main",
    "sourceRepositoryURI": f"https://github.com/{_REPO}",
    "runnerEnvironment": "github-hosted",
    "githubWorkflowTrigger": "push",
}
_PREDICATE = {"schema": "loop-engineer/verdict@1", "run_id": "coverage-repair",
              "chain": {"head": _HEAD, "sequence": 3, "unchained_prefix": 0}}


def _payload(*, certificate=None, statement=True):
    result = {"signature": {"certificate": dict(certificate or _CERTIFICATE)},
              "verifiedTimestamps": [{"type": "Tlog", "timestamp": "2026-07-29T00:00:00Z"}]}
    if statement:
        result["statement"] = {"predicateType": "urn:loop-engineer:verdict:1",
                               "predicate": _PREDICATE}
    return json.dumps([{"attestation": {}, "verificationResult": result}])


def _anchor(tmp_path, head=_HEAD):
    path = tmp_path / "loop-anchor.json"
    path.write_text(json.dumps({"schema": "loop-engineer/anchor@1", "chain_head": head}),
                    encoding="utf-8")
    return path


def _shim(tmp_path, *, stdout="", stderr="", exit_code=0):
    """An executable `gh` on PATH that logs its real argv and emits canned output."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    log = tmp_path / "argv.log"
    (bin_dir / "gh").write_text(
        "#!/bin/sh\n"
        f'for arg in "$@"; do echo "$arg" >> {log}; done\n'
        f"cat {tmp_path / 'stdout.txt'}\n"
        f"cat {tmp_path / 'stderr.txt'} >&2\n"
        f"exit {exit_code}\n",
        encoding="utf-8")
    (bin_dir / "gh").chmod(0o755)
    (tmp_path / "stdout.txt").write_text(stdout, encoding="utf-8")
    (tmp_path / "stderr.txt").write_text(stderr, encoding="utf-8")
    return bin_dir, log


def _resolve(tmp_path, *, bin_dir=None, anchor=None, signer_workflow=_WORKFLOW,
             path_override=None):
    env = dict(os.environ)
    if path_override is not None:
        env["PATH"] = str(path_override)
    elif bin_dir is not None:
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    runner_temp = tmp_path / "runner-temp"
    outputs = tmp_path / "github-output.txt"
    proc = subprocess.run(
        [sys.executable, "-B", str(SCRIPT),
         "--anchor", str(anchor if anchor is not None else _anchor(tmp_path)),
         "--repo", _REPO,
         "--signer-workflow", signer_workflow,
         "--runner-temp", str(runner_temp),
         "--github-output", str(outputs)],
        capture_output=True, text=True, env=env, cwd=tmp_path)
    parsed = {}
    if outputs.exists():
        for line in outputs.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                name, _, value = line.partition("=")
                parsed[name] = value
    return proc, parsed, runner_temp


def _argv(log: pathlib.Path) -> list[str]:
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


# --- the three outcomes ------------------------------------------------------


def test_resolve_corroborates_with_a_fake_gh(tmp_path):
    bin_dir, _log = _shim(tmp_path, stdout=_payload())
    proc, outputs, _temp = _resolve(tmp_path, bin_dir=bin_dir)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert outputs["anchor-outcome"] == "corroborated"


def test_resolve_reports_contradicted_when_verify_denies(tmp_path):
    """A signer the policy denies: an attestation WAS found and did not survive."""
    denied = dict(_CERTIFICATE,
                  subjectAlternativeName="https://github.com/other/repo/.github/workflows/x.yml@refs/heads/main")
    bin_dir, _log = _shim(tmp_path, stdout=_payload(certificate=denied))
    proc, outputs, _temp = _resolve(tmp_path, bin_dir=bin_dir)
    assert proc.returncode == 1
    assert outputs["anchor-outcome"] == "contradicted"
    assert "anchor_attestation_contradicted" in proc.stdout


def test_resolve_reports_unavailable_on_a_404(tmp_path):
    bin_dir, _log = _shim(tmp_path, stderr="Error: HTTP 404: Not Found (…)", exit_code=1)
    proc, outputs, _temp = _resolve(tmp_path, bin_dir=bin_dir)
    assert proc.returncode == 1
    assert outputs["anchor-outcome"] == "unavailable"
    assert "anchor_attestation_unavailable" in proc.stdout


def test_resolve_reports_unavailable_on_a_transport_failure(tmp_path):
    """A 5xx is 'I could not look', NOT 'it said no'."""
    bin_dir, _log = _shim(tmp_path, stderr="Error: HTTP 503 Service Unavailable", exit_code=7)
    proc, outputs, _temp = _resolve(tmp_path, bin_dir=bin_dir)
    assert proc.returncode == 1
    assert outputs["anchor-outcome"] == "unavailable"


def test_resolve_classifies_the_real_captured_404_stderr(tmp_path):
    """M2 — driven by the committed verbatim capture, not a paraphrase."""
    assert FIXTURE_404.is_file(), "the captured vendor string is the source of truth here"
    captured = FIXTURE_404.read_text(encoding="utf-8")
    assert "HTTP 404" in captured and "attestations/sha256:" in captured
    bin_dir, _log = _shim(tmp_path, stderr=captured, exit_code=1)
    proc, outputs, _temp = _resolve(tmp_path, bin_dir=bin_dir)
    assert proc.returncode == 1
    assert outputs["anchor-outcome"] == "unavailable"


def test_resolve_maps_an_unclassifiable_failure_to_unavailable(tmp_path):
    """M2's fallback rule: an unrecognized shape is the most suspicious case."""
    bin_dir, _log = _shim(tmp_path, stderr="weasel", exit_code=1)
    proc, outputs, _temp = _resolve(tmp_path, bin_dir=bin_dir)
    assert proc.returncode == 1
    assert outputs["anchor-outcome"] == "unavailable"
    assert "cannot" in proc.stdout                     # says it could not classify


@pytest.mark.parametrize("exit_code", [4, 2])
def test_resolve_maps_gh_auth_and_cancel_exits_to_unavailable(tmp_path, exit_code):
    bin_dir, _log = _shim(tmp_path, stderr="", exit_code=exit_code)
    proc, outputs, _temp = _resolve(tmp_path, bin_dir=bin_dir)
    assert proc.returncode == 1
    assert outputs["anchor-outcome"] == "unavailable"


def test_resolve_reports_unavailable_when_gh_is_not_on_path(tmp_path):
    """M3 — no shim can reach this: subprocess.run raises FileNotFoundError before any
    exit code or stderr exists, so the process never started."""
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    proc, outputs, _temp = _resolve(tmp_path, path_override=empty_bin)
    assert proc.returncode == 1
    assert outputs["anchor-outcome"] == "unavailable"
    assert "gh was not found on PATH" in proc.stdout
    assert "Traceback" not in proc.stderr


@pytest.mark.parametrize("stdout,marker", [
    ("this is not json at all", "not JSON"),
    ("[]", "empty array"),
    ('{"verificationResult": {}}', "not a list"),
])
def test_resolve_reports_unavailable_on_unparseable_gh_stdout(tmp_path, stdout, marker):
    """M1 — each shape assumption names itself when it fails."""
    bin_dir, _log = _shim(tmp_path, stdout=stdout, exit_code=0)
    proc, outputs, _temp = _resolve(tmp_path, bin_dir=bin_dir)
    assert proc.returncode == 1
    assert outputs["anchor-outcome"] == "unavailable"
    assert marker in proc.stdout
    assert "Traceback" not in proc.stderr


# --- fail-closed refusals ----------------------------------------------------


def test_resolve_fails_closed_when_signer_workflow_is_empty(tmp_path):
    bin_dir, _log = _shim(tmp_path, stdout=_payload())
    proc, _outputs, _temp = _resolve(tmp_path, bin_dir=bin_dir, signer_workflow="")
    assert proc.returncode == 2
    assert "--signer-workflow" in proc.stderr
    assert "<owner>/<repo>" in proc.stderr


def test_resolve_fails_closed_on_an_unreadable_anchor(tmp_path):
    bin_dir, _log = _shim(tmp_path, stdout=_payload())
    proc, _outputs, _temp = _resolve(tmp_path, bin_dir=bin_dir,
                                     anchor=tmp_path / "absent.json")
    assert proc.returncode == 2
    assert "anchor" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_resolve_refuses_when_the_policy_claims_are_absent(tmp_path):
    """A pinned claim name that does not match reality is a FAILURE, not a skip."""
    incomplete = {k: v for k, v in _CERTIFICATE.items() if k != "runnerEnvironment"}
    bin_dir, _log = _shim(tmp_path, stdout=_payload(certificate=incomplete))
    proc, outputs, _temp = _resolve(tmp_path, bin_dir=bin_dir)
    assert proc.returncode == 1
    assert outputs["anchor-outcome"] != "corroborated"
    assert "runnerEnvironment" in proc.stdout


# --- the subject file, the extraction, and the argv --------------------------


def test_resolve_writes_the_subject_file_bytes_from_the_anchor(tmp_path):
    bin_dir, _log = _shim(tmp_path, stdout=_payload())
    _proc, outputs, runner_temp = _resolve(tmp_path, bin_dir=bin_dir)
    subject = pathlib.Path(outputs["subject-path"])
    assert subject.parent == runner_temp
    assert subject.name == "loop-chain-head"
    assert subject.read_bytes() == _HEAD.encode("ascii")
    assert len(subject.read_bytes()) == 64


def test_resolve_extracts_a_bare_predicate_for_compare(tmp_path):
    bin_dir, _log = _shim(tmp_path, stdout=_payload())
    _proc, outputs, _temp = _resolve(tmp_path, bin_dir=bin_dir)
    extracted = json.loads(pathlib.Path(outputs["predicate-path"]).read_text(encoding="utf-8"))
    assert extracted["schema"] == "loop-engineer/verdict@1"
    assert not {"_type", "subject", "predicateType", "predicate"} & extracted.keys()


def test_resolve_never_passes_signer_digest(tmp_path):
    """D4: it resolves to job_workflow_sha, so it invalidates on every push."""
    bin_dir, log = _shim(tmp_path, stdout=_payload())
    _resolve(tmp_path, bin_dir=bin_dir)
    assert "--signer-digest" not in _argv(log)
    assert "--signer-digest" not in SCRIPT.read_text(encoding="utf-8").replace(
        "--signer-digest is NEVER passed", "")


def test_resolve_always_passes_deny_self_hosted_runners(tmp_path):
    bin_dir, log = _shim(tmp_path, stdout=_payload())
    _resolve(tmp_path, bin_dir=bin_dir)
    assert "--deny-self-hosted-runners" in _argv(log)


def test_resolve_passes_the_predicate_type(tmp_path):
    """Without it gh enforces the SLSA default and rejects everything."""
    bin_dir, log = _shim(tmp_path, stdout=_payload())
    _resolve(tmp_path, bin_dir=bin_dir)
    argv = _argv(log)
    assert "--predicate-type" in argv
    assert argv[argv.index("--predicate-type") + 1] == "urn:loop-engineer:verdict:1"
    assert "--source-ref" in argv
    assert argv[argv.index("--source-ref") + 1] == "refs/heads/main"


def test_resolve_invokes_gh_with_shell_false_argv(tmp_path):
    """The anchor head is never interpolated into a shell string."""
    bin_dir, log = _shim(tmp_path, stdout=_payload())
    _resolve(tmp_path, bin_dir=bin_dir)
    argv = _argv(log)
    assert all(" " not in token for token in argv), argv
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    runs = [node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"]
    assert len(runs) == 1
    shell = [kw for kw in runs[0].keywords if kw.arg == "shell"]
    assert shell and isinstance(shell[0].value, ast.Constant) and shell[0].value.value is False
    assert isinstance(runs[0].args[0], ast.Name)          # an argv list, not a string


def test_resolve_isolates_the_single_gh_invocation(tmp_path):
    """D6 — one call site, so a migration off the deprecated route is a one-line change."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    call_sites = [node for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                  and node.func.attr == "run"
                  and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess"]
    assert len(call_sites) == 1
    # AST-level, not a string count: prose ABOUT not using a bare catch must not fail a
    # test whose subject is the code. Every handler names the classes it means.
    blanket = [
        handler for node in ast.walk(tree) if isinstance(node, ast.Try)
        for handler in node.handlers
        if handler.type is None
        or (isinstance(handler.type, ast.Name) and handler.type.id in ("Exception", "BaseException"))
    ]
    assert blanket == [], [ast.dump(h) for h in blanket]


def test_resolve_emits_all_four_step_outputs(tmp_path):
    bin_dir, _log = _shim(tmp_path, stdout=_payload())
    _proc, outputs, _temp = _resolve(tmp_path, bin_dir=bin_dir)
    assert set(outputs) == {"anchor-outcome", "anchor-head", "predicate-path", "subject-path"}
    assert outputs["anchor-head"] == _HEAD
