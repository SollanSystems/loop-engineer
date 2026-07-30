# Slice 4b — `verdict@1` Consumption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **NORMATIVITY (read once, apply everywhere).** In this plan the **Acceptance line and the AC/step text are normative; every code snippet is ILLUSTRATIVE.** This project has twice shipped a slice where a worker treated a plan's code sketch as the contract while the acceptance text said otherwise (S2 `terminal_superseded`, S3a adversarial kernel — both cost a repair cycle). If a snippet and an Acceptance line disagree, the Acceptance line wins and the snippet is wrong.

**Goal:** Make the attested verdict *consumable*. Give the kernel a `loop verdict --compare` agreement check, a replay-based chain-**ancestry** gate that survives a growing store, a tested signer-trust policy over already-verified claims, and an anchor carry-channel — and change the attested subject from a synthesized digest to a head-bearing **file**, which is the change that makes `gh attestation verify` executable against a `verdict@1` attestation for the first time.

**Architecture:** Three new pure leaf modules plus one new pure predicate, all stdlib + `loop.*` only, none of which sign, verify a signature, touch the network, or read an environment variable:

- `loop/chain.py` gains `head_sequence(events, digest)` — replay from sequence 0, recomputing every hash, returning the sequence at which `digest` **was** the head, or `None`. This is the cross-run check that works on a chain that legitimately grew.
- `loop/anchor.py` — read a tracked `loop-engineer/anchor@1` file that *carries* a previously attested head. The attestation corroborates the carried head; it can never discover it.
- `loop/attestation.py` — a pure signer-trust policy over an **already-extracted** `verificationResult`, plus the three-outcome anchor-lookup vocabulary. It evaluates claims `gh` already verified; it establishes nothing itself.
- `loop/verdict.py` gains `compare_verdict()` (agreement, never authenticity) and `subject_bytes()` (the one definition of the subject file's byte form).
- The network, the environment, and `gh` live in `scripts/action_anchor_resolve.py` — the tool layer, following the `scripts/action_scorecard.py` precedent of an extracted, tested script invoked from `action.yml`.

**Tech Stack:** Python 3.10+ stdlib only (`json`, `hashlib`, `re`, `subprocess` in `scripts/` only). No new runtime dependencies. Tests via pytest under `uv run`. CI via `actions/attest` + `gh attestation verify` in a composite-action step.

**Baseline (main @ `c493804`, clean, no open PRs).** State the dependency set with every number — this repo has three legitimate baselines:

| Environment | Command | Result |
|---|---|---|
| **canonical** (this plan's zero-regression reference) | `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts` | **1353 passed / 18 skipped** |
| structural-fallback leg | same, without `--with jsonschema` | **1256 passed / 115 skipped** |
| CI-equivalent (live checkout, `--with hypothesis`) | canonical command run from the **live checkout** (not a fresh worktree) `+ --with hypothesis` | **1365 passed / 15 skipped** |

`pyyaml` is required even in the fallback leg (`scripts/validate_frontmatter.py` imports `yaml` unconditionally, so a truly bare env fails *collection*). Fresh worktrees run ~2 fewer passes / ~2 more skips than the live checkout — the documented checked-when-present class (`scripts/test_contract_records.py:180`, `scripts/test_docs_adoption.py:68`). **Pin every zero-regression assertion to the gate environment you actually measured in**, and say which.

> **Baseline measurement trap (carried from 4a).** Running the suite via `uv run --project <worktree>` installs the wheel, which materializes `loop/_bundle/` and makes `scripts/test_resources.py::test_repo_checkout_resolves_to_repo_dirs` fail *correctly*. Measure from inside the worktree (`bash -c 'cd <worktree> && uv run --with … pytest -q … scripts'`), never with `--project`.

**Source of decisions:** `/tmp/claude-1000/-mnt-c-Dev-projects-loop-engineer/f56b13c4-a1fa-4923-bf9e-66fef64fa76a/scratchpad/slice4b-binding-decisions.md` (D1–D10, governor-adjudicated and settled) and `…/slice4b-verified-findings.md` (F1–F6, the operator's own live probes). Those two files **override `docs/adr/0002-ci-attested-verdict.md`** for this slice — specifically its decisions 2, 4 and 5 — and this slice appends an `## Amendment (2026-07-29, Slice 4b)` section to the ADR recording exactly that. Where this plan and D1–D10 disagree, **D1–D10 win and this plan is wrong.**

**Expected new tests: **215 collected cases** (214 in the feature PR + 1 in the same-day post-merge correction) (per-task deltas below; 2 of them are `pytest.importorskip("jsonschema")`-gated and skip in the fallback leg). Projected end state:

| Environment | Expected |
|---|---|
| canonical | **1568 passed / 18 skipped** (1353 + 215) |
| structural-fallback | **1469 passed / 117 skipped** (1256 + 213 pass, +2 skip) |
| CI-equivalent (live checkout, hypothesis) | **1580 passed / 15 skipped** (1365 + 215) |

If an implementer needs an additional case, **update the arithmetic in this plan in the same commit** — never loosen an assertion to `>=`.

---

## Global Constraints

- **Zero new runtime dependencies.** `loop/` imports stdlib + `loop.*` only. `pyproject.toml` `[project.optional-dependencies]` stays exactly `yaml`, `schemas`, `dev`.
- **Kernel purity, unchanged and non-negotiable (D7).** No module under `loop/` may reference a signing stack (sigstore, cosign, fulcio, rekor, DSSE), key material, or an OIDC token; `grep -rn "environ\|getenv" --include=*.py loop/` stays at **zero** matches; no module under `loop/` opens a socket or shells out. `subprocess`, `urllib`, `socket`, `http` are banned inside `loop/`.
- **The kernel emits a predicate, never a Statement.** No `_type`, `subject`, `predicateType`, or `predicate` key is produced by anything under `loop/`. `subject_bytes()` produces the subject's *bytes*, which is a projection of the head — not an envelope, not a signature.
- **`--compare` reports `signature_checked: false` on every code path and no flag may flip it (D7, D10.1).** The kernel establishes agreement; it never establishes authenticity.
- **The signer-trust policy establishes nothing.** It is a pure function over JSON `gh` has already verified. It must **refuse** — typed, loudly — when a claim it needs is absent, because a policy that treats a missing claim as satisfied is worse than no policy.
- **No new file in `reference/`.** `evals/cases/structural.json:14-23` pins `reference_filenames` at **8**. The new normative section is **appended** to `reference/repo-os-contract.md` as **§24**, and §23's "subject seam" paragraph is **rewritten** (D1 makes its central claim false).
- **No version bump.** Tasks 1–11 land as one feature PR. Version surfaces (`pyproject.toml`, `.claude-plugin/plugin.json`, README, `scripts/test_docs_version.py`, CHANGELOG's released heading) move only in a separate release-cut PR.
- **`main` is protected** — PR required, force-push and deletion blocked, no bypass actors. All work lands via PR. Decision 6 (code-owner review) is **documented but not in force**: the live ruleset requires 0 approvals, so 4b lands autonomously and the PR body records the gap (D9). **Never describe CODEOWNERS as an operative control.**
- **Issues #96 / #97 / #98 are out of scope and stay open (D9).** Each was re-reproduced live against `c493804`; none touches verdict, `--compare`, anchor resolution, or signer trust. #98 sits on the evidence-write path this slice *reads*, but 4b degrades safely without it — `_strict_evidence_failure` already treats a malformed record as a failure. Ship them as separate small PRs.
- Repo env quirks: no system pytest — always `uv run`. The Bash deny-list blocks `rm`, bare `cd`, `VAR=` prefixes, `timeout`, `printf`, `source` — use `git -C <path>`, absolute paths, and `bash -c '…'`.

**Canonical test command** (run from the repo root):

```bash
uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts
```

---

## What this slice deliberately does NOT do

Say this in §24 and in the PR body, because a reader who assumes otherwise has a false sense of a gate:

1. **`--compare` never checks a signature.** `signature_checked` is the literal `false` on every branch, there is no flag to change it, and the CLI rejects `--verify-signature` / `--signature` / `--signer-*` outright. Authenticity is `gh attestation verify`'s job, it runs *first*, and neither check implies the other.
2. **`--compare` does not unwrap envelopes.** It accepts a **bare** `verdict@1` predicate only. An in-toto Statement (`_type` / `subject` / `predicateType` / `predicate`) and a `gh --format json` wrapper (a top-level array, or `verificationResult` / `attestation` keys) are **typed refusals** that name what was found and the documented jq path (`.[0].verificationResult.statement.predicate`) the operator skipped. Best-effort parsing of a vendor envelope inside the kernel is exactly how a trust boundary rots.
3. **Anchor resolution cannot discover a head (D2/F2).** `GET /repos/{o}/{r}/attestations/{subject_digest}` is the only list operation; the no-digest route is 404; there is no `gh attestation list`; GraphQL's `Repository` type has zero attestation fields; and **no ordering guarantee is documented**. You must already know the digest to look anything up. So the head is **carried** in a tracked anchor file and the attestation proves the carried head was notarized. ADR 0002 decision 5's "fetch the most recent matching attestation" is not implementable and this slice corrects it rather than papering over it.
4. **Anchor trust is exactly ordinary write access — no better.** An actor who can edit the anchor file re-points it at a head they had attested. That is the same class of limit as the ADR's existing "the worker can edit the verifier". CODEOWNERS gains the anchor path (D2), and CODEOWNERS is a control only while the ruleset enforces it.
5. **A 404 is not evidence of absence.** It is consistent with never-attested, attested-then-deleted, and a transient index fault. The distinct codes in D5's cases (2) and (3) exist for **observability**, so an operator reading a log knows what the gate saw. They must never become differential trust: **anything short of a verified 200 *plus* a successful `gh attestation verify` is non-promoting, and transport-class failures (5xx, timeout, auth) are separately reportable but exactly as non-promoting as a clean denial.** That sentence is the difference between a gate and a suggestion, and §24 carries it verbatim.
6. **Public/private asymmetry (D8).** Public repositories sign against the Sigstore Public Good instance and its public transparency log; **private** repositories use GitHub's own Sigstore instance, which has **no transparency log** and federates only with Actions. The independent-audit property this work leans on exists for public repos and does not exist for private ones. This repo's live attestation carries a genuine Rekor inclusion proof with a checkpoint signed by `rekor.sigstore.dev`; an adopter on a private repo gets a signature and no public log.
7. **`--signer-digest` is not a mandatory pin (D4).** It pins Fulcio's `BuildSignerDigest` extension (OID `1.3.6.1.4.1.57264.1.10`), populated from the OIDC `job_workflow_sha` claim. For this repo's non-reusable top-level workflow that value **equals the triggering commit SHA** — it differed across all three attestations this repo has minted even though none of those commits touched `attest.yml` or `action.yml`. It does not merely invalidate on a workflow edit; **it invalidates on every push.** `--signer-workflow` (whose `BuildSignerURI` was byte-identical across all three certs) is the mandatory pin; `--signer-digest` is offered only as an optional, human-invoked one-off.
8. **The REST attestations route is deprecated (D6).** Measured, and isolated against four clean control endpoints: `Deprecation: Tue, 10 Mar 2026 00:00:00 GMT` / `Sunset: Fri, 10 Mar 2028 00:00:00 GMT`, on both the 200 and the 404 route — route-level. The fetch/verify path therefore goes through `gh attestation verify`, a GitHub-maintained abstraction that will be migrated over whatever replaces the raw route. **The sunset date is recorded in §24 so a future maintainer meets it as a documented fact rather than an outage.**
9. **Auto-resolution detects an unattested rewrite at best one run late**, unchanged from ADR 0002's standing limits. An actor who can land a commit lets CI run once, which mints a genuine attestation over the rewritten chain. Opt-in changes operator consent; it does not change that property.
10. **This repo cannot dogfood cross-run ancestry.** `.github/workflows/attest.yml` seeds an *ephemeral* workspace in `$RUNNER_TEMP` on every run, so its chain head is new by construction and there is no persistent store to anchor. The anchor-corroboration path therefore gets (a) synthetic coverage through a fake `gh` on `PATH`, and (b) a real *within-run* grown-store ancestry exercise. A true cross-run dogfood needs a persistent store and is out of scope. Say so; do not let the CI green read as a cross-run proof.

---

## Existing interfaces this slice consumes

Read these before starting. Every signature below was read from HEAD `c493804`, not recalled.

| Symbol | Location | Signature / behavior |
|---|---|---|
| `doctor_report` | `loop/contract.py:1103` | `(target: str \| Path, *, mode: str \| None = None, expect_chain_head: str \| None = None) -> dict[str, Any]`. Calls `validate_contract` then `event_consistency_issues`; returns `{**report, "event_store": event_store, "issues": issues, "ok": report["ok"] and not event_issues}`. **The one place a new anchor kwarg must thread through.** |
| `ContractIssue` | `loop/contract.py:46` | `class ContractIssue(dict)` with `__init__(self, code: str, message: str, path: Path \| None = None)`. The single issue shape; every new code uses it. |
| `_strict_evidence_failure` | `loop/contract.py:856` | `(entry: object, paths: LoopPaths, bound: Mapping[str, tuple[str, ...]] \| None) -> str \| None`. The ONE definition of the verified-evidence bar. Consumed transitively via `build_verdict`; **do not restate it.** |
| `VALIDATION_MODES` | `loop/contract.py:32` | `("basic", "strict", "release")`. Note: `--mode basic` yields `validation_mode == "structural-fallback"`, **not** `"basic"`. |
| `SCHEMA_IDS` | `loop/contract.py:34-39` | `("loop-engineer/manifest@1", "loop-engineer/state@1", "loop-engineer/tasks@1", "loop-engineer/terminal@1")` — contract objects only. `anchor@1` must stay out, exactly as `verdict@1` does. |
| `ValidationModeError` | `loop/contract.py:42` | `RuntimeError` subclass. |
| `canonical_json` | `loop/chain.py:27` | `(value: Any) -> str` — `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False, allow_nan=False)`, then a UTF-8 encodability check. Raises `ChainHashError`. |
| `compute_event_hash` | `loop/chain.py:40` | `(record: Mapping[str, Any]) -> str` — SHA-256 over `canonical_json` of the 12 `_PREIMAGE_FIELDS`. |
| `_PREIMAGE_FIELDS` | `loop/chain.py:16-20` | `("schema","run_id","sequence","event_id","type","actor","ts","causation_id","correlation_id","payload","artifact_hashes","prev_event_hash")`. |
| `link_issue` | `loop/chain.py:45` | `(record: Mapping[str, Any], prev_head: Mapping[str, Any] \| None) -> str \| None` — one incremental chain check; `None` means `record` legally extends `prev_head`. **Reuse this for the ancestry replay; do not write a second link checker.** |
| `verify_chain` | `loop/chain.py:66` | `(events: Iterable[Mapping[str, Any]], *, expected_head: str \| None = None) -> dict[str, Any]` returning `{"ok","issues","chained_events","unchained_prefix","head"}` where `head` is `{"sequence","event_hash"} \| None`. The fold shape `head_sequence` must mirror. |
| `ChainHashError` | `loop/chain.py:23` | `ValueError` subclass. |
| `resolve_loop_paths` | `loop/paths.py:57` | `(target: str \| Path) -> LoopPaths`. |
| `LoopPaths` | `loop/paths.py:14-30` | `@dataclass(frozen=True)` with `workspace, loop_dir, manifest, state, tasks, runlog, terminal, spec, workflow, contract` + `to_json()`. `.terminal` already resolves `terminal_state.json` dual-path. |
| `build_verdict` | `loop/verdict.py:115` | `(target: str \| Path, *, mode: str \| None = None) -> dict[str, Any]` — the local projection `--compare` compares against. Refuses without a terminal record, so `--compare` inherits that refusal. |
| `VerdictError` | `loop/verdict.py:26` | `ValueError` subclass — "A verdict cannot be projected from this workspace." |
| `VERDICT_SCHEMA_ID` / `PREDICATE_TYPE` | `loop/verdict.py:22-23` | `"loop-engineer/verdict@1"` / `"urn:loop-engineer:verdict:1"`. |
| `_load_verdict_schema` | `loop/verdict.py:30` | The own-loader pattern to mirror for `anchor@1`. |
| `_terminal_record` | `loop/verdict.py:41` | Typed refusals for absent / unreadable / non-object / missing-or-non-boolean `false_completion`. |
| `event_consistency_issues` | `loop/runtime.py:282-337` | `(target, *, mode=None, expect_chain_head=None) -> tuple[dict[str, Any], list[dict[str, Any]]]`. Absent-store branch at `:287-300`; unreadable-store branch at `:301-314`; the R007 "an errored check fails, it never skips" guard is the shared `try`. |
| the head-equality compare | `loop/runtime.py:323-327` | `actual = (status["chain_head"] or {}).get("event_hash")`; `actual != expect_chain_head` → `_anchor_mismatch(...)`. **Exact current-head equality, not ancestry** — this is F3's finding and the reason a new gate is needed. |
| `_anchor_mismatch` | `loop/runtime.py:278` | `ContractIssue("chain_anchor_mismatch", message)`. |
| `_events` | `loop/runtime.py:132` | `(target, mode) -> tuple[Path, str, list[dict], dict]` — discovers the run id, reads rows read-only, validates every event, raises `RuntimeStoreError` on `empty_store`. The ordered event list the ancestry replay needs. |
| `_store_path` | `loop/runtime.py:38` | `(target) -> Path` — `.loop/events.db`. |
| `RuntimeStoreError` | `loop/runtime.py:30` | `RuntimeError` subclass carrying `.code` (`missing_store`, `empty_store`, `ambiguous_run_id`, `corrupt_store`, `invalid_event`). |
| `status_report` | `loop/runtime.py:181` | `(target, *, mode=None) -> dict` including `chain_head` and `unchained_prefix`. |
| `bound_artifact_digests` | `loop/runtime.py:385` | `(target, mode=None) -> dict[str, tuple[str, ...]] \| None`; `None` = no store, and the caller **must** degrade explicitly. |
| `_bound_evidence_issues` | `loop/runtime.py:340` | Precedent: a doctor-gated check that pays for **one extra read-only fold** of the store, documented as acceptable in §22. |
| `read_event_rows` | `loop/events.py:265` | `(conn, run_id, *, since_sequence=None) -> list[dict]`; records always carry `prev_event_hash`/`event_hash` keys, `None` on legacy stores. |
| `schemas_dir` | `loop/_resources.py:34` | `() -> Path` — bundle-first, repo-relative fallback. |
| `EVIDENCE_SCHEMA_ID` | `loop/evidence.py:35` | `"loop-engineer/evidence@1"` — the id-naming convention. |
| `verify_bundle_is_green` | `loop/evidence.py:41` | `(bundle: Mapping[str, Any]) -> bool` — the repo's ONE green-marker rule. |
| `_load_evidence_schema` | `loop/evidence.py:59` | Own-loader precedent. |
| `_print_json` | `loop/__main__.py:119` | `(report: dict) -> int` — prints indented JSON, returns `0 if report.get("ok") else 1`. **Reuse for the comparison report so exit 0/1 comes free.** |
| `_extract_mode_flag` | `loop/__main__.py:124` | `(argv) -> tuple[str \| None, list[str]]`; validates against `VALIDATION_MODES`. |
| `_extract_value_flag` | `loop/__main__.py:150` | `(argv, flag) -> tuple[str \| None, list[str]]`; supports both `--flag v` and `--flag=v`. |
| `_COMMANDS` / `_READ_COMMANDS` / `_USAGE` / `_HELP` | `loop/__main__.py:15,19,21,23` | CLI wiring. `verdict` is already in all four. |
| verdict dispatch | `loop/__main__.py:374-383` | Catches `(VerdictError, ChainHashError)` → `print(f"verdict: {exc}", file=sys.stderr); return 2`. |
| the 64-hex guard | `loop/__main__.py:264-267` | `re.fullmatch(r"[0-9a-f]{64}", expect_chain_head) is None` → exit 2. Copy this shape for the ancestor flag. |
| wrong-command flag guards | `loop/__main__.py:268-274`, `:291-297` | **The precedent that must be followed for every new flag**: without it, `scaffold --compare x` CREATES a directory named after the flag. |
| the `attest verdict` step | `action.yml:144-156` | `subject-name: loop-chain-head`, `subject-digest: sha256:${{ steps.chain-head.outputs.chain-head }}`, `predicate-type`, `predicate-path`, `push-to-registry: false`, `create-storage-record: false`. **D1 replaces the subject inputs here.** |
| the `chain head (anchor surface)` step | `action.yml:100-122` | `if: always()`; writes `chain-head=<value>` to `$GITHUB_OUTPUT` and a step-summary line. The head the subject file is written from. |
| the `verdict predicate` step | `action.yml:124-142` | Pre-checks `ACTIONS_ID_TOKEN_REQUEST_URL`, runs `loop verdict "$LOOP_PATH" > "${RUNNER_TEMP}/verdict.json"`. |
| `scripts/action_scorecard.py` invocation | `action.yml:175-176` | The precedent for an extracted, tested script invoked from the composite action. |
| attest workflow gate + assert | `.github/workflows/attest.yml:86-109` | `id: gate` `uses: ./` with `attest: "true"`, then the falsifiability assertion that an attestation URL exists and the observed head equals the seeded one. |
| `.github/CODEOWNERS` | `.github/CODEOWNERS:1-9` | `/loop/`, `/schemas/`, `/action.yml`, `/.github/workflows/`, `/.github/CODEOWNERS` — all `@SollanSystems`. D2 adds the anchor path. |
| `reference_filenames` | `evals/cases/structural.json:14-23` | Eight entries. `scripts/self_eval.py` compares live repo state against it — a new `reference/` file fails the gate. |
| `_terminal_workspace` / `_chained_workspace` / `_record_at` / `drop_triggers` | `scripts/test_adversarial_chain.py:60,80,102` + `scripts/chain_fixtures.py:48` | The existing wholesale-rewrite machinery. `test_full_rewrite_with_recompute_passes_without_anchor_pinned` (`:182`) is the fixture the D10.4 probe extends. |
| `scripts/ci_anchor_probe.py:44` | `seed(target) -> str` | Seeds a doctor-clean chained workspace through the real writer path and returns the head doctor observes. Reused by the within-run ancestry job. |

### Live GitHub facts, read from the source this session — do not re-derive from memory

- `actions/attest` inputs (read from `repos/actions/attest/contents/action.yml`): at most one of `subject-path` / `subject-digest` / `subject-checksums`; **`subject-name` is "Required when identifying the subject with the `subject-digest` input"** — i.e. optional with `subject-path`, where the name derives from the file. `create-storage-record` **defaults to `true`**, so `action.yml`'s explicit `false` is doing real work. Outputs: `bundle-path`, `attestation-id`, `attestation-url`, `storage-record-ids`.
- `gh attestation verify` (gh 2.92.0) usage is `gh attestation verify [<file-path> | oci://<image-uri>] [--owner | --repo] [flags]`. **There is no digest-only input** — `--digest-alg` selects *which algorithm to hash the artifact with*. Relevant flags: `--predicate-type` (defaults to `https://slsa.dev/provenance/v1`, so it **must** be passed), `--signer-workflow` in the form `[host/]<owner>/<repo>/<path>/<to>/<workflow>`, `--cert-identity` (exact SAN match), `--source-ref`, `--deny-self-hosted-runners`, `--format json`, `--limit`, `--bundle`.
- `--format json` emits an array of objects, each with an `attestation` and a `verificationResult`. Inside `verificationResult`: `signature.certificate` (parsed X.509), `verifiedTimestamps`, and `statement` (`subject`, `predicateType`, `predicate`). gh's own help states that **only `signature.certificate` and `verifiedTimestamps` cannot be manipulated by the workflow that originated the attestation** — `statement.predicate` is user-controllable metadata.
- The `--signer-workflow` value for this repo is `SollanSystems/loop-engineer/.github/workflows/attest.yml`. The full SAN (for `--cert-identity`, if ever needed) is `https://github.com/SollanSystems/loop-engineer/.github/workflows/attest.yml@refs/heads/main`.

---

## New issue codes and where they surface

Every code is `snake_case` and matches the `verdict@1` schema's `^[a-z0-9_]{1,64}$` pattern, because **doctor issue codes are the population from which `verdict.doctor.issue_codes` is drawn** — a permanent, public, append-only log. `loop verdict` does not itself pass the anchor flags today, so these codes cannot reach a predicate in this slice; they are nonetheless permanent-log-*eligible* and are pattern-tested as such. Each is documented in §24.

| Code | Surface | Meaning |
|---|---|---|
| `chain_anchor_not_ancestor` | `loop doctor` issues → eligible for `verdict.doctor.issue_codes` | `--expect-chain-ancestor` (or a resolved `--anchor`) was supplied and the digest was **never** the head at any sequence of the replayed chain. **Deliberately distinct from `chain_anchor_mismatch`** (D3): "your current head is not what I expected" and "the head you anchored is not in my history at all" are different facts, and one shared code would collapse them in a public log. Also raised — never skipped — when the store is absent or unreadable. |
| `anchor_file_unreadable` | `loop doctor` issues | The `--anchor` path is absent, unreadable, not UTF-8, or not JSON. |
| `anchor_file_invalid` | `loop doctor` issues | Readable, but not a conformant `anchor@1` document (absent or malformed `chain_head`). |
| `anchor_attestation_contradicted` | `loop/attestation.py` → the resolve step's annotations and `anchor-outcome` output | D5 case (2): the index was reached, an attestation was found, and it does **not** corroborate the carried head. "I looked and it said no." |
| `anchor_attestation_unavailable` | same | D5 case (3): no attestation was found (404), **or** the index could not be reached at all (5xx, timeout, auth). "I could not look." Distinct from (2) **for observability only** — never for differential trust. Both are equally non-promoting. |
| `signer_workflow_mismatch` | `loop/attestation.py` policy result | The certificate's signer SAN is not the pinned workflow. |
| `signer_repository_mismatch` | same | `sourceRepositoryURI` is not the pinned repository. |
| `self_hosted_runner` | same | `runnerEnvironment` is not `github-hosted`. Defensive: `--deny-self-hosted-runners` is passed unconditionally, so gh should already have refused. |
| `signer_trigger_mismatch` | same | The trigger claim is not `push`. |
| `verdict_head_disagreement` | `loop verdict --compare` report | Attested `chain.head` ≠ locally projected head. |
| `verdict_terminal_disagreement` | same | Attested `terminal.state`, `terminal.completion_policy`, or `terminal.false_completion` ≠ local. |
| `verdict_run_id_disagreement` | same | Attested `run_id` ≠ local. |
| `verdict_evidence_disagreement` | same | The attested and local verified-evidence digest sets differ. |

`--compare`'s **typed refusals** are not issue codes — they are `VerdictError` messages on stderr with exit 2, following the existing `verdict` dispatch (`loop/__main__.py:374-383`): a document that is not a bare `verdict@1` predicate produced no comparison at all, so reporting `ok: false` would imply a comparison happened.

---

## File structure

| File | Change | Responsibility |
|---|---|---|
| `schemas/anchor.schema.json` | **create** | The `loop-engineer/anchor@1` carry-channel shape. Not a contract artifact; own `$id`, own loader, out of `SCHEMA_IDS`. |
| `loop/anchor.py` | **create** | `ANCHOR_SCHEMA_ID`, `DEFAULT_ANCHOR_FILENAME`, `AnchorError`, `read_anchor()`. Pure; no env, no network. |
| `loop/attestation.py` | **create** | `check_signer_trust()`, `anchor_lookup_issue()`, the claim-name constants, `AttestationPolicyError`. Pure over already-extracted JSON. |
| `loop/chain.py` | modify | Add `head_sequence(events, digest)` — replay-based ancestry, I/O-free, reusing `link_issue`. |
| `loop/verdict.py` | modify | Add `SUBJECT_NAME`, `subject_bytes()`, `compare_verdict()`, `COMPARISON_CODES`. |
| `loop/runtime.py` | modify | `event_consistency_issues(..., expect_chain_ancestor=None)`; the ancestry gate + the conditional `event_store.anchor` block. |
| `loop/contract.py` | modify | Thread `expect_chain_ancestor` through `doctor_report` (`:1103-1112`). |
| `loop/__main__.py` | modify | `verdict --compare` / `--emit-subject`; `doctor --expect-chain-ancestor` / `--anchor`; wrong-command guards; `_USAGE` / `_HELP`. |
| `scripts/action_anchor_resolve.py` | **create** | The resolve step: read the anchor, regenerate the subject file, run `gh attestation verify`, classify the outcome, apply the signer-trust policy, extract the bare predicate. The only place `gh` is invoked. |
| `action.yml` | modify | **D1**: subject becomes a head-bearing file (`subject-path`). New `anchor` + `signer-workflow` inputs; `anchor-outcome` output; the resolve step. |
| `.github/workflows/attest.yml` | modify | The live experiment: verify what was just attested, then `--compare` it. |
| `.github/workflows/ci.yml` | modify | Extend `anchor-live` with the within-run grown-store ancestry exercise. |
| `.github/CODEOWNERS` | modify | Add the anchor path (D2). |
| `reference/repo-os-contract.md` | modify | **Append §24**; **rewrite** §23's subject-seam paragraph. |
| `docs/adr/0002-ci-attested-verdict.md` | modify | Append `## Amendment (2026-07-29, Slice 4b)`. |
| `CHANGELOG.md` | modify | Unreleased entry. |
| `scripts/fixtures/gh_attestation_verify/no_attestation_404.txt` | **create** | Verbatim captured `gh attestation verify` stderr for the "no attestation exists" case, so the stderr classifier is pinned against a real vendor string rather than a paraphrase (M2). `scripts/` file lists are not pinned by `evals/cases/structural.json`. A second fixture (`signer_denied.txt`) is capturable only **post-merge** — Task 10, Step 5. |
| `scripts/test_anchor.py` | **create** | Anchor + subject-byte-form tests (25). |
| `scripts/test_chain_ancestry.py` | **create** | The pure ancestry predicate (9). |
| `scripts/test_doctor_anchor_ancestry.py` | **create** | The doctor gate end-to-end (30). |
| `scripts/test_verdict_compare.py` | **create** | The agreement report (25). |
| `scripts/test_verdict_cli.py` | modify | `--compare` / `--emit-subject` CLI surface (+18). |
| `scripts/test_attestation_policy.py` | **create** | Signer trust + the three-outcome vocabulary (25). |
| `scripts/test_verdict_purity.py` | modify | Purity extended to the new modules (+8). |
| `scripts/test_action_anchor_resolve.py` | **create** | The resolve step against a fake `gh` — incl. the subprocess/parse exception enumeration, the absent-`gh` path, and the real-stderr fixture (23). |
| `scripts/test_action_attest_surface.py` | **create** | `action.yml` shape pins, incl. D1 and the no-swallowed-exit-code pins (12). |
| `scripts/test_attest_workflow.py` | **create** | Workflow shape + experiment pins, incl. "resolves through the shipped script" (9). |
| `scripts/test_docs_slice4b.py` | **create** | §24 / ADR / CODEOWNERS / CHANGELOG doc-parity, incl. the retired-subject-form pin (20). |
| `docs/superpowers/plans/2026-07-29-slice4b-verdict-consumption.md` | **track** | This plan. Currently **untracked** (`git status` → `??`). Committed by **Task 12**, in a separate fast-follow docs PR after the feature PR merges (#84 / #99 / #104 precedent). |

---

## The anchor shape (binding)

`loop-engineer/anchor@1`. Default filename **`loop-anchor.json`** at the workspace root. **It must be tracked and must not live under `.loop/`** (gitignored in this repo; `read_anchor` refuses a path with a `.loop` component so an adopter cannot accidentally carry an anchor inside the tree it certifies).

```json
{
  "schema": "loop-engineer/anchor@1",
  "chain_head": "9f2c…64hex",
  "sequence": 41,
  "attestation_id": "37747063",
  "run_id": "coverage-repair",
  "recorded_at": "2026-07-29T00:00:00+00:00"
}
```

`schema` and `chain_head` are **required**; `sequence`, `attestation_id`, `run_id`, `recorded_at` are optional provenance. `chain_head` is `^[0-9a-f]{64}$` with `maxLength: 64` — **`maxLength` accompanies every `pattern`**, because jsonschema's `pattern` is `re.search` semantics and a bare anchored pattern accepts a trailing newline (the hole closed in PR #89). Nothing in the anchor is trusted: it is a *carried claim* whose only function is to give the lookup a digest to ask about.

---

## Decision traceability — D1–D10 → tasks, and D10's ten defeat conditions → named tests

Walk this table before starting and again at whole-branch review. A decision with no task is an unimplemented decision.

| Decision | Realized by |
|---|---|
| **D1** subject becomes a head-bearing file | Task 1 (`subject_bytes`, the byte-form pin), Task 5 (`--emit-subject`), **Task 9** (`action.yml`), **Task 10** (the live experiment), Task 11 (§23 rewrite + amendment) |
| **D2** anchor corroborates a carried head; anchor is a gate-defining path | Task 1 (`anchor@1`, `read_anchor`), Task 3 (`--anchor`), Task 8 (the resolve step), Task 11 (§24 + CODEOWNERS) |
| **D3** the cross-run check is ancestry, by replay | **Task 2** (`head_sequence`), **Task 3** (the doctor gate + the distinct code), Task 10 (within-run live exercise), Task 11 (§24) |
| **D4** `--signer-workflow` mandatory, `--signer-digest` optional | Task 6 (no `signer_digest` parameter), Task 8 (never passed), Task 10 (pinned in the workflow), Task 11 (§24 + amendment) |
| **D5** absent/unverifiable/deleted anchors FAIL, never skip; three non-collapsing outcomes | Task 3 (absent/unreadable store never skips), **Task 6** (`anchor_lookup_issue`), Task 8 (classification), Task 11 (§24's non-promoting sentence) |
| **D6** REST route deprecated; prefer the CLI; record the date | Task 8 (single `gh` call site, `gh attestation verify` path), Task 11 (§24 records `10 Mar 2028`) |
| **D7** kernel never signs, verifies, or reads the environment; bare predicate only | Task 4 (refusals + `signature_checked`), Task 6 (pure policy), **Task 7** (mechanical purity), Task 11 (§24) |
| **D8** public/private asymmetry is an honest limit | Task 11 (§24 + a doc-parity pin) |
| **D9** governance and scope | Global Constraints, Out of scope, the PR-body checklist items |
| **D10** the ten defeat conditions | below |

| D10 | Named test(s) | Task |
|---|---|---|
| 1. `signature_checked: false` on every branch | `test_compare_reports_signature_checked_false_on_every_report_branch` (5 cases), `test_signature_checked_is_never_assigned_true_in_source`, `test_signature_checked_literal_is_always_false`, `test_verdict_never_advertises_a_signature_flag` (3 cases) | 4, 5, 7 |
| 2. Head disagreement typed; agreement is the negative control | `test_compare_head_disagreement_is_typed`, `test_compare_passes_on_a_self_projected_verdict` | 4 |
| 3. Statement- and gh-wrapper-shaped inputs are typed refusals | `test_compare_refuses_an_in_toto_statement` (4), `test_compare_refuses_a_gh_format_json_array_wrapper`, `test_compare_refuses_a_gh_verification_result_object`, `test_compare_refusal_names_the_unwrapping_step` | 4 |
| 4. Rewrite-detection probe | `test_ancestry_detects_a_wholesale_rewrite_that_self_verifies_clean` | 3 |
| 5. A forged row bearing the anchored `event_hash` does not satisfy ancestry | `test_head_sequence_recomputes_and_refuses_a_forged_event_hash_column`, `test_ancestry_refuses_a_forged_row_bearing_the_anchored_digest_end_to_end` | 2, 3 |
| 6. A missing anchor attestation fails with its own code, distinct from disagreement | `test_anchor_lookup_unavailable_has_a_distinct_code`, `test_anchor_lookup_transport_error_is_unavailable_not_contradicted`, `test_resolve_reports_unavailable_on_a_404` | 6, 8 |
| 7. The subject file is exactly 64 lowercase hex bytes, no trailing newline | `test_subject_bytes_is_exactly_64_lowercase_hex_with_no_trailing_newline`, `test_emit_subject_writes_exactly_64_bytes_no_newline`, `test_resolve_writes_the_subject_file_bytes_from_the_anchor` | 1, 5, 8 |
| 8. The signer-trust policy refuses when a required claim is absent | `test_signer_trust_refuses_when_a_required_claim_is_absent` (4), `test_signer_trust_refuses_when_verified_timestamps_are_absent_or_empty` (2), `test_signer_trust_refuses_when_neither_trigger_alias_is_present`, `test_resolve_refuses_when_the_policy_claims_are_absent` | 6, 8 |
| 9. Purity holds repo-wide | `test_kernel_never_references_a_signing_stack` + `test_kernel_reads_no_environment_variable` (pre-existing), `test_new_modules_import_only_stdlib_and_loop` (3), `test_no_module_under_loop_reaches_the_network_or_shells_out`, `test_kernel_emits_no_statement_key_anywhere` (2) | 7 |
| 10. `--signer-digest` documented as deliberately not required, with the `job_workflow_sha` reason | `test_section_24_documents_signer_digest_as_deliberately_not_required`, `test_signer_trust_has_no_signer_digest_parameter`, `test_resolve_never_passes_signer_digest`, `test_attest_workflow_pins_the_signer_workflow` | 11, 6, 8, 10 |

---

## Task 1: The contract layer — `anchor@1` and the subject byte form

Schema and byte-form first, so nothing downstream can drift (this project's own lesson: *author the schema as the contract before fanning out*).

**Files:**
- Create: `schemas/anchor.schema.json`, `loop/anchor.py`, `scripts/test_anchor.py`
- Modify: `loop/verdict.py`

**Interfaces:**
- Consumes: `loop/_resources.py:34::schemas_dir()`; `loop/verdict.py:26::VerdictError`; the `loop/evidence.py:35,59` own-id/own-loader precedent.
- Produces: `ANCHOR_SCHEMA_ID = "loop-engineer/anchor@1"`, `DEFAULT_ANCHOR_FILENAME = "loop-anchor.json"`, `class AnchorError(ValueError)`, `read_anchor(path) -> dict[str, Any]`, `_load_anchor_schema() -> dict`; and in `loop/verdict.py`: `SUBJECT_NAME = "loop-chain-head"`, `subject_bytes(head: str) -> bytes`.

- [ ] **Step 0: Measure the baseline before touching anything**

```bash
git -C /mnt/c/Dev/projects/loop-engineer log -1 --format=%H
uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts
uv run --with pyyaml --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts
```

Record both numbers and the environment in the PR draft. Expected `1353 passed / 18 skipped` and `1256 passed / 115 skipped` (fresh worktree; the live checkout runs +2/−2). **If either differs, stop and reconcile before writing code** — a wrong baseline silently converts a regression into a "new test".

- [ ] **Step 1: Write the failing tests** (27 cases)

`scripts/test_anchor.py`, following the `scripts/test_verdict.py` structure. **Note the corrected arithmetic:** this table's rows summed to 25 while its Total read 23 before hardening — the two parametrized 5-case rows were undercounted. The Total is now the true row sum, and the same correction was applied to Tasks 3, 5, 6 and 11. Trust the row sum, never a remembered headline.

| Test | Cases | Asserts |
|---|---|---|
| `test_anchor_schema_id_and_default_filename_are_pinned` | 1 | `ANCHOR_SCHEMA_ID == "loop-engineer/anchor@1"`, `DEFAULT_ANCHOR_FILENAME == "loop-anchor.json"` |
| `test_anchor_schema_file_declares_the_matching_id` | 1 | `$id` == the constant, `$schema` is draft 2020-12 |
| `test_anchor_schema_is_not_a_contract_artifact` | 1 | `ANCHOR_SCHEMA_ID not in loop.contract.SCHEMA_IDS` |
| `test_anchor_schema_pattern_carries_a_maxlength` | 1 | every `pattern` in the schema has a sibling `maxLength` (the PR #89 hole) |
| `test_anchor_schema_validates_the_shipped_example_anchor` | 1 | **`pytest.importorskip("jsonschema")`** — one of the two fallback-leg skips |
| `test_read_anchor_returns_the_carried_head` | 1 | round-trips `chain_head`, `sequence`, `attestation_id` |
| `test_read_anchor_refuses_a_missing_file` | 1 | `AnchorError`, message names the path |
| `test_read_anchor_refuses_a_non_object` | 1 | `AnchorError` |
| `test_read_anchor_refuses_undecodable_bytes` | 1 | `AnchorError`, no `UnicodeDecodeError` escapes (the #107 lesson) |
| `test_read_anchor_refuses_a_wrong_schema_id` | 1 | `AnchorError` |
| `test_read_anchor_refuses_a_missing_chain_head` | 1 | `AnchorError` |
| `test_read_anchor_refuses_a_schema_invalid_but_json_valid_document` | **2** | parametrized `{"sequence": -1}` and `{"sequence": "41"}` — a document that parses, carries the right `schema` id, and carries a well-formed `chain_head`, but violates `anchor@1` elsewhere. **Refused in BOTH dependency legs**: with `jsonschema` via the collected `iter_errors` result, without it via the structural hand-checks. Deliberately **not** `importorskip`-gated — mode parity is the point (the S3 `plan-lint` mode-parity repair is the precedent), and gating it would let the fallback leg accept a document the schema rejects |
| `test_read_anchor_refuses_a_malformed_chain_head` | **5** | parametrized: uppercase hex, 63 chars, 65 chars, trailing newline, non-hex |
| `test_read_anchor_refuses_an_anchor_under_a_loop_dir` | 1 | a path with a `.loop` component refuses — D2's "must not live under `.loop/`" made mechanical |
| `test_subject_name_is_pinned` | 1 | `loop.verdict.SUBJECT_NAME == "loop-chain-head"` |
| `test_subject_bytes_is_exactly_64_lowercase_hex_with_no_trailing_newline` | 1 | **D10.7** — `len(b) == 64`, `b == b.lower()`, `not b.endswith(b"\n")`, `b.decode("ascii")` is the head |
| `test_subject_bytes_refuses_a_malformed_head` | **5** | same five malformations → `VerdictError` |
| `test_subject_bytes_digest_is_not_the_head_itself` | 1 | `sha256(subject_bytes(h)).hexdigest() != h` — the property that distinguishes a D1 attestation from the three already minted |
| **Total** | **27** | |

- [ ] **Step 2: Run the tests and confirm they fail for the right reason**

Run: `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_anchor.py`
Expected: collection error / `ModuleNotFoundError: No module named 'loop.anchor'` — **not** an assertion failure. A test that fails for the wrong reason proves nothing.

- [ ] **Step 3: Write the schema** (`schemas/anchor.schema.json`)

Required: `schema`, `chain_head`. `additionalProperties: false`. `chain_head`: `{"type": "string", "pattern": "^[0-9a-f]{64}$", "maxLength": 64}`. Optional `sequence` (`integer`, `minimum: 0`), `attestation_id` (`string`, `maxLength: 64`), `run_id` (`string`, `minLength: 1`, `maxLength: 256`), `recorded_at` (`string`, `maxLength: 64`).

- [ ] **Step 4: Write `loop/anchor.py`**

ILLUSTRATIVE skeleton — the AC table above is normative:

```python
# loop/anchor.py  (ILLUSTRATIVE)
"""Read a tracked anchor@1 file that CARRIES a previously attested chain head.

Nothing here is trusted. The anchor is a carried claim whose only function is to
give an attestation lookup a digest to ask about; the attestation corroborates
it, and no attestation can ever discover it (GitHub exposes no list endpoint).
Anchor trust is exactly ordinary write access to the anchor file — no better.
Pure: no environment, no network, no signing.
"""
ANCHOR_SCHEMA_ID = "loop-engineer/anchor@1"
DEFAULT_ANCHOR_FILENAME = "loop-anchor.json"
_HEAD_PATTERN = re.compile(r"[0-9a-f]{64}")


class AnchorError(ValueError):
    """The anchor file is absent, unreadable, or not a conformant anchor@1."""
```

**Exception enumeration, per statement** (the S1-evidence lesson — do not wrap the body in one blanket `except`):

| Statement | Raises | Becomes |
|---|---|---|
| `path.read_bytes()` / `open()` | `OSError` (incl. `FileNotFoundError`, `IsADirectoryError`, `PermissionError`) | `AnchorError` naming the path |
| `.decode("utf-8")` | `UnicodeDecodeError` | `AnchorError` (the #107 lesson: no `UnicodeDecodeError` escapes) |
| `json.loads(...)` | `json.JSONDecodeError` | `AnchorError` naming the parse position |
| the `schema` / `chain_head` structural checks | nothing — they *return* a violation | `AnchorError` naming the field |

**Do NOT catch `ValueError` from jsonschema — it is never raised here.** Verified at HEAD `c493804`: **every** jsonschema call site in this repo uses `validator.iter_errors(data)`, which yields errors and **never raises** — `loop/contract.py:559-563`, `loop/events.py:225-229`, `loop/evidence.py:138-143`, `loop/plan.py:57-60`. Not one of them calls `jsonschema.validate()`. `read_anchor` follows that same idiom: construct a `Draft202012Validator` over `_load_anchor_schema()`, **collect** `iter_errors`, and convert a non-empty collection into an `AnchorError` naming the first violation's location and message. Catching `ValueError` around such a call is catching an exception that cannot occur, and it would silently mask a genuine `ValueError` from elsewhere in the same block.

The structural (no-jsonschema) leg must refuse the same documents the schema refuses for every field the schema declares — including the optional provenance fields (`sequence` an integer ≥ 0, `attestation_id` / `run_id` / `recorded_at` strings). Mode parity is asserted by `test_read_anchor_refuses_a_schema_invalid_but_json_valid_document` in **both** legs; the S3 `plan-lint` mode-parity repair is the precedent for why a schema-only check is not enough.

Validate `chain_head` with `re.fullmatch`, never `re.match`.

- [ ] **Step 5: Add `SUBJECT_NAME` and `subject_bytes()` to `loop/verdict.py`**

One definition of the byte form, so the attest side and the resolve side cannot disagree. `subject_bytes` raises `VerdictError` on anything but 64 lowercase hex, and returns `head.encode("ascii")` — 64 bytes, no newline, nothing else.

- [ ] **Step 6: Run the tests to green, then the full suite**

Run: `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts`

**Acceptance:** `scripts/test_anchor.py` reports **exactly 27 passed** on its own with `--with pyyaml --with jsonschema --with pytest`, and **26 passed / 1 skipped** with `--with pyyaml --with pytest` (the one skip is `test_anchor_schema_validates_the_shipped_example_anchor`; the schema-invalid mode-parity cases must pass in **both** legs); the full suite reports **exactly 1380 passed / 18 skipped** with `pyyaml+jsonschema+pytest` in the gate worktree (1353 baseline + 27). `uv run --with pyyaml python3 -B scripts/self_eval.py` still reports 13/13 (a new file in `schemas/` is fine; a new file in `reference/` is not).

- [ ] **Step 7: Commit**

```bash
git add schemas/anchor.schema.json loop/anchor.py loop/verdict.py scripts/test_anchor.py
git commit -m "feat(anchor): anchor@1 carry channel and the pinned subject byte form"
```

---

## Task 2: Ancestry in `loop/chain.py` — established by replay, never by column trust

**D3's core:** `--expect-chain-head` is exact current-head equality (`loop/runtime.py:323-327`), and appending one event moves the head (measured: `9d388ae5…` seq 4 → `c336ecdc…` seq 5). Feeding run N's head to `--expect-chain-head` at run N+1 therefore **fails by construction** on any growing store. The meaningful cross-run check is *the previously attested head still appears in my chain.*

**Files:**
- Modify: `loop/chain.py`
- Create: `scripts/test_chain_ancestry.py`

**Interfaces:**
- Consumes: `loop/chain.py:45::link_issue`, `:40::compute_event_hash`, `:23::ChainHashError`. Stays consistent with the module's docstring contract — "works over any ordered event list (a SQLite read or a JSONL export)", **I/O-free, imports no other `loop` module**.
- Produces: `head_sequence(events: Iterable[Mapping[str, Any]], digest: str) -> int | None`.

- [ ] **Step 1: Write the failing tests** (9 cases)

| Test | Cases | Asserts |
|---|---|---|
| `test_head_sequence_finds_the_current_head` | 1 | the last chained event's digest → its sequence |
| `test_head_sequence_finds_an_earlier_head_after_the_chain_grew` | 1 | a head from sequence 3 is still found after events 4–6 are appended — **the whole point of the predicate** |
| `test_head_sequence_returns_none_for_an_unknown_digest` | 1 | `None`, not an exception |
| `test_head_sequence_returns_none_for_an_empty_stream` | 1 | `None` |
| `test_head_sequence_ignores_an_unchained_prefix` | 1 | a migrated store's `event_hash: None` prefix contributes no sequence and does not abort the walk |
| `test_head_sequence_recomputes_and_refuses_a_forged_event_hash_column` | 1 | **D10.5** — a row whose stored `event_hash` is set to the anchored digest but whose recomputed hash differs yields `None`. A tamperer who can rewrite the store can also insert a row bearing the anchored hash; **only recomputation refuses that.** |
| `test_head_sequence_stops_at_a_broken_link` | 1 | a `prev_event_hash` splice makes every later head unreachable — the walk stops exactly where `verify_chain` stops |
| `test_head_sequence_accepts_any_ordered_mapping_sequence` | 1 | works over plain dicts read from a JSONL export, no store involved (the module's portability contract) |
| `test_head_sequence_finds_the_digest_at_sequence_zero` | 1 | the **genesis** event's own hash resolves to sequence `0`, not to a falsy miss. The boundary a `if seq:`-style truth test would silently swallow — and `0` is a legitimate ancestor, so callers must compare against `None`, never truthiness |
| `test_head_sequence_refuses_a_malformed_digest_argument` | 1 | non-64-hex → **exactly `ValueError`**, asserted as `type(exc) is ValueError`, never a silent `None` (a silent `None` on a typo would read as "rewrite detected"). **Not `ChainHashError`** — see the class ruling below |
| **Total** | **10** | |

**Exception-class ruling (normative).** The malformed-digest refusal raises a **plain `ValueError`**, and the test asserts the exact class with `type(exc) is ValueError`, not `pytest.raises(ValueError)`. Reason, read from HEAD `c493804`: `ChainHashError`'s own docstring at `loop/chain.py:23-24` scopes it to *"A value cannot be canonically hashed (non-JSON type, non-finite float, lone surrogate)"* — canonicalization failures. "The caller passed a digest argument that is not 64 lowercase hex" is **argument validation**, not a hashing failure, and reusing `ChainHashError` for it would make the class mean two unrelated things. Because `ChainHashError` **is** a `ValueError` subclass, a bare `pytest.raises(ValueError)` would pass for either class and would pin nothing — hence the exact-class assertion.

- [ ] **Step 2: Confirm they fail with `ImportError: cannot import name 'head_sequence'`**

- [ ] **Step 3: Implement**

ILLUSTRATIVE:

```python
# loop/chain.py  (ILLUSTRATIVE)
def head_sequence(events, digest):
    """Sequence at which `digest` WAS the chain head, or None if it never was.

    Established by REPLAY: every link is re-checked and every hash recomputed via
    link_issue/compute_event_hash. The stored event_hash column is never trusted —
    an adversary who can rewrite the store can also insert a row bearing the
    anchored digest, and only recomputation refuses that row.
    """
```

Walk with the same `head`/`unchained_prefix` state machine as `verify_chain` (`loop/chain.py:66-88`); `break` on the first `link_issue`; return the sequence when `record["event_hash"] == digest` **after** the link check passed for that record.

- [ ] **Step 4: Mutation probe — prove the test has teeth**

Temporarily reimplement `head_sequence` to trust the column (`if record.get("event_hash") == digest: return record["sequence"]` with no link check). Re-run. `test_head_sequence_recomputes_and_refuses_a_forged_event_hash_column` and `test_head_sequence_stops_at_a_broken_link` **must both FAIL**. Revert. A gate that cannot fail is not a gate. **Run this probe in a worktree with no other suite running** — a full-suite run was discarded for exactly this reason during Slice 4a.

**Acceptance:** `scripts/test_chain_ancestry.py` reports **exactly 10 passed** in **both** dependency legs (no `importorskip` in this file); the full suite reports **exactly 1390 passed / 18 skipped** (1380 + 10) with `pyyaml+jsonschema+pytest` and **exactly 1292 passed / 116 skipped** with `pyyaml+pytest`; the mutation probe failed the two named tests and was reverted, leaving `git diff loop/chain.py` showing only the addition.

- [ ] **Step 5: Commit**

```bash
git add loop/chain.py scripts/test_chain_ancestry.py
git commit -m "feat(chain): replay-established head_sequence ancestry predicate"
```

---

## Task 3: The doctor ancestry gate — `--expect-chain-ancestor` and `--anchor`

**Files:**
- Modify: `loop/runtime.py`, `loop/contract.py`, `loop/__main__.py`
- Create: `scripts/test_doctor_anchor_ancestry.py`

**Interfaces:**
- Consumes: Task 2's `head_sequence`; Task 1's `read_anchor`/`AnchorError`; `loop/runtime.py:132::_events`, `:278::_anchor_mismatch`, `:282::event_consistency_issues`, `:30::RuntimeStoreError`; `loop/contract.py:46::ContractIssue`, `:1103::doctor_report`; `loop/__main__.py:150::_extract_value_flag`, `:264-267` (hex guard), `:268-274` + `:291-297` (wrong-command guards).
- Produces: `event_consistency_issues(target, *, mode=None, expect_chain_head=None, expect_chain_ancestor=None)`; `doctor_report(..., expect_chain_ancestor=None)`; CLI flags `--expect-chain-ancestor SHA256` and `--anchor PATH`; the conditional `event_store.anchor` report block; codes `chain_anchor_not_ancestor`, `anchor_file_unreadable`, `anchor_file_invalid`.

**Design rules (normative):**

1. New kwargs are **appended and default `None`**, so every existing call site is untouched.
2. When neither ancestor flag is supplied, the doctor report is **byte-identical** to today's — the §22 habit. `event_store.anchor` appears **only** when an ancestor was supplied.
3. The ancestry check runs **inside** the existing `try` at `loop/runtime.py:301-314`, so a store that becomes unreadable between reads surfaces as a typed finding rather than a traceback out of `doctor_report` (R007).
4. **Absent store + supplied ancestor → `chain_anchor_not_ancestor`, never a skip** (D5). Mirror the existing shapes at `:296-298` and `:311-313` exactly: same guard structure, new code, message naming which condition held.
5. `--expect-chain-head` and `--expect-chain-ancestor` **compose** — equality and ancestry are different questions and both may be asked. `--anchor` and `--expect-chain-ancestor` are **mutually exclusive** at the CLI (exit 2 with a usage message): silent precedence between an explicit digest and a resolved one is how a gate becomes a suggestion. ADR decision 5's "explicit wins over resolved" is honored in the **action** (Task 9), where the inputs are the surface.
6. Reading the anchor is a **CLI-layer** concern: `loop/__main__.py` calls `read_anchor`, converts `AnchorError` into the `anchor_file_unreadable` / `anchor_file_invalid` doctor issue, and passes the resolved digest down as `expect_chain_ancestor`. Keeping `runtime.py` file-agnostic preserves its "reports over the store" scope. **A failed anchor read must still produce a doctor report with `ok: false`** — exit 1 with the issue in the JSON, not exit 2 — because an operator's CI reads the report, and a bare stderr line loses the code.

   **The pinned shape (normative, not merely "code present, exit 1").** An anchor-file failure is the one path where the report is *not* produced by `doctor_report` alone, so the shape must be pinned or it will drift. Read from HEAD `c493804`, `doctor_report` returns exactly these top-level keys: `paths`, `ok`, `validation_mode`, `requested_mode`, `schemas_checked`, `lifecycle`, `issues`, `event_store`. On an anchor-file failure the CLI must emit a report with **that same key set** — a full `doctor_report` built with `expect_chain_ancestor=None` (there is no digest to check), with the typed issue **appended** to `issues` and `ok` forced `False`. Acceptance is the key set plus the spliced issue, not just the code:

   ```python
   # loop/__main__.py  (ILLUSTRATIVE — the AC below is normative)
   resolved_ancestor = expect_chain_ancestor
   anchor_issue = None
   if anchor is not None:
       from .anchor import AnchorError, read_anchor
       try:
           resolved_ancestor = read_anchor(anchor)["chain_head"]
       except AnchorError as exc:
           # A report, never a bare stderr line: the operator's CI reads the JSON.
           # expect_chain_ancestor stays None so the ancestry gate is not ALSO
           # asked a question it has no digest for — one failure, one code.
           resolved_ancestor = None
           anchor_issue = ContractIssue(_anchor_file_code(exc), str(exc), Path(anchor))

   report = doctor_report(target, mode=mode, expect_chain_head=expect_chain_head,
                          expect_chain_ancestor=resolved_ancestor)
   if anchor_issue is not None:
       report = {**report, "issues": [*report["issues"], anchor_issue], "ok": False}
   return _print_json(report)          # ok False ⇒ exit 1, for free
   ```

   Two properties this shape buys and that the tests pin: the anchor failure contributes **exactly one** new issue (it does not also raise `chain_anchor_not_ancestor`, because no ancestor was ever supplied to the gate), and the report is still a full doctor report, so a consumer parsing `validation_mode` or `event_store` does not crash on the failure path.

   **Which of the two codes** is chosen by the failure class, not by taste: `anchor_file_unreadable` for absent / unreadable / non-UTF-8 / non-JSON (the `OSError` / `UnicodeDecodeError` / `json.JSONDecodeError` rows of Task 1's enumeration), `anchor_file_invalid` for "parsed fine, is not a conformant `anchor@1`". `read_anchor` must therefore let the caller tell them apart — carry the class on the `AnchorError` (e.g. a `.code` attribute, the `RuntimeStoreError` precedent at `loop/runtime.py:30`) rather than making the CLI regex the message.

- [ ] **Step 1: Write the failing tests** (31 cases — the row sum; the pre-hardening Total of 28 undercounted the three parametrized rows)

| Test | Cases | Asserts |
|---|---|---|
`test_ancestor_flag_passes_when_the_anchored_head_is_in_the_chain` | 1 | `ok: true`, no anchor codes
`test_ancestor_flag_passes_after_the_chain_grew` | 1 | the head from before the growth still passes
`test_expect_chain_head_fails_on_the_same_grown_store` | 1 | **the negative control that proves ancestry is strictly more useful** — F3 made mechanical
`test_ancestor_flag_fails_with_chain_anchor_not_ancestor_on_an_unknown_head` | 1 | the new code, `ok: false`
`test_ancestry_detects_a_wholesale_rewrite_that_self_verifies_clean` | 1 | **D10.4** — extend `scripts/test_adversarial_chain.py:182`'s rewrite, then grow it; `verify_chain` is `ok=True, issues=[]` and doctor reports no `event_chain_broken`, yet the anchored head is gone → `chain_anchor_not_ancestor`
`test_ancestry_refuses_a_forged_row_bearing_the_anchored_digest_end_to_end` | 1 | **D10.5** at doctor level, via `drop_triggers` (in-place `DELETE`/`UPDATE` is trigger-refused, so the attack must rewrite the file — which is what ancestry catches)
`test_absent_store_with_an_ancestor_fails_and_never_skips` | 1 | `chain_anchor_not_ancestor`, `event_store["present"] is False`
`test_unreadable_store_with_an_ancestor_fails_and_never_skips` | 1 | `chain_anchor_not_ancestor` **alongside** the `corrupt_store`-family code
`test_empty_store_with_an_ancestor_fails_and_never_skips` | 1 | same, for `empty_store`
`test_ancestor_code_is_distinct_from_chain_anchor_mismatch` | 1 | a store whose current head differs **and** whose ancestor is present yields `chain_anchor_mismatch` **without** `chain_anchor_not_ancestor` — D3's "a shared code would collapse them"
`test_anchor_file_resolves_the_expected_ancestor` | 1 | `--anchor` produces the same verdict as the equivalent explicit digest
`test_unreadable_anchor_file_fails_with_anchor_file_unreadable` | 1 | code present, **exit 1 with a report**, not exit 2
`test_invalid_anchor_file_fails_with_anchor_file_invalid` | 1 | code present
`test_anchor_file_failure_emits_a_full_doctor_report_shape` | **2** | **design rule 6's pinned shape** — parametrized unreadable / invalid: `set(report) == {"paths","ok","validation_mode","requested_mode","schemas_checked","lifecycle","issues","event_store"}`, `report["ok"] is False`, and **exactly one** new issue whose code is the anchor-file code — in particular `chain_anchor_not_ancestor` is **absent**, because a failed anchor read supplies the gate no digest to ask about
`test_doctor_report_is_byte_identical_when_no_anchor_flag_is_supplied` | 1 | `canonical_json` of the report equals a pre-change capture
`test_anchor_block_appears_only_when_an_ancestor_was_supplied` | 1 | `"anchor" not in event_store` by default; `{"expected", "sequence"}` when supplied
`test_expect_chain_head_and_expect_chain_ancestor_compose` | 1 | both satisfied → `ok: true`; both violated → both codes
`test_anchor_and_expect_chain_ancestor_are_mutually_exclusive` | 1 | exit 2, usage message
`test_ancestor_flag_rejected_for_non_doctor_commands` | **3** | parametrized `scaffold`, `verdict`, `status` — the `loop/__main__.py:268-274` precedent; without it `scaffold` **creates a directory named after the flag**
`test_anchor_flag_rejected_for_non_doctor_commands` | **3** | same three
`test_expect_chain_ancestor_must_be_64_lowercase_hex` | **4** | uppercase, 63, 65, non-hex → exit 2, reusing the `:264-267` guard shape
`test_anchor_resolution_works_in_release_mode` | 1 | **`pytest.importorskip("jsonschema")`** — the second fallback-leg skip; `--mode release` requires jsonschema
`test_new_doctor_codes_match_the_public_issue_code_pattern` | 1 | all three new codes match `^[a-z0-9_]{1,64}$` — they are eligible for a permanent public log
| **Total** | **31** | |

- [ ] **Step 2: Confirm the new tests fail and the existing suite still passes**

The pre-change capture for `test_doctor_report_is_byte_identical_when_no_anchor_flag_is_supplied` must be taken **before** the runtime edit — record it in the test as a literal or a committed fixture, not regenerated after the change (a self-regenerating snapshot pins nothing).

- [ ] **Step 3: Thread the kwarg through `runtime.py` and `contract.py`**

ILLUSTRATIVE — note the R007-preserving placement:

```python
# loop/runtime.py  (ILLUSTRATIVE)
def _not_ancestor(message):
    return ContractIssue("chain_anchor_not_ancestor", message)


def _ancestry(target, mode, expect_chain_ancestor):
    """Sequence at which the anchored head was the head, by replay. Fourth
    read of the store, in the same tradition as _bound_evidence_issues (§22)."""
    _, _run_id, events, _validation = _events(target, mode)
    return chain.head_sequence(events, expect_chain_ancestor)
```

- [ ] **Step 4: Wire the CLI**

`--expect-chain-ancestor` parsed beside `--expect-chain-head` (`loop/__main__.py:256-267`) with the identical hex guard; `--anchor` parsed with `_extract_value_flag`; three new wrong-command guards; `_USAGE` unchanged (it lists commands, not flags) but `_HELP`'s `doctor|validate|verify` usage line and `options:` block both gain the two flags. **Existing CLI-surface tests that pin the help text must have their fixtures updated to include the new flags — never weaken the assertion.**

- [ ] **Step 5: Run the full suite in both legs**

**Acceptance:** `scripts/test_doctor_anchor_ancestry.py` reports **exactly 31 passed** with `pyyaml+jsonschema+pytest` and **30 passed / 1 skipped** with `pyyaml+pytest`; the anchor-file failure path emits the pinned eight-key report shape with `ok: false`, exactly one new issue, and no `chain_anchor_not_ancestor`; the full suite reports **exactly 1421 passed / 18 skipped** (1390 + 31) with `pyyaml+jsonschema+pytest` and **exactly 1322 passed / 117 skipped** in the fallback leg (1256 + 22 + 9 + 27 pass; 115 + the two `importorskip` cases); `python3 -m loop doctor examples/coverage-repair` output is byte-identical to a pre-change capture.

- [ ] **Step 6: Commit**

```bash
git add loop/runtime.py loop/contract.py loop/__main__.py scripts/test_doctor_anchor_ancestry.py
git commit -m "feat(doctor): replay-based chain-ancestry gate with a distinct issue code"
```

---

## Task 4: `compare_verdict()` — agreement, and never anything more

**Files:**
- Modify: `loop/verdict.py`
- Create: `scripts/test_verdict_compare.py`

**Interfaces:**
- Consumes: `loop/verdict.py:115::build_verdict`, `:26::VerdictError`, `:22::VERDICT_SCHEMA_ID`; `loop/contract.py:46::ContractIssue`.
- Produces: `compare_verdict(attested: object, target: str | Path, *, mode: str | None = None) -> dict[str, Any]`, plus the `COMPARISON_CODES` tuple.

**The comparison report (binding).** Deliberately **not** a schema-bearing artifact — it is a report, like `doctor_report`'s, not an interchange object. Reuse `loop/__main__.py:119::_print_json` so exit 0/1 comes from `ok` for free.

```json
{
  "ok": false,
  "signature_checked": false,
  "compared": {
    "run_id":     { "attested": "coverage-repair", "local": "coverage-repair", "agrees": true },
    "head":       { "attested": "9f2c…", "local": "c336…", "agrees": false },
    "terminal":   { "attested": {"state": "Succeeded", "completion_policy": "all_required_verified_evidence", "false_completion": false},
                    "local":    {"state": "Succeeded", "completion_policy": "all_required_verified_evidence", "false_completion": false},
                    "agrees": true },
    "evidence":   { "attested": ["a1b2…"], "local": ["a1b2…"], "agrees": true }
  },
  "issues": [ { "code": "verdict_head_disagreement", "message": "…" } ]
}
```

**Normative rules:**

1. **`signature_checked` is the literal `false`, always.** No parameter, no flag, no branch changes it. The docstring says: *this function establishes agreement; `gh attestation verify` establishes authenticity; neither implies the other.*
2. **Four facets are compared:** `run_id`, `chain.head`, the whole `terminal` object (`state`, `completion_policy`, `false_completion`), and the `evidence[]` digest set (set equality on the three-tuple, matching `build_verdict`'s own de-duplicated sort).
3. **`doctor` and `tool` are deliberately NOT compared, and the report says so** — F4 measured that `doctor.validation_mode` and `tool.version` live inside the predicate, so the same run projects `873dfc87…` with jsonschema and `8de3d88c…` in structural-fallback. A consumer on another tool version could never reproduce them, and comparing them would make an honest environment difference read as tampering. Whether the attested `doctor.ok` should *gate* is a policy question, not an agreement question, and it is out of scope.
4. **An ancestor head is a disagreement, not a pass.** A verdict is the projection of **one** run; an attested head that is merely an ancestor of the local head is a *different* run's verdict, which is a fact to report, not to excuse. Ancestry lives in the doctor gate (Task 3), where it is the question being asked. *(This is a plan ruling — D1–D10 do not settle it; see Open Items.)*
5. **Typed refusals, exit 2, no report** — a document that is not a bare `verdict@1` predicate produced no comparison, so `ok: false` would imply one happened. Each refusal **names what was found** and the documented jq path `.[0].verificationResult.statement.predicate`:
   - any of `_type` / `subject` / `predicateType` / `predicate` present → "this is an in-toto Statement, not a predicate";
   - a top-level **array**, or `verificationResult` / `attestation` present → "this is a `gh --format json` envelope";
   - `schema` absent or not `loop-engineer/verdict@1` → unrecognized document;
   - not a JSON object at all → refusal.
6. `compare_verdict` calls `build_verdict` for the local side, so it **inherits** the no-terminal-record refusal — a workspace with no finished run cannot be compared against.

- [ ] **Step 1: Write the failing tests** (25 cases)

| Test | Cases | Asserts |
|---|---|---|
`test_compare_passes_on_a_self_projected_verdict` | 1 | **D10.2's negative control** — `build_verdict(ws)` compared against `ws` is `ok: true` with zero issues
`test_compare_reports_signature_checked_false_on_every_report_branch` | **5** | **D10.1** — parametrized over agreement, head-disagreement, terminal-disagreement, run-id-disagreement, evidence-disagreement; every report has `signature_checked is False`
`test_signature_checked_is_never_assigned_true_in_source` | 1 | every occurrence of `signature_checked` in `loop/verdict.py` is followed by the constant `False` (AST-level, not a substring scan)
`test_compare_head_disagreement_is_typed` | 1 | `verdict_head_disagreement`, `ok: false`
`test_compare_terminal_state_disagreement_is_typed` | 1 | `verdict_terminal_disagreement`
`test_compare_terminal_policy_disagreement_is_typed` | 1 | same code; `all_required` vs `all_required_verified_evidence` must not read as agreement
`test_compare_false_completion_disagreement_is_typed` | 1 | same code — the safety flag is part of the terminal facet
`test_compare_run_id_disagreement_is_typed` | 1 | `verdict_run_id_disagreement`
`test_compare_evidence_digest_disagreement_is_typed` | 1 | `verdict_evidence_disagreement`, both directions (attested ⊄ local **and** local ⊄ attested)
`test_compare_ignores_doctor_and_tool_differences` | 1 | an attested doc with a different `tool.version` and `doctor.validation_mode` still passes — **F4 made mechanical**
`test_compare_refuses_an_in_toto_statement` | **4** | parametrized over `_type`, `subject`, `predicateType`, `predicate`
`test_compare_refuses_a_gh_format_json_array_wrapper` | 1 | a top-level list refuses
`test_compare_refuses_a_gh_verification_result_object` | 1 | `verificationResult` / `attestation` keys refuse
`test_compare_refuses_an_unrecognized_schema` | 1 | wrong/absent `schema`
`test_compare_refusal_names_the_unwrapping_step` | 1 | the message contains `.[0].verificationResult.statement.predicate`
`test_compare_refuses_a_non_object_document` | 1 | a string / number / null refuses
`test_compare_treats_an_ancestor_head_as_a_disagreement` | 1 | rule 4 made mechanical
`test_compare_report_field_allowlist_holds` | 1 | `set(report) == {"ok","signature_checked","compared","issues"}`; `set(report["compared"]) == {"run_id","head","terminal","evidence"}`
| **Total** | **25** | |

- [ ] **Step 2: Confirm they fail with `ImportError: cannot import name 'compare_verdict'`**

- [ ] **Step 3: Implement `compare_verdict()`**

Refusal checks run **before** any comparison and in the order above, so an operator who piped a `gh` envelope is told to unwrap rather than told their heads disagree.

- [ ] **Step 4: Mutation probe**

Temporarily change `signature_checked` to `True` in one branch; confirm `test_compare_reports_signature_checked_false_on_every_report_branch` and `test_signature_checked_is_never_assigned_true_in_source` **both** fail. Then temporarily add `doctor` to the compared facets; confirm `test_compare_ignores_doctor_and_tool_differences` and `test_compare_report_field_allowlist_holds` fail. Revert both.

**Acceptance:** `scripts/test_verdict_compare.py` reports **exactly 25 passed** in both dependency legs (no `importorskip` in this file); the full suite reports **exactly 1446 passed / 18 skipped** (1421 + 25) and **1347 passed / 117 skipped** in the fallback leg; both mutation probes failed as predicted and were reverted.

- [ ] **Step 5: Commit**

```bash
git add loop/verdict.py scripts/test_verdict_compare.py
git commit -m "feat(verdict): compare_verdict agreement check with signature_checked pinned false"
```

---

## Task 5: CLI wiring — `verdict --compare` and `verdict --emit-subject`

**Files:**
- Modify: `loop/__main__.py`
- Modify: `scripts/test_verdict_cli.py`

**Interfaces:**
- Consumes: Task 4's `compare_verdict`; Task 1's `subject_bytes`; `loop/__main__.py:119::_print_json`, `:150::_extract_value_flag`, the existing verdict dispatch at `:374-383`.
- Produces: `python3 -m loop verdict [--mode …] [--compare <file|->] [--emit-subject] <workspace>`.

**Exit-code contract (normative):**

| Invocation | stdout | exit |
|---|---|---|
| `verdict <ws>` (unchanged) | canonical predicate JSON | 0 |
| `verdict --compare <f> <ws>` and they agree | indented comparison report | **0** |
| `verdict --compare <f> <ws>` and they disagree | indented comparison report | **1** |
| `verdict --compare <f> <ws>`, `<f>` is a Statement / `gh` envelope / unreadable | empty | **2** |
| `verdict --emit-subject <ws>` | **exactly 64 bytes, no trailing newline** | 0 |
| `verdict --emit-subject <ws>` with a null chain head | empty | **2** |
| `--compare` and `--emit-subject` together | empty | **2** |

`--emit-subject` writes bytes to stdout so the action can redirect them into a file with the byte form preserved exactly — a *read* command must not gain a write path. **Use `sys.stdout.buffer.write(...)`, never `print`**, or the trailing newline breaks the 64-byte pin.

- [ ] **Step 1: Write the failing tests** (19 cases appended to `scripts/test_verdict_cli.py` — the row sum; the pre-hardening Total of 15 undercounted the two parametrized 3-case rows)

| Test | Cases | Asserts |
|---|---|---|
`test_compare_exits_zero_on_agreement` | 1 | round-trip: `verdict` → file → `--compare` → 0
`test_compare_exits_one_on_disagreement` | 1 | mutated head → exit 1, report on stdout, code present
`test_compare_exits_two_on_a_wrapper_shape` | 1 | exit 2, stdout empty, `"Traceback" not in stderr`, `stderr.startswith("verdict:")`
`test_compare_reads_stdin_with_a_dash` | 1 | `--compare -` consumes stdin
`test_compare_missing_value_is_a_usage_error` | 1 | `--compare` with no value → exit 2
`test_compare_refuses_a_nonexistent_file` | 1 | **M6** — `FileNotFoundError` never escapes: exit **2**, `stderr.startswith("verdict:")`, `"Traceback" not in stderr`, stdout empty. Exit 1 here would read as a genuine disagreement
`test_compare_refuses_a_directory_path` | 1 | `IsADirectoryError` (an `OSError`) takes the same path → exit 2, no traceback
`test_compare_refuses_empty_stdin` | 1 | `--compare -` with empty stdin → exit 2, message names the empty input; never a comparison against `None`
`test_compare_rejected_for_non_verdict_commands` | **3** | parametrized `scaffold`, `doctor`, `status` — and for `scaffold`, assert **no directory named `--compare` was created**
`test_emit_subject_writes_exactly_64_bytes_no_newline` | 1 | **D10.7 at the CLI** — `len(proc.stdout) == 64` on the raw bytes
`test_emit_subject_bytes_equal_subject_bytes_of_the_projected_head` | 1 | CLI and `loop.verdict.subject_bytes` cannot drift
`test_emit_subject_refuses_a_null_head` | 1 | store-less workspace → exit 2, typed
`test_compare_and_emit_subject_are_mutually_exclusive` | 1 | exit 2
`test_help_documents_compare_and_emit_subject` | 1 | both appear in `--help`, with the "never verifies a signature" clause intact
`test_verdict_never_advertises_a_signature_flag` | **3** | parametrized `--verify-signature`, `--signature`, `--signer-workflow` → exit 2. **D10.1's third leg: there is no flag to flip.**
| **Total** | **19** | |

- [ ] **Step 2: Confirm they fail**

- [ ] **Step 3: Wire the dispatch**

Parse both flags before the generic single-target guards, mirroring how `metrics` (`loop/__main__.py:177-204`) and `--expect-chain-head` (`:256-274`) already do it. Add the wrong-command guard for `--compare`/`--emit-subject` in the same shape as `:268-274`.

**One read-and-parse helper serves BOTH `--compare` branches — the file path and `-` (stdin) — and both are wrapped in the same exception tuple.** This is not cosmetic. The existing verdict dispatch at `loop/__main__.py:374-383` catches only `(VerdictError, ChainHashError)`, so a bare `Path(value).read_text()` on the file-path branch lets `FileNotFoundError` / `IsADirectoryError` / `PermissionError` (all `OSError`) escape the dispatch entirely: the operator gets a **traceback and Python's own exit 1**, not the documented exit 2 — and exit 1 in this CLI *means "a report said not-ok"*, so an unreadable file would read as a genuine disagreement. Ship it as one helper, wrapped once:

```python
# loop/__main__.py  (ILLUSTRATIVE — the exit-code contract above is normative)
def _read_compare_document(value: str) -> object:
    """Load the attested document from a path or from stdin. ONE reader, so the
    file branch and the '-' branch cannot diverge in their failure behavior."""
    from .verdict import VerdictError
    try:
        text = sys.stdin.read() if value == "-" else Path(value).read_text(encoding="utf-8")
    except OSError as exc:                       # missing, a directory, unreadable
        raise VerdictError(f"--compare could not read {value!r}: {exc}") from exc
    except UnicodeDecodeError as exc:            # the #107 lesson
        raise VerdictError(f"--compare input is not valid UTF-8: {exc}") from exc
    if not text.strip():
        raise VerdictError(f"--compare input is empty: {value!r}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise VerdictError(f"--compare input is not JSON: {exc}") from exc
```

Empty input is refused **explicitly** rather than left to `json.loads` — `json.loads("")` does raise `JSONDecodeError`, but an empty stdin is the operator error that a pipeline whose upstream `jq` produced nothing hits, and it deserves a message that says so. Every one of these raises `VerdictError`, so the existing `except (VerdictError, ChainHashError)` at `:374-383` renders it as `verdict: …` on stderr with **exit 2** and no traceback.

- [ ] **Step 4: Run the full suite — the help text is asserted elsewhere**

Existing tests pinning `_HELP`/`_USAGE` must have their **fixtures** updated, never their assertions weakened.

**Acceptance:** `scripts/test_verdict_cli.py` reports **exactly 30 passed** (its 11 collected cases at `c493804` + 19); no `--compare` input failure — missing file, directory, non-UTF-8, non-JSON, empty stdin — produces a traceback or an exit code other than 2; the full suite reports **exactly 1465 passed / 18 skipped** (1446 + 19) and **1366 passed / 117 skipped** in the fallback leg; `python3 -m loop verdict --emit-subject examples/flaky-test-triage | wc -c` prints **0** (that example is store-less, so the command exits 2 and writes nothing) while the same command against a seeded chained workspace prints **64**.

- [ ] **Step 5: Commit**

```bash
git add loop/__main__.py scripts/test_verdict_cli.py
git commit -m "feat(cli): verdict --compare and --emit-subject"
```

---

## Task 6: The signer-trust policy — `loop/attestation.py`

**D7:** the policy is a pure function over **already-extracted** JSON. It evaluates claims `gh` has already verified; it establishes nothing itself, and it must say so in its own docstring. Only `signature.certificate` and `verifiedTimestamps` are unforgeable by the originating workflow — **everything under `statement.predicate` is user-controllable metadata, per `gh`'s own help text.** The policy draws conclusions from the former and treats the latter as data to be compared, never trusted.

**Files:**
- Create: `loop/attestation.py`, `scripts/test_attestation_policy.py`

**Interfaces:**
- Consumes: `loop/contract.py:46::ContractIssue` (the one issue shape).
- Produces: `AttestationPolicyError(ValueError)`; `REQUIRED_CERTIFICATE_CLAIMS`; `_TRIGGER_CLAIM_ALIASES`; `ANCHOR_LOOKUP_OUTCOMES = ("corroborated", "contradicted", "unavailable")`; `check_signer_trust(result, *, signer_workflow, source_repository_uri, expect_trigger="push") -> dict`; `anchor_lookup_issue(outcome, *, detail=None) -> dict | None`.

**Normative rules:**

1. **Refuse, never pass, on an absent claim.** `check_signer_trust` raises `AttestationPolicyError` when `signature.certificate` is absent or not an object, when `verifiedTimestamps` is absent or empty, or when any required claim key is missing. *A policy that treats a missing claim as satisfied is worse than no policy.*
2. **The policy never reads `statement`.** Asserted **behaviorally** (a result whose `statement.predicate` contradicts the certificate produces an unchanged verdict) **and** structurally (the literal `"statement"` does not appear in the function's source). The behavioral test is the stronger one; ship both.
3. **`signature_checked: false` in the returned dict too.** The policy evaluates a verdict `gh` already reached; it does not re-establish it.
4. **Denials are typed codes, not booleans:** `signer_workflow_mismatch`, `signer_repository_mismatch`, `self_hosted_runner`, `signer_trigger_mismatch`.
5. **`--signer-digest` is never required (D4).** The module must not have a `signer_digest` parameter at all, and §24 records the `job_workflow_sha` reason.
6. **The three lookup outcomes never collapse (D5).** `anchor_lookup_issue("corroborated")` → `None`; `"contradicted"` → `anchor_attestation_contradicted`; `"unavailable"` → `anchor_attestation_unavailable`. An unknown outcome string **raises** rather than defaulting to anything. The docstring carries D5's sentence verbatim: *anything short of a verified 200 plus a successful `gh attestation verify` is non-promoting, and transport-class failures are separately reportable but exactly as non-promoting as a clean denial.*
7. **Claim-name uncertainty is handled fail-closed.** `REQUIRED_CERTIFICATE_CLAIMS` pins `("subjectAlternativeName", "sourceRepositoryURI", "runnerEnvironment")` and `_TRIGGER_CLAIM_ALIASES` pins `("githubWorkflowTrigger", "buildTrigger")` — the two Fulcio GitHub-OIDC trigger extensions, of which **at least one** must be present. These leaf names cannot be established before merge: F1 proves `gh attestation verify` is unrunnable against all three existing attestations, so no `--format json` output exists yet to read them from. **A wrong name therefore produces a refusal, not a silent pass**, and Task 10's live experiment is where the names are confirmed. The extraction happens in `scripts/action_anchor_resolve.py` (one place, one `jq`-shaped mapping), so a correction is a one-line change outside `loop/`.

- [ ] **Step 1: Write the failing tests** (26 cases — the row sum; the pre-hardening Total of 25 undercounted a parametrized row)

| Test | Cases | Asserts |
|---|---|---|
`test_required_certificate_claims_are_pinned` | 1 | the constant tuples, exactly
`test_signer_trust_passes_on_a_conformant_result` | 1 | `ok: true`, zero issues
`test_signer_trust_refuses_when_signature_certificate_is_absent` | 1 | `AttestationPolicyError`
`test_signer_trust_refuses_when_a_required_claim_is_absent` | **4** | **D10.8** — parametrized over each of the three required claims plus a whole-claims-object-missing case
`test_signer_trust_refuses_when_verified_timestamps_are_absent_or_empty` | **2** | parametrized absent / `[]` — an unwitnessed attestation is not a trusted one
`test_signer_trust_accepts_either_trigger_claim_alias` | **2** | parametrized over the two alias names
`test_signer_trust_refuses_when_neither_trigger_alias_is_present` | 1 | `AttestationPolicyError`
`test_signer_workflow_mismatch_is_denied` | 1 | `signer_workflow_mismatch`
`test_source_repository_mismatch_is_denied` | 1 | `signer_repository_mismatch`
`test_self_hosted_runner_is_denied` | 1 | `self_hosted_runner`
`test_non_push_trigger_is_denied` | 1 | `signer_trigger_mismatch` — ADR decision 5's "requires a `push` trigger"
`test_signer_trust_ignores_statement_predicate_entirely` | 1 | **rule 2, behavioral** — a `statement.predicate` asserting a different workflow/repo/runner changes nothing
`test_signer_trust_source_never_reads_statement` | 1 | rule 2, structural
`test_signer_trust_reports_signature_checked_false` | 1 | rule 3
`test_signer_trust_has_no_signer_digest_parameter` | 1 | **D10.10's code half** — `inspect.signature` carries no `signer_digest`
`test_anchor_lookup_corroborated_yields_no_issue` | 1 | `None`
`test_anchor_lookup_contradicted_has_its_own_code` | 1 | `anchor_attestation_contradicted`
`test_anchor_lookup_unavailable_has_a_distinct_code` | 1 | **D10.6** — `anchor_attestation_unavailable`, and `!=` the contradicted code
`test_anchor_lookup_transport_error_is_unavailable_not_contradicted` | 1 | a 5xx/timeout detail maps to `unavailable`; "I could not look" ≠ "it said no"
`test_anchor_lookup_refuses_an_unknown_outcome` | 1 | raises; no silent default
`test_anchor_lookup_codes_match_the_public_issue_code_pattern` | 1 | all codes match `^[a-z0-9_]{1,64}$`
| **Total** | **26** | |

- [ ] **Step 2: Confirm they fail with `ModuleNotFoundError: No module named 'loop.attestation'`**

- [ ] **Step 3: Implement**

ILLUSTRATIVE:

```python
# loop/attestation.py  (ILLUSTRATIVE)
"""A pure signer-trust policy over an ALREADY-VERIFIED verificationResult.

This module evaluates claims `gh attestation verify` has already established. It
establishes NOTHING itself: it never signs, never verifies a signature, never
opens a socket, and never reads an environment variable. It refuses — loudly —
when a claim it needs is absent, because a policy that treats a missing claim as
satisfied is worse than no policy.

Only `signature.certificate` and `verifiedTimestamps` are unforgeable by the
workflow that produced the attestation (gh's own help text says so). Everything
under `statement.predicate` is user-controllable metadata and is never read here.
"""
```

- [ ] **Step 4: Mutation probe**

Temporarily make an absent required claim default to `""` and pass; confirm the four `test_signer_trust_refuses_when_a_required_claim_is_absent` cases fail. Temporarily read `result["statement"]["predicate"]["run_id"]` inside the function; confirm both rule-2 tests fail. Revert.

**Acceptance:** `scripts/test_attestation_policy.py` reports **exactly 26 passed** in both dependency legs; the full suite reports **exactly 1491 passed / 18 skipped** (1465 + 26) and **1392 passed / 117 skipped** in the fallback leg; `grep -rn "environ\|getenv\|subprocess\|urllib\|socket" loop/attestation.py` → **zero matches**; both mutation probes failed as predicted and were reverted.

- [ ] **Step 5: Commit**

```bash
git add loop/attestation.py scripts/test_attestation_policy.py
git commit -m "feat(attestation): pure signer-trust policy that refuses on an absent claim"
```

---

## Task 7: Purity, made mechanical again

The 4a boundary tests scan `loop/` wholesale, so they already cover the new modules for signing tokens and environment reads. This task closes what they do **not** cover: network/subprocess reach, Statement emission from the new surfaces, and the `signature_checked` constant.

**Files:**
- Modify: `scripts/test_verdict_purity.py`

- [ ] **Step 1: Write the tests** (8 cases)

| Test | Cases | Asserts |
|---|---|---|
`test_new_modules_import_only_stdlib_and_loop` | **3** | parametrized `anchor.py`, `attestation.py`, `verdict.py` — the AST walk already at `scripts/test_verdict_purity.py:45`
`test_no_module_under_loop_reaches_the_network_or_shells_out` | 1 | **D10.9's new leg** — `subprocess`, `socket`, `urllib`, `http.client`, `requests` banned repo-wide under `loop/`; the network lives in `scripts/`
`test_kernel_emits_no_statement_key_anywhere` | **2** | parametrized over `verdict` and `verdict --compare` output: no `_type` / `subject` / `predicateType` / `predicate` key
`test_compare_report_compared_block_carries_no_free_text` | 1 | scoped to `report["compared"]` — digests, enums and `run_id` only. `issues[].message` is deliberately exempt: a local report may explain itself; a **predicate** may not
`test_signature_checked_literal_is_always_false` | 1 | AST-level over `loop/`: every assignment or dict value for `signature_checked` is the constant `False`
| **Total** | **8** | |

- [ ] **Step 2: Run and confirm each fails against a deliberately broken tree, then green**

For the network ban, add `import subprocess` to `loop/anchor.py`, confirm the test fails, revert. **If either 4a purity test (`test_kernel_never_references_a_signing_stack`, `test_kernel_reads_no_environment_variable`) fails at any point, that is a real finding — fix the code, not the test.**

**Acceptance:** `scripts/test_verdict_purity.py` reports **exactly 14 passed** (its 6 collected cases at `c493804` + 8) with `pyyaml+jsonschema+pytest`, and **13 passed / 1 skipped** with `pyyaml+pytest` (its pre-existing `importorskip` case); the full suite reports **exactly 1499 passed / 18 skipped** (1491 + 8) and **1400 passed / 117 skipped** in the fallback leg; `grep -rn "environ\|getenv" --include=*.py loop/` → **zero matches**.

- [ ] **Step 3: Commit**

```bash
git add scripts/test_verdict_purity.py
git commit -m "test(verdict): extend the ADR 0002 boundary to the 4b modules"
```

---

## Task 8: The resolve step — `scripts/action_anchor_resolve.py`

The only place in this repo that invokes `gh`. It lives in `scripts/`, not `loop/`, because it reads the environment and touches the network — the tool layer, following the `scripts/action_scorecard.py` precedent (`action.yml:175-176`) of an extracted, **tested** script the composite action calls.

**Files:**
- Create: `scripts/action_anchor_resolve.py`, `scripts/test_action_anchor_resolve.py`

**Interfaces:**
- Consumes: Task 1's `read_anchor` / `subject_bytes` / `SUBJECT_NAME`; Task 6's `check_signer_trust` / `anchor_lookup_issue`; `loop/verdict.py:23::PREDICATE_TYPE`. Self-bootstraps `sys.path` from `__file__` exactly as `scripts/ci_anchor_probe.py:26-28` does — **a path-invoked script has no installed package in CI** (the S3b post-merge lesson).
- Produces: exit 0 corroborated, exit 1 contradicted-or-unavailable, exit 2 usage/refusal; step outputs `anchor-outcome`, `anchor-head`, `predicate-path`, `subject-path`; `::error::` / `::warning::` annotations carrying the typed code.

**What it does, in order (normative):**

1. Read the anchor file via `read_anchor`. `AnchorError` → exit 2 with the typed message. **Never proceed on an unreadable anchor.**
2. **Fail closed when `--signer-workflow` is empty** — D4 makes it the mandatory pin. Exit 2 with a legible message naming the `[host/]<owner>/<repo>/<path>/<to>/<workflow>` form.
3. Regenerate the subject file from the carried head: `subject_bytes(anchor["chain_head"])` written to `<runner-temp>/loop-chain-head`. Basename is `SUBJECT_NAME` so `actions/attest`'s name derivation and this regeneration agree. **This is only possible because of D1** — under 4a's `subject-digest` form the head has no preimage and no file could ever be presented (F1).
4. Run, as an argv list with `shell=False`:
   `gh attestation verify <subject-file> --repo <owner/repo> --predicate-type urn:loop-engineer:verdict:1 --signer-workflow <pin> --deny-self-hosted-runners --source-ref refs/heads/main --format json`

**`--source-ref refs/heads/main` is a deliberate repo-specific constant, not a placeholder.** ADR 0002 decision 5 requires the resolve step to pin a `push` trigger on the default branch, and this repo's default branch is `main` (`attest.yml` is `on: push: branches: [main]`). An adopter whose default branch differs must change it; it is **not** parameterized in this slice, because a `--source-ref` taken from an untrusted input would let a caller widen the pin to any ref and defeat the control. Say this in §24 rather than leaving a reader to assume portability.
   - `--predicate-type` is **mandatory**: it defaults to `https://slsa.dev/provenance/v1` and would reject every `verdict@1` attestation.
   - `--deny-self-hosted-runners` is passed **unconditionally** — ADR 0002's standing limits make it mandatory, not advisory, so there is deliberately no input to disable it.
   - `--signer-digest` is **never** passed (D4).
5. Classify with `anchor_lookup_issue`: exit 0 and a parsed result → `corroborated`; a clean verification failure or a 404 → `unavailable` when nothing was found, `contradicted` when an attestation was found but did not verify; a transport-class failure (5xx, timeout, auth, cancelled, `gh` missing from `PATH`) → `unavailable`. **Never let an unclassifiable failure fall through to success: anything the classifier cannot confidently classify is `anchor_attestation_unavailable`.** `gh`'s exit codes cannot tell these outcomes apart — see the exit-code subsection below, which is normative for this step.
6. Apply `check_signer_trust` to `[0].verificationResult`. An `AttestationPolicyError` (a claim name that does not match reality) is a **failure**, not a skip.
7. Extract the **bare** predicate — `.[0].verificationResult.statement.predicate` — to `<runner-temp>/attested-verdict.json` so `loop verdict --compare` receives a bare `verdict@1` and not the envelope it is required to refuse.

**The `[0]` selection is an assumption, and must be stated as one.** No ordering guarantee is documented for the underlying attestations endpoint (verified this session against the live docs), so `[0]` means *"some verified attestation for this subject"* — never *"the newest"*. It is sound here only because every entry in the array has already passed the same signer-trust policy and covers the same subject digest, so two entries cannot materially disagree about the head. **If the policy is ever relaxed to accept more than one signer, this assumption breaks** and the step must compare every entry rather than indexing. Record it in §24 beside the sunset date, not only here.
8. Emit the outputs and the annotation; exit 1 on any non-corroborated outcome.

**D6 note:** under D1 the whole path goes through `gh attestation verify`, so **no raw `gh api /repos/.../attestations/...` call remains** — the deprecated route is not on the critical path at all. Should one ever be needed, it goes in this file and nowhere else, and §24 records the `Sunset: Fri, 10 Mar 2028` date regardless.

### `gh`'s exit codes cannot distinguish D5's three outcomes (normative)

This is the sharpest constraint on step 5 and it must be written into the module's docstring, not discovered later. Read live from `gh help exit-codes` (gh 2.92.0):

> - If a command completes successfully, the exit code will be 0
> - If a command fails for any reason, the exit code will be 1
> - If a command is running but gets cancelled, the exit code will be 2
> - If a command requires authentication, the exit code will be 4

**There is no distinct exit code separating "no attestation exists" from "an attestation was found but the signer policy denied it" from "the index was unreachable".** All three arrive as exit 1. Verified live this session: a 64-hex subject file with no matching attestation produces

```
Error: HTTP 404: Not Found (https://api.github.com/repos/SollanSystems/loop-engineer/attestations/sha256:60e05bd1…?per_page=30&predicate_type=urn:loop-engineer:verdict:1)
```

and exits **1** — the same code a signature failure exits with. So the classifier **must parse stderr text**, which is a vendor string with no stability contract, and it can and will drift.

Three consequences, all normative:

1. **The fallback rule is fail-closed and absolute: any output the classifier cannot confidently classify becomes `anchor_attestation_unavailable`.** Never `corroborated`. Never a skip. An unrecognized stderr shape is the *most* suspicious case, not the most benign one, and the whole point of the distinct code is that "I could not look / I could not tell" is reportable without ever being promoting.
2. **Exit 4 (auth) and exit 2 (cancelled) are transport-class → `unavailable`.** Only exit 0 *plus* a parseable payload *plus* a passing `check_signer_trust` reaches `corroborated`.
3. **The stderr-classification table is pinned by a test over a REAL captured fixture, not a paraphrase.** Commit `scripts/fixtures/gh_attestation_verify/no_attestation_404.txt` containing the verbatim stderr above (captured by the command in Step 0 below), and drive the classifier from the file. A test author's remembered approximation of a vendor message is exactly the thing that passes review and fails in production. The **denial** shape cannot be captured pre-merge — F1 proves no `gh attestation verify` invocation against this repo's three existing attestations can get far enough to produce one — so it is captured in the first post-merge run and added as a second fixture (Task 10, Step 6).

- [ ] **Step 0: Capture the real `gh` stderr fixture**

```bash
bash -c 'cd "$(mktemp -d)" && python3 -c "open(\"loop-chain-head\",\"w\").write(\"0\"*64)" && \
  gh attestation verify ./loop-chain-head --repo SollanSystems/loop-engineer \
    --predicate-type urn:loop-engineer:verdict:1 --deny-self-hosted-runners \
    --format json > /dev/null; echo "EXIT=$?"'
```

Expected: the `HTTP 404: Not Found` line above on stderr and `EXIT=1`. Copy that stderr **verbatim** into `scripts/fixtures/gh_attestation_verify/no_attestation_404.txt`. `scripts/` file lists are not pinned by `evals/cases/structural.json`, so a new fixture directory there is safe (only `reference/` is count-pinned).

### Exception enumeration for the subprocess-and-parse path (normative)

This is the highest-risk new module in the slice: it shells out and parses another program's stdout. Every failure below must land as a **typed outcome naming which shape assumption failed** — never a traceback, never a silent pass.

| Statement | Raises | Becomes |
|---|---|---|
| `subprocess.run(["gh", …])` with `gh` absent from `PATH` | `FileNotFoundError` | `anchor_attestation_unavailable`, message naming `gh` as not found. **Categorically different from a bad exit code** — the process never started, so there is no stderr to classify |
| `subprocess.run(…)` with `gh` present but not executable | `PermissionError` / `OSError` | `anchor_attestation_unavailable` |
| `json.loads(proc.stdout)` on non-JSON stdout (exit 0 but a banner, an update notice, empty output) | `json.JSONDecodeError` | `anchor_attestation_unavailable`, message naming "gh stdout was not JSON" |
| `result[0]` on a non-empty-list assumption | `IndexError` (empty array `[]`) / `TypeError` (an object, a string, `null` — anything not a list) | `anchor_attestation_unavailable`, message naming which of "empty array" / "not a list" held |
| `result[0]["verificationResult"]` and its nested reads | `KeyError` / `TypeError` | `anchor_attestation_unavailable`, message naming the missing key path |
| `check_signer_trust(...)` on a payload missing a pinned claim | `AttestationPolicyError` | a **failure** (exit 1), never a skip — Task 6 rule 1 |

Catch `(json.JSONDecodeError, IndexError, KeyError, TypeError)` at the parse site **as a named tuple with a comment on each class**, not as a bare `except Exception`: a bare catch would also swallow a genuine bug in this file and report it as a clean "index unavailable", which is a false-negative gate. `FileNotFoundError`/`OSError` are caught at the `subprocess.run` call site, separately, because the failure means something different (the tool is missing, not the answer).

- [ ] **Step 1: Write the failing tests** (23 cases)

Test with a **fake `gh` on `PATH`**: write an executable shim into `tmp_path/bin/gh` that echoes a canned `--format json` payload (or a canned failure) and prepend it to `PATH` for the subprocess. No network, no credentials, and the real argv is observable by having the shim log its arguments to a file.

**One case must do the opposite — `PATH` set to a directory with no `gh` in it at all** (`env={"PATH": str(tmp_path / "empty-bin")}`, not merely a shim that exits non-zero). Every other case exercises a `gh` that exists; the absent-tool path raises `FileNotFoundError` from `subprocess.run` before any exit code or stderr exists, so a shim can never reach it. That gap is exactly how a named-in-prose failure mode ships untested.

| Test | Cases | Asserts |
|---|---|---|
`test_resolve_corroborates_with_a_fake_gh` | 1 | exit 0, `anchor-outcome=corroborated` in the outputs file
`test_resolve_reports_contradicted_when_verify_denies` | 1 | exit 1, `anchor_attestation_contradicted`
`test_resolve_reports_unavailable_on_a_404` | 1 | exit 1, `anchor_attestation_unavailable`
`test_resolve_reports_unavailable_on_a_transport_failure` | 1 | a shim exiting 7 with a 5xx message → `unavailable`, **not** `contradicted`
`test_resolve_classifies_the_real_captured_404_stderr` | 1 | **M2** — drives the classifier from the committed verbatim fixture `scripts/fixtures/gh_attestation_verify/no_attestation_404.txt` (shim exits 1, echoes the file to stderr) → `anchor_attestation_unavailable`. A paraphrased vendor string proves nothing about the real one
`test_resolve_maps_an_unclassifiable_failure_to_unavailable` | 1 | **M2's fallback rule** — a shim exiting 1 with stderr the classifier has no pattern for (`"weasel"`) → `anchor_attestation_unavailable`, **never** `corroborated` and never a skip. An unrecognized shape is the most suspicious case, not the most benign
`test_resolve_maps_gh_auth_and_cancel_exits_to_unavailable` | **2** | parametrized exit **4** (auth) and exit **2** (cancelled) — the two other documented `gh` exit codes; both transport-class, both `unavailable`
`test_resolve_reports_unavailable_when_gh_is_not_on_path` | 1 | **M3** — `PATH` contains no `gh`; `subprocess.run` raises `FileNotFoundError` before any exit code exists → `anchor_attestation_unavailable`, message names `gh`, **no traceback**, exit 1
`test_resolve_reports_unavailable_on_unparseable_gh_stdout` | **3** | **M1** — parametrized over a shim exiting 0 with (a) non-JSON stdout, (b) `[]`, (c) `{"verificationResult": …}` (an object, not a list). Each → `anchor_attestation_unavailable` with a message naming which shape assumption failed (`json.JSONDecodeError` / `IndexError` / `TypeError`); **no traceback** in any of the three
`test_resolve_fails_closed_when_signer_workflow_is_empty` | 1 | exit 2, message names the `--signer-workflow` form
`test_resolve_fails_closed_on_an_unreadable_anchor` | 1 | exit 2, typed
`test_resolve_writes_the_subject_file_bytes_from_the_anchor` | 1 | the written file is **exactly 64 bytes**, basename `loop-chain-head`
`test_resolve_extracts_a_bare_predicate_for_compare` | 1 | the extracted file has a `schema` key and **no** `_type`/`subject`/`predicateType`/`predicate` key — i.e. `loop verdict --compare` will accept it
`test_resolve_never_passes_signer_digest` | 1 | **D4** — the shim's argv log contains no `--signer-digest`
`test_resolve_always_passes_deny_self_hosted_runners` | 1 | present in every invocation
`test_resolve_passes_the_predicate_type` | 1 | `--predicate-type urn:loop-engineer:verdict:1` present — without it gh enforces the SLSA default and rejects everything
`test_resolve_invokes_gh_with_shell_false_argv` | 1 | the anchor head is never interpolated into a shell string
`test_resolve_refuses_when_the_policy_claims_are_absent` | 1 | a payload missing `runnerEnvironment` → exit 1 with the refusal surfaced, **not** a pass
`test_resolve_isolates_the_single_gh_invocation` | 1 | **D6** — exactly one `gh` call site in the file (AST-level), so a future migration is a one-line change
`test_resolve_emits_all_four_step_outputs` | 1 | `anchor-outcome`, `anchor-head`, `predicate-path`, `subject-path`
| **Total** | **23** | |

- [ ] **Step 2: Confirm they fail, then implement**

- [ ] **Step 3: Verify the script runs path-invoked with no `PYTHONPATH`**

```bash
bash -c 'cd /tmp && uv run --with pyyaml python3 -B /mnt/c/Dev/projects/loop-engineer/scripts/action_anchor_resolve.py --help'
```

Expected: usage text, exit 0 — **not** `ModuleNotFoundError: No module named 'loop'`. This exact failure broke CI post-merge in Slice 4b's sibling S3b; the `sys.path` bootstrap is the fix and this command is the proof.

**Acceptance:** `scripts/test_action_anchor_resolve.py` reports **exactly 23 passed** in both dependency legs; `scripts/fixtures/gh_attestation_verify/no_attestation_404.txt` is committed and is the source the 404-classification test reads; **no** failure path in the module produces a traceback or reaches `corroborated` — grep the file for `except Exception` and find **zero** matches; the full suite reports **exactly 1522 passed / 18 skipped** (1499 + 23) and **1423 passed / 117 skipped** in the fallback leg; the path-invoked `--help` check exits 0.

- [ ] **Step 4: Commit**

```bash
git add scripts/action_anchor_resolve.py scripts/test_action_anchor_resolve.py \
        scripts/fixtures/gh_attestation_verify/no_attestation_404.txt
git commit -m "feat(action): tested anchor-resolution step over gh attestation verify"
```

---

## Task 9: `action.yml` — D1's subject change and the anchor inputs

**This is the load-bearing change of the slice.** Under 4a's form the subject is `sha256:<chain head>`, and the chain head is a SHA-256 over a **synthesized event preimage** (§16) — no bytes exist whose hash equals it, and producing some would be a preimage attack. F1's decisive probe: a file *named* after the digest but empty made `gh` look up `…/attestations/sha256:e3b0c442…` (the SHA-256 of the empty string) and return 404, because **gh hashes the file's content**. So `gh attestation verify` can never succeed against a `verdict@1` attestation as currently minted, and ADR 0002 decision 4's authenticity step was not executable.

D1's fix: `action.yml` writes a file whose **entire content is the chain head** and passes it as `subject-path`. Byte form is normative and pinned by test: **exactly 64 bytes, lowercase hex, no trailing newline. Nothing else.** The consumer regenerates those bytes from the head alone. The predicate bytes were the obvious alternative subject and are **rejected**: `doctor.validation_mode` and `tool.version` live inside the predicate, so the bytes differ across environments (measured: `873dfc87…` with jsonschema, `8de3d88c…` in structural-fallback) and a consumer on another tool version could never reproduce them. **The head is version-independent.**

ADR 0002 decision 2's sentence *"The subject is the chain head alone"* survives in spirit — the subject still commits to nothing but the head — and changes in **mechanism** only.

**Files:**
- Modify: `action.yml`
- Create: `scripts/test_action_attest_surface.py`

- [ ] **Step 1: Replace the subject inputs on the `attest verdict` step** (`action.yml:144-156`)

ILLUSTRATIVE:

```yaml
    - name: chain-head subject file          # (ILLUSTRATIVE)
      id: subject
      if: ${{ inputs.attest == 'true' && steps.chain-head.outputs.chain-head != '' }}
      shell: bash
      env:
        LOOP_PATH: "${{ inputs.path }}"
      run: |
        # 64 bytes, lowercase hex, NO trailing newline (reference §24). The one
        # writer is loop.verdict.subject_bytes, reached via --emit-subject, so the
        # attest side and the resolve side cannot disagree on the byte form.
        loop verdict --emit-subject "$LOOP_PATH" > "${RUNNER_TEMP}/loop-chain-head"
        echo "path=${RUNNER_TEMP}/loop-chain-head" >> "$GITHUB_OUTPUT"

    - name: attest verdict                    # (ILLUSTRATIVE)
      id: attest
      if: ${{ inputs.attest == 'true' && steps.chain-head.outputs.chain-head != '' }}
      uses: actions/attest@v4
      with:
        subject-path: ${{ steps.subject.outputs.path }}
        predicate-type: urn:loop-engineer:verdict:1
        predicate-path: ${{ steps.verdict.outputs.predicate-path }}
        push-to-registry: false
        create-storage-record: false
```

**Pass `subject-path` ONLY — no `subject-name`.** Verified live from `repos/actions/attest/contents/action.yml`: `subject-name` is *"Required when identifying the subject with the `subject-digest` input"*, i.e. optional with `subject-path`, where the name derives from the file. Because the file is literally named `loop-chain-head`, the derived subject name equals 4a's explicit one. Passing both is untested behavior; Task 10 asserts the derived name in the live run instead. `create-storage-record: false` stays — its **live default is `true`** (F5), so the explicit pin does real work.

- [ ] **Step 2: Add the anchor inputs, the resolve step, and the output**

New inputs: `anchor` (default `""` — a path to a tracked `anchor@1` file) and `signer-workflow` (default `""`). New output: `anchor-outcome`. The resolve step runs `python "${{ github.action_path }}/scripts/action_anchor_resolve.py" …` (the `action_scorecard.py` invocation shape), then feeds its extracted predicate to `loop verdict --compare` and its carried head to `loop doctor --expect-chain-ancestor`.

**Precedence (ADR decision 5, honored here rather than in the CLI):** a non-empty `expect-chain-head` input **wins** over anchor resolution, and the step must say which it used in the step summary — a silently dropped anchor is worse than a refused one. `anchor` non-empty with `signer-workflow` empty **fails the step with a legible message**, never resolves unpinned.

**A composite action that swallows the resolve step's exit code turns the whole gate into decoration.** Task 8's 23 tests exercise the *script*; nothing there pins that `action.yml` lets its failure reach the job. That is the exact failure mode D5 exists to prevent — the script correctly returns exit 1 for `anchor_attestation_unavailable` and the job goes green anyway. So the wiring is pinned by test, and the illustrative YAML shows the shape that passes those pins:

```yaml
    - name: resolve the anchor attestation      # (ILLUSTRATIVE)
      id: anchor
      # No continue-on-error. No `if: always()`. Both would decouple this step's
      # exit code from the job's outcome, which is the whole gate.
      if: ${{ inputs.anchor != '' && inputs.expect-chain-head == '' }}
      shell: bash
      env:
        GH_TOKEN: ${{ inputs.github-token }}
        LOOP_PATH: "${{ inputs.path }}"
        LOOP_ANCHOR: "${{ inputs.anchor }}"
        LOOP_SIGNER_WORKFLOW: "${{ inputs.signer-workflow }}"
      run: |
        # NO `set +e` around a gating call. The scorecard step below uses `set +e`
        # deliberately, because inspect is ADVISORY (see its own comment) — this
        # step is not advisory, and its exit code is the finding.
        python "${{ github.action_path }}/scripts/action_anchor_resolve.py" \
          --anchor "$LOOP_ANCHOR" \
          --repo "$GITHUB_REPOSITORY" \
          --signer-workflow "$LOOP_SIGNER_WORKFLOW" \
          --runner-temp "$RUNNER_TEMP"

    - name: compare the attested verdict        # (ILLUSTRATIVE)
      if: ${{ steps.anchor.outputs.anchor-outcome == 'corroborated' }}
      shell: bash
      env:
        LOOP_PATH: "${{ inputs.path }}"
      run: |
        loop verdict --compare "${{ steps.anchor.outputs.predicate-path }}" "$LOOP_PATH"
        loop doctor --expect-chain-ancestor "${{ steps.anchor.outputs.anchor-head }}" "$LOOP_PATH"

    - name: anchor resolution skipped (explicit head wins)   # (ILLUSTRATIVE)
      if: ${{ inputs.anchor != '' && inputs.expect-chain-head != '' }}
      shell: bash
      run: |
        echo "**loop-engineer anchor:** not resolved — the explicit expect-chain-head input wins (ADR 0002 decision 5)." \
          >> "$GITHUB_STEP_SUMMARY"
```

Three properties the YAML must hold and the tests pin: (a) **no `continue-on-error`** on the resolve step or on either downstream gating step; (b) **no `if: always()`** on any of them — `always()` runs a step even after an upstream failure and, combined with a same-step non-failure, is the standard way a gate's red goes unseen; (c) **no `set +e`** wrapping the `python …action_anchor_resolve.py`, `loop verdict --compare`, or `loop doctor --expect-chain-ancestor` calls. Note the repo already contains **two** deliberate `set +e` uses, both correct and both advisory: `action.yml:172` in `loop inspect (scorecard)` (its own comment says *"inspect is advisory"*, and `set -e` is restored at `:174`) and `action.yml:189` in `PR scorecard comment (optional)` (*"Non-fatal on any API failure"*). And one deliberate `if: always()` at `action.yml:102` on `chain head (anchor surface)`, which must keep running after a doctor failure because *a mismatch is exactly the run whose head an operator needs recorded*. So the tests must be scoped to the **gating** steps by step id, rather than banning either string outright — a blanket ban would fail on three pieces of correct existing code and would be deleted by the next implementer instead of fixed.

- [ ] **Step 3: Write the tests** (12 cases, `scripts/test_action_attest_surface.py`, parsing `action.yml` with `yaml.safe_load`)

| Test | Cases | Asserts |
|---|---|---|
`test_action_attests_a_subject_path_not_a_subject_digest` | 1 | **D1** — the attest step has `subject-path` and **no** `subject-digest`
`test_action_never_passes_subject_digest_anywhere` | 1 | the string `subject-digest` appears nowhere in `action.yml`
`test_subject_file_basename_is_the_pinned_subject_name` | 1 | the redirect target's basename equals `loop.verdict.SUBJECT_NAME`
`test_subject_file_is_written_by_emit_subject` | 1 | the step uses `loop verdict --emit-subject`, so the byte form has exactly one definition
`test_action_pins_push_to_registry_and_create_storage_record_false` | 1 | both explicit `false` (F5: the latter's live default is `true`)
`test_action_declares_the_anchor_and_signer_workflow_inputs` | 1 | both present with `default: ""`
`test_action_requires_signer_workflow_when_anchor_is_set` | 1 | the resolve step's guard exists and its message names `--signer-workflow`
`test_action_outputs_the_anchor_outcome` | 1 | `anchor-outcome` in `outputs`
`test_explicit_expect_chain_head_wins_over_the_resolved_anchor` | 1 | the precedence condition is expressed in the step `if:`/guard, not left implicit
`test_resolve_step_and_downstream_checks_have_no_continue_on_error` | **2** | **B2** — parametrized over the resolve step and the compare/ancestor step: neither carries a `continue-on-error` key at all (not even `false`), and **no** `set +e` appears in either step's `run:` body. Scoped to those step ids so the two deliberate advisory `set +e` uses (`action.yml:172` in `loop inspect (scorecard)`, `:189` in `PR scorecard comment (optional)`) still pass. A swallowed exit code here makes the gate decoration
`test_no_gating_step_is_marked_if_always` | 1 | **B2** — the resolve step's `if:` and the downstream compare/ancestor step's `if:` contain no `always()`. `always()` runs the step after an upstream failure and is the standard way a gate's red goes unseen; the pre-existing `if: always()` on `chain head (anchor surface)` (`action.yml:102`) is deliberate and is explicitly excluded by step id
`test_compare_is_guarded_on_head_equality_while_ancestry_is_unconditional` | 1 | **ADDED BY WHOLE-BRANCH REVIEW.** `--compare` treats an ancestor head as a disagreement (Task 4 rule 4), so comparing an older attested predicate against a store that legitimately grew fails every time — which would make the `anchor` input unusable for the cross-run detection it exists for. Ancestry must run FIRST and unconditionally; `--compare` is guarded on `ANCHOR_HEAD = CURRENT_HEAD` and its skip is announced in the step summary
| **Total** | **13** | |

- [ ] **Step 4: Lint the YAML**

```bash
uv run --with pyyaml python3 -B -c "
import yaml, pathlib
doc = yaml.safe_load(pathlib.Path('action.yml').read_text(encoding='utf-8'))
print('inputs:', sorted(doc['inputs']))
print('outputs:', sorted(doc['outputs']))
print('steps:', [s.get('name') for s in doc['runs']['steps']])"
```

Expected: `anchor` and `signer-workflow` in inputs; `anchor-outcome` in outputs; the subject-file step ordered **after** `chain head (anchor surface)` and **before** `attest verdict`.

**Acceptance:** `scripts/test_action_attest_surface.py` reports **exactly 13 passed**; `grep -n "continue-on-error" action.yml` → **0 matches**; the only `set +e` uses in `action.yml` are the two pre-existing advisory ones (`:172` `loop inspect`, `:189` PR comment) and the only `if: always()` is the pre-existing `:102` `chain head (anchor surface)` — none of the three is the resolve step or the compare/ancestor step; the full suite reports **exactly 1535 passed / 18 skipped** (1522 + 13) and **1436 passed / 117 skipped** in the fallback leg; `grep -c "subject-digest" action.yml` → **0**; the YAML lint prints the expected inputs, outputs, and step order.

- [ ] **Step 5: Commit**

```bash
git add action.yml scripts/test_action_attest_surface.py
git commit -m "feat(action): attest a head-bearing subject file so verification is executable"
```

---

## Task 10: The live experiment — verify what we just attested

**This task cannot be validated before merge.** `.github/workflows/attest.yml` fires on `push: branches: [main]` only, so a real attestation mints only after landing. Plan it as an experiment with a stated prediction and a falsifiable check, exactly as 4a did — and note that this repo has **three prior live attest runs** to compare against, so the delta is measurable rather than merely asserted.

**Files:**
- Modify: `.github/workflows/attest.yml`, `.github/workflows/ci.yml`
- Create: `scripts/test_attest_workflow.py`

### What lands

1. **`attest.yml` gains a "resolve the attestation we just minted" step** after the existing `assert an attestation was actually created` step (`:92-109`) — and it runs **the shipped `scripts/action_anchor_resolve.py`**, not a hand-written copy of its logic.

   **This is the point of the step, and it is not negotiable.** The adopter-facing artifact is `scripts/action_anchor_resolve.py` — it is what `action.yml`'s `anchor` input actually invokes, and Task 8's 23 tests exercise it only against a **fake** `gh` shim. If the live experiment reimplements verify-and-classify inline in bash, then the one thing that gets real-`gh`, real-index mileage is a duplicate that no adopter ever runs, the two implementations can drift silently, and the slice ships a live-green badge for code that was never live-exercised. So the experiment is a **same-run self-referential dogfood**: write an `anchor@1` file whose `chain_head` is the head this very job just attested, hand it to the real script, and assert the script's exit code and step outputs.

```yaml
      - name: resolve the attestation we just minted   # (ILLUSTRATIVE)
        id: resolve
        env:
          GH_TOKEN: ${{ github.token }}
          WS: ${{ steps.seed.outputs.workspace }}
          HEAD: ${{ steps.gate.outputs.chain-head }}
        run: |
          # A real anchor@1 file carrying the head THIS job just attested. The
          # script regenerates the 64-byte subject from it, so the byte form is
          # exercised end to end by loop.verdict.subject_bytes — one writer.
          python -B - "$HEAD" "${RUNNER_TEMP}/loop-anchor.json" <<'PY'
          import json, sys
          json.dump({"schema": "loop-engineer/anchor@1", "chain_head": sys.argv[1]},
                    open(sys.argv[2], "w"))
          PY
          # THE SHIPPED SCRIPT — the same entry point action.yml's `anchor` input
          # calls. No inline gh invocation lives in this workflow.
          # The attestation index is eventually consistent; bound the wait rather
          # than assuming it, and fail loud when the budget is exhausted. The retry
          # wraps the SCRIPT, so `anchor_attestation_unavailable` (its honest
          # answer while the index catches up) is what is being retried.
          for attempt in 1 2 3 4 5 6; do
            if python -B scripts/action_anchor_resolve.py \
                 --anchor "${RUNNER_TEMP}/loop-anchor.json" \
                 --repo "$GITHUB_REPOSITORY" \
                 --signer-workflow SollanSystems/loop-engineer/.github/workflows/attest.yml \
                 --runner-temp "$RUNNER_TEMP" \
                 --github-output "$GITHUB_OUTPUT"; then
              break
            fi
            [ "$attempt" = "6" ] && {
              echo "::error::action_anchor_resolve.py never corroborated the attestation we just minted"
              exit 1; }
            sleep 5
          done
```

   **Honest scope, stated in the workflow's own comment and in the PR body:** this is a **within-run** exercise. The anchor is written from a head minted seconds earlier in the same job, so it proves the resolve path works against the real `gh` and the real index — it does **not** prove cross-run detection, because `attest.yml` seeds an ephemeral `$RUNNER_TEMP` workspace and there is no persistent store to anchor across runs (honest limit 10). Do not let this step's green read as a cross-run proof.

2. **Then the assertions that make it falsifiable**, in the same job, driven off the script's own outputs and the JSON it extracted:
   - `steps.resolve.outputs.anchor-outcome == "corroborated"` — the script's own verdict, which is the artifact under test.
   - the subject file the script wrote is **exactly 64 bytes** and its basename is `loop-chain-head` — the D1 byte form, regenerated by `loop.verdict.subject_bytes` from the carried head alone.
   - `subject[0].name == "loop-chain-head"` — the name `actions/attest` derived from the file matches the pinned one.
   - `subject[0].digest.sha256 == sha256(<the 64 head bytes>)` **and `!= predicate.chain.head`.** F2 verified that in all three prior attestations `subject[0].digest.sha256` **equalled** `predicate.chain.head`; under D1 it must now differ, because the subject digest is the hash of a *file containing* the head. **This single inequality is the crispest proof that D1 landed.**
   - `check_signer_trust` over `.[0].verificationResult` returned `ok: true` — reached **through the script**, which is where the policy is actually wired. If a pinned claim name does not match gh's actual JSON, this **refuses loudly** (Task 6 rule 1) and the job fails — the fail-closed design turning an unknowable-pre-merge fact into a legible red build rather than a silent pass.
   - `python -B -m loop verdict --compare "$(…outputs.predicate-path)" "$WS"` exits **0**, against the bare predicate **the script extracted** — the first live exercise of the agreement path, on the same extraction an adopter gets.

3. **`ci.yml`'s `anchor-live` job gains a within-run grown-store ancestry exercise** (no network, runs on every PR): seed with `scripts/ci_anchor_probe.py`, record head `H`, append two more events, then assert `loop doctor --expect-chain-ancestor "$H"` **exits 0** while `loop doctor --expect-chain-head "$H"` **exits 1 with `chain_anchor_not_ancestor` absent and `chain_anchor_mismatch` present**. That inverted pair is F3 proven live, and it is the only ancestry coverage this repo can honestly claim — see honest limit 10.

### The prediction, stated before the run

- **Before this slice:** `gh attestation verify` against any of the three existing `verdict@1` attestations is *structurally impossible* — there is no file to present.
- **After the first post-merge run:** `gh attestation verify` exits **0**, and `subject[0].digest.sha256 != predicate.chain.head` for the first time in this repo's history.
- **If the run fails**, the fix is a follow-up PR, not a revert: the `attest` input still defaults to `false`, so no consumer is affected, and the previous three attestations remain valid records of what they were.
- The most likely failure is a mismatched `signature.certificate` leaf claim name (Task 6 rule 7). That surfaces as an `AttestationPolicyError` naming the missing key — read it, correct `REQUIRED_CERTIFICATE_CLAIMS` or `_TRIGGER_CLAIM_ALIASES`, and ship the one-line follow-up.

- [ ] **Step 1: Write the tests** (10 cases, `scripts/test_attest_workflow.py`)

| Test | Cases | Asserts |
|---|---|---|
`test_attest_workflow_resolves_through_the_shipped_script` | 1 | **M4** — the `verdict` job invokes `scripts/action_anchor_resolve.py`, the same entry point `action.yml`'s `anchor` input calls
`test_attest_workflow_contains_no_inline_gh_attestation_call` | 1 | **M4's teeth** — the string `gh attestation` appears **nowhere** in `.github/workflows/attest.yml`. Without this pin the inline duplicate can be reintroduced beside the script and the two drift silently
`test_attest_workflow_writes_a_real_anchor_file_for_the_resolve` | 1 | the step builds a `loop-engineer/anchor@1` document whose `chain_head` is the head this job attested — so the anchor read path is exercised, not bypassed
`test_attest_workflow_pins_the_signer_workflow` | 1 | `--signer-workflow SollanSystems/loop-engineer/.github/workflows/attest.yml` present; `--signer-digest` **absent** (D4)
`test_attest_workflow_pins_the_predicate_type_and_denies_self_hosted` | 1 | both are the **script's** responsibility, so this asserts the script is invoked without any flag that would disable either, and cross-checks Task 8's argv pins — without `--predicate-type`, gh enforces the SLSA default
`test_attest_workflow_asserts_the_subject_name_and_digest_inequality` | 1 | the step body asserts `subject[0].name` and `subject[0].digest.sha256 != predicate.chain.head`
`test_attest_workflow_runs_compare_against_the_resolved_predicate` | 1 | a `loop verdict --compare` invocation consumes the script's `predicate-path` output, not a hand-rolled `jq` extraction
`test_attest_workflow_bounds_the_index_consistency_retry` | 1 | the retry loop has a finite attempt budget and **fails loud** when exhausted — an unbounded or silently-passing wait would make the step unfalsifiable
`test_attest_workflow_still_runs_only_on_push_to_main` | 1 | `on.push.branches == ["main"]`, no `pull_request` trigger — ADR decision 5's confused-deputy guard, unchanged
`test_ci_exercises_ancestry_on_a_grown_store_and_a_fallback_leg` | 1 | **ADDED DURING EXECUTION.** Item 3's within-run ancestry pair had no test row, and Open Item 10's fallback leg (resolved below) had none either — both are ci.yml shape, so one case pins both: the grown-store `--expect-chain-ancestor` 0 / `--expect-chain-head` 1 inversion with the two codes not collapsing, and `gates-fallback` installing no jsonschema while proving it is really the fallback leg
| **Total** | **10** | |

- [ ] **Step 2: Lint both workflow files**

```bash
uv run --with pyyaml python3 -B -c "
import yaml, pathlib
for f in ('.github/workflows/attest.yml', '.github/workflows/ci.yml'):
    doc = yaml.safe_load(pathlib.Path(f).read_text(encoding='utf-8'))
    print(f, sorted(doc['jobs']))"
```

- [ ] **Step 3: Confirm the action majors still match the repo's other workflows**

```bash
grep -rn "actions/checkout@\|actions/setup-python@" .github/workflows/
```

`ci.yml` mixes `setup-python@v7` (most jobs) and `@v6` (`recipe-openhands`, `recipe-ruflo`). **Do not "fix" that drift in this slice** — it is unrelated scope and a dependabot PR's job.

**Acceptance:** `scripts/test_attest_workflow.py` reports **exactly 10 passed**; the full suite reports **exactly 1545 passed / 18 skipped** (1535 + 10) and **1446 passed / 117 skipped** in the fallback leg; both workflow files parse; `grep -c "gh attestation" .github/workflows/attest.yml` → **0** (the workflow resolves through the shipped script, M4); the PR body states that `attest.yml` is unvalidatable pre-merge, names the **first post-merge run** as the experiment, and records the `subject[0].digest.sha256 != predicate.chain.head` inequality as the falsifiable check.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/attest.yml .github/workflows/ci.yml scripts/test_attest_workflow.py
git commit -m "ci: verify the minted attestation and exercise ancestry within a run"
```

- [ ] **Step 5: POST-MERGE CLOSURE — the slice is not done until the experiment is read**

A prediction nobody is required to go look at is not an experiment; it is a hope. Stating the prediction in the PR body (Step 4) is only half the protocol — **this step is the other half, and the slice stays open until it is checked off.** Task 6 rule 7 deliberately ships claim-name constants that *cannot be established pre-merge*; this is where they get established.

Immediately after the feature PR squash-merges to `main`:

1. **Watch the first `attest.yml` run.** `gh run list --workflow attest.yml --limit 1` then `gh run watch <id>`.
2. **Record the actual outcome in the run notes**, whichever way it went — a green resolve, or the exact failure. Not "as predicted": the observed value.
3. **Record the observed certificate claim names verbatim** from the run's extracted JSON:

   ```bash
   gh run view <id> --log | grep -A40 'resolve the attestation we just minted'
   # or, locally against the now-verifiable attestation:
   python -c "open('h','w').write('<the attested head>')"
   gh attestation verify ./h --repo SollanSystems/loop-engineer \
     --predicate-type urn:loop-engineer:verdict:1 --format json \
     | python -c "import json,sys; print(sorted(json.load(sys.stdin)[0]['verificationResult']['signature']['certificate']))"
   ```

   Those leaf names are Open Item 1 and Open Item 2. Write the observed list into the run notes and into §24 if it differs from the pinned constants.
4. **If the prediction was wrong, ship the one-line correction to `REQUIRED_CERTIFICATE_CLAIMS` / `_TRIGGER_CLAIM_ALIASES` immediately** — a same-day follow-up PR, before the slice is treated as done. The design is fail-closed precisely so this correction is a legible red build and a one-line diff rather than an investigation; do not leave a known-red gate standing to be "picked up next session". A wrong claim name means the anchor path refuses **every** attestation, which reads to an adopter as "the gate is broken", and a slice that ships that is not finished.
5. **Also capture the DENIAL-shape stderr fixture** that could not be captured pre-merge (Task 8, Step 0, third consequence): now that a verifiable attestation exists, run `gh attestation verify` against it with a deliberately wrong `--signer-workflow` and commit the verbatim stderr as `scripts/fixtures/gh_attestation_verify/signer_denied.txt`, with a test classifying it as `anchor_attestation_contradicted`. This is the second half of the M2 fixture pair and closes the "found but denied" branch against a real vendor string instead of a paraphrase.
6. **Then, and only then**, mark the slice done and update the plan's Open Items 1 and 2 from "unresolvable pre-merge" to the observed fact.

---

## Task 11: Normative documentation, the ADR amendment, and governance

**Files:**
- Modify: `reference/repo-os-contract.md` (append §24; **rewrite** part of §23), `docs/adr/0002-ci-attested-verdict.md`, `.github/CODEOWNERS`, `CHANGELOG.md`
- Create: `scripts/test_docs_slice4b.py`

- [ ] **Step 1: Rewrite §23's subject-seam paragraph** (`reference/repo-os-contract.md:1615-1626`)

That paragraph currently tells readers that *"fetch the bytes, re-hash, compare"* is a **false** inference. Under D1 it becomes **true for the subject file** — and remains false for the head as a hash of event data. **The paragraph must be rewritten, not merely amended** (D1's explicit instruction). It must now say:

- the signer binds `subject-path` to a file whose entire content is the chain head, so a consumer **can** regenerate the subject bytes from the head alone and `gh attestation verify` **does** succeed;
- the chain head itself is still a SHA-256 over a synthesized event preimage (§16) — there is no artifact whose bytes hash to the head, and a consumer must not go looking for one;
- the predicate bytes are **not** the subject, and why (`doctor.validation_mode` + `tool.version` make them environment-coupled; measured `873dfc87…` vs `8de3d88c…`);
- authenticity (`gh attestation verify`) and agreement (`loop verdict --compare`) are separate checks, in that order, and neither implies the other — pointing forward to §24.

- [ ] **Step 2: Append §24 — `loop verdict --compare`, anchor ancestry, and signer trust**

Numbered-section style matching §16/§17/§22/§23. It must cover, each as normative prose:

1. **The comparison report** — the four compared facets, the shape, the exit-code contract, and that **`doctor` and `tool` are deliberately not compared** with F4's measured reason.
2. **`signature_checked: false` on every path, with no flag to flip it.** The kernel establishes agreement; it never establishes authenticity.
3. **The typed refusals** — bare predicate only; Statement-shaped and `gh`-wrapper-shaped inputs refused by name; the documented jq path `.[0].verificationResult.statement.predicate`.
4. **`anchor@1`** — the shape, the default `loop-anchor.json` filename, the "tracked and not under `.loop/`" rule, and the inversion: **the attestation corroborates a carried head; it can never discover one**, because GitHub exposes no list endpoint, no ordering guarantee, and no digest-free route (F2).
5. **Anchor trust is exactly ordinary write access.** Same class of limit as "the worker can edit the verifier".
6. **Ancestry, not head equality** — `head_sequence`'s contract, why `--expect-chain-head` fails by construction on a growing store (F3, with the measured `9d388ae5…` seq 4 → `c336ecdc…` seq 5), and that ancestry is **established by replay, recomputing every hash, never by trusting the stored `event_hash` column** — because a tamperer who can rewrite the store can also insert a row bearing the anchored hash.
7. **The five new doctor/lookup codes**, each with its meaning, and why `chain_anchor_not_ancestor` is deliberately **not** a reuse of `chain_anchor_mismatch`.
8. **D5's three outcomes, and the sentence that keeps this a gate** — verbatim: *anything short of a verified 200 plus a successful `gh attestation verify` is non-promoting, and transport-class failures (5xx, timeout, auth) are separately reportable but exactly as non-promoting as a clean denial.* Plus: attestations are **deletable** (user- and org-scoped delete, bulk-delete, and delete-request endpoints, all permission-gated); GitHub's own guidance says to *"delete attestations that are no longer needed"*; **no retention window is documented anywhere** (the familiar 90-day/400-day figures are workflow **artifacts and logs**, not attestations) and roadmap issue #1128 records no built-in expiry. So the anchor is a deletable dependency, and a missing anchor must be a typed failure — otherwise an availability attack on the index becomes a gate bypass.
9. **Do not over-read the codes.** A 404 is consistent with never-attested, attested-then-deleted, and a transient index fault; HTTP status alone cannot separate them. The distinct codes exist for observability, never for differential trust. **Do not key logic on response body text** — the no-digest route returns a *generic* `documentation_url` while the digest-present-but-non-matching family returns `…/rest/repos/attestations#list-attestations`.
10. **The signer-trust policy** — pure over already-verified claims; refuses on an absent claim; reads only `signature.certificate` and `verifiedTimestamps`; treats `statement.predicate` as data to compare and never to trust.
11. **`--signer-digest` is deliberately not required (D10.10)** — with the `job_workflow_sha` reason spelled out: it pins `BuildSignerDigest` (OID `1.3.6.1.4.1.57264.1.10`), which for a non-reusable top-level workflow equals the triggering commit SHA and therefore **invalidates on every push**, not merely on a workflow edit. `--signer-workflow` is the mandatory pin.
12. **The REST route is deprecated (D6)** — `Deprecation: Tue, 10 Mar 2026`, **`Sunset: Fri, 10 Mar 2028`**, route-level (present on both the 200 and the 404 route, and absent from four control endpoints). The path goes through `gh attestation verify`; any raw call is isolated to one file.
13. **Public/private asymmetry (D8)** — public repos use the Sigstore Public Good instance and its public transparency log; **private repos use GitHub's own Sigstore instance, which has no transparency log** and federates only with Actions. The independent-audit property exists for public repos and does not exist for private ones. Also: for a public repo the attestations read succeeds **unauthenticated**, so `attestations: read` is defensive/future-proofing rather than a requirement.
14. **The honest limits**, including that this repo cannot dogfood cross-run ancestry (its attest workspace is ephemeral by construction), and that detection of an unattested rewrite is at best one run late.

- [ ] **Step 3: Append the ADR amendment**

`## Amendment (2026-07-29, Slice 4b)` at the end of `docs/adr/0002-ci-attested-verdict.md`. **A new section, not an in-place edit of the decision text** — the #108 erratum is the precedent for a correction, and this is a *decision change*, which earns its own dated section. It must record:

- **Decision 2 — mechanism change.** The subject is now a head-bearing **file** (`subject-path`), not `subject-digest: sha256:<head>`. Decision 2's sentence *"The subject is the chain head alone"* **survives in spirit** — the subject still commits to nothing but the head — and changes in mechanism only. Rejects the predicate bytes as the subject, with F4's measured reason.
- **Decision 4 — its first half was not executable as shipped.** `gh attestation verify` accepts only `[<file-path> | oci://<image-uri>]` and hashes the file's **content**; there is no digest-only input; a synthesized chain head has no preimage. D1 makes it executable.
- **Decision 5 — two corrections.** (a) *"fetch the most recent matching attestation"* is **not implementable from the index** (F2), so the head is carried in a tracked anchor file and the attestation corroborates it. (b) The cross-run check is **ancestry**, not head equality (F3) — the ADR's resolve target was incoherent because appending one event moves the head.
- **Open verification item 3 — settled.** `--signer-digest` invalidates on every push (`job_workflow_sha`), so it is not a mandatory pin; `--signer-workflow` is.
- **Open verification item 2 — settled.** No retention window is documented; attestations are deletable; the REST route is deprecated with a `10 Mar 2028` sunset. An absent anchor is therefore a typed failure, never a skip.
- **Decision 6 — the path list grew** by the anchor path, and decision 6 remains **documented but not in force**: the live ruleset requires 0 approvals. Do not describe CODEOWNERS as an operative control.

- [ ] **Step 4: Add the anchor path to CODEOWNERS** (D2)

Append a pattern covering the conventional anchor filename at any depth, with a comment naming *why* — an actor who can edit the anchor re-points it at a head they had attested, so it is a gate-defining path in exactly the sense `loop/**` and `action.yml` are.

- [ ] **Step 5: CHANGELOG under `## Unreleased`**

In the project's established voice: the `--compare` agreement check, the replay-based ancestry gate, `anchor@1`, the signer-trust policy, and the **behavioral change** that the attested subject is now a head-bearing file (so previously minted attestations carry a different subject form). Then what it does **not** buy — one run of detection latency, worker-can-edit-the-verifier, anchor trust equals write access, and the public/private asymmetry. **Do not use the word "tamper-proof".**

**Two sentences already in `## Unreleased` become FALSE and must be corrected in place, not merely appended past.** 4a's entry is still unreleased, so 4a and 4b ship in the *same* release and the section must describe one coherent shipped state:

1. `CHANGELOG.md:32` advertises `` `subject-name: loop-chain-head` / `subject-digest: sha256:<chain-head>` `` as the shipped form. Under D1 there is no `subject-digest` input at all. Rewrite it to the head-bearing-file form.
2. `CHANGELOG.md:47-49` says *"Verification (`--compare`, anchor auto-resolution, signer-trust policy) is slice 4b and does not ship here."* Once this slice lands that sentence is false in the release it appears in. Replace it — and note that 4a's "the control is code-owner review on those paths, which is in force only once the repository ruleset requires it" stays **true and must be kept**, because the ruleset still requires 0 approvals (D9).

A changelog that describes a subject form the code does not implement is exactly the false claim this project refuses; it is worth a test of its own.

- [ ] **Step 6: Write the doc-parity tests** (22 cases, `scripts/test_docs_slice4b.py` — the row sum; the pre-hardening Total of 20 undercounted the two parametrized rows)

Every assertion below must be **proven to FAIL against the tree as it stood before the documentation commit** — a pin that passes both before and after documents nothing (the evidence-wiring precedent at `scripts/test_conformance.py:441-446`).

| Test | Cases | Asserts |
|---|---|---|
`test_section_24_exists` | 1 | `## 24.` heading present in `reference/repo-os-contract.md`
`test_section_24_documents_every_new_issue_code` | **5** | parametrized over `chain_anchor_not_ancestor`, `anchor_file_unreadable`, `anchor_file_invalid`, `anchor_attestation_contradicted`, `anchor_attestation_unavailable`
`test_section_24_documents_the_subject_file_byte_form` | 1 | "64" + "no trailing newline" (or equivalent) present
`test_section_23_subject_seam_paragraph_was_rewritten` | 1 | the retired *"never conclude 'fetch the bytes, re-hash, compare'"* framing is gone as an unqualified claim — regex-based, case-insensitive, in the `scripts/test_conformance.py:458` style
`test_section_24_records_the_rest_sunset_date` | 1 | **D6** — `10 Mar 2028` present
`test_section_24_documents_the_public_private_asymmetry` | 1 | **D8** — a private-repo/no-transparency-log sentence present
`test_section_24_documents_signer_digest_as_deliberately_not_required` | 1 | **D10.10** — both `signer-digest` and `job_workflow_sha` present
`test_section_24_carries_the_non_promoting_sentence` | 1 | **D5** — the "non-promoting" sentence present
`test_section_24_states_that_ancestry_is_established_by_replay` | 1 | **D3** — the never-trust-the-column rule present
`test_adr_0002_carries_the_slice_4b_amendment` | 1 | `## Amendment (2026-07-29, Slice 4b)` present
`test_amendment_names_the_three_overridden_decisions` | **3** | parametrized: decision 2, decision 4, decision 5 each named in the amendment
`test_codeowners_covers_the_anchor_path` | 1 | the anchor pattern is present and owned
`test_reference_file_count_is_still_eight` | 1 | `len(structural.json["reference_filenames"]) == 8` and the live `reference/` listing matches — §24 was appended, not added as a file
`test_changelog_has_an_unreleased_slice_4b_entry` | 1 | `## Unreleased` mentions `--compare` and the subject change
`test_no_shipped_surface_still_advertises_the_retired_subject_form` | 1 | **Step 5.** No unreleased CHANGELOG prose, and no line of `action.yml`, still names `subject-digest` or claims 4b "does not ship here". Fails against the tree as it stands today (`CHANGELOG.md:32`, `:47-49`) — the negative control is the current file, so this pin is non-vacuous by construction.
`test_no_version_bump_in_this_slice` | 1 | `pyproject.toml` version == `.claude-plugin/plugin.json` version == the version at `c493804`
| **Total** | **22** | |

- [ ] **Step 7: Verify the reference-file count and the frontmatter gates**

```bash
uv run --with pyyaml python3 -B scripts/self_eval.py
uv run --with pyyaml python3 -B scripts/validate_frontmatter.py
```

Expected: **13/13 PASS** and **9/9**. If `reference_filenames` fails, a new file was created in `reference/` — move the content into `repo-os-contract.md` §24 instead.

- [ ] **Step 8: Verify GitHub parses CODEOWNERS** (after pushing the branch)

```bash
gh api "repos/SollanSystems/loop-engineer/codeowners/errors" --jq '.errors'
```

Expected: `[]`. **A malformed CODEOWNERS fails silently — GitHub simply enforces nothing — so this check is the deliverable, not the file.**

**Acceptance:** `scripts/test_docs_slice4b.py` reports **exactly 22 passed**; the full suite reports **exactly 1567 passed / 18 skipped** (1545 + 22) with `pyyaml+jsonschema+pytest` and **exactly 1468 passed / 117 skipped** with `pyyaml+pytest`; `self_eval.py` 13/13; `validate_frontmatter.py` 9/9; `codeowners/errors` → `[]`; every doc-parity assertion was demonstrated to fail against the pre-documentation tree.

- [ ] **Step 9: Commit**

```bash
git add reference/repo-os-contract.md docs/adr/0002-ci-attested-verdict.md .github/CODEOWNERS CHANGELOG.md scripts/test_docs_slice4b.py
git commit -m "docs: normative section 24, the ADR 0002 slice-4b amendment, and the anchor path"
```

---

## Task 12: Commit this plan (a SEPARATE fast-follow docs PR)

**Nothing above ever commits the plan document itself, and that is a real defect with a real precedent.** Verified live at plan-authoring time:

```bash
git -C /mnt/c/Dev/projects/loop-engineer status --porcelain \
  docs/superpowers/plans/2026-07-29-slice4b-verdict-consumption.md
# → ?? docs/superpowers/plans/2026-07-29-slice4b-verdict-consumption.md
```

This repo has already **lost a plan entirely** this way: the 2026-07-11 UI-upgrade plan in a sibling project was session-local, never committed, and had to be reconstructed from a decisions register and fresh source reads. The register entry that cited its path was pointing at a file that did not exist. A plan that guided eleven tasks of kernel work and then evaporated is unreviewable, unauditable, and cannot be cited by the next slice.

**Files:**
- Add (tracked for the first time): `docs/superpowers/plans/2026-07-29-slice4b-verdict-consumption.md`

**This is a SEPARATE PR from the feature branch**, opened **after** the feature PR merges. That ordering is the established convention here — v0.10.0's plan landed in PR **#84** after feature PR #82, Slice 2's in **#99** after #94, Slice 3's in **#104** after #102, and 4a's plan followed the same path. The reason is diff reviewability: a ~130KB plan document in the feature PR's diff buries the kernel change a reviewer is there to read, and this project's own lesson is that **only a whole-branch review attacks the assembled system** — a review whose diff is 90% plan prose is not that review.

- [ ] **Step 1: After the feature PR merges, branch from the updated `main`**

```bash
git -C /mnt/c/Dev/projects/loop-engineer checkout main
git -C /mnt/c/Dev/projects/loop-engineer pull --ff-only
git -C /mnt/c/Dev/projects/loop-engineer checkout -b docs/slice4b-plan
```

`pull --ff-only` first, deliberately: a stale local `main` is a documented hazard in this repo (a Rust `git` wrapper on `PATH` can serve stale `git log` tips — trust `rev-parse`/`cat-file`), and both recipe branches once needed a rebase because a worktree branched from a stale local checkout.

- [ ] **Step 2: Commit the plan verbatim, including the hardening**

Commit the plan **as executed**, with every in-flight amendment already folded in — the Global Constraints line *"If an implementer needs an additional case, update the arithmetic in this plan in the same commit"* means the committed document must match what actually shipped, not the pre-execution draft. If a task's test count, an Acceptance line, or an Open Item moved during execution, those edits are part of this commit.

```bash
git -C /mnt/c/Dev/projects/loop-engineer add docs/superpowers/plans/2026-07-29-slice4b-verdict-consumption.md
git -C /mnt/c/Dev/projects/loop-engineer commit -m "docs(plan): commit the executed slice 4b verdict-consumption plan"
```

- [ ] **Step 3: Open the PR and confirm the file is tracked**

```bash
git -C /mnt/c/Dev/projects/loop-engineer push -u origin docs/slice4b-plan
gh pr create --title "docs(plan): slice 4b verdict-consumption plan" \
  --body "Fast-follow docs PR for the slice 4b feature PR (#<n>), following the #84 / #99 / #104 precedent: the plan lands separately so the feature PR's diff stays reviewable."
git -C /mnt/c/Dev/projects/loop-engineer status --porcelain docs/superpowers/plans/2026-07-29-slice4b-verdict-consumption.md
```

The final `status --porcelain` must print **nothing** — an empty result means tracked and clean. A `??` means the task did not happen.

- [ ] **Step 4: Record the post-merge experiment result in the same PR if it is already known**

If Task 10's Step 5 closure has already run by the time this PR is opened, fold the observed outcome and the observed certificate claim names into the plan's Open Items 1 and 2 in this commit rather than leaving them as "unresolvable pre-merge". The plan is the durable record; a stale Open Item in a committed plan misleads the next reader exactly as much as a missing plan does.

| Test | Cases | Asserts |
|---|---|---|
| _(none — this task ships a documentation file and adds no test surface)_ | 0 | |
| **Total** | **0** | |

**Acceptance:** `git status --porcelain docs/superpowers/plans/2026-07-29-slice4b-verdict-consumption.md` prints **nothing**; the file is present in `git ls-files`; the plan PR is open (or merged) and is **not** the feature PR; the plan's committed content matches what shipped, including any test-count or Open-Item edits made during execution; **zero** new tests and **zero** change to either suite count — this task must not move the arithmetic.

---

## Verification checklist (definition of done)

- [ ] Full suite green in **both** dependency legs, measured from **inside** a fresh worktree (never `--project`): **1567 passed / 18 skipped** with `--with pyyaml --with jsonschema --with pytest`, **1468 passed / 117 skipped** with `--with pyyaml --with pytest`. State the environment beside every number.
- [ ] The CI-equivalent leg (`+ --with hypothesis`) reports **1579 passed / 15 skipped** in the live checkout (measured **1577 / 17** in a fresh worktree, the documented −2/+2 delta). `--with hypothesis` swings roughly +10/−1 — never quote a count without its dependency set.
- [ ] `uv run --with pyyaml python3 -B scripts/self_eval.py` → **13/13**; `reference_filenames` still 8.
- [ ] `uv run --with pyyaml python3 -B scripts/validate_frontmatter.py` → **9/9**.
- [ ] `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m py_compile loop/*.py scripts/*.py` → clean.
- [ ] `grep -rn "environ\|getenv" --include=*.py loop/` → **zero matches**.
- [ ] `grep -rn "subprocess\|urllib\|socket\|http.client" --include=*.py loop/` → **zero matches**. The network lives in `scripts/`.
- [ ] `grep -c "subject-digest" action.yml` → **0** (D1).
- [ ] `python3 -m loop verdict examples/flaky-test-triage` still emits a predicate with no `_type`, `subject`, `predicateType`, or `predicate` key.
- [ ] `python3 -m loop doctor examples/coverage-repair` output is **byte-identical** to a pre-change capture (no anchor flag ⇒ no report change).
- [ ] Every mutation probe named in Tasks 2, 4, 6, 7 was **run**, failed the predicted tests, and was reverted — verified by a clean `git diff` against the committed tree. Run probes in a worktree with no concurrent suite.
- [ ] `scripts/action_anchor_resolve.py --help` runs **path-invoked with no `PYTHONPATH`** and exits 0.
- [ ] `grep -n "continue-on-error" action.yml` → **zero matches**, and neither the resolve step nor the compare/ancestor step carries `if: always()` or wraps a gating call in `set +e`. A composite action that swallows the resolve step's exit code makes the whole gate decoration (B2). The three pre-existing advisory uses (`:172`, `:189`, `:102`) are deliberate and stay.
- [ ] `grep -c "gh attestation" .github/workflows/attest.yml` → **0**. The live experiment resolves through the **shipped** `scripts/action_anchor_resolve.py`, so the adopter-facing artifact — not a hand-written duplicate — is what gets real-`gh` mileage (M4).
- [ ] `scripts/action_anchor_resolve.py` contains **zero** `except Exception` clauses; every failure path lands as a typed outcome naming which shape assumption failed, and an unclassifiable one is `anchor_attestation_unavailable` — never `corroborated`, never a skip (M1/M2).
- [ ] The absent-`gh` path is covered by a test that removes `gh` from `PATH` entirely, not by a shim that exits non-zero (M3) — `FileNotFoundError` is categorically different from a bad exit code and no shim can reach it.
- [ ] `scripts/fixtures/gh_attestation_verify/no_attestation_404.txt` is committed **verbatim** as captured from live `gh`, and the classifier test reads it from the file.
- [ ] **POST-MERGE (Task 10, Step 5) — the slice is not done until this is checked:** the first `attest.yml` run after merge was watched, its actual outcome and the **observed certificate claim names** were recorded, the one-line correction to `REQUIRED_CERTIFICATE_CLAIMS` / `_TRIGGER_CLAIM_ALIASES` shipped same-day if the prediction was wrong, the `signer_denied.txt` fixture was captured, and Open Items 1 and 2 were updated from "unresolvable pre-merge" to the observed fact (M5).
- [ ] **This plan is committed (Task 12)** — `git status --porcelain docs/superpowers/plans/2026-07-29-slice4b-verdict-consumption.md` prints **nothing**, in a **separate** fast-follow docs PR opened after the feature PR merged (#84 / #99 / #104 precedent). It was `??` at authoring time, and this repo has already lost a plan exactly that way (B1).
- [ ] `actions/attest` and `gh attestation verify` input/flag names were read from the **live** definitions (recorded above), not from memory.
- [ ] `gh api repos/SollanSystems/loop-engineer/codeowners/errors` → `[]`.
- [ ] Every doc-parity pin in Task 11 was demonstrated to **fail** against the pre-documentation tree.
- [ ] **No version bump** in this PR: `pyproject.toml`, `.claude-plugin/plugin.json`, README, `scripts/test_docs_version.py` and the CHANGELOG's released headings are untouched.
- [ ] PR body states: (a) `attest.yml` is unvalidatable pre-merge and the **first post-merge run is the experiment**, with `subject[0].digest.sha256 != predicate.chain.head` as the falsifiable check; (b) **ADR 0002 decision 6 is documented but not in force** — the live ruleset requires 0 approvals — and the anchor path joined its path list; (c) this repo cannot dogfood cross-run ancestry, and why; (d) #96/#97/#98 remain open and out of scope, with #98's proximity to the evidence-write path noted and its safe degradation named.
- [ ] Whole-branch review runs **before** the PR is opened. The auto-merge ruleset would otherwise outrun a post-PR review (the v0.10.0 lesson), and only a whole-branch pass attacks the assembled system — per-task reviews check a task against its brief.

## Out of scope

- **Issues #96 / #97 / #98** — separate small PRs (D9).
- **Any `loop verdict` flag that threads an anchor into the predicate.** Adding a field to `verdict@1` is a one-way door into a permanent public log; ancestry is a doctor concern.
- **A schema for the comparison report.** It is a report, like `doctor_report`'s, not an interchange artifact.
- **In-kernel signature verification** — permanently rejected: it needs a TUF trust root, X.509 chain validation, and Rekor inclusion proofs, which is the dependency constraint ADR 0002 exists to hold.
- **Registry push, storage records, GHES, or a private Sigstore path.** Both flags stay explicitly `false`.
- **A persistent-store CI job** so this repo can dogfood cross-run ancestry. Worth doing; not this slice.
- **The `setup-python@v6`/`@v7` drift** in `ci.yml` — unrelated scope.
- **The version bump / release cut**, as in 4a.

## Open items to resolve during execution

These are places where **D1–D10 are genuinely under-specified**, or where a fact cannot be established before merge. Each is handled fail-closed; none blocks starting.

1. **RESOLVED 2026-07-30 by the first post-merge run** (`attest.yml` run `30509952627`, head `74e3743`, chain head `3f0aa6d5…`). All three pinned `REQUIRED_CERTIFICATE_CLAIMS` are present verbatim, and the observed key set is: `buildConfigDigest`, `buildConfigURI`, `buildSignerDigest`, `buildSignerURI`, `buildTrigger`, `certificateIssuer`, `githubWorkflowName`, `githubWorkflowRef`, `githubWorkflowRepository`, `githubWorkflowSHA`, `githubWorkflowTrigger`, `issuer`, `runInvocationURI`, `runnerEnvironment`, `sourceRepositoryDigest`, `sourceRepositoryIdentifier`, `sourceRepositoryOwnerIdentifier`, `sourceRepositoryOwnerURI`, `sourceRepositoryRef`, `sourceRepositoryURI`, `sourceRepositoryVisibilityAtSigning`, `subjectAlternativeName`. `verifiedTimestamps` carried 1 entry. **No correction was needed.** Original wording: the exact leaf claim names cannot be established pre-merge. F1 proves `gh attestation verify` is unrunnable against all three existing attestations, so no `--format json` output exists to read them from; D4 names the X.509 **extensions** (`BuildSignerDigest`, `BuildSignerURI`) and D7 names the **top-level paths**, but neither names gh's JSON leaf keys. Handled by Task 6 rule 7 (pinned constants + refusal on absence + the mapping isolated in `scripts/`), confirmed by Task 10. **Resolve in the first post-merge run and ship the one-line correction if needed.**
2. **RESOLVED 2026-07-30: BOTH aliases are present** (`githubWorkflowTrigger` and `buildTrigger`), so the fail-closed "at least one" rule was satisfied twice over and no correction was needed. Original wording: the trigger claim name (`githubWorkflowTrigger` vs `buildTrigger`) is the same class of unknown; ADR decision 5's "requires a `push` trigger" names no claim. Handled by requiring **at least one** alias and refusing when neither is present.
3. **The anchor file's path and schema are a plan decision, not a decided one.** D2 says only "tracked, not under `.loop/`, records at minimum `chain_head`". This plan chooses `loop-anchor.json`, `anchor@1`, and a CODEOWNERS pattern at any depth. If the operator wants a different convention, change it in Task 1 before anything consumes it.
4. **Whether `--compare` should accept an ancestor head as agreement is not settled by D1–D10.** This plan rules it a **disagreement** (Task 4 rule 4) on the grounds that a verdict projects one run. Flagged because it is a real judgment call, not a derivation.
5. **D5's three outcomes describe the attestation-index lookup; the anchor FILE's own failure modes are unaddressed.** This plan adds `anchor_file_unreadable` and `anchor_file_invalid` by analogy with D5's never-skip rule.
6. **D6's "isolate the raw `gh api` call in one place" is close to vacuous under D1** — the whole path now goes through `gh attestation verify`, so no raw route call remains on the critical path. The sunset date is recorded anyway, and Task 8's single-call-site test keeps the property true if one is ever added.
7. **`--emit-subject` and the single-writer subject byte form are this plan's addition**, not a decision's. They exist so the attest side and the resolve side cannot disagree about 64 bytes. If an implementer finds a simpler single-writer arrangement, the AC (64 bytes, lowercase hex, no trailing newline, one definition) is what must hold.
8. **This repo cannot dogfood cross-run ancestry** (honest limit 10) and D9 does not acknowledge it. Coverage is synthetic (fake `gh`) plus a within-run grown store. Do not let CI green read as a cross-run proof.
9. **D9's baseline is a live-checkout number with `hypothesis`** (1365/15) while the task brief's canonical command has neither. Both are recorded in the header; use the canonical one for zero-regression claims and say which environment produced any number you quote.
10. **DISCOVERED DURING TASK 1 EXECUTION: no CI job runs the structural-fallback leg, so the structural checks this plan relies on for mode parity have no CI teeth.** Every job in `.github/workflows/ci.yml` installs `jsonschema` (`:27`, `:75`, `:88`, `:112`, `:203`, `:241`), so the `pyyaml`-only leg is exercised only by a human or agent running it locally. Proven by mutation probe on Task 1: loosening `_HEAD_PATTERN.fullmatch` to `.match` in `loop/anchor.py` and `loop/verdict.py` kills **4** tests in the fallback leg but only **2** in the canonical leg — the `read_anchor` mutants survive because the jsonschema layer masks them. So a future drift between `_structural_violation` and `anchor.schema.json` would pass CI. This weakens mode parity for **every** task that claims it (1, 3, and the `--compare` validation in 4). Options: add a `structural-fallback` matrix leg to the `verify` job (cheapest, catches the whole class), or accept it and say so in §24. **RESOLVED IN TASK 10 (execution ruling R4):** ci.yml gains a `gates-fallback` job — a SEPARATE job, deliberately not a matrix leg on `gates`, because a matrix would rename `gates`' check contexts and this repo's branch ruleset pins its required contexts by name (a renamed context is pinned "expected" forever and wedges the PR). The job installs pyyaml+pytest only and asserts `importlib.util.find_spec("jsonschema") is None`, so it cannot silently decay into a duplicate of `gates`. §24 records the parity-teeth point as well.

---

## Post-merge closure (Task 10, Step 5) — executed 2026-07-30

Feature PR **#110**, squash-merged as **`74e3743`**. First `attest.yml` run after merge:
**`30509952627`, conclusion success on the first attempt.**

**The prediction held.** `gh attestation verify` exited **0** against a `verdict@1`
attestation for the first time in this repository's history, and the falsifiable check
came back the right way round:

| Observed | Value |
|---|---|
| `anchor-outcome` | `corroborated` (annotation: *anchor corroborated for `3f0aa6d5…`*) |
| `subject[0].name` | `loop-chain-head` — the name `actions/attest` derived from the file basename |
| `subject[0].digest.sha256` | `6530115e3a0770803d6dfb14182ab85d79421a7983166e295d4d01cbdccb8359` |
| `predicate.chain.head` | `3f0aa6d509003152abfde8278f9a692e0cb8580a0f15112f44876cf4ecdc457f` |
| **D1 proof** | subject digest **≠** chain head, **and** subject digest **==** `sha256(<the 64 head bytes>)` |

Both halves of the D1 proof are confirmed, not just the inequality: the subject digest is
demonstrably the hash of a file *containing* the head. In all three attestations minted
before this slice those two values were equal.

**The one thing the experiment DID falsify — corrected same-day.** The denial-shape stderr,
capturable only now that a verifiable attestation exists, is verbatim:

```
Error: verifying with issuer "sigstore.dev"
```

None of `_CONTRADICTED_MARKERS` matched it, so the most common denial fell through the
fail-closed default and was reported as `anchor_attestation_unavailable` — non-promoting
either way, so never a security hole, but it collapsed D5's observability distinction in
the wrong direction: *"it said no"* read as *"I could not look."* The pre-merge marker set
was a remembered approximation of a vendor string, which is exactly the failure mode the
plan's M2 fixture requirement exists to catch. Fixed by adding the real marker, pinned by
`test_resolve_classifies_the_real_captured_denial_stderr` over the committed verbatim
fixture `scripts/fixtures/gh_attestation_verify/signer_denied.txt`, and verified to fail
without the marker. That closes the M2 fixture pair (404 + denial), both driven from real
vendor strings rather than paraphrases.
