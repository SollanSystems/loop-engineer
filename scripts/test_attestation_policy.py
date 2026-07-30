"""scripts/test_attestation_policy.py — the signer-trust policy establishes NOTHING.

It is a pure function over a `verificationResult` gh has ALREADY verified. Only
`signature.certificate` and `verifiedTimestamps` are unforgeable by the workflow that
produced the attestation (gh's own help says so); everything under `statement.predicate`
is user-controllable metadata and is never read here.

It must REFUSE — loudly — when a claim it needs is absent, because a policy that treats
a missing claim as satisfied is worse than no policy. The exact leaf claim names cannot
be established before merge (F1), so a wrong name yields a refusal, not a silent pass.
"""
from __future__ import annotations

import copy
import inspect
import re

import pytest

from loop.attestation import (ANCHOR_LOOKUP_OUTCOMES, REQUIRED_CERTIFICATE_CLAIMS,
                              _TRIGGER_CLAIM_ALIASES, AttestationPolicyError,
                              anchor_lookup_issue, check_signer_trust)

_WORKFLOW = "SollanSystems/loop-engineer/.github/workflows/attest.yml"
_REPO_URI = "https://github.com/SollanSystems/loop-engineer"
_SAN = f"https://github.com/{_WORKFLOW}@refs/heads/main"


def _result(*, certificate=None, drop=(), **overrides):
    base_certificate = {
        "subjectAlternativeName": _SAN,
        "sourceRepositoryURI": _REPO_URI,
        "runnerEnvironment": "github-hosted",
        "githubWorkflowTrigger": "push",
    }
    # drop FIRST, then apply overrides — otherwise dropping the alias defaults would
    # also remove the single alias a caller just asked for.
    for key in drop:
        base_certificate.pop(key, None)
    if certificate is not None:
        base_certificate.update(certificate)
    result = {
        "signature": {"certificate": base_certificate},
        "verifiedTimestamps": [{"type": "Tlog", "timestamp": "2026-07-29T00:00:00Z"}],
    }
    result.update(overrides)
    return result


def _check(result):
    return check_signer_trust(result, signer_workflow=_WORKFLOW,
                              source_repository_uri=_REPO_URI)


def _codes(verdict):
    return {issue["code"] for issue in verdict["issues"]}


def test_required_certificate_claims_are_pinned():
    assert REQUIRED_CERTIFICATE_CLAIMS == ("subjectAlternativeName", "sourceRepositoryURI",
                                           "runnerEnvironment")
    assert _TRIGGER_CLAIM_ALIASES == ("githubWorkflowTrigger", "buildTrigger")
    assert ANCHOR_LOOKUP_OUTCOMES == ("corroborated", "contradicted", "unavailable")


def test_signer_trust_passes_on_a_conformant_result():
    verdict = _check(_result())
    assert verdict["ok"] is True
    assert verdict["issues"] == []


def test_signer_trust_refuses_when_signature_certificate_is_absent():
    for result in ({"verifiedTimestamps": [1]},
                   {"signature": {}, "verifiedTimestamps": [1]},
                   {"signature": {"certificate": "not-an-object"}, "verifiedTimestamps": [1]}):
        with pytest.raises(AttestationPolicyError):
            _check(result)


@pytest.mark.parametrize("missing", ["subjectAlternativeName", "sourceRepositoryURI",
                                     "runnerEnvironment", "<all>"])
def test_signer_trust_refuses_when_a_required_claim_is_absent(missing):
    """D10.8 — an absent claim is a refusal, never a pass."""
    if missing == "<all>":
        result = _result(drop=REQUIRED_CERTIFICATE_CLAIMS)
    else:
        result = _result(drop=(missing,))
    with pytest.raises(AttestationPolicyError) as excinfo:
        _check(result)
    if missing != "<all>":
        assert missing in str(excinfo.value)


@pytest.mark.parametrize("timestamps", [None, []])
def test_signer_trust_refuses_when_verified_timestamps_are_absent_or_empty(timestamps):
    """An unwitnessed attestation is not a trusted one."""
    result = _result()
    if timestamps is None:
        del result["verifiedTimestamps"]
    else:
        result["verifiedTimestamps"] = timestamps
    with pytest.raises(AttestationPolicyError) as excinfo:
        _check(result)
    assert "verifiedTimestamps" in str(excinfo.value)


