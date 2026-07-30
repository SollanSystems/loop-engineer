# ADR 0002: Attest the verdict in CI; never sign in the kernel

- **Status:** Accepted
- **Date:** 2026-07-25
- **Decision owners:** Loop Engineer maintainers
- **Relationship to ADR 0001:** Discharges the decision deferred in ADR 0001
  § Non-goals. ADR 0001 remains Accepted and unamended; its non-equivalence
  statement is restated below as a standing limit.

## Context

Slice 1 gave every run a SHA-256 hash chain with an externally anchorable head,
and said plainly what it does not buy: without an external anchor, a worker that
can rewrite `.loop/` can recompute the chain over the rewritten history, and the
result verifies clean. `loop doctor --expect-chain-head` is the control for
that, and today the expected value is a number a human remembers. Nothing
carries run N's head to run N+1.

What is missing is not more hashing. It is a record of *head-at-time-T* that is
durable, externally timestamped, and not mintable at will by the process under
judgment. GitHub Actions can produce one: an OIDC token exchanged for a
short-lived Fulcio certificate binds the repository, the commit, the workflow
file and ref, the trigger, and the runner environment, and the resulting bundle
is logged publicly and append-only.

Taking that capability introduces a real hazard to the architecture. Signing
requires key material, a network call, a trust root, and a vendor identity —
every one of which ADR 0001 keeps out of the portable layer. The decision below
is primarily about where the boundary runs.

## Decision

### 1. The kernel projects a verdict; it never signs one

A new verb, `loop verdict <workspace>`, emits a `loop-engineer/verdict@1`
document: a projection over `doctor_report()`, the terminal record, and the
chain-bound evidence digests that satisfy the strict verified-evidence bar. It
is a pure function of local state, built with `json` and `hashlib`, reusing
`loop.chain.canonical_json` and `_strict_evidence_failure` rather than
re-deriving either.

The kernel emits the **predicate body only**. It does not construct the in-toto
Statement. `actions/attest` builds the Statement from `subject-*` +
`predicate-type` + `predicate-path`; handing it a complete Statement would nest
a Statement inside a predicate and write a malformed attestation to a permanent
public log.

### 2. The signer lane owns the envelope, the subject, and all cryptography

`action.yml` writes the predicate to `$RUNNER_TEMP`, passes it to
`actions/attest` with `subject-name: loop-chain-head` and
`subject-digest: sha256:<head>`, and declares the resulting attestation URL as
an action output. The calling workflow's job supplies `id-token: write` and
`attestations: write`; a composite action cannot declare its own `permissions:`,
so the step must fail with a legible message when they are absent rather than
surfacing a raw OIDC 403.

The subject is the chain head alone. The source commit is **not** carried in the
predicate: the kernel reads no environment variable today, and making it read
`GITHUB_SHA` would put a vendor identifier inside the portable layer. The Fulcio
certificate already binds the source repository digest more strongly than the
kernel could assert it.

### 3. Predicate identity is `urn:loop-engineer:verdict:1`

Backed by `schemas/verdict.schema.json` with the matching `$id`, following the
convention every existing schema uses. The predicateType is written immutably
into a public log and cannot change without a major version bump, so it names no
vendor host, no organization, and no repository — a rename must not be able to
orphan it.

### 4. Authenticity and agreement are separate checks, in that order

`gh attestation verify` establishes *this was signed by that workflow at that
time*. `loop verdict --compare <file|-> <workspace>` establishes *these claims
agree with local state* — attested head equals the local chain head, attested
evidence digests resolve and match, attested terminal state equals the local
terminal record.

`--compare` reports `signature_checked: false` on every code path, and no flag
may flip it. It accepts a bare `verdict@1` predicate only; unwrapping any
vendor envelope happens outside `loop/`, and a `gh`-shaped envelope is rejected
with a typed error rather than best-effort parsed.

Disagreement is a typed failure. An absent, unverifiable, or ignored attestation
is never a promotion — consistent with in-toto's monotonicity principle, that
ignoring an attestation must never convert a denial into an approval.

### 5. The work ships as two slices

