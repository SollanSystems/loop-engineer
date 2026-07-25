"""Acceptance for the OpenHands recipe: a post-run certifier reads a persisted
Conversation record (``base_state.json`` + ``events/``), projects it through
``loop.integrations``, and emits a contract ``loop doctor`` round-trips and
``loop metrics`` scores clean.

Deterministic and credential-free: every case is driven by a COMMITTED fixture
conversation dir, so this file runs in the default gates matrix on 3.10–3.12.
The live schema-drift alarm against the installed SDK lives in
``test_openhands_sdk_drift.py`` (its own CI job, python 3.12).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_DIR = REPO_ROOT / "examples" / "openhands-certify"
EXAMPLE = EXAMPLE_DIR / "certify_run.py"
CONVERSATIONS = EXAMPLE_DIR / "fixtures" / "conversations"
WORKSPACES = EXAMPLE_DIR / "fixtures" / "workspaces"


def _certify(out_dir: Path, conversation: str, workspace: str = "green") -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
    return subprocess.run(
        [
            sys.executable, "-B", str(EXAMPLE), str(out_dir),
            "--conversation", str(CONVERSATIONS / conversation),
            "--agent-workspace", str(WORKSPACES / workspace),
        ],
        cwd=out_dir.parent, env=env, capture_output=True, text=True,
    )


def _cli(cmd: str, workspace: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", "-m", "loop", cmd, str(workspace)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )


def _terminal(out_dir: Path) -> dict:
    return json.loads((out_dir / ".loop" / "terminal_state.json").read_text(encoding="utf-8"))


def test_finished_and_green_is_succeeded_doctor_clean_and_metrics_clean(tmp_path):
    out = tmp_path / "openhands-run"
    proc = _certify(out, "finished", "green")
    assert proc.returncode == 0, proc.stdout + proc.stderr

    doctored = _cli("doctor", out)
    assert doctored.returncode == 0, doctored.stdout
    assert json.loads(doctored.stdout)["ok"] is True

    terminal = _terminal(out)
    assert terminal["state"] == "Succeeded"
    assert terminal["false_completion"] is False
    assert terminal["evidence"]

    metrics = _cli("metrics", out)
    assert metrics.returncode == 0, metrics.stdout + metrics.stderr
    card = json.loads(metrics.stdout)
    assert card["false_completion_rate"] == 0.0
    assert card["false_completions"] == 0
    assert card["iterations_claiming_success"] >= 1
    assert card["evidence_backed"] is True
    prov = card["provenance"]
    assert prov["unmatched_verify"] == []
    assert prov["unrecognized_outcomes"] == []
    assert prov["fcr_methods_agree"] is True


def test_finished_but_withheld_check_red_is_false_completion_never_succeeded(tmp_path):
    """Issue #37's pinned invariant: the visible check passes, the withheld one
    does not — the run is recorded as a false completion, never laundered."""
    out = tmp_path / "openhands-run-stale"
    proc = _certify(out, "finished", "stale")

    terminal = _terminal(out)
    assert terminal["state"] == "FailedUnverifiable"
    assert terminal["state"] != "Succeeded"
    assert terminal["false_completion"] is True, (terminal, proc.stdout, proc.stderr)
    assert terminal["reason"] == "visible passed but holdout failed — false completion"

    doctored = _cli("doctor", out)
    assert json.loads(doctored.stdout)["ok"] is True  # an honest failure is a valid contract


@pytest.mark.parametrize(
    "conversation,expected",
    [
        ("max-iterations", "FailedBudget"),
        ("stuck", "FailedBudget"),
        ("blocked", "FailedBlocked"),
        ("paused", "AbortedByHuman"),
        ("running", "FailedUnverifiable"),
    ],
)
def test_execution_status_maps_to_typed_terminal(tmp_path, conversation, expected):
    """Every non-happy OpenHands terminal maps to its typed state even though the
    gate over the workspace is GREEN — the engine signal is never overridden by a
    passing check."""
    out = tmp_path / f"openhands-run-{conversation}"
    proc = _certify(out, conversation, "green")
    assert proc.returncode == 1, proc.stdout + proc.stderr

    terminal = _terminal(out)
    assert terminal["state"] == expected
    assert terminal["state"] != "Succeeded"
    assert json.loads(_cli("doctor", out).stdout)["ok"] is True


def test_max_iterations_error_is_budget_not_blocked(tmp_path):
    """The precedence trap: MaxIterationsReached arrives AS execution_status
    'error'. Setting both external_error and budget_exhausted would resolve to
    FailedBlocked (blocked outranks budget) and silently lose the budget signal —
    so the mapper must set exactly one."""
    sys.path.insert(0, str(EXAMPLE_DIR))
    try:
        import certify_run
    finally:
        sys.path.remove(str(EXAMPLE_DIR))

    record = certify_run.read_conversation(CONVERSATIONS / "max-iterations")
    outcome = certify_run.to_engine_outcome(record, ["a.json"])
    assert outcome.budget_exhausted is True
    assert outcome.external_error is None
    assert outcome.reached_end is False

    blocked = certify_run.to_engine_outcome(
        certify_run.read_conversation(CONVERSATIONS / "blocked"), ["a.json"]
    )
    assert blocked.external_error is not None
    assert blocked.budget_exhausted is False
    assert "LLMAuthenticationError" in blocked.external_error


def test_error_status_without_an_error_event_still_blocks(tmp_path):
    """An 'error' record whose ConversationErrorEvent is missing must not fall
    through to a certifiable outcome: external_error is never empty."""
    sys.path.insert(0, str(EXAMPLE_DIR))
    try:
        import certify_run
    finally:
        sys.path.remove(str(EXAMPLE_DIR))

    conv = tmp_path / "conv"
    (conv / "events").mkdir(parents=True)
    (conv / "base_state.json").write_text(
        json.dumps({"execution_status": "error"}), encoding="utf-8"
    )
    outcome = certify_run.to_engine_outcome(certify_run.read_conversation(conv), ["a.json"])
    assert outcome.external_error
    assert outcome.budget_exhausted is False


def test_events_are_read_in_index_order_not_lexical_order(tmp_path):
    """event-{idx:05d} overflows past 99999, where lexical order and index order
    disagree — the last error event must still be the last one written."""
    sys.path.insert(0, str(EXAMPLE_DIR))
    try:
        import certify_run
    finally:
        sys.path.remove(str(EXAMPLE_DIR))

    conv = tmp_path / "conv"
    events = conv / "events"
    events.mkdir(parents=True)
    (conv / "base_state.json").write_text(
        json.dumps({"execution_status": "error"}), encoding="utf-8"
    )
    for idx, code in ((99999, "LLMAuthenticationError"), (100000, "MaxIterationsReached")):
        (events / f"event-{idx:05d}-aaaaaaaa-0000-4000-8000-{idx:012d}.json").write_text(
            json.dumps(
                {
                    "id": f"aaaaaaaa-0000-4000-8000-{idx:012d}",
                    "source": "environment",
                    "code": code,
                    "detail": "",
                    "kind": "ConversationErrorEvent",
                }
            ),
            encoding="utf-8",
        )
    record = certify_run.read_conversation(conv)
    assert [Path(p).name for p in record["event_paths"]][-1].startswith("event-100000-")
    outcome = certify_run.to_engine_outcome(record, ["a.json"])
    assert outcome.budget_exhausted is True
    assert outcome.external_error is None


def test_certifier_imports_no_openhands_package():
    """The certifier is a stdlib reader over a documented on-disk layout — that is
    what keeps it on the 3.10 floor while the SDK requires 3.12."""
    lines = [line.strip() for line in EXAMPLE.read_text(encoding="utf-8").splitlines()]
    assert not [
        line for line in lines
        if line.startswith(("import openhands", "from openhands"))
    ]