@pytest.mark.parametrize("alias", ["githubWorkflowTrigger", "buildTrigger"])
def test_signer_trust_accepts_either_trigger_claim_alias(alias):
    result = _result(drop=_TRIGGER_CLAIM_ALIASES, certificate={alias: "push"})
    assert _check(result)["ok"] is True


def test_signer_trust_refuses_when_neither_trigger_alias_is_present():
    with pytest.raises(AttestationPolicyError) as excinfo:
        _check(_result(drop=_TRIGGER_CLAIM_ALIASES))
    assert "trigger" in str(excinfo.value)


def test_signer_workflow_mismatch_is_denied():
    result = _result(certificate={
        "subjectAlternativeName": "https://github.com/other/repo/.github/workflows/x.yml@refs/heads/main"})
    verdict = _check(result)
    assert verdict["ok"] is False
    assert "signer_workflow_mismatch" in _codes(verdict)


def test_source_repository_mismatch_is_denied():
    verdict = _check(_result(certificate={"sourceRepositoryURI": "https://github.com/other/repo"}))
    assert "signer_repository_mismatch" in _codes(verdict)


def test_self_hosted_runner_is_denied():
    verdict = _check(_result(certificate={"runnerEnvironment": "self-hosted"}))
    assert "self_hosted_runner" in _codes(verdict)


def test_non_push_trigger_is_denied():
    verdict = _check(_result(certificate={"githubWorkflowTrigger": "workflow_dispatch"}))
    assert "signer_trigger_mismatch" in _codes(verdict)


def test_signer_trust_ignores_statement_predicate_entirely():
    """Rule 2, behavioral — the stronger of the two. statement.predicate is
    user-controllable metadata; contradicting the certificate from there changes nothing."""
    honest = _check(_result())
    lying = copy.deepcopy(_result())
    lying["statement"] = {
        "predicateType": "urn:loop-engineer:verdict:1",
        "predicate": {"schema": "loop-engineer/verdict@1", "run_id": "whatever",
                      "subjectAlternativeName": "https://github.com/other/repo/x.yml",
                      "sourceRepositoryURI": "https://github.com/other/repo",
                      "runnerEnvironment": "self-hosted", "githubWorkflowTrigger": "pull_request"},
    }
    assert _check(lying) == honest


def test_signer_trust_source_never_reads_statement():
    """Rule 2, structural."""
    assert "statement" not in inspect.getsource(check_signer_trust)


def test_signer_trust_reports_signature_checked_false():
    """The policy evaluates a verdict gh already reached; it does not re-establish it."""
    assert _check(_result())["signature_checked"] is False


def test_signer_trust_has_no_signer_digest_parameter():
    """D10.10's code half: --signer-digest pins job_workflow_sha, which for a
    non-reusable top-level workflow equals the triggering commit SHA — it invalidates
    on EVERY push, not merely on a workflow edit."""
    assert "signer_digest" not in inspect.signature(check_signer_trust).parameters


def test_anchor_lookup_corroborated_yields_no_issue():
    assert anchor_lookup_issue("corroborated") is None


def test_anchor_lookup_contradicted_has_its_own_code():
    issue = anchor_lookup_issue("contradicted", detail="signature did not verify")
    assert issue["code"] == "anchor_attestation_contradicted"
    assert "signature did not verify" in issue["message"]


def test_anchor_lookup_unavailable_has_a_distinct_code():
    """D10.6 — 'I could not look' must not collapse into 'it said no'."""
    unavailable = anchor_lookup_issue("unavailable", detail="HTTP 404: Not Found")
    contradicted = anchor_lookup_issue("contradicted", detail="denied")
    assert unavailable["code"] == "anchor_attestation_unavailable"
    assert unavailable["code"] != contradicted["code"]


def test_anchor_lookup_transport_error_is_unavailable_not_contradicted():
    issue = anchor_lookup_issue("unavailable", detail="HTTP 503 from the attestations index")
    assert issue["code"] == "anchor_attestation_unavailable"
    # Distinct for OBSERVABILITY only — equally non-promoting.
    assert "non-promoting" in issue["message"]


def test_anchor_lookup_refuses_an_unknown_outcome():
    """No silent default: an unknown outcome is a programming error, not a pass."""
    for outcome in ("promoted", "", None, "CORROBORATED"):
        with pytest.raises(AttestationPolicyError):
            anchor_lookup_issue(outcome)


def test_anchor_lookup_codes_match_the_public_issue_code_pattern():
    for outcome in ("contradicted", "unavailable"):
        assert re.fullmatch(r"[a-z0-9_]{1,64}", anchor_lookup_issue(outcome)["code"])
