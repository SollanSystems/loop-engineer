"""A pure signer-trust policy over an ALREADY-VERIFIED ``verificationResult``.

This module evaluates claims ``gh attestation verify`` has already established. It
establishes NOTHING itself: it never signs, never verifies a signature, never reaches
the network, and never reads a process variable. It refuses — loudly — when a claim it
needs is absent, because a policy that treats a missing claim as satisfied is worse
than no policy.

Only ``signature.certificate`` and ``verifiedTimestamps`` are unforgeable by the
workflow that produced the attestation (gh's own help text says so). Everything under
``statement.predicate`` is user-controllable metadata and is never read here.

The three anchor-lookup outcomes never collapse: *anything short of a verified 200 plus
a successful ``gh attestation verify`` is non-promoting, and transport-class failures
(5xx, timeout, auth) are separately reportable but exactly as non-promoting as a clean
denial.* The distinction exists for observability, never for differential trust.
"""

from __future__ import annotations

from typing import Any, Mapping

from .contract import ContractIssue

# The certificate claim names gh surfaces under signature.certificate. These leaf names
# cannot be established before merge (F1: gh attestation verify is unrunnable against
# every attestation this repo has minted so far, so no --format json output exists to
# read them from), so they are PINNED and a wrong name produces a refusal rather than a
# silent pass. The live experiment in .github/workflows/attest.yml confirms them; the
# extraction lives in scripts/action_anchor_resolve.py so a correction is a one-line
# change outside loop/. Why these names and not others: repo-os-contract.md #24.
REQUIRED_CERTIFICATE_CLAIMS = ("subjectAlternativeName", "sourceRepositoryURI",
                               "runnerEnvironment")

# At least one must be present. ADR 0002 decision 5 requires a `push` trigger but names
# no claim, and the two candidates are equally plausible — so require either and refuse
# when neither appears.
_TRIGGER_CLAIM_ALIASES = ("githubWorkflowTrigger", "buildTrigger")

ANCHOR_LOOKUP_OUTCOMES = ("corroborated", "contradicted", "unavailable")

_LOOKUP_CODES = {
    "contradicted": "anchor_attestation_contradicted",
    "unavailable": "anchor_attestation_unavailable",
}
_NON_PROMOTING = (
    "anything short of a verified 200 plus a successful `gh attestation verify` is "
    "non-promoting, and transport-class failures (5xx, timeout, auth) are separately "
    "reportable but exactly as non-promoting as a clean denial"
)


class AttestationPolicyError(ValueError):
    """A claim the policy needs is absent, or an outcome it cannot classify was passed."""


def _certificate(result: object) -> Mapping[str, Any]:
    if not isinstance(result, Mapping):
        raise AttestationPolicyError(
            f"verificationResult must be an object, found {type(result).__name__}")
    signature = result.get("signature")
    certificate = signature.get("certificate") if isinstance(signature, Mapping) else None
    if not isinstance(certificate, Mapping):
        raise AttestationPolicyError(
            "verificationResult.signature.certificate is absent or is not an object — "
            "the certificate is one of only two fields the originating workflow cannot "
            "forge, so its absence is a refusal, never a pass")
    timestamps = result.get("verifiedTimestamps")
    if not isinstance(timestamps, list) or not timestamps:
        raise AttestationPolicyError(
            "verificationResult.verifiedTimestamps is absent or empty — an unwitnessed "
            "attestation is not a trusted one")
    missing = [claim for claim in REQUIRED_CERTIFICATE_CLAIMS if claim not in certificate]
    if missing:
        raise AttestationPolicyError(
            f"certificate is missing required claim(s): {', '.join(missing)} — a pinned "
            "claim name that does not match gh's actual JSON must fail loudly, so this "
            "refuses rather than treating the claim as satisfied")
    if not any(alias in certificate for alias in _TRIGGER_CLAIM_ALIASES):
        raise AttestationPolicyError(
            "certificate carries neither trigger claim "
            f"({' nor '.join(_TRIGGER_CLAIM_ALIASES)}) — the trigger cannot be checked")
    return certificate