**4a — emission.** Schema, `loop verdict`, the `attest` action input (default
off), a repo CI job restricted to `push` on the default branch, docs, and the
purity tests. Write-only and reversible by ignoring it.

**4b — consumption.** `--compare`, anchor auto-resolution, and the signer-trust
policy. This changes what the hard gate *accepts*, which is a different risk
class and belongs in its own review.

Anchor auto-resolution ships opt-in and default off. When enabled, the resolve
step pins `--signer-workflow`, requires a `push` trigger, and an
explicitly-supplied `expect-chain-head` always wins over a resolved one. The
signer-identity and trigger policy is evaluated by a tested kernel-side function
over already-extracted JSON — still no crypto and no network — because a trust
policy written in YAML fails silently and open.

### 6. Governance changes with it

Human review is required on `loop/**`, `action.yml`, and `.github/workflows/**`.
Everything else stays autonomous. This is the only control that addresses the
largest hazard in the design, and it is a governance decision, not a code one.

## Governing rule

ADR 0001's rule stands: **agents propose; the kernel disposes.** This ADR adds
the seam that makes it survive contact with cryptography:

**The kernel disposes on contents; the CI lane notarizes context; neither is the
other.** The kernel may hash. It must never sign, and it must never establish
authenticity.

## Immediate consequences

1. `loop/verdict.py` imports nothing outside the standard library and `loop.*`.
   No module under `loop/` may reference a signing stack, key material, or an
   OIDC token; no module under `loop/` reads an environment variable. Both are
   asserted mechanically, not intended.
2. The predicate carries digests, enums, and issue **codes** only — never
   free-text detail strings, workspace paths, or task titles. Everything in it
   is public, append-only, and permanent; adding a field is a one-way door.
   An allowlist test enforces the field set.
3. `schemas/verdict.schema.json` is not a contract artifact and does not enter
   `_SCHEMA_FILES`; it follows the `evidence.py` precedent of its own schema id
   and loader.
4. Section 23 is **appended** to `reference/repo-os-contract.md`. No new file
   enters `reference/` — `evals/cases/structural.json` pins that list at eight.
5. Attestation happens on `push` to the default branch only. The PR gate remains
   the existing, unattested `loop doctor` hard gate. Attestation is a post-merge
   notarization of what landed, not a pre-merge approval.
6. No new runtime dependency. This is the constraint that rules out in-kernel
   signature verification, which would require X.509 chain validation, a TUF
   trust root, and Rekor inclusion proofs.

## Standing limits

ADR 0001's non-equivalence statement stands unchanged: **this does not make
structural evidence equivalent to cryptographic attestation.** The signature
attests context — which repository, which commit, which workflow, which trigger,
which runner, at what time. It never attests correctness. A signed verdict over
a weak gate is a signed weak gate.

**The worker can edit the verifier.** An agent with ordinary merge rights can
land a change to `loop/**`, `action.yml`, or the gate workflow and then mint a
perfectly genuine attestation for the loosened gate. Decision 6 is the control;
signing is not. `gh attestation verify` says this outright: only the certificate
and the verified timestamps are unforgeable by the workflow that produced the
attestation — the predicate is user-controllable metadata.

**Auto-resolution detects an unattested rewrite for exactly one run.** An actor
who can land a commit lets CI run once, which mints a genuine attestation over
the rewritten chain, and the next run resolves forward to it. Opt-in changes
operator consent; it does not change that property. The value of decision 5's
resolve step is that it makes the anchoring assumption explicit and revocable,
not that it eliminates self-satisfaction.

**Rekor makes independent historical audit possible; nothing here performs it.**
That is a property of Sigstore's public log, available with or without this
work. The resolve step reads the most recent matching attestation and looks no
further back.

**Fabricated history remains indistinguishable.** `compute_event_hash` draws its
preimage entirely from the record's own fields, so a chain fabricated wholesale
at commit-authoring time is byte-valid. The chain proves order and
non-tampering relative to an anchor; it does not prove the events happened when
claimed.

**Self-hosted runners void the guarantee.** The runner-environment claim is
self-reported. `--deny-self-hosted-runners` is mandatory on the verify side, not
advisory.

