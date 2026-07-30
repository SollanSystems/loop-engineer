"""scripts/test_attest_workflow.py — the live experiment's shape.

Task 10 cannot be validated before merge: attest.yml fires on push to main only, so a
real attestation mints only after landing. The FIRST post-merge run IS the experiment,
and its falsifiable check is `subject[0].digest.sha256 != predicate.chain.head` — an
inequality that was false in all three attestations this repo minted before this slice.

What IS pinnable now is that the experiment resolves through the SHIPPED script rather
than a hand-written duplicate. Without that, the only code getting real-gh mileage would
be one no adopter ever runs.
"""
from __future__ import annotations

import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
ATTEST = ROOT / ".github" / "workflows" / "attest.yml"
CI = ROOT / ".github" / "workflows" / "ci.yml"
_SIGNER_WORKFLOW = "SollanSystems/loop-engineer/.github/workflows/attest.yml"


@pytest.fixture(scope="module")
def attest_text() -> str:
    return ATTEST.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def attest_steps(attest_text) -> dict[str, dict]:
    document = yaml.safe_load(attest_text)
    return {step.get("name"): step
            for step in document["jobs"]["verdict"]["steps"] if step.get("name")}


def test_attest_workflow_resolves_through_the_shipped_script(attest_steps):
    """M4 — the same entry point action.yml's `anchor` input calls."""
    body = attest_steps["resolve the attestation we just minted"]["run"]
    assert "scripts/action_anchor_resolve.py" in body
    assert (ROOT / "scripts" / "action_anchor_resolve.py").is_file()


def test_attest_workflow_contains_no_inline_gh_attestation_call(attest_text):
    """M4's teeth. Without this pin an inline duplicate can be reintroduced beside the
    script and the two drift silently."""
    assert "gh attestation" not in attest_text


def test_attest_workflow_writes_a_real_anchor_file_for_the_resolve(attest_steps):
    """So the anchor READ path is exercised, not bypassed."""
    body = attest_steps["resolve the attestation we just minted"]["run"]
    assert "loop-engineer/anchor@1" in body
    assert "chain_head" in body
    assert "--anchor" in body


def test_attest_workflow_pins_the_signer_workflow(attest_steps):
    """D4: --signer-workflow is the mandatory pin; --signer-digest invalidates on every
    push, so it is deliberately absent."""
    body = attest_steps["resolve the attestation we just minted"]["run"]
    assert f"--signer-workflow {_SIGNER_WORKFLOW}" in body
    assert "--signer-digest" not in body


def test_attest_workflow_pins_the_predicate_type_and_denies_self_hosted():
    """Both are the SCRIPT's responsibility, so this cross-checks that the script the
    workflow invokes really carries them unconditionally — without --predicate-type gh
    enforces the SLSA default and rejects every verdict@1 attestation."""
    script = (ROOT / "scripts" / "action_anchor_resolve.py").read_text(encoding="utf-8")
    assert '"--predicate-type", PREDICATE_TYPE' in script
    assert '"--deny-self-hosted-runners"' in script
    body = ATTEST.read_text(encoding="utf-8")
    for disabling in ("--no-deny-self-hosted", "--predicate-type "):
        assert disabling not in body, disabling


def test_attest_workflow_asserts_the_subject_name_and_digest_inequality(attest_steps):
    body = attest_steps["assert the resolved attestation proves D1 landed"]["run"]
    assert 'subject.name == "loop-chain-head"' in body
    assert "len(raw) == 64" in body
    assert "subject_digest != head" in body


def test_attest_workflow_runs_compare_against_the_resolved_predicate(attest_steps):
    """Consumes the script's predicate-path output, not a hand-rolled jq extraction."""
    steps = attest_steps["assert the resolved attestation proves D1 landed"]
    assert "loop verdict --compare" in steps["run"]
    assert steps["env"]["PREDICATE"] == "${{ steps.resolve.outputs.predicate-path }}"
    assert "jq" not in steps["run"]


def test_attest_workflow_bounds_the_index_consistency_retry(attest_steps):
    """An unbounded or silently-passing wait would make the step unfalsifiable."""
    body = attest_steps["resolve the attestation we just minted"]["run"]
    assert "for attempt in 1 2 3 4 5 6" in body
    assert 'if [ "$attempt" = "6" ]' in body
    assert "exit 1" in body


def test_attest_workflow_still_runs_only_on_push_to_main(attest_text):
    """ADR decision 5's confused-deputy guard, unchanged: attesting on a PR would mint a
    signed verdict under the repository's identity before review."""
    document = yaml.safe_load(attest_text)
    triggers = document[True] if True in document else document["on"]
    assert set(triggers) == {"push"}
    assert triggers["push"]["branches"] == ["main"]


def test_ci_exercises_ancestry_on_a_grown_store_and_a_fallback_leg():
    """The within-run ancestry pair (the only ancestry coverage this repo can honestly
    claim) plus the structural-fallback leg that gives mode parity its CI teeth."""
    document = yaml.safe_load(CI.read_text(encoding="utf-8"))
    anchor_steps = {step.get("name"): step
                    for step in document["jobs"]["anchor-live"]["steps"] if step.get("name")}
    body = anchor_steps["Ancestry survives a grown store where head equality cannot"]["run"]
    assert "--expect-chain-ancestor" in body and "--expect-chain-head" in body
    assert "chain_anchor_not_ancestor" in body and "chain_anchor_mismatch" in body

    fallback = document["jobs"]["gates-fallback"]
    installs = [step["run"] for step in fallback["steps"] if "run" in step]
    assert not any("jsonschema" in line for line in installs if "pip install" in line)
    assert any("find_spec" in line for line in installs), "the leg must prove it is the leg"