def _normalize_identity(value: object) -> str:
    """Strip an optional scheme, an optional `@<ref>` suffix, and a trailing slash.

    Exact equality after normalization, deliberately NOT a substring test: the SAN is
    `https://<host>/<owner>/<repo>/<path>@<ref>` while the pin is
    `[host/]<owner>/<repo>/<path>`, and a substring match would accept a crafted
    repository whose name merely ends with the pinned path.
    """
    text = str(value)
    text = text.split("@", 1)[0]
    for scheme in ("https://", "http://"):
        if text.startswith(scheme):
            text = text[len(scheme):]
            break
    return text.rstrip("/")


def _identity_agrees(claim: object, pin: str) -> bool:
    normalized_claim = _normalize_identity(claim)
    normalized_pin = _normalize_identity(pin)
    return normalized_claim in (normalized_pin, f"github.com/{normalized_pin}")


def check_signer_trust(result: object, *, signer_workflow: str, source_repository_uri: str,
                       expect_trigger: str = "push") -> dict[str, Any]:
    """Evaluate the pinned signer claims. Denials are typed codes, never booleans.

    There is deliberately no ``signer_digest`` parameter (D4): the signer-digest pin
    resolves to the ``job_workflow_sha`` claim, which for a non-reusable top-level
    workflow equals the *triggering commit SHA* — so it invalidates on every push, not
    merely on a workflow edit. ``--signer-workflow`` is the mandatory pin.
    Full reasoning: reference/repo-os-contract.md #24.

    ``signature_checked`` is ``False`` here too: this evaluates a verdict gh already
    reached, and re-asserting authenticity would be a claim this module cannot make.
    """
    certificate = _certificate(result)
    issues: list[dict[str, Any]] = []
    if not _identity_agrees(certificate["subjectAlternativeName"], signer_workflow):
        issues.append(ContractIssue(
            "signer_workflow_mismatch",
            f"certificate signer {certificate['subjectAlternativeName']!r} is not the "
            f"pinned workflow {signer_workflow!r}"))
    if not _identity_agrees(certificate["sourceRepositoryURI"], source_repository_uri):
        issues.append(ContractIssue(
            "signer_repository_mismatch",
            f"certificate sourceRepositoryURI {certificate['sourceRepositoryURI']!r} is "
            f"not the pinned repository {source_repository_uri!r}"))
    if certificate["runnerEnvironment"] != "github-hosted":
        issues.append(ContractIssue(
            "self_hosted_runner",
            f"certificate runnerEnvironment is {certificate['runnerEnvironment']!r}; "
            "--deny-self-hosted-runners is passed unconditionally, so gh should already "
            "have refused — this check is defensive"))
    trigger = next((certificate[alias] for alias in _TRIGGER_CLAIM_ALIASES
                    if alias in certificate), None)
    if trigger != expect_trigger:
        issues.append(ContractIssue(
            "signer_trigger_mismatch",
            f"certificate trigger is {trigger!r}, expected {expect_trigger!r}"))
    return {"ok": not issues, "signature_checked": False, "issues": issues}


def anchor_lookup_issue(outcome: object, *, detail: str | None = None) -> dict[str, Any] | None:
    """Map an anchor-lookup outcome to its issue, or ``None`` when corroborated.

    An unknown outcome RAISES rather than defaulting to anything: a silent default here
    would be the difference between a gate and a suggestion.
    """
    if outcome == "corroborated":
        return None
    code = _LOOKUP_CODES.get(outcome) if isinstance(outcome, str) else None
    if code is None:
        raise AttestationPolicyError(
            f"unknown anchor lookup outcome {outcome!r}; expected one of "
            f"{', '.join(ANCHOR_LOOKUP_OUTCOMES)}")
    reason = {
        "contradicted": "an attestation was found and it does not corroborate the carried "
                        "chain head (I looked and it said no)",
        "unavailable": "no attestation was found, or the index could not be reached at all "
                       "(I could not look)",
    }[outcome]
    message = f"{reason}: {_NON_PROMOTING}"
    if detail:
        message = f"{message} — {detail}"
    return ContractIssue(code, message)
