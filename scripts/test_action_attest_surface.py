"""scripts/test_action_attest_surface.py — action.yml's attest and anchor surface.

D1 is the load-bearing change of the slice: the subject becomes a head-bearing FILE, so
`gh attestation verify` is executable against a verdict@1 attestation for the first time.

A composite action that swallows the resolve step's exit code turns the whole gate into
decoration — Task 8's tests exercise the SCRIPT, and nothing there pins that action.yml
lets its failure reach the job. That wiring is pinned here.
"""
from __future__ import annotations

import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
ACTION = ROOT / "action.yml"

# Scoped by step id/name, not a blanket string ban: this repo contains three DELIBERATE
# advisory uses that must keep passing — `set +e` in "loop inspect (scorecard)" (inspect
# is advisory) and in "PR scorecard comment (optional)" (non-fatal on any API failure),
# and `if: always()` on "chain head (anchor surface)" (a mismatch is exactly the run whose
# head an operator needs recorded). A blanket ban would fail on correct existing code and
# be deleted by the next implementer instead of fixed.
_GATING_STEPS = ("resolve the anchor attestation", "compare the attested verdict")


@pytest.fixture(scope="module")
def action() -> dict:
    return yaml.safe_load(ACTION.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def steps(action) -> dict[str, dict]:
    return {step.get("name"): step for step in action["runs"]["steps"] if step.get("name")}


def test_action_attests_a_subject_path_not_a_subject_digest(steps):
    """D1. Under the retired form the subject digest was a SHA-256 over a synthesized
    event preimage: no bytes hash to it, so no artifact could ever be presented."""
    attest = steps["attest verdict"]
    assert attest["uses"].startswith("actions/attest@")
    assert "subject-path" in attest["with"]
    assert "subject-digest" not in attest["with"]
    assert "subject-name" not in attest["with"]


def test_action_never_passes_subject_digest_anywhere():
    assert "subject-digest" not in ACTION.read_text(encoding="utf-8")


def test_subject_file_basename_is_the_pinned_subject_name(steps):
    from loop.verdict import SUBJECT_NAME

    body = steps["chain-head subject file"]["run"]
    assert f'"${{RUNNER_TEMP}}/{SUBJECT_NAME}"' in body
    assert steps["attest verdict"]["with"]["subject-path"] == "${{ steps.subject.outputs.path }}"


def test_subject_file_is_written_by_emit_subject(steps):
    """One definition of the byte form, so the attest side and the resolve side cannot
    disagree about 64 bytes."""
    assert "loop verdict --emit-subject" in steps["chain-head subject file"]["run"]


def test_action_pins_push_to_registry_and_create_storage_record_false(steps):
    """create-storage-record's live default is true (F5), so the explicit pin does work."""
    with_block = steps["attest verdict"]["with"]
    assert with_block["push-to-registry"] is False
    assert with_block["create-storage-record"] is False


def test_action_declares_the_anchor_and_signer_workflow_inputs(action):
    for name in ("anchor", "signer-workflow"):
        assert action["inputs"][name]["default"] == ""
        assert action["inputs"][name]["required"] is False


def test_action_requires_signer_workflow_when_anchor_is_set(steps):
    """The script fails closed; the action must actually hand it the input."""
    resolve = steps["resolve the anchor attestation"]
    assert "--signer-workflow" in resolve["run"]
    assert resolve["env"]["LOOP_SIGNER_WORKFLOW"] == "${{ inputs.signer-workflow }}"
    assert "scripts/action_anchor_resolve.py" in resolve["run"]


def test_action_outputs_the_anchor_outcome(action):
    assert "anchor-outcome" in action["outputs"]
    assert action["outputs"]["anchor-outcome"]["value"] == \
        "${{ steps.anchor.outputs.anchor-outcome }}"


def test_explicit_expect_chain_head_wins_over_the_resolved_anchor(steps):
    """ADR decision 5's precedence, expressed in the guard rather than left implicit —
    and the drop is announced, because a silently dropped anchor is worse than a refused
    one."""
    assert steps["resolve the anchor attestation"]["if"] == \
        "${{ inputs.anchor != '' && inputs.expect-chain-head == '' }}"
    skip = steps["anchor resolution skipped (explicit head wins)"]
    assert skip["if"] == "${{ inputs.anchor != '' && inputs.expect-chain-head != '' }}"
    assert "GITHUB_STEP_SUMMARY" in skip["run"]


def _effective(run: str) -> str:
    """The shell body with comment-only lines removed.

    The comments in these steps explain WHY they must not swallow an exit code, and they
    name the constructs they avoid. Matching against raw text would let accurate prose
    fail a test whose subject is the executed script.
    """
    return "\n".join(line for line in run.splitlines() if not line.strip().startswith("#"))


@pytest.mark.parametrize("name", _GATING_STEPS)
def test_resolve_step_and_downstream_checks_have_no_continue_on_error(steps, name):
    """B2 — a swallowed exit code here makes the gate decoration."""
    step = steps[name]
    assert "continue-on-error" not in step        # not even `false`
    body = _effective(step["run"])
    assert "set +e" not in body
    assert "|| true" not in body
    assert body.strip(), "the step must still actually run something"


def test_compare_is_guarded_on_head_equality_while_ancestry_is_unconditional(steps):
    """Found by whole-branch review: `--compare` treats an ancestor head as a
    DISAGREEMENT (a verdict projects one run), so running it against an older attested
    predicate on a store that legitimately grew fails every time — which would make the
    `anchor` input unusable for the cross-run detection it exists for. Ancestry is the
    cross-run gate and must be unconditional; agreement is a same-run question and must
    be guarded on head equality, with the skip announced."""
    body = steps["compare the attested verdict"]["run"]
    ancestry, _, remainder = body.partition("loop doctor --expect-chain-ancestor")
    assert remainder, "the ancestry gate must be present"
    assert "loop verdict --compare" not in ancestry, "ancestry must run FIRST, unguarded"
    assert 'if [ "$ANCHOR_HEAD" = "$CURRENT_HEAD" ]' in remainder
    assert "loop verdict --compare" in remainder
    assert "GITHUB_STEP_SUMMARY" in remainder, "a skipped compare must be announced"
    env = steps["compare the attested verdict"]["env"]
    assert env["CURRENT_HEAD"] == "${{ steps.chain-head.outputs.chain-head }}"


def test_no_gating_step_is_marked_if_always(steps):
    """always() runs a step after an upstream failure and is the standard way a gate's
    red goes unseen. The pre-existing `if: always()` on "chain head (anchor surface)" is
    deliberate and is excluded by name."""
    for name in _GATING_STEPS:
        assert "always()" not in str(steps[name].get("if", ""))
    # Non-vacuous: the one deliberate always() really is present, so the exclusion is a
    # scoping decision rather than an absence of any always() to find.
    assert "always()" in str(steps["chain head (anchor surface)"]["if"])
