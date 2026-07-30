#!/usr/bin/env python3
"""Resolve a carried anchor@1 head against the attestation index, via `gh`.

The ONLY place in this repo that invokes `gh`. It lives in scripts/, not loop/, because
it reads the environment and touches the network — the tool layer, following the
scripts/action_scorecard.py precedent of an extracted, TESTED script the composite
action calls.

WHY THE CLASSIFIER PARSES STDERR (normative, from `gh help exit-codes`, gh 2.92.0):

    0  success   1  any failure   2  cancelled   4  authentication required

There is NO distinct exit code separating "no attestation exists" from "an attestation
was found but the signer policy denied it" from "the index was unreachable". All three
arrive as exit 1 — measured live: a 64-hex subject with no matching attestation prints
`Error: HTTP 404: Not Found (…)` and exits 1, the same code a signature failure exits
with. So the classifier must read a vendor string that has no stability contract and
can drift.

Three consequences, all normative:

1. The fallback rule is fail-closed and ABSOLUTE: any output the classifier cannot
   confidently classify becomes `unavailable`. Never `corroborated`. Never a skip. An
   unrecognized stderr shape is the MOST suspicious case, not the most benign one.
2. Exit 4 (auth) and exit 2 (cancelled) are transport-class -> `unavailable`. Only
   exit 0 PLUS a parseable payload PLUS a passing signer-trust policy reaches
   `corroborated`.
3. The 404 branch is driven by a VERBATIM captured fixture
   (scripts/fixtures/gh_attestation_verify/no_attestation_404.txt), not a paraphrase.
   The DENIAL shape cannot be captured before this ships — no attestation this repo has
   minted is verifiable yet — so it is captured in the first post-merge run.

Anything short of a verified 200 plus a successful `gh attestation verify` is
non-promoting, and transport-class failures are separately reportable but exactly as
non-promoting as a clean denial.

Exit codes: 0 corroborated, 1 contradicted-or-unavailable, 2 usage/refusal.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    # A path-invoked script has no installed package in CI (the slice-3b lesson).
    sys.path.insert(0, str(_REPO_ROOT))

from loop.anchor import AnchorError, read_anchor                            # noqa: E402
from loop.attestation import (AttestationPolicyError, anchor_lookup_issue,  # noqa: E402
                              check_signer_trust)
from loop.verdict import PREDICATE_TYPE, SUBJECT_NAME, subject_bytes       # noqa: E402

# refs/heads/main is a deliberate repo-specific constant, NOT a placeholder: ADR 0002
# decision 5 requires a push trigger on the default branch, and this repo's default
# branch is main. It is not parameterized because a --source-ref taken from an untrusted
# input would let a caller widen the pin to any ref and defeat the control.
SOURCE_REF = "refs/heads/main"
PREDICATE_FILENAME = "attested-verdict.json"

# Checked in order. "nothing was found" and transport faults are read FIRST, because
# `HTTP 404: Not Found` would otherwise fall through to a denial pattern.
_UNAVAILABLE_MARKERS = (
    "http 404", "not found", "no attestation", "no matching attestation",
    "http 500", "http 502", "http 503", "http 504", "timeout", "timed out",
    "authentication", "gh auth", "connection refused", "connection reset",
    "temporary failure", "cancelled", "canceled",
)
# Only these reach `contradicted`: an attestation WAS found and did not survive.
#
# `verifying with issuer` is the REAL shape, captured from live gh against this repo's
# first verifiable attestation with a deliberately wrong --signer-workflow
# (scripts/fixtures/gh_attestation_verify/signer_denied.txt). The rest of this tuple was
# a pre-merge guess, and the guess did not match: without this marker the most common
# denial fell through to the fail-closed default and was reported as `unavailable`, which
# is non-promoting either way but loses D5's observability distinction — "it said no" read
# as "I could not look". The fixture is why that was caught rather than assumed.
_CONTRADICTED_MARKERS = (
    "verifying with issuer", "verification failed", "failed to verify", "signature",
    "does not match", "not signed by", "unable to verify", "policy", "mismatch",
)


class ResolveUsageError(Exception):
    """The step was invoked in a way that can never produce a trustworthy answer."""


def _classify_failure(exit_code: int, stderr: str) -> tuple[str, str]:
    """(outcome, detail) for a non-zero `gh` invocation. Never returns corroborated."""
    if exit_code in (2, 4):
        return "unavailable", (f"gh exited {exit_code} (transport class: "
                               f"{'cancelled' if exit_code == 2 else 'authentication'})")
    haystack = stderr.lower()
    for marker in _UNAVAILABLE_MARKERS:
        if marker in haystack:
            return "unavailable", f"gh exited {exit_code}: {stderr.strip()[:400]}"
    for marker in _CONTRADICTED_MARKERS:
        if marker in haystack:
            return "contradicted", f"gh exited {exit_code}: {stderr.strip()[:400]}"
    # Fail-closed: an unrecognized shape is the most suspicious case, not the most benign.
    return "unavailable", (f"gh exited {exit_code} with output this classifier cannot "
                           f"confidently classify: {stderr.strip()[:400]}")


def _verification_result(stdout: str) -> tuple[dict | None, str | None]:
    """The first entry's verificationResult, or (None, detail) naming the shape that failed.

    Each caught class is named deliberately: a blanket catch-all handler would also
    swallow a genuine bug in this file and report it as a clean "index unavailable",
    which is a false-negative gate.
    """
    try:
        payload = json.loads(stdout)                     # JSONDecodeError: banner/empty
    except json.JSONDecodeError as exc:
        return None, f"gh stdout was not JSON: {exc}"
    if not isinstance(payload, list):
        return None, (f"gh stdout was not a list (found {type(payload).__name__}) — the "
                      "--format json contract is an array of attestations")
    if not payload:
        return None, "gh stdout was an empty array: no attestation to evaluate"
    try:
        result = payload[0]["verificationResult"]        # KeyError / TypeError
    except (KeyError, TypeError) as exc:
        return None, f"gh stdout is missing [0].verificationResult: {exc}"
    if not isinstance(result, dict):
        return None, (f"[0].verificationResult is not an object "
                      f"(found {type(result).__name__})")
    return result, None


def _bare_predicate(result: dict) -> tuple[dict | None, str | None]:
    """`.[0].verificationResult.statement.predicate`, so `loop verdict --compare`
    receives a bare verdict@1 and not the envelope it is required to refuse."""
    try:
        predicate = result["statement"]["predicate"]
    except (KeyError, TypeError) as exc:
        return None, f"gh stdout is missing [0].verificationResult.statement.predicate: {exc}"
    if not isinstance(predicate, dict):
        return None, f"the extracted predicate is not an object (found {type(predicate).__name__})"
    return predicate, None


def _run_gh(subject_path: Path, repo: str, signer_workflow: str) -> tuple[int, str, str] | str:
    """Invoke gh as an argv list with shell=False. Returns (code, stdout, stderr), or a
    detail string when the process never started at all — categorically different from a
    bad exit code, because there is no stderr to classify.

    --predicate-type is MANDATORY: it defaults to the SLSA provenance type and would
    reject every verdict@1 attestation. --deny-self-hosted-runners is passed
    unconditionally and there is deliberately no input to disable it.
    --signer-digest is NEVER passed (D4): it resolves to job_workflow_sha, which for a
    non-reusable top-level workflow equals the triggering commit SHA, so it would
    invalidate on every push.
    """
    argv = [
        "gh", "attestation", "verify", str(subject_path),
        "--repo", repo,
        "--predicate-type", PREDICATE_TYPE,
        "--signer-workflow", signer_workflow,
        "--deny-self-hosted-runners",
        "--source-ref", SOURCE_REF,
        "--format", "json",
    ]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, shell=False)
    except FileNotFoundError:
        return "gh was not found on PATH: the process never started, so there is no exit code to classify"
    except OSError as exc:
        return f"gh could not be executed: {exc}"
    return proc.returncode, proc.stdout, proc.stderr


def _emit(outputs: dict[str, str], github_output: str | None) -> None:
    lines = [f"{name}={value}" for name, value in outputs.items()]
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


def resolve(args: argparse.Namespace) -> int:
    if not args.signer_workflow or not args.signer_workflow.strip():
        raise ResolveUsageError(
            "--signer-workflow is mandatory: it is the pin that makes a corroboration "
            "mean anything. Expected the form [host/]<owner>/<repo>/<path>/<to>/<workflow>")
    try:
        anchor = read_anchor(args.anchor)
    except AnchorError as exc:
        raise ResolveUsageError(f"anchor is unusable, refusing to resolve: {exc}") from exc

    head = anchor["chain_head"]
    runner_temp = Path(args.runner_temp)
    runner_temp.mkdir(parents=True, exist_ok=True)
    subject_path = runner_temp / SUBJECT_NAME
    # Regenerated from the carried head alone. Only possible because the subject is a
    # head-bearing FILE: under a synthesized subject-digest there is no preimage, so no
    # file could ever be presented to `gh attestation verify`.
    subject_path.write_bytes(subject_bytes(head))

    outputs = {"anchor-outcome": "unavailable", "anchor-head": head,
               "subject-path": str(subject_path), "predicate-path": ""}

    invocation = _run_gh(subject_path, args.repo, args.signer_workflow)
    if isinstance(invocation, str):
        return _finish("unavailable", invocation, outputs, args.github_output)
    code, stdout, stderr = invocation
    if code != 0:
        outcome, detail = _classify_failure(code, stderr)
        return _finish(outcome, detail, outputs, args.github_output)

    result, shape_detail = _verification_result(stdout)
    if result is None:
        return _finish("unavailable", shape_detail, outputs, args.github_output)

    try:
        trust = check_signer_trust(result, signer_workflow=args.signer_workflow,
                                   source_repository_uri=f"https://github.com/{args.repo}")
    except AttestationPolicyError as exc:
        # A claim name that does not match reality is a FAILURE, never a skip. It is
        # `unavailable` rather than `contradicted`: we could not evaluate the claims, so
        # we cannot honestly say the index said no.
        return _finish("unavailable", f"signer-trust policy refused: {exc}",
                       outputs, args.github_output)
    if not trust["ok"]:
        codes = ", ".join(issue["code"] for issue in trust["issues"])
        return _finish("contradicted", f"signer-trust policy denied: {codes}",
                       outputs, args.github_output)

    predicate, predicate_detail = _bare_predicate(result)
    if predicate is None:
        return _finish("unavailable", predicate_detail, outputs, args.github_output)
    predicate_path = runner_temp / PREDICATE_FILENAME
    predicate_path.write_text(json.dumps(predicate), encoding="utf-8")
    outputs["predicate-path"] = str(predicate_path)
    return _finish("corroborated", None, outputs, args.github_output)


def _finish(outcome: str, detail: str | None, outputs: dict[str, str],
            github_output: str | None) -> int:
    outputs["anchor-outcome"] = outcome
    _emit(outputs, github_output)
    issue = anchor_lookup_issue(outcome, detail=detail)
    if issue is None:
        print(f"::notice::anchor corroborated for {outputs['anchor-head']}")
        return 0
    print(f"::error::{issue['code']}: {issue['message']}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="action_anchor_resolve.py",
        description="Corroborate a carried anchor@1 chain head against the attestation index.")
    parser.add_argument("--anchor", required=True, help="path to a tracked anchor@1 file")
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--signer-workflow", default="",
                        help="[host/]<owner>/<repo>/<path>/<to>/<workflow> (mandatory)")
    parser.add_argument("--runner-temp", required=True, help="scratch directory")
    parser.add_argument("--github-output", default=None,
                        help="append step outputs here instead of stdout")
    args = parser.parse_args(argv)
    try:
        return resolve(args)
    except ResolveUsageError as exc:
        print(f"action_anchor_resolve: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