**Fork pull requests cannot be attested.** A fork's `pull_request` run receives
no OIDC token. Same-repo branches — how this repo's own agents push — do receive
one, so "forks cannot sign" is not a mitigation available to us.

**Most attestations are never verified.** An attestation nothing gates on is
decoration. If 4b is never enabled, this work ships a publication surface, not a
gate, and should be described that way.

### Limits that become tests

Following the project's habit of shipping defeat conditions as passing tests:
`loop verdict` refuses, typed, on a workspace with no terminal record (a
store-less workspace projects honestly, with a null chain head — the shipped
semantics `reference/repo-os-contract.md` §23 documents); `--compare` reports `signature_checked: false` across every branch;
head disagreement fails with a typed code and agreement passes as the negative
control; predicate conformance is machine-pinned; the field allowlist holds;
import purity and the no-signing / no-environment assertions hold repo-wide; and
an insider-mint case — two attestations, both from the pinned signer workflow,
the second covering a chain rewritten between runs — is asserted as an accepted,
documented limitation rather than left as prose.

## Non-goals

No signature verification, key material, network access, or trust root inside
`loop/`, ever. No local DSSE or HMAC signing — that remains permanently
rejected. No per-event or per-evidence attestations; one verdict per run. No
registry push or storage records. No GitHub Enterprise Server or private
Sigstore instance path. No attestation lifecycle or retention management. No
policy engine deciding who may attest beyond documented `--signer-workflow`
guidance.

## Rejected alternatives

**SLSA Verification Summary Attestation.** Its `verificationResult` is a
PASSED/FAILED enum and `verifiedLevels` is required and typed to SLSA results.
Adopting it would collapse seven typed terminal states to a bit and imply a
build-level evaluation we did not perform. The mapping from `verdict@1` to a VSA
or in-toto SVR predicate is total, so a second attestation in a standard shape
can be added later without a `verdict@1` version bump.

**in-toto SVR.** Purpose-built for policy verdicts, but its payload is a list of
property strings; 64-hex digests would become stringly-typed tokens, which is
the lossy re-encoding this project refuses elsewhere. It is also pre-1.0, and
pinning our hard gate to someone else's pre-1.0 version risk is not a trade we
want.

**in-toto Test Result.** Models individually-named tests with a single
pass/warn/fail. That is CI-runner output, not a multi-criterion contract verdict.

**Cryptography in the kernel.** Requires a trust root, X.509 validation, and
network access; violates the dependency constraint and the boundary this ADR
exists to draw.

**A `github.com` or owned-domain predicateType URI.** The first bakes a vendor
host, organization, and repository name into the portable contract's type
identifier forever, and a rename orphans it permanently. The second creates an
indefinite domain-renewal obligation whose failure mode is a dead type URI in an
append-only log.

**Attesting on pull requests.** An unreviewed branch would mint a signed verdict
under the repository's own identity before any review — the strongest form of the
confused-deputy problem this ADR is trying not to create.

**A multi-subject Statement (chain head and commit).** Not expressible through
`actions/attest`, which accepts at most one of `subject-path` / `subject-digest`
/ `subject-checksums`. The commit is cert-bound regardless, and asserting a
weaker second copy invites a reader to trust it.

## Open verification items

These must be established before the Slice 4 plan relies on them; none changes
the decisions above.

1. **Subject digest algorithm.** The chain head is a SHA-256 over a synthesized
   event preimage, not over retrievable bytes, so the `sha256` DigestSet key
   licenses an inference — fetch, re-hash, compare — that is false here. A
   namespaced key (the `gitCommit` / `dirHash` precedent) is correct in in-toto
   terms, but `actions/attest`'s `subject-digest` input may accept only
   `sha256:`. Resolve by experiment; if the input constrains us, the subject
   name and the §23 preimage spec must carry the disambiguation instead.
2. **Attestation retention and index durability.** Rekor log permanence and
   GitHub's attestation index are different properties. Auto-resolution queries
   the latter. Establish the retention window from GitHub's own documentation
   before enabling 4b; do not assume it from Rekor.
3. **`--signer-digest` as a hard pin.** If it invalidates on every legitimate
   workflow edit it is unusable in practice. Needs a two-revision experiment.
4. **Fork-PR OIDC unavailability** is corroborated but not smoke-tested. Decision
   5 does not depend on it; any future design that attests on PRs must test it
   first.
5. **`create-storage-record` and `push-to-registry` defaults.** Pass both
   explicitly as false so the two-permission claim is true by construction rather
   than by assumed default.

## Amendment (2026-07-29, Slice 4b)

A new dated section rather than an in-place edit of the decision text: the
2026-07-28 erratum is the precedent for a *correction*, and this is a **decision
change**, which earns its own record. Where this amendment and the decisions above
disagree, the amendment governs. Normative detail lives in
`reference/repo-os-contract.md` §24.

**Decision 2 — mechanism change.** The subject is now a head-bearing **file**
(`subject-path`), not `subject-digest: sha256:<head>`. Decision 2's sentence *"The
subject is the chain head alone"* **survives in spirit** — the subject still commits
to nothing but the head — and changes in **mechanism** only. The predicate bytes were
the obvious alternative subject and are **rejected**: `doctor.validation_mode` and
`tool.version` live inside the predicate, so the same run projects `873dfc87…` with
jsonschema and `8de3d88c…` in structural-fallback, and a consumer on another tool
version could never reproduce them. The head is version-independent.

**Decision 4 — its first half was not executable as shipped.** `gh attestation
verify` accepts only `[<file-path> | oci://<image-uri>]` and hashes the file's
**content**; there is no digest-only input, and `--digest-alg` selects only which
algorithm to hash the artifact with. A synthesized chain head has no preimage, so no
artifact could ever be presented for a subject identified by that digest — the
decisive probe was a file *named* after the digest but empty, which made `gh` look up
the SHA-256 of the empty string and return 404. Decision 2's mechanism change makes
the authenticity step executable for the first time.

**Decision 5 — two corrections.**

1. *"Fetch the most recent matching attestation"* is **not implementable from the
   index.** `GET /repos/{owner}/{repo}/attestations/{subject_digest}` is the only list
   operation, the no-digest route 404s, there is no `gh attestation list`, GraphQL's
   `Repository` type exposes no attestation fields, and no ordering guarantee is
   documented. So the head is **carried** in a tracked `loop-engineer/anchor@1` file and
   the attestation *corroborates* it: an attestation can never *discover* a head. Anchor
   trust is exactly ordinary write access to the anchor file — the same class of limit as
   "the worker can edit the verifier".
2. The cross-run check is **ancestry**, not head equality. Appending one event moves the
   head (measured `9d388ae5…` seq 4 → `c336ecdc…` seq 5), so the ADR's resolve target was
   incoherent: feeding run N's head to `--expect-chain-head` at run N+1 fails by
   construction. `loop doctor --expect-chain-ancestor` asks the answerable question, and
   answers it by **replay**, recomputing every hash rather than trusting the stored
   `event_hash` column.

**Open verification item 2 — settled.** No retention window is documented anywhere for
the attestation index (the familiar 90-day/400-day figures are workflow artifacts and
logs). Attestations are **deletable** through permission-gated endpoints, and GitHub's
own guidance recommends deleting ones no longer needed. The REST attestations route is
additionally **deprecated**, route-level, with `Sunset: Fri, 10 Mar 2028`. An absent
anchor attestation is therefore a **typed failure, never a skip** — otherwise an
availability attack on the index becomes a gate bypass.

**Open verification item 3 — settled.** `--signer-digest` pins the signer-digest
certificate extension, populated from the `job_workflow_sha` claim, which for a
non-reusable top-level workflow **equals the triggering commit SHA**. It invalidates on
**every push**, not merely on a workflow edit — observed across all three attestations
this repository had minted, none of whose commits touched `attest.yml` or `action.yml`.
It is therefore **not** a mandatory pin. `--signer-workflow`, byte-identical across all
three certificates, is.

**Decision 6 — the path list grew** by the anchor path (`loop-anchor.json` at any
depth), which is a gate-defining path in exactly the sense `loop/**` and `action.yml`
are: an actor who can edit it re-points the anchor at a head they had attested.
Decision 6 itself remains **documented but not in force** — the live repository ruleset
requires 0 approvals — so slice 4b landed autonomously and CODEOWNERS must not be
described as an operative control until the ruleset requires it.

**What 4b deliberately does not add.** No in-kernel signature verification (permanently
rejected: it needs a trust root, X.509 chain validation and log inclusion proofs, which
is the dependency constraint this ADR exists to hold). No `verdict@1` field carrying an
anchor — adding a field to a permanent public log is a one-way door, and ancestry is a
doctor concern. No schema for the comparison report: it is a report, like
`doctor_report`'s, not an interchange artifact.

## Amendment (2026-07-30, decision 6 is unavailable, not deferred)

A third dated section, for the same reason as the last two: this is a decision
change, not a correction, and it earns its own record. Where this amendment and
anything above it disagree — including `## Standing limits`' *"Decision 6 is the
control; signing is not"* and the Slice 4b amendment's closing paragraph, both of
which describe a control awaiting a ruleset flip — this amendment governs.

**Decision 6 is withdrawn.** Not deferred, not pending: withdrawn. It asked for
human review on `loop/**`, `action.yml`, `.github/workflows/**` and (per the 4b
amendment) the anchor path. This repository cannot supply it. Verified against the
live API on 2026-07-30: `SollanSystems` is the sole collaborator; ruleset
`main protection` carries `required_approving_review_count: 0`,
`require_code_owner_review: false`, `bypass_actors: []` and
`current_user_can_bypass: "never"`; there is no classic branch protection layered
underneath, so there is no admin-override escape either. GitHub does not permit a
pull request author to approve their own pull request.

**What flipping it would actually do**, stated precisely, because the earlier
framing was not: it would not block "every PR". It would leave every
*maintainer-authored* pull request touching an owned path permanently unmergeable,
while *bot-authored* ones — dependabot, copilot-swe-agent — became gated and
approvable. That is close to the inverse of the intent. The hazard decision 6 was
written against is an agent with ordinary merge rights, and in this harness agent
work is authored and merged under the maintainer's own account, so it would fall on
the unmergeable side of that line, not the gated one.

**The escapes are closed, not merely unattractive.** A GitHub App cannot be a code
owner — `CODEOWNERS` admits only users and teams holding write access — so the
approval cannot be automated. Per-path `required_reviewers` needs teams, teams need
an organization, and this repository is user-owned. A second machine *user* account
would technically satisfy the mechanism while producing a signature from the same
hand, which is not review. Adding a bypass actor for the maintainer would restore
mergeability by making the control inert.

**What replaces it: nothing, and that is the finding.** `.github/CODEOWNERS` stays,
demoted to what it honestly is — a record of which paths are gate-defining, useful
to a reader and to any future maintainer, and not a review requirement. The residual
risk is accepted and named: an actor with merge rights can loosen the gate and mint
a genuine attestation for the loosened result, and no control in this repository
prevents it. What the design still buys is legibility, one run late — the
attestation trail records what the gate said at each push under a certificate the
workflow cannot forge, so a loosening is discoverable afterward by comparing runs.
It is worth being exact about the limit of that: `--expect-chain-ancestor` binds an
actor who can rewrite the event store but *not* the repository. Against an actor
with merge rights it is defeated in the same commit, because the anchor file is
editable in that same diff (`reference/repo-os-contract.md` §24: anchor trust is
exactly ordinary write access, no better).

**Reactivation is a fact about the repository, not a task on a list.** If this
project ever has a second maintainer with write access, decision 6 becomes available
and should be reconsidered on its merits. Until then it must not appear anywhere as
pending.

**A ledger-style substitute was considered and rejected.** A required check that
refuses a diff touching a gate-defining path without a matching entry in a tracked
ledger is *mechanically* possible — `pull_request_target` evaluates the workflow
from the base branch's default ref, so the check would not be editable by the pull
request it judges, and the obvious circularity objection does not hold. It is
rejected on merit instead: a ledger entry the author writes in their own pull
request is a self-declaration, not independent review, so it would restate the
problem in a new file. It is also a new mechanism with its own risk class, which by
decision 5's own logic earns its own ADR rather than an amendment clause.
