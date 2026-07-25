# Verifier Identity + Independence (Tamper-Evident Provenance, Slice 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Review status:** three adversarial lenses ran (design-lint, kernel-reality, threat-honesty), **43 findings raised** (5 BLOCKER, 16 MAJOR, 18 MINOR, 4 NIT; the fabricated-verifier-identity BLOCKER was raised independently by all three). **41 applied in full; 2 applied with one sub-claim each rejected** — two stale line-number sub-claims the live tree refutes (`scripts/test_doctor_eventstore.py:107-112` and `scripts/metrics.py:238-239` were already correct). No finding was rejected outright. Every design-altering resolution is recorded in **Post-review design changes** below.

**Goal:** Record *which verifier actually ran* — as honest, null-when-unknowable digests on `evidence@1` plus a metrics-compatible verify bundle carrying the visible/held-out criterion partition — and turn the prose-only independence invariant at `reference/safety-and-approvals.md:97` into a hard `loop doctor` finding when a record declares that its producer verified its own work.

**Architecture:** A new pure leaf module `loop/verifier.py` computes the two digests (`code_digest` = sha256 of argv[0]'s file *only when that file lives inside the workspace*; `policy_digest` = sha256 of the canonical JSON of the declared goalpost subset of the TASKS.json entry, reusing Slice 1's `loop.chain.canonical_json`) and the two *identity blocks* (executed-command vs injected-callable). `dispatch_once` builds the identity block **before** invoking the verifier and hands it to `emit.write_verify_evidence()`, which writes the bundle and its hashed `evidence@1` record; `loop/contract.py` grows a declared discovery location (`.loop/evidence/*.json`) whose records are validated in both modes and screened for declared self-verification (`self_verified_evidence`) and for an orphaned bundle (`missing_evidence_record`).

**Tech Stack:** Python 3.10+ stdlib only (`hashlib`, `json`, `shlex`, `os`, `pathlib`). No new runtime dependencies. Tests via pytest under `uv run`.

**Baseline: `main` @ `91bf36a` (the v0.10.0 cut).** Fresh-worktree numbers there are **1021 passed / 16 skipped** with `[schemas,yaml]` extras and **951 / 86** pyyaml-only. **There is no rebase gate today.** Verified live at planning time: the only open PR is dependabot **#88**; **#81** (read verbs leave `events.db-shm` on a crash-left WAL), **#85** (events.py error surface), **#86** (`reduce_events(initial=)` false `ChainBreakError`), **#87** (live CI anchor coverage) are **open issues with no PRs and no assignees**. Waiting on them is unbounded, so Task 0 does not wait. The collision analysis stands as a forward-looking note: this slice touches none of `loop/events.py`, `loop/reducer.py`, `loop/chain.py`, `action.yml`, `ci.yml`, and its `loop/runner.py` edit is in `dispatch_once` (~201-249), not the `_projection` chain-mapping region (~121-150) that #86 targets. Task 0 re-measures the actual branch point; every later "no regressions" claim is **that** measurement plus the predicted delta.

## Global Constraints

- **Zero new runtime dependencies.** `loop/` imports stdlib only; `pyproject.toml` `[project.optional-dependencies]` stays exactly `yaml`, `schemas`, `dev`.
- **evidence@1 stays evidence@1.** `schemas/evidence.schema.json` `required` is untouched; every new field is optional, nullable, and lives inside the already-optional `verified_by` object (which is already `additionalProperties: true`).
- **Validation-mode parity.** Every new field is type-checked identically in `jsonschema` and `structural-fallback` mode; `reference/repo-os-contract.md` commits to fallback parity, so a field the schema constrains and the fallback ignores is a bug, not a shortcut.
- **Absent-evidence doctor byte-stability.** With no `.loop/evidence/` directory and no `verify-iter<N>.json` bundle, `doctor_report` output is byte-identical to today's. This slice adds **no new top-level doctor key**, so the absent-everything pin at `scripts/test_doctor_eventstore.py:107-112` (`test_absent_event_store_matches_pre_slice_doctor_shape`) passes **unmodified**.
- **Typed fail-loud everywhere.** No new code path may skip on error (R007: an errored verifier must FAIL, not skip). A malformed evidence record fails doctor; a verify-bundle write that fails after a committed event raises a typed `RunnerError` naming the committed iteration; a non-JSON-able task entry raises a typed `EmitError`, never a bare `ChainHashError`.
- **Honest-recording, never proof.** The digests state what *this process observed*. A worker can write any `verified_by.by` string, and can rewrite or delete the artifacts afterwards. The forbidden claim is "proves independence"; the shipped claim is **"surfaces declared self-verification"**. Docs and pinned honest-limitation tests must both carry it.
- **Never fabricate a digest or an identity.** `code_digest` is `null` with an explicit `code_digest_basis` whenever argv[0] is not a hashable workspace file — `python3 -m pytest -q` has no hashable workspace script and `null` is the truthful value. When the caller **injects a verifier callable**, the task's declared `verify` command never runs, so `command` and `code_digest` are `null` with basis `injected_verifier`: recording the declared command there would be a fabrication.
- **Never fabricate a holdout, and never fabricate an attempt count.** The bundle records the *declared* partition and always carries `holdout_executed: false`; `scripts/holdout_gate.py` remains the only thing that executes a holdout set. `attempt` is derived from durable prior `iteration_appended` entries for the same `task_id`, or recorded `null` — the kernel does **not** track TASKS.json `attempts` (verified: zero references in `loop/*.py`).
- **One bundle format, not a third.** The bundle must satisfy `scripts/metrics.py`'s green-marker convention (`outcome == "PASS"` or `passed is True`, `metrics.py:238-239`) and must never be mistaken for a `holdout_gate.decide` verdict (`metrics.py:315` requires a `false_completion` key before `_is_valid_gate_verdict` at `:283-301` ever runs — neither the bundle nor the record has one). Bundles keep the **already-shipped** home `.loop/artifacts/`; this slice introduces no second bundle location.
- **`evals/cases/structural.json` is untouched** — no new skill, reference, template, or *schema file* ships. Editing the existing `schemas/tasks.schema.json` and `schemas/evidence.schema.json` is additive and leaves the pinned filename list alone. `loop/verifier.py` and the new test files are not pinned there.
- **Version bumps live only in the release-cut PR** (Task 9): pyproject + plugin.json + README surfaces + `scripts/test_docs_version.py` + CHANGELOG move together. Tasks 0-8 land as one feature PR with no version change.
- Repo env quirks: no system pytest — run tests via `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider ...`; the Bash deny-list blocks `rm`, bare `cd`, `VAR=` prefixes, `timeout`, `printf`, `source` — use `git -C`, absolute paths, `bash -c`.

---

## Program context (what this plan is Slice 2 of)

Source: `review/2026-07-24-graph-engineering-report-assessment.md`. The accepted program is **tamper-evident provenance**; the "graph engineering" framing was rejected (assessment §2 blocker 5). Slice 1 shipped as v0.10.0 (`7002580` / `91bf36a`).

| Slice | Scope contract | Status |
|---|---|---|
| 1 | Hash-linked chain, `loop migrate`, doctor chain gate + `--expect-chain-head`, honest-limitation tests/docs. | **shipped v0.10.0** |
| **2 (this plan)** | Verifier identity + independence: `verified_by.code_digest`/`policy_digest` on evidence@1 (the runner hashes the verifier it actually executed), `produced_by.executor == verified_by.by` becomes a doctor-surfaced anti-cheat finding, held-out/visible criterion partition recorded in verify bundles. Ships as **v0.11.0**. | now |
| 3 | Wire evidence@1 into writer + doctor (the §17 deferral): content-addressed objects via `artifact_object_path`, doctor **hash-verifies** evidence referenced by criteria, doctor compares a record's `policy_digest` against the live TASKS.json entry, evidence artifacts bind into the hash chain, `Succeeded` tightens from non-empty paths to hash-verified evidence. | after Slice 2 |
| 4 | CI-attested verdict (in-toto Statement shape, GitHub OIDC keyless). Needs its own ADR. | after Slice 3 |
| 5 | Docs/interop pass (Mermaid in reference/docs only, trace-context-as-data, Cypher recipe). | anytime |

Rejected permanently (do not resurrect): `graph` CLI verbs + query DSL, FastAPI HTTP API/SDK, Neo4j/Qdrant integrations, unanchored Merkle checkpoints, local DSSE/HMAC signing.

**Assessment lines this slice implements** — P12 (assessment:87): *"NOT a query: a hard anti-cheat finding surfaced through doctor. `produced_by.executor == verified_by.by` on an evidence record ⇒ finding. Data already modeled in evidence@1; enforces the safety-and-approvals.md:97 invariant that is currently prose-only."* P10 (assessment:89): *"Right invariant, wrong object: goes on evidence@1 `verified_by` (additive), NOT receipt@1. runner.py hashes the verify script it actually executed; record visible/held-out partition in the bundle."*

The invariant being enforced, verbatim from `reference/safety-and-approvals.md:97`: *"The verifier must remain an *independent* signal; the moment the agent under test can also move the goalposts, the success signal is worthless."*

---

## Post-review design changes

Findings that changed the **design**, not just the prose. Each is a recorded ruling; where two lenses conflicted, the resolution is toward threat-honesty over convenience.

1. **Identity is computed from what actually ran, before it runs** (3 lenses, BLOCKER). The original design read `task["verify"]` inside the writer unconditionally. `dispatch_once` calls `(verifier or _default_verifier)(...)` (`loop/runner.py:232`), so an injected `verifier=` means the declared command **never executes** — recording its digest is a fabrication, and the original Task-4 test pinned that fabrication as correct. Resolution: `dispatch_once` builds the identity block itself — `executed_verifier_identity(task["verify"], workspace)` when `verifier is None`, `injected_verifier_identity()` otherwise — **before** invoking the verifier, and passes it to the writer as a **required** keyword `code_identity`. The writer never guesses. This also closes the read-after-execute window (a self-modifying verify script previously recorded its post-run bytes): the digest is now taken pre-execution. New eighth basis `injected_verifier`; new ninth basis `unresolvable` (see 8).
2. **Bundles keep the shipped home `.loop/artifacts/`** (kernel-reality MAJOR). The plan invented `.loop/verify/`, which would have forked the convention against both released examples (`examples/coverage-repair/.loop/artifacts/verify-T1.json`, `examples/flaky-test-triage/.loop/artifacts/verify-T1-iter1.json`) and left them silently non-conforming to a new §1 tree line. `artifacts/` is already declared at `reference/repo-os-contract.md:70`. Only `.loop/evidence/` is a new declared location. Decision 4's namespace separation is preserved: the record is `evidence-iter<N>.json` under `evidence/`, never `verify-*.json`.
3. **The "recorded forgery" claim is deleted, and the gap is pinned** (threat-honesty BLOCKER). Both artifacts are plain overwrite-permitting files outside Slice 1's hash chain; a worker with write access to `.loop/` can rewrite or delete them and doctor will not notice. Chain-binding the record (option (a) of the finding) requires a new event type in `loop/events.py` + `loop/reducer.py` — surfaces this slice contractually does not touch and that open issues #85/#86 target. **Ruling: option (b).** The phrase is removed from §17, CHANGELOG, and README; the literal truth is stated instead; `test_rewriting_the_evidence_record_to_independent_identities_leaves_doctor_clean_pinned` pins it; chain-binding is named as Slice-3 scope in the program table.
4. **`missing_evidence_record` ships** (threat-honesty MAJOR). The original deferral was justified by "Slice 2 has no production writer requirement" — false the moment Task 4 makes the runner a production writer. Deleting only the record leaves the bundle behind as detectable residue, exactly the shape §22's shipped `missing_event_store` tripwire already covers. Resolution: doctor reports `missing_evidence_record` when `.loop/artifacts/verify-iter<N>.json` exists with no matching `.loop/evidence/evidence-iter<N>.json`. Scoped strictly to the `verify-iter<N>.json` name so the shipped example bundles (`verify-T1.json`, `verify-T1-iter1.json`) never trip it, and absent-everything stays byte-stable. Deleting **both** remains clean — that is the honest residual, now pinned under its true name.
5. **§17's integrity boundary becomes three tiers** (kernel-reality BLOCKER). The original "Surfaces" list claimed goalpost-movement, verifier-script swap and bundle swap were surfaced, while the same paragraph's "Does not surface" list said bundle tampering is not — and the plan's own pins assert `doctor_report(...)["ok"] is True` after both swaps. Nothing in Slice 2 compares any digest to anything. Resolution: **Fails doctor** (`self_verified_evidence`, `missing_evidence_record`, malformed/unparseable records) / **Recorded for later comparison, not checked by any shipped surface** (`policy_digest`, `code_digest`) / **Detectable only by explicitly calling `verify_evidence`** (bundle swap). Automated `policy_digest` comparison is deferred to Slice 3 and named there. New pin `test_no_automated_digest_comparison_exists_pinned`.
6. **`--verifier-identity` ships alongside `--executor`** (threat-honesty MAJOR). With `--executor` alone, `verified_by.by` is the constant `"loop.run"` on every kernel-written record, so `self_verified_evidence` had **no reachable positive case** on the kernel's own write path. Rather than ship a doctor gate whose only audience is third-party writers and not say so, the CLI gets the mirrored flag (same `_extract_value_flag` shape, same misuse guard). The residual truth is still documented: defaults never collide, so an unattributed run cannot manufacture the finding.
7. **`attempt` is derived or `null`, never minted** (threat-honesty MAJOR). `task["attempts"] + 1` was a fabricated provenance number: grep confirms zero references to `attempts` anywhere in `loop/*.py`, so the field is never incremented and every re-dispatch would have recorded the same value. Resolution: `dispatch_once` counts prior `iteration_appended` entries for this `task_id` in `projection["runlog_entries"]` (which carry `task_id`, `loop/reducer.py:126`) and passes `attempt=count + 1`; a caller that supplies nothing gets `null`, which the schema already permits.
8. **`unresolvable` basis added** (threat-honesty MINOR). An `OSError` from `.resolve()`/`.is_file()` (ELOOP, EACCES on a parent, ENAMETOOLONG) was reported as `not_a_file` — a false statement about the file rather than an honest "could not determine". The basis field's contract is that it always *explains* a null; a wrong explanation breaks it.
9. **The verdict's provenance is recorded next to the verdict** (design-lint MAJOR). `outcome`/`passed` on the injected path is an arbitrary callable's self-report, and every bundle is read as gate evidence by `metrics._load_verify_bundles`. The bundle now carries `verifier.source` (`"declared_command"` / `"injected_callable"`), §17 states that only `declared_command` bundles are gate evidence, and the widened FCR input surface is named in the integrity-boundary paragraph.
10. **`visible_criteria` / `holdout_criteria` are declared in `schemas/tasks.schema.json`** (both lenses, MINOR). The partition was structurally present but read from fields no schema knew about, so every real repo produced `{visible:[ref], holdout:[], declared:false}` and a typo was indistinguishable from "no partition declared". They are now optional `array of string` properties on tasks@1 (`additionalProperties: true`, `required` untouched — additive, no version bump, no `structural.json` change), with a fallback type-check. The typo case stays silent by construction and is pinned as such.
11. **`ChainHashError` is folded into the typed surface** (threat-honesty MAJOR). The self-review claimed a non-JSON task entry "cannot arise from `json.loads`-parsed TASKS.json"; that is wrong — `json.loads('{"criterion_ref": NaN}')` succeeds by default and `loop.chain.canonical_json` uses `allow_nan=False` (`loop/chain.py:30`), so it raises. `_load_tasks` (`loop/runner.py:110`) uses bare `json.loads`. The writer now catches it and raises `EmitError`, which the runner's existing except tuple already converts to a `RunnerError` naming the committed iteration.
12. **Bundle write is temp-then-replace** (threat-honesty MINOR). Writing the bundle into place first meant a failure between the two writes left an orphan metrics-green `verify-*.json` produced by a failed write path — an accidental green marker in a repo where FCR is a first-class metric. Now: bundle to a same-directory temp name → record → `os.replace` the bundle into place.
13. **The usage line stays byte-unchanged** (design-lint MAJOR). `scripts/test_runner_dispatch.py:119` asserts the literal `"python3 -m loop run [--mode basic|strict|release] <workspace>"`; inserting a flag there fails a pre-existing test while Task 8 claims byte-unmodified test files. The new flags are documented in the `options:` block only, which satisfies the new help assertion.
14. **One `EVIDENCE_DIR_NAME`** (design-lint MINOR). Defined once in `loop/paths.py` and imported by `emit` and `contract`; the duplicated `EVIDENCE_DIRNAME`/`EVIDENCE_DIR_NAME` pair is gone. The dead `_RECORD_SCHEMA_FILES["evidence"]` entry is dropped (both lenses: `_validate_record` is its only consumer and is never called with `"evidence"`).
15. **Task 0 worktree uses `--detach`** (design-lint MAJOR). `git worktree add <path> <branch>` refuses a branch already checked out in the main worktree, so Task 0 failed on its own first substantive step.
16. **Task 6's absence-pins carry their own positive controls** (design-lint MAJOR), and Step 2 is a deterministic mutation probe with a stated kill count instead of a one-off manual observation recorded in a PR body — the repo's own PR-#77 lesson ("negative-control claims need empirical verification").
17. **`loop simulate` stays decision-level — recorded, not fixed** (design-lint MINOR). `_empty_prediction` gains no field. Rationale: simulate's existing `legacy_sync_would_write` predicate answers "would this dispatch write outside the event log **unexpectedly**"; a dispatched action *always* writes the two evidence files, so a boolean predicting `True` on every dispatch carries no information. The asymmetry with `legacy_sync_would_write` is stated in §17 so a reader does not infer that simulate enumerates writes.

**Rejected findings (with reason):**

- **design-lint MINOR (citations), sub-claim "`test_absent_event_store_matches_pre_slice_doctor_shape` is at lines 103-108".** Refuted live: the `def` is at `scripts/test_doctor_eventstore.py:107` and the body runs to `:112`. The plan's `:107-112` was already correct and is retained.
- **kernel-reality NIT (Global Constraints), sub-claim "`metrics.py`'s green marker is at :236-238".** Refuted live: `outcome = str(data.get("outcome", "")).upper()` is `metrics.py:238` and `green = outcome == "PASS" or data.get("passed") is True` is `:239`. The plan's `:238-239` was already correct and is retained. The *other* half of that NIT — conflating `_is_valid_gate_verdict` (`:283-301`) with the `false_completion`-key gate (`:315`) — was real and **is** applied.
- **kernel-reality NIT (plan length).** Resolved by deleting duplicate Task-8 behavior-matrix rows that restated a Task acceptance line verbatim, not by cutting literal test bodies — the literal bodies are what made the arithmetic and honesty defects reviewable. Net length still rose (1406 → ~1900) because the BLOCKER fixes demanded 19 additional literal tests and this review section; that trade is deliberate and recorded rather than hidden.

---

## Design decisions (binding)

1. **`code_digest` honesty rule.** `TASKS.json` `verify` is an arbitrary command string that `loop/runner.py:78-99` `shlex.split`s and subprocess-runs. The digest hashes argv[0]'s resolved file **only** when (a) argv[0] contains a path separator, (b) it resolves to an existing regular file, and (c) that file is inside the workspace root. Otherwise the digest is `null` and `code_digest_basis` says exactly why. The nine bases are the complete enumeration:

   | basis | when | digest |
   |---|---|---|
   | `workspace_file` | argv[0] is a regular file under the workspace and was readable | hex sha256 |
   | `path_lookup` | argv[0] has no path separator (`pytest`, `python3`, `true`) — the OS resolved it through `PATH`, so a same-named workspace file is *not* what ran | `null` |
   | `outside_workspace` | argv[0] resolved to a real file outside the workspace (`/usr/bin/python3`, a symlink escaping the tree) | `null` |
   | `not_a_file` | argv[0] does not resolve to an existing regular file (missing path, directory, dangling symlink) | `null` |
   | `unresolvable` | resolving argv[0] raised `OSError` (symlink loop, permission-denied parent, name too long) — the honest "could not determine" | `null` |
   | `unreadable` | the file exists inside the workspace but could not be read | `null` |
   | `unparseable_command` | `shlex.split` raised | `null` |
   | `empty_command` | `verify` is absent, blank, or splits to zero words | `null` |
   | `injected_verifier` | the caller injected a verifier callable, so **no declared command ran** — recording one would be a fabrication | `null` |

   `python -m pytest` and `python3 -m pytest -q` are `path_lookup`: **there is no hashable workspace script and `null` is the truthful value.** A repo whose gate is `./scripts/verify-fast.sh` or `scripts/verify-fast.sh` gets a real digest.

   **The nine values co-move across four surfaces** — `CODE_DIGEST_BASES` (`loop/verifier.py`), the `enum` in `schemas/evidence.schema.json`, the structural-fallback check in `loop/evidence.py`, and the §17 table. Task 7 Step 6 pins schema-and-doc agreement with `CODE_DIGEST_BASES` in one test.

2. **The identity block is built by the caller who knows what ran, before it runs.** `dispatch_once` computes it *before* invoking the verifier and hands it to the writer as a required keyword. `executed_verifier_identity(command, workspace)` is used only on the path where the declared command is about to execute (`verifier is None`); `injected_verifier_identity()` is used otherwise. `write_verify_evidence` never derives identity from `task["verify"]`. Consequence: the digest is of the bytes that were **about to run**, closing the self-modifying-verifier window; and an injected callable can never produce a `workspace_file` digest.

3. **`policy_digest` binds to a real object.** The policy is the TASKS.json entry's *declared goalpost*: `POLICY_FIELDS = ("criterion_ref", "depends_on", "id", "verify")`, canonicalized with `loop.chain.canonical_json` and sha256'd. Run state (`status`, `attempts`, `evidence`) is deliberately excluded — it changes for non-policy reasons and would make the digest noise. This is not decorative and Task 6 pins it both ways: mutating `verify` or `criterion_ref` **must** change the digest; incrementing `attempts` **must not**. `id` and `depends_on` are deliberately included as *identity and ordering* binding, and Task 1 pins that an `id` rename and a `depends_on` reorder both change the digest — so a reviewer reading a changed digest must check which field moved. **The digest binds the criterion *reference*, not the criterion *text*:** editing SPEC.md's acceptance wording leaves it identical. That is stated in §17 and is Slice-3 scope. The alternative binding (`completion_policy`, `loop/completion.py`) was rejected: it is the *terminal* policy, identical for every task in a run, and would carry no per-verification information.

4. **Canonicalization is reused, never re-implemented.** `loop.chain.canonical_json` (shipped Slice 1, normatively pinned in repo-os-contract §16) is the single canonicalizer for `policy_digest`. One canonicalizer, writer and verifier. Because it sets `allow_nan=False` (`loop/chain.py:30`), a `NaN`/`Infinity` in a `json.loads`-parsed TASKS.json entry raises `ChainHashError` — the writer converts that to `EmitError` (decision 12).

5. **Two files per verified dispatch, with distinct name spaces.**
   - bundle → `.loop/artifacts/verify-iter<N>.json` — the **already-shipped** bundle home (`reference/repo-os-contract.md:70`, both released examples). `metrics.py:232` rglobs `verify-*.json` under `.loop/`, so this is discovered exactly like every existing bundle.
   - record → `.loop/evidence/evidence-iter<N>.json` (evidence@1; **must not** match `verify-*.json`)

   The record's name is load-bearing, not cosmetic: naming it `verify-iter<N>.json` would make `metrics._load_verify_bundles` ingest it as a *bundle with no green marker*, i.e. a phantom RED bundle that poisons FCR. The record carries no `false_completion` key, so `metrics._load_gate_verdicts` (`metrics.py:315`) ignores it too.

6. **The bundle gets no new schema file.** Slice 2 writes bundles; nothing *reads* bundles as a validated record. Shipping `schemas/verify-bundle.schema.json` and force-validating every `.loop/**/verify-*.json` would fail the many honest ad-hoc bundles existing runs already wrote. The bundle's integrity is committed by the evidence record's `sha256`; the record is the schema-validated object.

7. **Discovery location is declared, not configured.** `.loop/evidence/*.json` becomes a location declared in `reference/repo-os-contract.md` §1 and scanned by `_validate_optional_records` (`loop/contract.py:635-657`). Task 7 Step 1 also adds `repair/` and `receipts/` to the §1 tree, which currently lists neither despite both being scanned — so "joins its declared peers" becomes true rather than aspirational. No manifest schema change, no new CLI flag.

8. **Discovery lives in `validate_contract`, not `doctor_report` — a recorded deviation.** The prompt's guidance was to mirror `runtime.event_consistency_issues` (a new doctor key that is a no-op when absent). Reusing `_validate_optional_records` is strictly better here and the justification is concrete: (a) evidence discovery has **no health block to report** — its only output is issues, so a new key would be permanently `{"present": false}` noise; (b) it keeps `test_absent_event_store_matches_pre_slice_doctor_shape` (`scripts/test_doctor_eventstore.py:107-112`) passing **unmodified** rather than requiring the pin itself to be edited; (c) it inherits the existing mode-parity record machinery and the `schemas_checked` accounting; (d) `doctor`/`validate`/`verify` are aliases of one code path (`loop/__main__.py:336-338`), so "surfaced through `loop doctor`" is satisfied either way. `doctor_report` needs **no change at all** in this slice.

9. **`self_verified_evidence` comparison is normalized.** `produced_by.executor.strip().casefold() == verified_by.by.strip().casefold()` (both non-empty). Case/whitespace normalization closes trivial evasion (`"Worker-A"` vs `"worker-a"`) with no realistic false-positive: a case-insensitive identity collision is the same actor. Any real rename still evades — that is the pinned limitation, not a bug.

10. **Default identities cannot manufacture the finding, and the check IS reachable.** `produced_by.executor` defaults to the literal `"unattributed"` (the runner genuinely does not know who produced the work) and `verified_by.by` defaults to `"loop.run"` (the runner genuinely did run the verifier). They are never equal, so a default `loop run` never trips the finding. Both are settable from the CLI (`--executor`, `--verifier-identity`), so an operator whose harness produces *and* verifies under one identity trips it on the kernel's own write path. An executor that omits its identity evades the check, which Task 6 pins and Task 7 documents.

11. **`missing_evidence_record` closes the residue gap.** A `.loop/artifacts/verify-iter<N>.json` with no matching `.loop/evidence/evidence-iter<N>.json` is a finding, mirroring §22's shipped `missing_event_store` tripwire. Scoped strictly to the `verify-iter<N>.json` name: legacy bundles (`verify-T1.json`, `verify-T1-iter1.json`) and an absent-everything workspace are untouched. Deleting **both** files is still clean — the honest residual, pinned by name in Task 6.

12. **Write order: durable event first, evidence second; bundle placed last.** `dispatch_once` appends the `iteration_appended` event, *then* writes bundle + record. Writing evidence first would break the shipped crash-injection pin `test_crash_injection_before_iteration_event_commit_leaves_no_partial_dispatch` (`scripts/test_runner_dispatch.py:102-105`), which asserts a byte-identical tree after a SIGKILL at the pre-commit `COMMIT`. Within the writer, the bundle goes to a same-directory temp name, the record is written, and only then is the bundle `os.replace`d into place — so a partial write leaves nothing metrics-visible. The cost is an honest, documented gap: a crash in the window between commit and bundle write leaves an iteration with no bundle. The event log stays authoritative; Slice 3 (which makes evidence load-bearing for `Succeeded`) is where that window gets closed.

13. **A failed evidence write is loud.** After a committed append, an `OSError`/`EmitError` from the writer raises `RunnerError` whose message names the committed iteration. It is never swallowed (R007). `ChainHashError` from a non-finite task value is converted to `EmitError` inside the writer so it cannot escape untyped.

14. **Doctor does not hash-verify the referenced bundle, and does not compare any digest, in this slice.** `verify_evidence()` exists (`loop/evidence.py:117`) and Slice 3 wires it. Slice 2's doctor checks *structure*, *declared independence*, and *record presence beside a bundle* only. Task 6 pins both boundaries so nobody mistakes silence for verification.

15. **Evidence artifacts live outside the hash chain.** Both files are plain, overwrite-permitting writes. A worker with write access to `.loop/` can rewrite the record's identities or delete the pair, and doctor will not notice. Binding the record digest into the chain needs a new event type (`loop/events.py` + `loop/reducer.py`) — out of this slice's declared surface and named as Slice-3 scope. Task 6 pins the rewrite; §17, README and CHANGELOG state it literally, and the phrase "recorded forgery" is forbidden.

16. **`loop simulate` stays decision-level.** No field is added to `_empty_prediction`. See Post-review design change 17.

---

## File structure

| File | Change | Responsibility |
|---|---|---|
| `loop/verifier.py` | **create** | Pure verifier identity: `code_digest` + basis, the two identity blocks, `policy_digest`, criterion partition. stdlib + `loop.chain` only. |
| `loop/paths.py` | modify (append) | `EVIDENCE_DIR_NAME`, `ARTIFACTS_DIR_NAME` — the single definition both `emit` and `contract` import. |
| `loop/evidence.py` | modify (docstring 1-6, body ~42-114) | Honest module docstring; structural parity for the four new `verified_by` fields; extract the mode-dispatch seam `evidence_issues()`. |
| `schemas/evidence.schema.json` | modify (description line 5, `verified_by.properties` ~26-35) | Honest description; optional `command`, `code_digest`, `code_digest_basis`, `policy_digest`. |
| `schemas/tasks.schema.json` | modify (task `properties`) | Optional `visible_criteria` / `holdout_criteria` arrays; `required` untouched. |
| `loop/emit.py` | modify (append) | `write_verify_evidence()` — temp-then-replace bundle + hashed evidence@1 record. |
| `loop/runner.py` | modify (~201-249) | `dispatch_once(..., executor=, verifier_identity=)`; build the identity block pre-execution; derive `attempt`; write evidence after the durable append; typed failure. |
| `loop/contract.py` | modify (~556 `_RECORD_SCHEMA_FILES` context, ~564-568 `_RECORD_SCHEMA_IDS`, ~635-657 `_validate_optional_records`, + new helpers) | `.loop/evidence/*.json` discovery, mode-parity validation, `self_verified_evidence`, `missing_evidence_record`. |
| `loop/__main__.py` | modify (~75 options help, ~245-265 flags, ~340 dispatch) | `--executor` / `--verifier-identity`, valid only on `run`; misuse guard; help text. **Usage line 32 is byte-unchanged.** |
| `scripts/test_verifier_identity.py` | **create** | Digest/basis/identity-block/policy/partition unit coverage + doc pins. |
| `scripts/test_verify_evidence_writer.py` | **create** | Writer output shape, metrics compatibility, atomicity, typed errors. |
| `scripts/test_doctor_evidence.py` | **create** | Discovery, both-mode validation, `self_verified_evidence`, `missing_evidence_record`, byte-stability, read-only. |
| `scripts/test_adversarial_verifier_identity.py` | **create** | 10 pinned honest limitations + 3 real detections. |
| `scripts/test_evidence.py` | extend | Schema/fallback parity for the four new fields. |
| `scripts/test_runner_dispatch.py` | extend | Runner wiring + CLI identity flags. |
| `scripts/test_conformance.py` | extend | The machine-pinned `policy_digest` conformance vector (Slice-1 precedent). |
| `reference/repo-os-contract.md` | modify §1, §17, §22 | Declared locations, verifier-identity normative section, two doctor issue-code rows. |
| `reference/safety-and-approvals.md` | modify §5 | One sentence: the :97 invariant now has a machine check. |
| `README.md` | modify | One-line capability + one honest clause (Task 7); version surfaces (Task 9). |
| `CHANGELOG.md`, `pyproject.toml`, `.claude-plugin/plugin.json`, `scripts/test_docs_version.py` | modify (Task 9) | Release cut v0.11.0. |

Interfaces produced (used across tasks — exact signatures):

```python
# loop/paths.py
EVIDENCE_DIR_NAME = "evidence"
ARTIFACTS_DIR_NAME = "artifacts"

# loop/verifier.py
CODE_DIGEST_BASES: tuple[str, ...]   # ("workspace_file","path_lookup","outside_workspace","not_a_file",
                                     #  "unresolvable","unreadable","unparseable_command",
                                     #  "empty_command","injected_verifier")
POLICY_FIELDS: tuple[str, ...]       # ("criterion_ref", "depends_on", "id", "verify")
def verifier_code_digest(command: str | None, workspace: str | Path) -> tuple[str | None, str]: ...
def executed_verifier_identity(command: str | None, workspace: str | Path) -> dict[str, Any]: ...
# {"command": str|None, "code_digest": str|None, "code_digest_basis": str, "source": "declared_command"}
def injected_verifier_identity() -> dict[str, Any]: ...
# {"command": None, "code_digest": None, "code_digest_basis": "injected_verifier",
#  "source": "injected_callable"}
def verification_policy(task: Mapping[str, Any]) -> dict[str, Any]: ...
def verification_policy_digest(task: Mapping[str, Any]) -> str: ...      # hex sha256; raises ChainHashError
def criterion_partition(task: Mapping[str, Any]) -> dict[str, Any]: ...
# {"visible": [str], "holdout": [str], "declared": bool, "holdout_executed": False}

# loop/evidence.py
def evidence_issues(data: Any, *, resolved_mode: str) -> list[ContractIssue]: ...   # new seam

# loop/emit.py
def write_verify_evidence(target: str | Path, *, run_id: str, iteration_id: int,
                          task: Mapping[str, Any], passed: bool,
                          code_identity: Mapping[str, Any],          # REQUIRED — never derived here
                          summary: str = "", executor: str | None = None,
                          verifier_identity: str | None = None,
                          attempt: int | None = None) -> dict[str, Any]: ...
# {"bundle": Path, "evidence": Path, "sha256": str}
UNATTRIBUTED_EXECUTOR = "unattributed"
DEFAULT_VERIFIER_IDENTITY = "loop.run"

# loop/runner.py
def dispatch_once(target, *, verifier=None, mode=None,
                  executor: str | None = None, verifier_identity: str | None = None) -> dict[str, Any]: ...
# result gains "evidence": str (the record path) on a dispatched action

# loop/contract.py
def _self_verified(record: Mapping[str, Any]) -> bool: ...
# new issue codes: "self_verified_evidence", "missing_evidence_record"
```

---

### Task 0: Branch setup and baseline measurement

**Files:** none.

- [ ] **Step 1:** Record the branch point: `git -C /mnt/c/Dev/projects/loop-engineer log --oneline -6 origin/main`. Note in the PR draft whether any of issues #81/#85/#86/#87 landed since planning (at planning time all four were **open issues with no PRs**; there is no rebase gate). Do **not** wait on them.
- [ ] **Step 2:** `git -C /mnt/c/Dev/projects/loop-engineer checkout -b feat/verifier-identity main` (main protection blocks direct pushes; all work lands via PR).
- [ ] **Step 3:** Create the baseline worktree **detached** — `git worktree add <path> <branch>` refuses a branch already checked out in the main worktree: `git -C /mnt/c/Dev/projects/loop-engineer worktree add --detach /mnt/c/Dev/projects/loop-engineer/.tmp/s2-base feat/verifier-identity`.
- [ ] **Step 4:** Measure the extras baseline there (the live checkout reads +2/−2 — two checked-when-present tests): `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider /mnt/c/Dev/projects/loop-engineer/.tmp/s2-base/scripts`.
- [ ] **Step 5:** Measure the pyyaml-only baseline in the same worktree: `uv run --with pyyaml --with pytest python3 -B -m pytest -q -p no:cacheprovider /mnt/c/Dev/projects/loop-engineer/.tmp/s2-base/scripts`.
- [ ] **Step 6:** Record both `(passed, skipped)` pairs at the top of the PR draft as `BASE_EXTRAS` and `BASE_FALLBACK`. Every later acceptance line is `BASE + delta`. State the dependency set with every number (`--with hypothesis` swings ~+10/−1 and CI installs it — never compare across dependency sets).

**Acceptance:** two recorded `(passed, skipped)` pairs; detached worktree left in place for Task 8.

---

### Task 1: `loop/verifier.py` — honest digests, identity blocks, and the declared partition

**Files:** Create `loop/verifier.py`; Modify `loop/paths.py`; Modify `schemas/tasks.schema.json`; Create `scripts/test_verifier_identity.py`.

**Interfaces:** Produces `CODE_DIGEST_BASES`, `POLICY_FIELDS`, `verifier_code_digest`, `executed_verifier_identity`, `injected_verifier_identity`, `verification_policy`, `verification_policy_digest`, `criterion_partition`, `EVIDENCE_DIR_NAME`, `ARTIFACTS_DIR_NAME`.

- [ ] **Step 1: Write the failing tests** — `scripts/test_verifier_identity.py`:

```python
"""Verifier identity — honest code/policy digests and the declared criterion partition."""
from __future__ import annotations

import hashlib
from pathlib import Path

from loop import verifier
from loop.verifier import (CODE_DIGEST_BASES, POLICY_FIELDS, criterion_partition,
                           executed_verifier_identity, injected_verifier_identity,
                           verification_policy, verification_policy_digest, verifier_code_digest)


def _task(**overrides):
    base = {"id": "T-1", "title": "t", "status": "pending", "criterion_ref": "C-1",
            "verify": "./scripts/verify-fast.sh", "depends_on": [], "attempts": 0, "evidence": None}
    base.update(overrides)
    return base


def _script(workspace: Path, rel: str, body: str = "#!/bin/sh\nexit 0\n") -> Path:
    path = workspace / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_code_digest_hashes_a_workspace_script(tmp_path):
    path = _script(tmp_path, "scripts/verify-fast.sh")
    digest, basis = verifier_code_digest("./scripts/verify-fast.sh --quiet", tmp_path)
    assert basis == "workspace_file"
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()


def test_code_digest_is_null_for_a_bare_program_name_resolved_through_path(tmp_path):
    _script(tmp_path, "pytest")  # a same-named workspace file is NOT what ran
    assert verifier_code_digest("pytest -q", tmp_path) == (None, "path_lookup")


def test_code_digest_is_null_for_an_absolute_path_outside_the_workspace(tmp_path):
    outside = tmp_path.parent / "outside.sh"
    outside.write_text("#!/bin/sh\n", encoding="utf-8")
    assert verifier_code_digest(f"{outside} run", tmp_path) == (None, "outside_workspace")


def test_code_digest_is_null_when_a_symlink_escapes_the_workspace(tmp_path):
    outside = tmp_path.parent / "escape.sh"
    outside.write_text("#!/bin/sh\n", encoding="utf-8")
    link = tmp_path / "verify.sh"
    link.symlink_to(outside)
    assert verifier_code_digest("./verify.sh", tmp_path) == (None, "outside_workspace")


def test_code_digest_is_null_for_a_missing_relative_path(tmp_path):
    assert verifier_code_digest("./scripts/missing.sh", tmp_path) == (None, "not_a_file")


def test_code_digest_is_null_for_a_directory_argv0(tmp_path):
    (tmp_path / "scripts").mkdir()
    assert verifier_code_digest("./scripts", tmp_path) == (None, "not_a_file")


def test_code_digest_says_unresolvable_when_resolution_raises(tmp_path):
    """An OSError while resolving is 'could not determine', NOT 'not a file'."""
    a, b = tmp_path / "a.sh", tmp_path / "b.sh"
    a.symlink_to(b)
    b.symlink_to(a)  # ELOOP on resolve()
    assert verifier_code_digest("./a.sh", tmp_path) == (None, "unresolvable")


def test_code_digest_is_null_and_explained_when_the_file_cannot_be_read(tmp_path, monkeypatch):
    _script(tmp_path, "scripts/verify-fast.sh")
    monkeypatch.setattr(verifier, "_digest_file", lambda path: None)
    assert verifier_code_digest("./scripts/verify-fast.sh", tmp_path) == (None, "unreadable")


def test_code_digest_is_null_for_an_unparseable_command(tmp_path):
    assert verifier_code_digest("echo 'unbalanced", tmp_path) == (None, "unparseable_command")


def test_code_digest_is_null_for_an_absent_or_blank_command(tmp_path):
    assert verifier_code_digest(None, tmp_path) == (None, "empty_command")
    assert verifier_code_digest("   ", tmp_path) == (None, "empty_command")


def test_every_returned_basis_is_a_declared_basis(tmp_path):
    commands = [None, "   ", "echo 'x", "pytest -q", "./missing.sh", "/bin/sh -c true"]
    assert {verifier_code_digest(c, tmp_path)[1] for c in commands} <= set(CODE_DIGEST_BASES)


def test_executed_identity_block_names_the_command_it_is_about_to_run(tmp_path):
    path = _script(tmp_path, "scripts/verify-fast.sh")
    block = executed_verifier_identity("./scripts/verify-fast.sh", tmp_path)
    assert block == {"command": "./scripts/verify-fast.sh",
                     "code_digest": hashlib.sha256(path.read_bytes()).hexdigest(),
                     "code_digest_basis": "workspace_file", "source": "declared_command"}


def test_injected_identity_block_fabricates_nothing(tmp_path):
    """No declared command ran, so command and digest are null — never the task's verify."""
    assert injected_verifier_identity() == {
        "command": None, "code_digest": None,
        "code_digest_basis": "injected_verifier", "source": "injected_callable"}
    assert "injected_verifier" in CODE_DIGEST_BASES


def test_policy_digest_ignores_run_state(tmp_path):
    a = verification_policy_digest(_task(attempts=0, status="pending", evidence=None))
    b = verification_policy_digest(_task(attempts=7, status="done", evidence=["RUNLOG.md"]))
    assert a == b
    assert set(verification_policy(_task())) == set(POLICY_FIELDS)


def test_policy_digest_changes_when_the_verify_command_changes():
    assert verification_policy_digest(_task()) != verification_policy_digest(_task(verify="true"))


def test_policy_digest_changes_when_the_criterion_ref_changes():
    assert verification_policy_digest(_task()) != verification_policy_digest(_task(criterion_ref="C-2"))


def test_policy_digest_changes_when_the_task_id_changes():
    """id is deliberately bound: the digest identifies WHICH goalpost, not just its shape."""
    assert verification_policy_digest(_task()) != verification_policy_digest(_task(id="T-2"))


def test_policy_digest_changes_when_depends_on_is_reordered():
    """depends_on is bound as declared ordering; a reorder is a visible policy edit."""
    assert (verification_policy_digest(_task(depends_on=["A", "B"]))
            != verification_policy_digest(_task(depends_on=["B", "A"])))


def test_criterion_partition_derives_visible_from_criterion_ref_when_undeclared():
    assert criterion_partition(_task()) == {
        "visible": ["C-1"], "holdout": [], "declared": False, "holdout_executed": False}


def test_criterion_partition_records_a_declared_split_and_never_claims_execution():
    task = _task(visible_criteria=["C-1", "C-2"], holdout_criteria=["C-9"])
    assert criterion_partition(task) == {
        "visible": ["C-1", "C-2"], "holdout": ["C-9"], "declared": True, "holdout_executed": False}
```

- [ ] **Step 2: Run it — expect collection failure.** `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_verifier_identity.py` fails with `ModuleNotFoundError: No module named 'loop.verifier'`.

- [ ] **Step 3: Add the shared location constants** — append to `loop/paths.py` so exactly one definition exists for both `emit` and `contract`:

```python
# Declared .loop/ subdirectory names (reference/repo-os-contract.md §1). Defined here,
# the lowest module both the writer and the validator already import, so the literal
# never forks between loop.emit and loop.contract.
ARTIFACTS_DIR_NAME = "artifacts"
EVIDENCE_DIR_NAME = "evidence"
```

- [ ] **Step 4: Declare the partition fields on tasks@1** — in `schemas/tasks.schema.json`, inside the task item `properties` (additive; `required` untouched, `additionalProperties` stays `true`, so this is not a version bump and `evals/cases/structural.json` stays untouched):

```json
        "visible_criteria": {"type": ["array", "null"], "items": {"type": "string"}, "default": null,
                             "description": "Criterion refs the verifier may see (repo-os-contract §17)."},
        "holdout_criteria": {"type": ["array", "null"], "items": {"type": "string"}, "default": null,
                             "description": "Criterion refs held back from the verifier (repo-os-contract §17)."}
```

- [ ] **Step 5: Implement `loop/verifier.py`:**

```python
"""Verifier identity — honest digests of the verifier that actually ran.

This module RECORDS; it does not prove. A digest states what this process
observed about a command it was handed and is about to execute. A worker that
lies about *who* verified, or that rewrites the record afterwards, is not caught
here — see reference/safety-and-approvals.md §5 and reference/repo-os-contract.md §17.
"""

from __future__ import annotations

import hashlib
import os
import shlex
from pathlib import Path
from typing import Any, Mapping

from .chain import canonical_json

CODE_DIGEST_BASES = (
    "workspace_file", "path_lookup", "outside_workspace", "not_a_file",
    "unresolvable", "unreadable", "unparseable_command", "empty_command",
    "injected_verifier",
)
POLICY_FIELDS = ("criterion_ref", "depends_on", "id", "verify")

_CHUNK = 64 * 1024


def _digest_file(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            while chunk := handle.read(_CHUNK):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def verifier_code_digest(command: str | None, workspace: str | Path) -> tuple[str | None, str]:
    """Digest argv[0] only when it is a readable regular file inside the workspace.

    Returns ``(digest_or_None, basis)``. ``basis`` is always one of
    ``CODE_DIGEST_BASES`` and always explains a null digest truthfully — a null is
    the right answer for ``python3 -m pytest``, and ``unresolvable`` (not
    ``not_a_file``) is the right answer when resolution itself failed.
    Never raises.
    """
    if not isinstance(command, str) or not command.strip():
        return None, "empty_command"
    try:
        argv = shlex.split(command, posix=True)
    except ValueError:
        return None, "unparseable_command"
    if not argv:
        return None, "empty_command"
    argv0 = argv[0]
    if "/" not in argv0 and os.sep not in argv0:
        # No separator: the OS resolves this through PATH. A same-named file in
        # the workspace is NOT what ran, so hashing it would be a fabrication.
        return None, "path_lookup"
    try:
        root = Path(workspace).resolve()
        candidate = Path(argv0)
        resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
        is_file = resolved.is_file()
    except OSError:
        return None, "unresolvable"
    if not is_file:
        return None, "not_a_file"
    try:
        resolved.relative_to(root)
    except ValueError:
        return None, "outside_workspace"
    digest = _digest_file(resolved)
    return (digest, "workspace_file") if digest is not None else (None, "unreadable")


def executed_verifier_identity(command: str | None, workspace: str | Path) -> dict[str, Any]:
    """Identity of a DECLARED command this process is about to execute.

    Call this BEFORE running the verifier: the digest must describe the bytes that
    ran, and a verify script that rewrites itself would otherwise be recorded by
    its post-run bytes.
    """
    digest, basis = verifier_code_digest(command, workspace)
    return {"command": command, "code_digest": digest,
            "code_digest_basis": basis, "source": "declared_command"}


def injected_verifier_identity() -> dict[str, Any]:
    """Identity when the caller injected a verifier callable.

    The task's declared ``verify`` command did NOT run, so recording it — or a
    digest of it — would be a fabrication. Everything the process does not know
    is null, and the basis says why.
    """
    return {"command": None, "code_digest": None,
            "code_digest_basis": "injected_verifier", "source": "injected_callable"}


def verification_policy(task: Mapping[str, Any]) -> dict[str, Any]:
    """The declared goalpost subset of a TASKS.json entry (run state excluded)."""
    return {field: task.get(field) for field in POLICY_FIELDS}


def verification_policy_digest(task: Mapping[str, Any]) -> str:
    """sha256 over the canonical JSON of the declared goalpost.

    Reuses loop.chain.canonical_json — one canonicalizer for writer and verifier
    (repo-os-contract.md §16). Raises ChainHashError for a task entry that is not
    canonicalizable (e.g. a NaN that survived json.loads); callers convert that to
    their own typed error rather than letting it escape.
    """
    return hashlib.sha256(canonical_json(verification_policy(task)).encode("utf-8")).hexdigest()


def criterion_partition(task: Mapping[str, Any]) -> dict[str, Any]:
    """Record the DECLARED visible/held-out split — never invent one.

    ``holdout_executed`` is always False: the runner executes exactly the task's
    declared ``verify`` command. Running a holdout set is scripts/holdout_gate.py's
    job, and its verdict artifact is a different, canonical shape.
    """
    declared_visible = task.get("visible_criteria")
    declared_holdout = task.get("holdout_criteria")
    declared = isinstance(declared_visible, list) or isinstance(declared_holdout, list)
    if isinstance(declared_visible, list):
        visible = [item for item in declared_visible if isinstance(item, str)]
    else:
        ref = task.get("criterion_ref")
        visible = [ref] if isinstance(ref, str) and ref else []
    holdout = ([item for item in declared_holdout if isinstance(item, str)]
               if isinstance(declared_holdout, list) else [])
    return {"visible": visible, "holdout": holdout,
            "declared": declared, "holdout_executed": False}
```

- [ ] **Step 6: Run the gate.** `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_verifier_identity.py scripts/test_loop_contract_core.py` — expect **20 passed** in the new file and zero change in the contract-core file (the tasks@1 edit is additive).
- [ ] **Step 7:** Commit: `feat(verifier): honest code/policy digests, identity blocks, and the declared criterion partition`.

**Acceptance:** `scripts/test_verifier_identity.py` 20 passed, 0 skipped, in **both** dependency sets (no jsonschema dependence in this file). `test_injected_identity_block_fabricates_nothing` and `test_code_digest_says_unresolvable_when_resolution_raises` are the two new-honesty pins.

---

### Task 2: evidence@1 gains four optional identity fields (both modes)

**Files:** Modify `schemas/evidence.schema.json` (description line 5, `verified_by.properties` ~26-35), `loop/evidence.py` (docstring 1-6, body ~42-114); Extend `scripts/test_evidence.py`.

- [ ] **Step 1: Write the failing tests** — append to `scripts/test_evidence.py`:

```python
import pytest

from loop.evidence import evidence_issues, validate_evidence

_IDENTITY = {
    "by": "ci", "at": "2026-07-25T00:00:00+00:00",
    "command": "./scripts/verify-fast.sh",
    "code_digest": "a" * 64, "code_digest_basis": "workspace_file",
    "policy_digest": "b" * 64,
}


def _record(**verified_by_overrides):
    verified_by = dict(_IDENTITY)
    verified_by.update(verified_by_overrides)
    return {
        "schema": "loop-engineer/evidence@1", "id": "e1", "kind": "verify-bundle",
        "uri": ".loop/artifacts/verify-iter5.json", "sha256": "c" * 64,
        "media_type": "application/json", "created_at": "2026-07-25T00:00:00+00:00",
        "produced_by": {"run_id": "run-1", "task_id": "T-1", "attempt": 1, "executor": "worker-a"},
        "verified_by": verified_by,
    }


def _modes():
    return ["basic", "strict"]


@pytest.mark.parametrize("mode", _modes())
def test_identity_fields_are_accepted(mode):
    if mode == "strict":
        pytest.importorskip("jsonschema")
    assert validate_evidence(_record(), mode=mode)["ok"] is True


@pytest.mark.parametrize("mode", _modes())
def test_identity_fields_accept_explicit_nulls(mode):
    if mode == "strict":
        pytest.importorskip("jsonschema")
    record = _record(command=None, code_digest=None, code_digest_basis="injected_verifier",
                     policy_digest=None)
    assert validate_evidence(record, mode=mode)["ok"] is True


@pytest.mark.parametrize("mode", _modes())
def test_malformed_code_digest_is_rejected(mode):
    if mode == "strict":
        pytest.importorskip("jsonschema")
    assert validate_evidence(_record(code_digest="NOTHEX"), mode=mode)["ok"] is False


@pytest.mark.parametrize("mode", _modes())
def test_malformed_policy_digest_is_rejected(mode):
    if mode == "strict":
        pytest.importorskip("jsonschema")
    assert validate_evidence(_record(policy_digest="short"), mode=mode)["ok"] is False


@pytest.mark.parametrize("mode", _modes())
def test_unknown_code_digest_basis_is_rejected(mode):
    if mode == "strict":
        pytest.importorskip("jsonschema")
    assert validate_evidence(_record(code_digest_basis="vibes"), mode=mode)["ok"] is False


@pytest.mark.parametrize("mode", _modes())
def test_non_string_command_is_rejected(mode):
    if mode == "strict":
        pytest.importorskip("jsonschema")
    assert validate_evidence(_record(command=17), mode=mode)["ok"] is False


def test_evidence_issues_seam_dispatches_on_resolved_mode():
    assert evidence_issues(_record(), resolved_mode="structural-fallback") == []
    assert evidence_issues("not an object", resolved_mode="structural-fallback")[0]["code"] == "invalid_evidence"
```

- [ ] **Step 2: Run it — expect failures.** `ImportError` on `evidence_issues`, and (once that is stubbed) the four rejection tests pass in `strict` but FAIL in `basic` because the structural fallback ignores unknown fields.

- [ ] **Step 3: Schema — fields.** In `schemas/evidence.schema.json`, inside `verified_by.properties` (currently lines 29-32), add — `required` stays `["by", "at"]`:

```json
        "command": {"type": ["string", "null"], "default": null,
                    "description": "The declared verify command that was executed; null when no declared command ran."},
        "code_digest": {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$", "default": null,
                        "description": "sha256 of argv[0]'s file when it is a workspace file; null otherwise."},
        "code_digest_basis": {"type": ["string", "null"],
                              "enum": ["workspace_file", "path_lookup", "outside_workspace",
                                       "not_a_file", "unresolvable", "unreadable",
                                       "unparseable_command", "empty_command",
                                       "injected_verifier", null],
                              "default": null,
                              "description": "Why code_digest is what it is. Always explains a null."},
        "policy_digest": {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$", "default": null,
                          "description": "sha256 of the canonical JSON of the declared goalpost (repo-os-contract §17)."}
```

- [ ] **Step 4: Schema — honest description.** Replace `schemas/evidence.schema.json` line 5's `"It is standalone in v1; see reference/repo-os-contract.md #17."` with: `"loop doctor discovers and validates records from the declared location .loop/evidence/*.json; it does not yet hash-verify the artifacts they reference. See reference/repo-os-contract.md #17."`

- [ ] **Step 5: Structural parity.** In `loop/evidence.py`, extend the `verified_by` branch (currently lines 74-81) so the fallback checks exactly what the schema checks, and add the mode-dispatch seam:

```python
from .verifier import CODE_DIGEST_BASES

def _is_sha256_or_null(value: Any) -> bool:
    return value is None or (isinstance(value, str) and _SHA256_PATTERN.fullmatch(value) is not None)


# inside _structural_validate_evidence, replacing the verified_by else-branch body:
        else:
            for field in ("by", "at"):
                if not _is_non_empty_string(verified_by.get(field)):
                    issues.append(ContractIssue("invalid_evidence", f"verified_by.{field} must be a non-empty string"))
            command = verified_by.get("command")
            if command is not None and not isinstance(command, str):
                issues.append(ContractIssue("invalid_evidence", "verified_by.command must be a string or null"))
            for field in ("code_digest", "policy_digest"):
                if not _is_sha256_or_null(verified_by.get(field)):
                    issues.append(ContractIssue(
                        "invalid_evidence",
                        f"verified_by.{field} must be a 64-character lowercase hexadecimal string or null"))
            basis = verified_by.get("code_digest_basis")
            if basis is not None and basis not in CODE_DIGEST_BASES:
                issues.append(ContractIssue(
                    "invalid_evidence",
                    f"verified_by.code_digest_basis must be null or one of {CODE_DIGEST_BASES}"))


def evidence_issues(data: Any, *, resolved_mode: str) -> list[ContractIssue]:
    """Mode-dispatched issue list for one record — the seam doctor discovery reuses."""
    if not isinstance(data, dict):
        return [ContractIssue("invalid_evidence", "evidence record must be an object")]
    if resolved_mode == "jsonschema":
        return _jsonschema_validate_evidence(data)
    return _structural_validate_evidence(data)


def validate_evidence(data: dict[str, Any], *, mode: str | None = None) -> dict[str, Any]:
    """Validate a standalone evidence@1 record in the requested validation mode."""
    requested_mode, resolved_mode = _resolve_requested_mode(mode)
    issues = evidence_issues(data, resolved_mode=resolved_mode)
    return {"ok": not issues, "validation_mode": resolved_mode, "requested_mode": requested_mode,
            "schemas_checked": [EVIDENCE_SCHEMA_ID], "issues": issues}
```

  Import direction check: `loop.verifier` imports `loop.chain` only, so `loop.evidence → loop.verifier` introduces no cycle.

- [ ] **Step 6: Honest module docstring.** Replace `loop/evidence.py` lines 1-6 (which currently claim the module "is standalone in v1 and is not yet read by ``loop doctor``" — false after Task 5) with:

```python
"""loop-engineer/evidence@1 — hashed evidence + artifact provenance.

``loop doctor`` discovers and validates records from the declared location
``.loop/evidence/*.json`` (reference/repo-os-contract.md #17) and reports
``self_verified_evidence`` / ``missing_evidence_record``. It does NOT yet
hash-verify the artifacts those records reference, and it never compares a
recorded digest against anything — ``verify_evidence()`` below is the explicit,
caller-invoked check. That wiring is the evidence-wiring slice.
"""
```

- [ ] **Step 7: Run the gate.** `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_evidence.py` — expect the prior file total **+13 passed**; pyyaml-only expects **+7 passed / +6 skipped**.
- [ ] **Step 8:** Commit: `feat(evidence): optional verifier-identity fields on verified_by, with fallback parity`.

**Acceptance:** 13 new tests; 6 of them (`strict` halves) skip in the pyyaml-only set. Both modes reject all four malformed shapes. Neither `loop/evidence.py` nor `schemas/evidence.schema.json` still contains the strings `standalone in v1` or `not yet read by` (pinned in Task 7 Step 6).

---

### Task 3: `emit.write_verify_evidence` — the bundle + record writer

**Files:** Modify `loop/emit.py`; Create `scripts/test_verify_evidence_writer.py`.

- [ ] **Step 1: Write the failing tests** — `scripts/test_verify_evidence_writer.py` (no `sys.path` manipulation: there is no `conftest.py` in this repo, so pytest's rootdir-prepend already puts `scripts/` on the path — the shipped bare `from chain_fixtures import ...` at `scripts/test_doctor_eventstore.py:7` is the precedent):

```python
"""The verify-bundle + evidence@1 writer: shape, digests, and metrics compatibility."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import metrics  # the shipped metrics reader — compatibility is the point
from loop import emit
from loop.evidence import validate_evidence, verify_evidence
from loop.verifier import executed_verifier_identity, injected_verifier_identity


def _task(**overrides):
    base = {"id": "T-1", "title": "t", "status": "pending", "criterion_ref": "C-1",
            "verify": "./scripts/verify-fast.sh", "depends_on": [], "attempts": 2, "evidence": None}
    base.update(overrides)
    return base


def _ws(tmp_path):
    workspace = tmp_path / "workspace"
    emit.open_contract(workspace)
    script = workspace / "scripts" / "verify-fast.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    return workspace


def _write(workspace, **overrides):
    kwargs = {"run_id": "run-1", "iteration_id": 5, "task": _task(), "passed": True,
              "summary": "ok",
              "code_identity": executed_verifier_identity("./scripts/verify-fast.sh", workspace)}
    kwargs.update(overrides)
    return emit.write_verify_evidence(workspace, **kwargs)


def test_bundle_is_green_by_the_shipped_metrics_convention(tmp_path):
    workspace = _ws(tmp_path)
    written = _write(workspace)
    bundle = json.loads(Path(written["bundle"]).read_text(encoding="utf-8"))
    assert bundle["outcome"] == "PASS" and bundle["passed"] is True
    assert bundle["iteration_id"] == 5 and bundle["task"] == "T-1"
    assert Path(written["bundle"]).parent.name == "artifacts"


def test_metrics_sees_exactly_one_bundle_and_no_gate_verdict(tmp_path):
    workspace = _ws(tmp_path)
    _write(workspace)
    loop_dir = workspace / ".loop"
    bundles = metrics._load_verify_bundles(loop_dir)
    assert [b["name"] for b in bundles] == ["verify-iter5.json"]
    assert bundles[0]["green"] is True and bundles[0]["iter"] == "5"
    assert metrics._load_gate_verdicts(loop_dir) == []


def test_failing_verification_writes_a_red_bundle(tmp_path):
    workspace = _ws(tmp_path)
    written = _write(workspace, passed=False, summary="boom")
    bundle = json.loads(Path(written["bundle"]).read_text(encoding="utf-8"))
    assert bundle["outcome"] == "FAIL" and bundle["passed"] is False
    assert metrics._load_verify_bundles(workspace / ".loop")[0]["green"] is False


def test_bundle_records_verifier_identity_and_partition(tmp_path):
    workspace = _ws(tmp_path)
    written = _write(workspace)
    bundle = json.loads(Path(written["bundle"]).read_text(encoding="utf-8"))
    script = (workspace / "scripts" / "verify-fast.sh").read_bytes()
    assert bundle["verifier"]["code_digest"] == hashlib.sha256(script).hexdigest()
    assert bundle["verifier"]["code_digest_basis"] == "workspace_file"
    assert bundle["verifier"]["by"] == emit.DEFAULT_VERIFIER_IDENTITY
    assert bundle["partition"] == {"visible": ["C-1"], "holdout": [],
                                   "declared": False, "holdout_executed": False}


def test_bundle_names_the_verdict_source(tmp_path):
    """outcome/passed came from SOMETHING — the bundle says what, so a reader of
    metrics can tell a declared-command gate from an injected callable."""
    workspace = _ws(tmp_path)
    declared = json.loads(Path(_write(workspace)["bundle"]).read_text(encoding="utf-8"))
    injected = json.loads(Path(
        _write(workspace, iteration_id=6, code_identity=injected_verifier_identity())["bundle"]
    ).read_text(encoding="utf-8"))
    assert declared["verifier"]["source"] == "declared_command"
    assert injected["verifier"]["source"] == "injected_callable"


def test_injected_verifier_identity_records_nulls_not_a_fabricated_digest(tmp_path):
    """The declared verify command did not run; recording it would be a fabrication."""
    workspace = _ws(tmp_path)
    written = _write(workspace, code_identity=injected_verifier_identity())
    record = json.loads(Path(written["evidence"]).read_text(encoding="utf-8"))
    assert record["verified_by"]["command"] is None
    assert record["verified_by"]["code_digest"] is None
    assert record["verified_by"]["code_digest_basis"] == "injected_verifier"


def test_record_sha256_commits_to_the_bundle_bytes(tmp_path):
    workspace = _ws(tmp_path)
    written = _write(workspace)
    record = json.loads(Path(written["evidence"]).read_text(encoding="utf-8"))
    assert record["sha256"] == hashlib.sha256(Path(written["bundle"]).read_bytes()).hexdigest()
    assert verify_evidence(record, workspace_root=workspace)["ok"] is True


@pytest.mark.parametrize("mode", ["basic", "strict"])
def test_record_validates_as_evidence_at_1(tmp_path, mode):
    if mode == "strict":
        pytest.importorskip("jsonschema")
    workspace = _ws(tmp_path)
    record = json.loads(Path(_write(workspace)["evidence"]).read_text(encoding="utf-8"))
    assert validate_evidence(record, mode=mode)["ok"] is True


def test_defaults_never_collide_so_a_default_run_is_not_self_verified(tmp_path):
    workspace = _ws(tmp_path)
    record = json.loads(Path(_write(workspace)["evidence"]).read_text(encoding="utf-8"))
    assert record["produced_by"]["executor"] == emit.UNATTRIBUTED_EXECUTOR
    assert record["verified_by"]["by"] == emit.DEFAULT_VERIFIER_IDENTITY
    assert record["produced_by"]["executor"] != record["verified_by"]["by"]


def test_supplied_identities_are_recorded_verbatim(tmp_path):
    workspace = _ws(tmp_path)
    record = json.loads(Path(
        _write(workspace, executor="worker-a", verifier_identity="worker-a", attempt=3)["evidence"]
    ).read_text(encoding="utf-8"))
    assert record["produced_by"]["executor"] == "worker-a"
    assert record["verified_by"]["by"] == "worker-a"
    assert record["produced_by"]["attempt"] == 3


def test_attempt_is_null_when_the_caller_supplies_none(tmp_path):
    """The kernel does not track TASKS.json `attempts` (zero references in loop/),
    so an unsupplied attempt is null, never task['attempts'] + 1."""
    workspace = _ws(tmp_path)
    record = json.loads(Path(_write(workspace)["evidence"]).read_text(encoding="utf-8"))
    assert record["produced_by"]["attempt"] is None


def test_rewrite_of_the_same_iteration_is_idempotent_in_path(tmp_path):
    workspace = _ws(tmp_path)
    first, second = _write(workspace), _write(workspace)
    assert first["bundle"] == second["bundle"] and first["evidence"] == second["evidence"]
    assert first["sha256"] == second["sha256"]
    assert [p.name for p in sorted((workspace / ".loop" / "artifacts").iterdir())] == ["verify-iter5.json"]


def test_writer_refuses_a_workspace_with_no_contract(tmp_path):
    with pytest.raises(emit.EmitError):
        emit.write_verify_evidence(tmp_path / "nope", run_id="r", iteration_id=1,
                                   task=_task(), passed=True,
                                   code_identity=injected_verifier_identity())


def test_a_non_canonicalizable_task_raises_a_typed_emit_error(tmp_path):
    """json.loads accepts NaN by default; canonical_json sets allow_nan=False. The
    resulting ChainHashError must never escape the writer untyped."""
    workspace = _ws(tmp_path)
    task = json.loads('{"id": "T-1", "criterion_ref": NaN, "verify": "true", "depends_on": []}')
    with pytest.raises(emit.EmitError, match="canonical"):
        _write(workspace, task=task)


def test_a_failed_record_write_leaves_no_metrics_visible_bundle(tmp_path, monkeypatch):
    """Bundle goes to a temp name, record next, bundle placed last — so an error
    between them cannot leave an orphan green marker for FCR to read."""
    workspace = _ws(tmp_path)
    real = emit._atomic_write_text

    def explode(path, text):
        if path.name.startswith("evidence-iter"):
            raise OSError("disk full")
        return real(path, text)

    monkeypatch.setattr(emit, "_atomic_write_text", explode)
    with pytest.raises(OSError):
        _write(workspace)
    assert metrics._load_verify_bundles(workspace / ".loop") == []
```

- [ ] **Step 2: Run it — expect `AttributeError: module 'loop.emit' has no attribute 'write_verify_evidence'`.**

- [ ] **Step 3: Implement.** Append to `loop/emit.py`. Four import edits at the top — verified against the current header (`loop/emit.py:8-30`, which has `json`, `os`, `tempfile`, `datetime`, `Path`, `Any`/`Sequence`, `fsm`, `completion`, `contract`, `paths`): add `import hashlib`; widen `from typing import Any, Sequence` to include `Mapping`; add `from .chain import ChainHashError`; widen `from .paths import resolve_loop_paths` to `from .paths import ARTIFACTS_DIR_NAME, EVIDENCE_DIR_NAME, resolve_loop_paths`; add `from .verifier import criterion_partition, verification_policy_digest`.

```python
UNATTRIBUTED_EXECUTOR = "unattributed"
DEFAULT_VERIFIER_IDENTITY = "loop.run"
_EVIDENCE_SCHEMA_ID = "loop-engineer/evidence@1"


def write_verify_evidence(
    target: str | Path, *, run_id: str, iteration_id: int, task: Mapping[str, Any], passed: bool,
    code_identity: Mapping[str, Any], summary: str = "", executor: str | None = None,
    verifier_identity: str | None = None, attempt: int | None = None,
) -> dict[str, Any]:
    """Write one verify bundle and its hashed evidence@1 record.

    ``code_identity`` is REQUIRED and is never derived here: only the caller knows
    which verifier actually ran (see loop.verifier.executed_verifier_identity vs
    injected_verifier_identity). Deriving it from ``task['verify']`` would record a
    command that an injected verifier never executed.

    The bundle is the artifact (metrics-compatible; carries verifier identity, the
    verdict's source, and the DECLARED criterion partition); the record is the
    schema-validated pointer that commits to the bundle's bytes. Identities are
    recorded, never inferred: an unsupplied executor is the literal ``unattributed``
    and an unsupplied attempt is ``null``.
    """
    paths = _require_contract(target)
    iteration_id = _require_iteration_id(iteration_id)
    try:
        policy_digest = verification_policy_digest(task)
    except ChainHashError as exc:
        raise EmitError(f"task entry is not canonical-JSON serializable: {exc}") from exc

    identity = {
        "by": verifier_identity or DEFAULT_VERIFIER_IDENTITY,
        "command": code_identity["command"],
        "code_digest": code_identity["code_digest"],
        "code_digest_basis": code_identity["code_digest_basis"],
        "source": code_identity["source"],
        "policy_digest": policy_digest,
    }
    bundle = {
        "iteration_id": iteration_id,
        "task": task.get("id"),
        "outcome": "PASS" if passed else "FAIL",
        "passed": bool(passed),
        "summary": summary,
        "verifier": identity,
        "partition": criterion_partition(task),
    }
    bundle_path = paths.loop_dir / ARTIFACTS_DIR_NAME / f"verify-iter{iteration_id}.json"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_text = json.dumps(bundle, indent=2, sort_keys=True) + "\n"
    # Staged under a name metrics does not rglob, so a failure before the record is
    # written cannot leave an orphan green bundle for FCR to count.
    staged = bundle_path.with_name(bundle_path.name + ".staged")
    _atomic_write_text(staged, bundle_text)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record = {
        "schema": _EVIDENCE_SCHEMA_ID,
        "id": f"{run_id}:{iteration_id}:verify",
        "kind": "verify-bundle",
        "uri": bundle_path.relative_to(paths.workspace).as_posix(),
        "sha256": hashlib.sha256(bundle_text.encode("utf-8")).hexdigest(),
        "media_type": "application/json",
        "created_at": now,
        "produced_by": {"run_id": run_id, "task_id": task.get("id"), "attempt": attempt,
                        "executor": executor or UNATTRIBUTED_EXECUTOR},
        "verified_by": {"by": identity["by"], "at": now, "command": identity["command"],
                        "code_digest": identity["code_digest"],
                        "code_digest_basis": identity["code_digest_basis"],
                        "policy_digest": identity["policy_digest"]},
    }
    record_path = paths.loop_dir / EVIDENCE_DIR_NAME / f"evidence-iter{iteration_id}.json"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _atomic_write_text(record_path, json.dumps(record, indent=2, sort_keys=True) + "\n")
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    os.replace(staged, bundle_path)
    return {"bundle": bundle_path, "evidence": record_path, "sha256": record["sha256"]}
```

- [ ] **Step 4: Run the gate.** `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_verify_evidence_writer.py scripts/test_metrics.py` — expect **15 passed** in the new file (pyyaml-only **14 passed / 1 skipped**) and zero change in `test_metrics.py`.
- [ ] **Step 5:** Commit: `feat(emit): write_verify_evidence — metrics-compatible bundle plus hashed evidence record`.

**Acceptance:** 15 collected (14 names, 1 jsonschema half). The load-bearing assertions are `test_metrics_sees_exactly_one_bundle_and_no_gate_verdict` (runs the *shipped* readers, not a re-implementation), `test_injected_verifier_identity_records_nulls_not_a_fabricated_digest`, and `test_a_failed_record_write_leaves_no_metrics_visible_bundle`.

---

### Task 4: Runner wiring and the identity flags

**Files:** Modify `loop/runner.py` (~201-249), `loop/__main__.py` (~75 options help, ~245-265 flags, ~340 dispatch); Extend `scripts/test_runner_dispatch.py`.

- [ ] **Step 1: Write the failing tests** — append to `scripts/test_runner_dispatch.py`:

```python
def _verify_ws(tmp_path, verify="./scripts/verify-fast.sh"):
    workspace, store = _ws(tmp_path, [{**_task("T-1"), "verify": verify}])
    script = workspace / "scripts" / "verify-fast.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    return workspace, store


def _bundle(workspace, n=5):
    return json.loads((workspace / ".loop" / "artifacts" / f"verify-iter{n}.json").read_text())


def _record(workspace, n=5):
    return json.loads((workspace / ".loop" / "evidence" / f"evidence-iter{n}.json").read_text())


def test_dispatch_with_the_declared_verifier_records_a_workspace_file_digest(tmp_path):
    """Only the path that ACTUALLY executes ./scripts/verify-fast.sh may hash it."""
    workspace, _ = _verify_ws(tmp_path)
    result = dispatch_once(workspace)  # no injected verifier -> the declared command runs
    record = _record(workspace)
    assert _bundle(workspace)["outcome"] == "PASS"
    assert record["verified_by"]["command"] == "./scripts/verify-fast.sh"
    assert record["verified_by"]["code_digest_basis"] == "workspace_file"
    assert record["verified_by"]["code_digest"] == hashlib.sha256(
        (workspace / "scripts" / "verify-fast.sh").read_bytes()).hexdigest()
    assert result["evidence"].endswith("evidence-iter5.json")


def test_dispatch_with_an_injected_verifier_records_no_fabricated_identity(tmp_path):
    """The declared command never ran, so command/digest are null with an explicit basis."""
    workspace, _ = _verify_ws(tmp_path)
    dispatch_once(workspace, verifier=_pass)
    record = _record(workspace)
    assert record["verified_by"]["command"] is None
    assert record["verified_by"]["code_digest"] is None
    assert record["verified_by"]["code_digest_basis"] == "injected_verifier"
    assert _bundle(workspace)["verifier"]["source"] == "injected_callable"


def test_dispatch_once_writes_a_red_bundle_for_a_failing_task(tmp_path):
    workspace, _ = _verify_ws(tmp_path)
    dispatch_once(workspace, verifier=lambda task, root: VerifyOutcome(False, "boom"))
    assert _bundle(workspace)["passed"] is False and _bundle(workspace)["summary"] == "boom"


def test_dispatch_once_records_the_supplied_executor(tmp_path):
    workspace, _ = _verify_ws(tmp_path)
    dispatch_once(workspace, verifier=_pass, executor="worker-a")
    record = _record(workspace)
    assert record["produced_by"]["executor"] == "worker-a" and record["verified_by"]["by"] == "loop.run"


def test_attempt_counts_durable_prior_iterations_for_this_task(tmp_path):
    """Derived from the event log, not from the never-incremented TASKS.json `attempts`."""
    workspace, _ = _verify_ws(tmp_path)
    dispatch_once(workspace, verifier=lambda task, root: VerifyOutcome(False, "red"))
    assert _record(workspace, 5)["produced_by"]["attempt"] == 1
    dispatch_once(workspace, verifier=lambda task, root: VerifyOutcome(False, "red again"))
    assert _record(workspace, 6)["produced_by"]["attempt"] == 2


def test_terminal_dispatch_writes_no_verify_bundle(tmp_path):
    workspace, _ = _ws(tmp_path, [_task("T-1", status="done")])
    assert dispatch_once(workspace, verifier=_pass)["action"] == "terminal_written"
    assert not (workspace / ".loop" / "evidence").exists()


def test_evidence_write_failure_after_a_committed_event_is_loud(tmp_path, monkeypatch):
    workspace, store = _verify_ws(tmp_path)
    def boom(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(emit, "write_verify_evidence", boom)
    with pytest.raises(RunnerError, match="committed"):
        dispatch_once(workspace, verifier=_pass)
    assert len(store.read("run-1")) == 6  # the event IS durable; the failure is reported, not hidden


def test_run_cli_accepts_executor_and_records_it(tmp_path):
    workspace, _ = _verify_ws(tmp_path, verify="true")
    result = _cli("run", "--executor", "worker-a", str(workspace))
    assert result.returncode == 0 and _record(workspace)["produced_by"]["executor"] == "worker-a"


def test_run_cli_verifier_identity_makes_the_finding_reachable(tmp_path):
    """Without this flag verified_by.by is always 'loop.run' and the kernel's own
    write path could never trip self_verified_evidence."""
    workspace, _ = _verify_ws(tmp_path, verify="true")
    result = _cli("run", "--executor", "solo", "--verifier-identity", "Solo", str(workspace))
    assert result.returncode == 0
    assert _record(workspace)["verified_by"]["by"] == "Solo"
    assert "self_verified_evidence" in {i["code"] for i in doctor_report(workspace)["issues"]}


def test_identity_flags_are_rejected_on_other_commands_and_create_nothing(tmp_path):
    for flag in ("--executor", "--verifier-identity"):
        target = tmp_path / f"fresh{flag}"
        result = _cli("scaffold", flag, "worker-a", str(target))
        assert result.returncode == 2 and "only valid for run" in result.stderr and not target.exists()


def test_run_help_documents_the_identity_flags():
    result = _cli("--help")
    assert result.returncode == 0
    assert "--executor" in result.stdout and "--verifier-identity" in result.stdout
```

  (Add `RunnerError` to the `loop.runner` import line at `scripts/test_runner_dispatch.py:15`, plus `hashlib` and `from loop.contract import doctor_report`.)

- [ ] **Step 2: Run it — expect 11 failures** (`FileNotFoundError` on the bundle path, `TypeError` on `executor=`, exit-2 assertions on the CLI).

- [ ] **Step 3: Implement the runner change** — `loop/runner.py`, in `dispatch_once`. Note the identity block is built **before** the verifier call:

```python
def dispatch_once(
    target: str | Path, *, verifier: Verifier | None = None, mode: str | None = None,
    executor: str | None = None, verifier_identity: str | None = None,
) -> dict[str, Any]:
    ...
    # Identity of what is ABOUT TO RUN. Built here, not in the writer: only this
    # frame knows whether the declared command or an injected callable will execute,
    # and hashing before execution keeps a self-modifying verify script honest.
    code_identity = (
        injected_verifier_identity() if verifier is not None
        else executed_verifier_identity(task.get("verify"), paths.workspace)
    )
    attempt = 1 + sum(
        1 for entry in projection["runlog_entries"] if entry.get("task_id") == task["id"]
    )
    outcome = (verifier or _default_verifier)(task, paths.workspace)
    ...
    store = SQLiteEventStore(paths.loop_dir / "events.db")
    _store_append(store, run_id, "iteration_appended", payload, actor="loop.run",
                  expected_sequence=projection["last_sequence"] + 1)
    # Evidence is written AFTER the durable append: writing it first would leave a
    # bundle behind a SIGKILL at the pre-commit COMMIT and break the zero-write
    # crash pin (test_crash_injection_before_iteration_event_commit_...).
    try:
        written = emit.write_verify_evidence(
            target, run_id=run_id, iteration_id=iteration_id, task=task,
            passed=outcome.passed, summary=outcome.summary, code_identity=code_identity,
            executor=executor, verifier_identity=verifier_identity, attempt=attempt,
        )
    except (OSError, emit.EmitError) as exc:
        raise RunnerError(
            f"iteration {iteration_id} is committed to the event log but its verify "
            f"bundle could not be written: {exc}"
        ) from exc
    emit.append_iteration(target, iteration_id=iteration_id, outcome=payload["outcome"],
                          task_id=payload["task_id"], notes=payload["summary"])
    return {"ok": True, "action": "dispatched", "task_id": task["id"],
            "outcome": payload["outcome"], "iteration_id": iteration_id, "run_id": run_id,
            "evidence": str(written["evidence"])}
```

  (Add `from .verifier import executed_verifier_identity, injected_verifier_identity` to the imports. `EmitError` already covers the `ChainHashError` conversion made in Task 3, so no new except member is needed here.)

- [ ] **Step 4: CLI — help text only.** In `loop/__main__.py`, add to the `options:` block (~line 75) — **do not touch the usage line at `loop/__main__.py:32`**, whose literal is asserted verbatim by `scripts/test_runner_dispatch.py:119`:

```
  --executor ID           (run) record this identity as produced_by.executor on the
                          run's evidence records; unset records "unattributed".
  --verifier-identity ID  (run) record this identity as verified_by.by; unset records
                          "loop.run". Equal to --executor => self_verified_evidence.
```

- [ ] **Step 5: CLI — flag parsing and misuse guard.** After the `--expect-chain-head` block (~line 248-263), mirroring its shape exactly:

```python
    executor = verifier_identity = None
    if command == "run":
        for flag, slot in (("--executor", "executor"), ("--verifier-identity", "verifier_identity")):
            try:
                value, argv = _extract_value_flag(argv, flag)
            except ValueError as exc:
                print(f"{command}: {exc}", file=sys.stderr)
                return 2
            if value is not None and not value.strip():
                print(f"{command}: {flag} must be a non-empty identity", file=sys.stderr)
                return 2
            if slot == "executor":
                executor = value
            else:
                verifier_identity = value
    else:
        for flag in ("--executor", "--verifier-identity"):
            if any(a == flag or a.startswith(f"{flag}=") for a in argv):
                print(f"{command}: {flag} is only valid for run", file=sys.stderr)
                return 2
```

- [ ] **Step 6: CLI — dispatch site.** At the `run` dispatch site: `dispatch_once(target, mode=mode, executor=executor, verifier_identity=verifier_identity)`.

- [ ] **Step 7: Run the gate.** `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_runner_dispatch.py scripts/test_runner_verifier.py scripts/test_loop_simulate_zero_writes.py scripts/test_loop_simulate_cli.py scripts/test_loop_cli.py` — expect prior totals **+11 passed**, **zero** pre-existing failures. The three crash-injection tests (`test_runner_dispatch.py:102-116`), `test_run_command_listed_in_help_and_usage` (:118-119), and every `_hashes(w) == before` zero-write assertion must be untouched and green.
- [ ] **Step 8:** Commit: `feat(runner): record the verifier that actually ran, plus the criterion partition, on every dispatch`.

**Acceptance:** +11 passed in both dependency sets. `test_crash_injection_before_iteration_event_commit_leaves_no_partial_dispatch` and `test_run_command_listed_in_help_and_usage` both pass **unmodified** — proof that decisions 12 and 13 hold.

---

### Task 5: Doctor discovery, `self_verified_evidence`, `missing_evidence_record`

**Files:** Modify `loop/contract.py` (~564-568 `_RECORD_SCHEMA_IDS`, ~635-657 `_validate_optional_records`, + new helpers); Create `scripts/test_doctor_evidence.py`.

- [ ] **Step 1: Write the failing tests** — `scripts/test_doctor_evidence.py`:

```python
"""Doctor's evidence@1 discovery, the self-verification finding, and the orphan-bundle tripwire."""
from __future__ import annotations

import hashlib
import json

import pytest

from loop.contract import doctor_report, validate_contract
from loop.scaffold import scaffold


def _codes(report):
    return {issue["code"] for issue in report["issues"]}


def _record(executor="worker-a", by="ci", **overrides):
    record = {
        "schema": "loop-engineer/evidence@1", "id": "e1", "kind": "verify-bundle",
        "uri": ".loop/artifacts/verify-iter5.json", "sha256": "c" * 64,
        "media_type": "application/json", "created_at": "2026-07-25T00:00:00+00:00",
        "produced_by": {"run_id": "run-1", "task_id": "T-1", "attempt": 1, "executor": executor},
        "verified_by": {"by": by, "at": "2026-07-25T00:00:00+00:00",
                        "command": "./scripts/verify-fast.sh",
                        "code_digest": "a" * 64, "code_digest_basis": "workspace_file",
                        "policy_digest": "b" * 64},
    }
    record.update(overrides)
    return record


def _ws(tmp_path, records=(), bundles=(), name="workspace"):
    target = tmp_path / name
    scaffold(target)
    if records:
        directory = target / ".loop" / "evidence"
        directory.mkdir(parents=True, exist_ok=True)
        for index, record in enumerate(records):
            text = record if isinstance(record, str) else json.dumps(record)
            (directory / f"evidence-iter{index}.json").write_text(text, encoding="utf-8")
    for bundle_name in bundles:
        directory = target / ".loop" / "artifacts"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / bundle_name).write_text(
            json.dumps({"outcome": "PASS", "passed": True}), encoding="utf-8")
    return target


def _tree(workspace):
    return {str(p.relative_to(workspace)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in workspace.rglob("*") if p.is_file()}


def test_absent_evidence_directory_is_a_byte_stable_no_op(tmp_path):
    target = _ws(tmp_path)
    assert doctor_report(target) == {**validate_contract(target), "event_store": {"present": False}}


def test_independent_verifier_identity_is_doctor_clean(tmp_path):
    report = doctor_report(_ws(tmp_path, [_record()], ["verify-iter0.json"]))
    assert report["ok"] is True, report["issues"]
    assert "loop-engineer/evidence@1" in report["schemas_checked"]


@pytest.mark.parametrize("mode", ["basic", "strict"])
def test_self_verified_evidence_fails_doctor(tmp_path, mode):
    if mode == "strict":
        pytest.importorskip("jsonschema")
    report = doctor_report(_ws(tmp_path, [_record(executor="worker-a", by="worker-a")]), mode=mode)
    assert report["ok"] is False and "self_verified_evidence" in _codes(report)


@pytest.mark.parametrize("mode", ["basic", "strict"])
def test_malformed_evidence_record_fails_doctor_rather_than_being_skipped(tmp_path, mode):
    if mode == "strict":
        pytest.importorskip("jsonschema")
    bad = _record()
    bad["verified_by"]["code_digest"] = "NOTHEX"
    report = doctor_report(_ws(tmp_path, [bad]), mode=mode)
    assert report["ok"] is False and "invalid_evidence" in _codes(report)


@pytest.mark.parametrize("mode", ["basic", "strict"])
def test_unparseable_evidence_json_fails_doctor(tmp_path, mode):
    if mode == "strict":
        pytest.importorskip("jsonschema")
    report = doctor_report(_ws(tmp_path, ["{not json"]), mode=mode)
    assert report["ok"] is False


def test_self_verification_detection_survives_case_and_whitespace_evasion(tmp_path):
    report = doctor_report(_ws(tmp_path, [_record(executor=" Worker-A ", by="worker-a")]))
    assert "self_verified_evidence" in _codes(report)


def test_finding_names_the_record_and_the_colliding_identity(tmp_path):
    report = doctor_report(_ws(tmp_path, [_record(executor="worker-a", by="worker-a")]))
    finding = next(i for i in report["issues"] if i["code"] == "self_verified_evidence")
    assert "evidence-iter0.json" in finding["message"] and "worker-a" in finding["message"]


def test_only_the_colliding_record_is_reported(tmp_path):
    """Two records, one collision — exactly one finding, naming the guilty file."""
    target = _ws(tmp_path, [_record(), _record(executor="solo", by="solo")],
                 ["verify-iter0.json", "verify-iter1.json"])
    findings = [i for i in doctor_report(target)["issues"] if i["code"] == "self_verified_evidence"]
    assert len(findings) == 1 and "evidence-iter1.json" in findings[0]["message"]


def test_null_verified_by_is_not_a_finding_in_this_slice(tmp_path):
    report = doctor_report(_ws(tmp_path, [_record(verified_by=None)], ["verify-iter0.json"]))
    assert report["ok"] is True, report["issues"]


def test_a_bundle_whose_record_was_deleted_is_reported(tmp_path):
    """The residue tripwire, mirroring §22's missing_event_store."""
    report = doctor_report(_ws(tmp_path, bundles=["verify-iter5.json"]))
    assert report["ok"] is False and "missing_evidence_record" in _codes(report)


def test_neither_bundle_nor_record_is_clean(tmp_path):
    """The negative control: absent-everything must stay byte-stable."""
    assert "missing_evidence_record" not in _codes(doctor_report(_ws(tmp_path)))


def test_legacy_bundle_names_never_trip_the_orphan_tripwire(tmp_path):
    """Shipped examples use verify-T1.json / verify-T1-iter1.json — not the runner's
    verify-iter<N>.json — and must stay doctor-clean."""
    target = _ws(tmp_path, bundles=["verify-T1.json", "verify-T1-iter1.json"])
    assert "missing_evidence_record" not in _codes(doctor_report(target))


def test_doctor_evidence_scan_writes_nothing(tmp_path):
    target = _ws(tmp_path, [_record()], ["verify-iter0.json"])
    before = _tree(target)
    doctor_report(target)
    assert _tree(target) == before
```

- [ ] **Step 2: Run it — expect failures**: `schemas_checked` lacks the evidence id, `self_verified_evidence` / `missing_evidence_record` never appear, malformed records pass silently.

- [ ] **Step 3: Register the schema id.** In `loop/contract.py`, **append** `("evidence", "loop-engineer/evidence@1")` as the **last** element of `_RECORD_SCHEMA_IDS` (line 564-568). Order is load-bearing: `validate_contract` (`contract.py:735-737`) preserves it in `schemas_checked`, and `scripts/test_contract_records.py:151` asserts `schemas_checked[:4]`. **Do not** add an `_RECORD_SCHEMA_FILES` entry — `_validate_record` is that dict's only consumer and discovery uses `evidence_issues`, so an entry would be dead config.

- [ ] **Step 4: Implement the helpers** in `loop/contract.py`. Three imports must be added at the top — verified absent from the current header (`loop/contract.py:1-14` imports only `json`, `Path`, `Any`, `fsm`, `completion`, `paths`): `import re`, `from typing import Any, Mapping`, and `from .paths import ARTIFACTS_DIR_NAME, EVIDENCE_DIR_NAME, LoopPaths, resolve_loop_paths`.

```python
_RUNNER_BUNDLE_RE = re.compile(r"verify-iter(\d+)\.json")


def _self_verified(record: Mapping[str, Any]) -> bool:
    """True when a record DECLARES that its producer also verified it.

    Comparison is strip+casefold: it closes trivial case evasion with no realistic
    false positive. A genuine rename still evades — this surfaces DECLARED
    self-verification, it does not prove independence
    (reference/safety-and-approvals.md §5).
    """
    produced_by, verified_by = record.get("produced_by"), record.get("verified_by")
    if not isinstance(produced_by, dict) or not isinstance(verified_by, dict):
        return False
    executor, verifier = produced_by.get("executor"), verified_by.get("by")
    if not isinstance(executor, str) or not isinstance(verifier, str):
        return False
    normalized = executor.strip().casefold()
    return bool(normalized) and normalized == verifier.strip().casefold()


def _orphan_bundle_issues(paths: LoopPaths, issues: list[dict]) -> None:
    """A runner-written bundle with no matching record is detectable residue.

    Mirrors the shipped `missing_event_store` tripwire (repo-os-contract §22): the
    check fires ONLY when a bundle is present, so absent-everything stays
    byte-identical. Scoped to the runner's own `verify-iter<N>.json` name, so the
    shipped example bundles (`verify-T1.json`, `verify-T1-iter1.json`) never trip it.
    Deleting BOTH files remains undetectable — the honest residual, pinned by name.
    """
    artifacts_dir = paths.loop_dir / ARTIFACTS_DIR_NAME
    if not artifacts_dir.is_dir():
        return
    for bundle_path in sorted(artifacts_dir.glob("verify-iter*.json")):
        match = _RUNNER_BUNDLE_RE.fullmatch(bundle_path.name)
        if match is None:
            continue
        record_path = paths.loop_dir / EVIDENCE_DIR_NAME / f"evidence-iter{match.group(1)}.json"
        if not record_path.is_file():
            issues.append(ContractIssue(
                "missing_evidence_record",
                f"{bundle_path.name} has no matching evidence record at "
                f".loop/{EVIDENCE_DIR_NAME}/{record_path.name} — the bundle's provenance "
                f"record is absent or was removed",
                bundle_path))


def _validate_evidence_records(paths: LoopPaths, mode: str, issues: list[dict]) -> bool:
    """Validate declared evidence@1 records and surface declared self-verification.

    Declared location: `.loop/evidence/*.json` (repo-os-contract.md §17). An absent
    directory is a no-op, so a contract with no evidence produces a byte-identical
    report — the same rule §22 pins for an absent event store.
    """
    from .evidence import evidence_issues  # local: loop.evidence imports this module

    _orphan_bundle_issues(paths, issues)
    evidence_dir = paths.loop_dir / EVIDENCE_DIR_NAME
    if not evidence_dir.is_dir():
        return False
    checked = False
    for record_path in sorted(evidence_dir.glob("*.json")):
        data = _read_json(record_path, issues)
        if data is None:
            continue
        checked = True
        for issue in evidence_issues(data, resolved_mode=mode):
            issues.append(ContractIssue(issue["code"], f"{record_path.name}: {issue['message']}", record_path))
        if _self_verified(data):
            issues.append(ContractIssue(
                "self_verified_evidence",
                f"{record_path.name}: produced_by.executor == verified_by.by "
                f"({data['produced_by']['executor']!r}) — the producer declares it verified its own work",
                record_path))
    return checked
```

- [ ] **Step 5: Wire it in** — in `_validate_optional_records`, after the receipts block and before `return checked`:

```python
    if _validate_evidence_records(paths, mode, issues):
        checked.add("evidence")
```

- [ ] **Step 6: Run the gate.** `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_doctor_evidence.py scripts/test_doctor_eventstore.py scripts/test_loop_contract_core.py scripts/test_contract_records.py` — expect **16 collected** in the new file (13 names, 3 parametrized ×2) and **zero** changes in the three existing files; `test_absent_event_store_matches_pre_slice_doctor_shape` must pass unmodified.
- [ ] **Step 7: Dogfood check.** `uv run --with pyyaml python3 -B -m loop doctor examples/coverage-repair` and `... examples/flaky-test-triage` — both must stay clean, proving `test_legacy_bundle_names_never_trip_the_orphan_tripwire` reflects the shipped trees.
- [ ] **Step 8:** Commit: `feat(doctor): discover evidence@1 records, fail on declared self-verification and orphaned bundles`.

**Acceptance:** +16 passed extras / +13 passed +3 skipped pyyaml-only. `scripts/test_doctor_eventstore.py`, `scripts/test_loop_contract_core.py` and `scripts/test_contract_records.py` are byte-unmodified. Both dogfood examples stay doctor-clean.

---

### Task 6: Adversarial + honest-limitation pins

**Files:** Create `scripts/test_adversarial_verifier_identity.py`.

Every pinned limitation asserts the **honest** outcome of a real attack **and contains its own positive control** — the finding must be shown to fire before the evasion is applied — so deleting the detector fails the pin instead of silently satisfying it.

- [ ] **Step 1: Write the tests:**

```python
"""Adversarial coverage: what verifier identity DOES and DOES NOT catch.

The claim this file defends is "surfaces DECLARED self-verification", never
"proves independence". Each *_pinned test first proves the detector fires, then
applies the evasion and proves it does not — so a deleted detector fails here.
"""
from __future__ import annotations

import hashlib
import json

from loop import emit
from loop.contract import doctor_report
from loop.evidence import verify_evidence
from loop.verifier import (executed_verifier_identity, injected_verifier_identity,
                           verification_policy_digest, verifier_code_digest)


def _task(**overrides):
    base = {"id": "T-1", "title": "t", "status": "pending", "criterion_ref": "C-1",
            "verify": "./scripts/verify-fast.sh", "depends_on": [], "attempts": 0, "evidence": None}
    base.update(overrides)
    return base


def _ws(tmp_path):
    workspace = tmp_path / "workspace"
    emit.open_contract(workspace)
    script = workspace / "scripts" / "verify-fast.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    return workspace


def _write(workspace, *, iteration_id=1, task=None, passed=True, **kwargs):
    task = task or _task()
    kwargs.setdefault("code_identity",
                      executed_verifier_identity(task["verify"], workspace))
    return emit.write_verify_evidence(workspace, run_id="run-1", iteration_id=iteration_id,
                                      task=task, passed=passed, **kwargs)


def _codes(report):
    return {issue["code"] for issue in report["issues"]}


# --- pinned honest limitations -------------------------------------------------

def test_disguised_verifier_identity_is_not_detected_pinned(tmp_path):
    """A worker that self-verifies but WRITES a different verifier name is not caught."""
    workspace = _ws(tmp_path)
    _write(workspace, iteration_id=1, executor="worker-a", verifier_identity="worker-a")
    assert "self_verified_evidence" in _codes(doctor_report(workspace))   # control: it fires
    _write(workspace, iteration_id=1, executor="worker-a", verifier_identity="ci")
    assert "self_verified_evidence" not in _codes(doctor_report(workspace))


def test_unattributed_executor_never_trips_the_finding_pinned(tmp_path):
    """Omitting --executor evades the check; attribution is the caller's to supply."""
    workspace = _ws(tmp_path)
    _write(workspace, iteration_id=1, executor="loop.run")
    assert "self_verified_evidence" in _codes(doctor_report(workspace))   # control: it fires
    _write(workspace, iteration_id=1)                                    # default: unattributed
    assert "self_verified_evidence" not in _codes(doctor_report(workspace))


def test_deleting_both_bundle_and_record_leaves_doctor_clean_pinned(tmp_path):
    """Deleting the RECORD alone is caught (missing_evidence_record). Deleting the
    PAIR is not: nothing outside the event log remembers the dispatch happened.
    Slice 3 closes this by making Succeeded require hash-verified evidence.
    """
    workspace = _ws(tmp_path)
    written = _write(workspace, executor="w", verifier_identity="w")
    assert "self_verified_evidence" in _codes(doctor_report(workspace))   # control: it fires
    written["evidence"].unlink()
    assert "missing_evidence_record" in _codes(doctor_report(workspace))  # residue IS caught
    written["bundle"].unlink()
    assert doctor_report(workspace)["ok"] is True                         # the pair is not


def test_rewriting_the_evidence_record_to_independent_identities_leaves_doctor_clean_pinned(tmp_path):
    """The record is a plain file OUTSIDE the hash chain. A worker with write access
    to .loop/ can rewrite it after the fact and doctor will not notice. Binding the
    record digest into the chain is Slice 3.
    """
    workspace = _ws(tmp_path)
    written = _write(workspace, executor="solo", verifier_identity="solo")
    assert "self_verified_evidence" in _codes(doctor_report(workspace))   # control: it fires
    record = json.loads(written["evidence"].read_text(encoding="utf-8"))
    record["verified_by"]["by"] = "ci"
    written["evidence"].write_text(json.dumps(record), encoding="utf-8")
    assert doctor_report(workspace)["ok"] is True


def test_hand_written_record_with_a_fabricated_code_digest_is_doctor_clean_pinned(tmp_path):
    """Digests are values the WRITER asserts. Doctor validates their shape, never
    their truth — a hand-written record is indistinguishable from a runner-written one.
    """
    workspace = _ws(tmp_path)
    written = _write(workspace)
    record = json.loads(written["evidence"].read_text(encoding="utf-8"))
    record["verified_by"]["code_digest"] = "f" * 64
    record["verified_by"]["policy_digest"] = "e" * 64
    written["evidence"].write_text(json.dumps(record), encoding="utf-8")
    assert doctor_report(workspace)["ok"] is True


def test_no_automated_digest_comparison_exists_pinned(tmp_path):
    """Two records for the same task with DIFFERENT policy digests: doctor is silent.
    Nothing in this release compares a recorded digest against anything.
    """
    workspace = _ws(tmp_path)
    _write(workspace, iteration_id=1, task=_task())
    _write(workspace, iteration_id=2, task=_task(verify="true"))
    digests = {json.loads((workspace / ".loop" / "evidence" / f"evidence-iter{n}.json")
                          .read_text(encoding="utf-8"))["verified_by"]["policy_digest"]
               for n in (1, 2)}
    assert len(digests) == 2                       # the goalpost demonstrably moved
    assert doctor_report(workspace)["ok"] is True  # and nothing surfaced it


def test_doctor_does_not_hash_verify_the_referenced_bundle_pinned(tmp_path):
    """Slice 2 checks structure, declared independence, and record presence only."""
    workspace = _ws(tmp_path)
    written = _write(workspace, passed=False)
    written["bundle"].write_text(json.dumps({"outcome": "PASS", "passed": True}), encoding="utf-8")
    assert doctor_report(workspace)["ok"] is True


def test_code_digest_is_null_for_the_common_python_m_pytest_command_pinned(tmp_path):
    """The most common real verify command has no hashable workspace script."""
    assert verifier_code_digest("python3 -m pytest -q", tmp_path) == (None, "path_lookup")


def test_recorded_digests_do_not_change_when_the_verifier_file_changes_afterwards_pinned(tmp_path):
    """A digest is a record of one moment, not a live guard."""
    workspace = _ws(tmp_path)
    written = _write(workspace)
    recorded = json.loads(written["evidence"].read_text())["verified_by"]["code_digest"]
    (workspace / "scripts" / "verify-fast.sh").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    assert json.loads(written["evidence"].read_text())["verified_by"]["code_digest"] == recorded
    assert doctor_report(workspace)["ok"] is True


def test_a_misspelled_holdout_field_is_silently_undeclared_pinned(tmp_path):
    """tasks@1 is additionalProperties:true, so `holdout_critera` validates and yields
    declared:false with an empty holdout — indistinguishable from "none declared".
    """
    workspace = _ws(tmp_path)
    written = _write(workspace, task=_task(holdout_critera=["C-9"]))
    partition = json.loads(written["bundle"].read_text(encoding="utf-8"))["partition"]
    assert partition == {"visible": ["C-1"], "holdout": [],
                         "declared": False, "holdout_executed": False}


# --- real detections -----------------------------------------------------------

def test_moving_the_goalpost_changes_the_policy_digest(tmp_path):
    assert verification_policy_digest(_task()) != verification_policy_digest(_task(verify="true"))
    assert verification_policy_digest(_task()) == verification_policy_digest(_task(attempts=9, status="done"))


def test_swapping_the_verifier_script_changes_the_code_digest(tmp_path):
    workspace = _ws(tmp_path)
    first, _ = verifier_code_digest("./scripts/verify-fast.sh", workspace)
    (workspace / "scripts" / "verify-fast.sh").write_text("#!/bin/sh\nexit 0\n# tampered\n", encoding="utf-8")
    second, basis = verifier_code_digest("./scripts/verify-fast.sh", workspace)
    assert basis == "workspace_file" and first != second


def test_swapping_the_bundle_breaks_the_records_committed_digest(tmp_path):
    workspace = _ws(tmp_path)
    written = _write(workspace, passed=False)
    written["bundle"].write_text(json.dumps({"outcome": "PASS", "passed": True}), encoding="utf-8")
    record = json.loads(written["evidence"].read_text())
    result = verify_evidence(record, workspace_root=workspace)
    assert result["ok"] is False and result["issues"][0]["code"] == "hash_mismatch"
    assert record["sha256"] != hashlib.sha256(written["bundle"].read_bytes()).hexdigest()
```

- [ ] **Step 2: Run the gate.** `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_adversarial_verifier_identity.py` — expect **13 passed**.
- [ ] **Step 3: Prove the pins are non-vacuous — deterministic mutation probe, not a manual observation.** Stub the detector, re-run, revert, and record the exact kill counts in the PR body:

```bash
bash -c "cd /mnt/c/Dev/projects/loop-engineer && \
  python3 - <<'PY'
import pathlib
p = pathlib.Path('loop/contract.py'); s = p.read_text(encoding='utf-8')
p.write_text(s.replace('    produced_by, verified_by = record.get',
                       '    return False\n    produced_by, verified_by = record.get', 1), encoding='utf-8')
PY
  uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider \
    scripts/test_adversarial_verifier_identity.py scripts/test_doctor_evidence.py; \
  git checkout -- loop/contract.py"
```

  Expected kill count with `_self_verified` stubbed to `False`: **4 failures** in `test_adversarial_verifier_identity.py` (the four pins whose positive control asserts the finding fires) and **5** in `test_doctor_evidence.py` (`self_verified_evidence` ×2 parametrized, case-evasion, finding-names, only-the-colliding-record) = **9 total**. A mutation that kills fewer than 9 means a pin lost its control; a mutation that kills 0 means the file is decorative. Repeat with `_orphan_bundle_issues` short-circuited to `return`: expected **2 failures** (`test_a_bundle_whose_record_was_deleted_is_reported`, `test_deleting_both_bundle_and_record_leaves_doctor_clean_pinned`). Confirm `git status` is clean afterwards.

- [ ] **Step 4:** Commit: `test(adversarial): pin what verifier identity does and does not catch`.

**Acceptance:** 13 passed in both dependency sets; every `_pinned` name carries a docstring stating the honest limitation in one sentence; the two mutation probes kill exactly 9 and 2 respectively, recorded in the PR body.

---

### Task 7: Docs — declared locations, normative identity section, doctor codes, README

**Files:** Modify `reference/repo-os-contract.md` (§1, §17, §22), `reference/safety-and-approvals.md` (§5), `README.md`; extend `scripts/test_verifier_identity.py` and `scripts/test_conformance.py`.

No new file in `reference/` (structural.json pins the 8-filename list at `evals/cases/structural.json`).

- [ ] **Step 1: §1 tree** (`reference/repo-os-contract.md:66-74`) — add three lines under `.loop/`, keeping the existing comment alignment style. Note `artifacts/` is already listed at line 70 and the bundle lives **there**; `repair/` and `receipts/` are added because `_validate_optional_records` already scans them and the tree does not list them (making decision 7's "declared peers" true):

```
    repair/           # repair@1 records — scanned by doctor when present
    receipts/         # receipt@1 ledgers (*.jsonl) — scanned by doctor when present
    evidence/         # evidence@1 records — the declared location doctor scans (§17)
```

- [ ] **Step 2: §17 — the four fields and the honesty rule.** Open a `### Verifier identity (v0.11.0+)` subsection with:
  1. The four additive `verified_by` fields (`command`, `code_digest`, `code_digest_basis`, `policy_digest`), all optional and nullable; `required` stays `["by","at"]`; both validation modes type-check them identically.
  2. The **code-digest honesty rule** with the nine-basis table copied verbatim from decision 1 of this plan, plus: *"`python3 -m pytest -q` has no hashable workspace script; `null` with basis `path_lookup` is the truthful record, and a fabricated digest would be worse than none. When a caller injects a verifier callable the declared command does not run at all: `command` and `code_digest` are `null` with basis `injected_verifier`."* State that these nine values co-move across four surfaces (`CODE_DIGEST_BASES`, the schema `enum`, the structural-fallback check, this table).

- [ ] **Step 3: §17 — the policy digest and its machine-pinned vector.**
  1. Definition: sha256 over `loop.chain.canonical_json` of `{criterion_ref, depends_on, id, verify}` from the TASKS.json entry, with the exclusion rationale (run state is not policy) and the inclusion rationale (`id` binds *which* goalpost; `depends_on` binds declared ordering).
  2. One sentence on the boundary: *"The digest binds the criterion **reference**, not the criterion **text** — editing `SPEC.md`'s acceptance wording leaves it unchanged. Binding criterion text is the evidence-wiring slice."*
  3. **Generate** the conformance vector: run `verification_policy_digest` over the literal task entry below and paste the literal canonical JSON and 64-hex digest into the doc **and** into `scripts/test_conformance.py` (Step 6) — same literal in both places.

```python
{"id": "T-1", "title": "ignored", "status": "pending", "criterion_ref": "C-1",
 "verify": "./scripts/verify-fast.sh", "depends_on": [], "attempts": 0, "evidence": None}
```

- [ ] **Step 4: §17 — bundle/record pair, partition, independence rule.**
  1. The **bundle/record pair**: `.loop/artifacts/verify-iter<N>.json` (the artifact; carries `outcome`/`passed` per the metrics green-marker convention, `verifier` incl. `source`, and `partition`) and `.loop/evidence/evidence-iter<N>.json` (evidence@1; commits to the bundle bytes via `sha256`). State the naming rule normatively: *"an evidence record MUST NOT be named `verify-*.json` — a record in the bundle namespace is read by metrics as a bundle with no green marker, i.e. a phantom failing gate."* State the gate-evidence rule: *"`verifier.source` is `declared_command` only when the task's declared `verify` command was executed. A bundle whose source is `injected_callable` carries a caller-supplied verdict and is not gate evidence."* Add the simulate asymmetry note: *"`loop simulate` predicts decisions, not writes: it reports `legacy_sync_would_write` because that write is conditional, but it does not enumerate the bundle and record a dispatch always writes."*
  2. The **partition** semantics: `visible` defaults to the task's `criterion_ref`; `holdout` is empty unless the task declares `holdout_criteria`; both fields are optional `array of string` on tasks@1; `holdout_executed` is always `false` because the runner executes exactly the declared `verify` command. Running a holdout set remains `scripts/holdout_gate.py`'s job and its verdict keeps its own canonical shape. State plainly: *"a misspelled field name validates (tasks@1 is `additionalProperties: true`) and yields `declared: false` — an undeclared partition and a mistyped one are indistinguishable."*
  3. The **independence rule**: *"A record whose `produced_by.executor` equals its `verified_by.by` (compared strip+casefold) declares that the producer verified its own work. `loop doctor` reports `self_verified_evidence` and fails. On the `loop run` path both identities are operator-supplied (`--executor`, `--verifier-identity`); their defaults (`unattributed`, `loop.run`) never collide, so a default run cannot manufacture the finding."*

- [ ] **Step 5: §17 — the integrity boundary, in three honest tiers.** In the Slice-1 voice, and **not** as a single "Surfaces / Does not surface" pair:

  - **Fails `loop doctor`:** a record declaring self-verification (`self_verified_evidence`); a runner-written bundle whose record is absent (`missing_evidence_record`); a malformed or unparseable record (`invalid_evidence` — an errored check fails, it never skips).
  - **Recorded for later comparison, not checked by any shipped surface:** `policy_digest` and `code_digest`. Nothing in v0.11.0 compares either against the live TASKS.json entry or re-hashes the verifier file, so a moved goalpost or a swapped verify script is *legible in a diff of two records* and nothing more. Automated comparison is the evidence-wiring slice.
  - **Detectable only by explicitly calling `verify_evidence()`:** a swapped bundle. `loop doctor` does not hash-verify referenced artifacts in this release.
  - **Not surfaced at all:** a worker that writes a false `verified_by.by`; a worker that omits its executor identity; a hand-written record whose digests are invented (doctor validates their *shape*, never their truth); a rewrite or deletion of the record **and** its bundle together. **Both artifacts are plain files outside the hash chain: a worker with write access to `.loop/` can rewrite or remove them and `loop doctor` will not notice.** Binding the record digest into the chain requires a new event type and is the evidence-wiring slice.
  - Close with: *"This does not prove independence. It surfaces **declared** self-verification, and it records — honestly, with nulls where the process could not know — what verified the work."* The phrase "recorded forgery" is forbidden: nothing here is recorded immutably.

- [ ] **Step 6: §17 — replace the stale scope-boundary paragraph** (`reference/repo-os-contract.md:824-827`), which currently says evidence@1 *"is not yet an artifact `loop doctor` reads from a scaffolded workspace"* — now false. Replace with: *"`loop doctor` reads evidence@1 records from the declared location `.loop/evidence/*.json` and validates them; it does **not** yet hash-verify the artifacts they reference, does **not** compare any recorded digest against anything, and `Succeeded` still requires non-empty evidence *paths*, not verified hashes. Those tightenings are the next slice."*

- [ ] **Step 7: §22 additions** — one paragraph plus two issue-code rows, matching the existing table style at `reference/repo-os-contract.md:984-989`:

```
| `self_verified_evidence` | A discovered evidence@1 record declares `produced_by.executor == verified_by.by` (strip+casefold) — the producer verified its own work. Enforces the independence rule of `reference/safety-and-approvals.md` §5, which was prose-only before v0.11.0. |
| `missing_evidence_record` | A runner-written verify bundle `.loop/artifacts/verify-iter<N>.json` exists with no matching `.loop/evidence/evidence-iter<N>.json`. Residue of a removed provenance record, in the same family as `missing_event_store`. Fires only when a bundle is present, so an absent-everything contract stays byte-identical. |
```

  The paragraph states: doctor scans `.loop/evidence/*.json` when the directory exists; an absent directory with no runner bundle is a no-op that leaves every doctor key byte-identical (no new top-level key was added); a malformed or unparseable record **fails** doctor rather than being skipped; and `loop-engineer/evidence@1` joins `schemas_checked` when at least one record was read.

- [ ] **Step 8: `reference/safety-and-approvals.md` §5** — after the sentence at line 97, add: *"Since v0.11.0 this invariant has a machine check: `loop doctor` reports `self_verified_evidence` when an evidence@1 record declares that its producer also verified it (`reference/repo-os-contract.md` §17). The check surfaces *declared* self-verification — a worker that writes a false verifier name, or that rewrites the record afterwards, is not caught, which is why the protected-file and canary rules above remain load-bearing."*

- [ ] **Step 9: README** (version surfaces are Task 9) — extend the event-sourced-runtime bullet (`README.md:24-28`) with one sentence: *"verify runs record which verifier actually ran — command, code digest, policy digest — and `loop doctor` fails when a record declares that its own producer verified it"* plus one honest clause: *"identity is recorded, not proven: a worker can write a false verifier name, and the records live outside the hash chain."* Do **not** touch the "how it compares" heading or the FCR/RP markers (`structural.json` `readme_differentiation` pins them).

- [ ] **Step 10: Pin the conformance vector** — append to `scripts/test_conformance.py`, next to the Slice-1 chain vectors (this file is the repo's declared home for machine-pinned normative vectors):

```python
from loop.verifier import verification_policy, verification_policy_digest

_POLICY_VECTOR_TASK = {"id": "T-1", "title": "ignored", "status": "pending", "criterion_ref": "C-1",
                       "verify": "./scripts/verify-fast.sh", "depends_on": [], "attempts": 0,
                       "evidence": None}
_POLICY_VECTOR_CANONICAL = "<paste canonical_json(verification_policy(_POLICY_VECTOR_TASK))>"
_POLICY_VECTOR_DIGEST = "<paste verification_policy_digest(_POLICY_VECTOR_TASK)>"


def test_documented_policy_digest_vector_matches_the_implementation():
    from loop.chain import canonical_json
    assert canonical_json(verification_policy(_POLICY_VECTOR_TASK)) == _POLICY_VECTOR_CANONICAL
    assert verification_policy_digest(_POLICY_VECTOR_TASK) == _POLICY_VECTOR_DIGEST
    doc = (Path(__file__).resolve().parent.parent / "reference" / "repo-os-contract.md").read_text(encoding="utf-8")
    assert _POLICY_VECTOR_DIGEST in doc and _POLICY_VECTOR_CANONICAL in doc
```

- [ ] **Step 11: Pin the docs and the retired claims** — append to `scripts/test_verifier_identity.py`:

```python
_ROOT = Path(__file__).resolve().parent.parent
_DOC = _ROOT / "reference" / "repo-os-contract.md"
_SAFETY = _ROOT / "reference" / "safety-and-approvals.md"


def test_every_code_digest_basis_is_documented_and_in_the_schema():
    """The nine values co-move across four surfaces; two of them are pinned here."""
    import json as _json
    text = _DOC.read_text(encoding="utf-8")
    schema = _json.loads((_ROOT / "schemas" / "evidence.schema.json").read_text(encoding="utf-8"))
    enum = schema["properties"]["verified_by"]["properties"]["code_digest_basis"]["enum"]
    assert all(basis in text for basis in CODE_DIGEST_BASES)
    assert set(CODE_DIGEST_BASES) | {None} == set(enum)


def test_safety_reference_names_the_machine_check():
    assert "self_verified_evidence" in _SAFETY.read_text(encoding="utf-8")


def test_no_shipped_surface_still_claims_evidence_is_unread():
    """Task 5 makes both claims false; nothing may still ship them."""
    for path in (_ROOT / "loop" / "evidence.py", _ROOT / "schemas" / "evidence.schema.json"):
        text = path.read_text(encoding="utf-8")
        assert "standalone in v1" not in text and "not yet read by" not in text
```

- [ ] **Step 12: Run the gates.** `uv run --with pyyaml python3 -B scripts/self_eval.py` (**13/13** — proves no pin was disturbed), `uv run --with pyyaml python3 -B scripts/validate_frontmatter.py` (**9/9**), and `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_verifier_identity.py scripts/test_conformance.py scripts/test_docs_adoption.py scripts/test_docs_claims.py` — `test_verifier_identity.py` now **23 passed**, `test_conformance.py` **+1**.
- [ ] **Step 13:** Commit: `docs(contract): normative verifier identity, the independence rule, and its honest boundary`.

**Acceptance:** +4 passed in both sets (3 in `test_verifier_identity.py`, 1 in `test_conformance.py`); self_eval 13/13; the conformance digest **and** its canonical JSON appear in both the test and `reference/repo-os-contract.md`; the §17 boundary has three tiers and contains neither the word "forgery" nor any "proves independence" phrasing.

---

### Task 8: Full-suite gate + feature PR

**Files:** none new.

- [ ] **Step 1: Extras suite.** `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts` — expect `BASE_EXTRAS.passed + 92` passed, `BASE_EXTRAS.skipped` skipped.
- [ ] **Step 2: Fallback suite.** `uv run --with pyyaml --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts` — expect `BASE_FALLBACK.passed + 82` passed, `BASE_FALLBACK.skipped + 10` skipped.

| Task | new collected tests | jsonschema halves (skip in fallback) |
|---|---|---|
| 1 | 20 | 0 |
| 2 | 13 | 6 |
| 3 | 15 | 1 |
| 4 | 11 | 0 |
| 5 | 16 | 3 |
| 6 | 13 | 0 |
| 7 | 4 | 0 |
| **total** | **92** | **10** |

  Arithmetic check the implementer must reproduce: 20+13+15+11+16+13+4 = **92**; 92 − 10 = **82** fallback passes. Every row is the count of *collected items* (a `parametrize(["basic","strict"])` test contributes 2), re-derived from the literal test bodies in each task, not from prose.

- [ ] **Step 3: Fresh-worktree verification.** Point the detached baseline worktree at the feature head and re-run both suites there — the live checkout reads +2/−2: `git -C /mnt/c/Dev/projects/loop-engineer/.tmp/s2-base checkout --detach feat/verifier-identity`, then Steps 1-2's commands against `/mnt/c/Dev/projects/loop-engineer/.tmp/s2-base/scripts`. Record both numbers with their dependency sets as the PR-body baselines. Then `git -C /mnt/c/Dev/projects/loop-engineer worktree remove /mnt/c/Dev/projects/loop-engineer/.tmp/s2-base`.
- [ ] **Step 4: Zero-regression spot checks.** `scripts/test_doctor_eventstore.py`, `scripts/test_loop_simulate_zero_writes.py`, `scripts/test_loop_simulate_cli.py`, `scripts/test_adversarial_process.py`, `scripts/test_metrics.py`, `scripts/test_contract_records.py` must be green **and** byte-unmodified in `git diff --stat`.
- [ ] **Step 5: Dogfood.** `loop doctor` clean on `examples/coverage-repair` and `examples/flaky-test-triage`; `loop inspect` scores unchanged.
- [ ] **Step 6: Late-landing check.** If any of issues #81/#85/#86/#87 landed during execution, `git -C ... rebase origin/main`, re-run Steps 1-3, and restate the baselines. (At planning time none had a PR; do not block on them.)
- [ ] **Step 7:** Push and open the PR **non-draft** (single `opened` event — the CI-wedge lesson): `feat(kernel): verifier identity + declared-independence doctor gate (v0.11.0, slice 2/5)`. Body carries the three-tier integrity boundary verbatim, the Task-6 Step-3 mutation-probe kill counts, both fresh-worktree baselines with their dependency sets named, and the behavior matrix below. Required checks + auto-merge per the repo ruleset.
- [ ] **Step 8:** Any count mismatch in either direction at Steps 1-2 is a **stop-and-explain**, not a number to adjust: re-derive the offending file's collected count and reconcile against the table before touching the acceptance line.

**Behavior matrix — each row names the test that proves it** (rows that merely restate a Task acceptance line have been removed; these are the ones a reviewer cannot infer):

| Situation | Surface | Expected | Test |
|---|---|---|---|
| no `.loop/evidence/`, no runner bundle | doctor | byte-identical to `validate_contract` + `event_store` | `test_absent_evidence_directory_is_a_byte_stable_no_op` |
| record, executor == verifier | doctor (both modes) | hard fail `self_verified_evidence` | `test_self_verified_evidence_fails_doctor` |
| record, case/whitespace evasion | doctor | hard fail `self_verified_evidence` | `test_self_verification_detection_survives_case_and_whitespace_evasion` |
| record, disguised verifier name | doctor | **no finding** (pinned, with control) | `test_disguised_verifier_identity_is_not_detected_pinned` |
| record rewritten after the fact | doctor | **no finding** — artifacts are outside the chain (pinned) | `test_rewriting_the_evidence_record_to_independent_identities_leaves_doctor_clean_pinned` |
| hand-written record, invented digests | doctor | `ok` — shape is checked, truth is not (pinned) | `test_hand_written_record_with_a_fabricated_code_digest_is_doctor_clean_pinned` |
| two records, different `policy_digest` | doctor | `ok` — no automated comparison exists (pinned) | `test_no_automated_digest_comparison_exists_pinned` |
| bundle present, record deleted | doctor | hard fail `missing_evidence_record` | `test_a_bundle_whose_record_was_deleted_is_reported` |
| bundle **and** record deleted | doctor | `ok` (pinned residual; Slice 3) | `test_deleting_both_bundle_and_record_leaves_doctor_clean_pinned` |
| legacy `verify-T1.json` bundles | doctor | `ok` — shipped examples unaffected | `test_legacy_bundle_names_never_trip_the_orphan_tripwire` |
| bundle swapped for a green one | doctor / `verify_evidence` | `ok` (pinned) / `hash_mismatch` | `test_doctor_does_not_hash_verify_the_referenced_bundle_pinned`, `test_swapping_the_bundle_breaks_the_records_committed_digest` |
| declared command executed | dispatch | real `code_digest`, basis `workspace_file`, source `declared_command` | `test_dispatch_with_the_declared_verifier_records_a_workspace_file_digest` |
| verifier callable injected | dispatch | `command`/`digest` null, basis `injected_verifier`, source `injected_callable` | `test_dispatch_with_an_injected_verifier_records_no_fabricated_identity` |
| `python3 -m pytest -q` | digest | `null` + `path_lookup` (pinned) | `test_code_digest_is_null_for_the_common_python_m_pytest_command_pinned` |
| resolution raises `OSError` | digest | `null` + `unresolvable`, never `not_a_file` | `test_code_digest_says_unresolvable_when_resolution_raises` |
| repeated dispatch of one task | record | `attempt` counts durable prior iterations | `test_attempt_counts_durable_prior_iterations_for_this_task` |
| caller supplies no attempt | record | `attempt: null`, never `attempts + 1` | `test_attempt_is_null_when_the_caller_supplies_none` |
| `id` rename / `depends_on` reorder | policy digest | changes (intentional identity binding) | `test_policy_digest_changes_when_the_task_id_changes`, `..._depends_on_is_reordered` |
| misspelled `holdout_critera` | bundle | `declared: false`, empty holdout (pinned) | `test_a_misspelled_holdout_field_is_silently_undeclared_pinned` |
| bundle vs metrics readers | metrics | 1 bundle, 0 gate verdicts | `test_metrics_sees_exactly_one_bundle_and_no_gate_verdict` |
| record write fails mid-writer | writer | no metrics-visible bundle left behind | `test_a_failed_record_write_leaves_no_metrics_visible_bundle` |
| `NaN` in TASKS.json | writer | typed `EmitError`, never bare `ChainHashError` | `test_a_non_canonicalizable_task_raises_a_typed_emit_error` |
| crash before the iteration commit | dispatch | byte-identical tree (unchanged pin) | `test_crash_injection_before_iteration_event_commit_leaves_no_partial_dispatch` |
| evidence write fails post-commit | dispatch | typed `RunnerError`, event durable | `test_evidence_write_failure_after_a_committed_event_is_loud` |
| `--executor X --verifier-identity X` | CLI → doctor | the finding IS reachable on the kernel path | `test_run_cli_verifier_identity_makes_the_finding_reachable` |
| identity flags on other verbs | CLI | exit 2, nothing created | `test_identity_flags_are_rejected_on_other_commands_and_create_nothing` |
| `--help` usage line | CLI | byte-unchanged; flags in `options:` | `test_run_command_listed_in_help_and_usage` (unmodified), `test_run_help_documents_the_identity_flags` |

---

### Task 9: Release cut v0.11.0 (separate PR, after Task 8 merges) — OPERATOR-GATED

**Files:** Modify `pyproject.toml`, `.claude-plugin/plugin.json`, `README.md`, `scripts/test_docs_version.py`, `CHANGELOG.md`.

- [ ] **Step 1:** Branch `release/v0.11.0` off updated main; bump `version = "0.11.0"` in pyproject and plugin.json.
- [ ] **Step 2: README version surfaces** — the release badge, the documented action pin (`SollanSystems/loop-engineer@v0.10.0` → `@v0.11.0`), and the release/tag table rows.
- [ ] **Step 3:** `scripts/test_docs_version.py`: retarget the version pin to `"0.11.0"` and add `"## 0.11.0"` to the CHANGELOG-headings assertions (the badge and action-pin assertions added at the v0.10.0 cut keep those surfaces machine-pinned).
- [ ] **Step 4: CHANGELOG `## 0.11.0`** — the four additive `verified_by` fields; the bundle/record pair and their declared locations; `--executor` / `--verifier-identity`; the new `self_verified_evidence` and `missing_evidence_record` doctor codes; the optional tasks@1 `visible_criteria`/`holdout_criteria`; and these explicit honesty notes: (a) identity is **recorded, not proven** — a disguised verifier name is not caught; (b) evidence records and verify bundles live **outside the hash chain**, so a worker with write access to `.loop/` can rewrite or delete the pair and doctor will not notice — the orphan-bundle tripwire catches only a half-deletion; (c) doctor does **not** hash-verify referenced bundles and does **not** compare any recorded digest against anything — a moved goalpost is legible in a diff of two records and nothing more; (d) `code_digest` is `null` for any verifier that is not a workspace file, including the common `python -m pytest` form and every injected-callable dispatch, and the basis field always says why. (b) and (c) tighten in the evidence-wiring slice.
- [ ] **Step 5: Gates.** Full suite in both dependency sets + `python3 -m loop --version` smoke + `self_eval` 13/13.
- [ ] **Step 6: Land.** PR, required checks, merge.
- [ ] **Step 7: Publish.** `git tag v0.11.0 <squash-sha> && git push origin v0.11.0` → PyPI publish; verify `uvx loop-engineer@0.11.0 inspect examples/coverage-repair` from a scratch clone.
- [ ] **Step 8: Refresh the harness.** `git archive HEAD | tar -x -C <cache-dir>`; `diff -rq` to verify; restart Claude Code.

**Acceptance:** tag published, PyPI funnel verified from a scratch clone, plugin cache `diff -rq` clean.

---

## Self-review

**Spec coverage vs the Slice-2 scope contract:**

| Scope item | Where |
|---|---|
| P10 `verified_by.code_digest` (additive, evidence@1 — not receipt@1) | Task 2 (schema + parity), Task 1 (computation) |
| P10 `verified_by.policy_digest` bound to a real object | decision 3 (TASKS.json goalpost subset), pinned four ways in Tasks 1 and 6 |
| P10 "the runner hashes the verifier it **ACTUALLY** executed" | decision 2 + Task 4 Step 3 (identity built pre-execution, from the branch that knows what will run); the injected path records nulls, pinned by `test_dispatch_with_an_injected_verifier_records_no_fabricated_identity` |
| P10 visible/held-out partition recorded in verify bundles | Task 1 `criterion_partition` + Task 3 bundle `partition` block; the declaration path exists on tasks@1 (Task 1 Step 4) so the partition is not vacuous |
| P12 `produced_by.executor == verified_by.by` ⇒ hard doctor finding | Task 5 `self_verified_evidence`; reachable on the kernel path via `--verifier-identity` (decision 10, `test_run_cli_verifier_identity_makes_the_finding_reachable`) |
| P12 enforces the prose-only invariant at `safety-and-approvals.md:97` | cited in Task 5 code comment, Task 7 Steps 4/8 |
| Declared discovery location, absent = byte-stable no-op | decision 7/8 + `test_absent_evidence_directory_is_a_byte_stable_no_op`, `test_neither_bundle_nor_record_is_clean` |
| Absent-directory-bypass adjudicated honestly + tightening documented | Task 5 `missing_evidence_record` (half-deletion caught), Task 6 `test_deleting_both_bundle_and_record_leaves_doctor_clean_pinned` (pair-deletion honestly not caught), Task 7 Steps 5/6, Task 9 Step 4(b) |
| Threat honesty as deliverable; "proves independence" forbidden | Global Constraints, decision 15, Task 6 module docstring + 10 pins, Task 7 Step 5's three tiers |
| Validation-mode parity | Task 2 (six parametrized), Task 5 (three parametrized) |
| Inherited global constraints (zero deps, @1, typed fail-loud, structural.json, no version bump in the feature PR, env quirks) | Global Constraints |
| Adversarial/honest-limitation task with proven non-vacuity | Task 6 (10 pins + 3 detections + two mutation probes with stated kill counts) |
| Docs task (repo-os-contract section + README one-liner) | Task 7 |
| Operator-gated release cut kept out of the feature PR | Task 9 |
| Baseline pinned to a real commit + concurrent-work note | Baseline paragraph (`91bf36a`; #81/#85/#86/#87 are open **issues**, no rebase gate), Task 0, Task 8 Step 6 |

Rejected items deliberately absent: no graph verbs/DSL, no HTTP API, no Neo4j/Qdrant, no Merkle, no local signing. Also deliberately absent, each with a named later slice: doctor hash-verification of bundles, automated `policy_digest` comparison, chain-binding of evidence artifacts, criterion-*text* binding, a `verify-bundle` schema file (decision 6), a `loop simulate` write-prediction field (decision 16), and any change to `loop/events.py`, `loop/reducer.py`, `loop/chain.py`, `action.yml`, or `ci.yml`.

**Placeholder scan:** grep for `TBD`, `TODO`, `similar to Task`, `add validation`, `...` in task bodies → two intentional fill-ins remain, both in Task 7 Step 10 (`_POLICY_VECTOR_CANONICAL`, `_POLICY_VECTOR_DIGEST`), which cannot be computed before `loop/verifier.py` exists and whose generation instruction is Task 7 Step 3.3. The `...` in the Task 4 Step 3 code block marks unchanged existing lines of `dispatch_once` and is labelled as such. Everything else is literal code or a literal command. Helper names in Task 4 (`_ws`, `_task`, `_pass`, `_cli`) are the **existing** helpers at `scripts/test_runner_dispatch.py:21-39` — read that file before appending.

**Type-consistency check:**
- `verifier_code_digest` returns `tuple[str | None, str]` in every branch; every basis it can return is in `CODE_DIGEST_BASES` (pinned by `test_every_returned_basis_is_a_declared_basis`). `injected_verifier` is the one member it never returns — it is produced only by `injected_verifier_identity()`.
- `executed_verifier_identity` / `injected_verifier_identity` return the same four keys (`command`, `code_digest`, `code_digest_basis`, `source`), so `write_verify_evidence` indexes `code_identity` without `.get()` defaults — a caller passing a foreign mapping fails loudly with `KeyError` rather than silently recording nulls.
- `verification_policy_digest` returns `str`, and **can** raise `ChainHashError`: `json.loads` accepts `NaN`/`Infinity` by default while `loop.chain.canonical_json` sets `allow_nan=False` (`loop/chain.py:30`), and `_load_tasks` (`loop/runner.py:110`) uses bare `json.loads`. The writer converts it to `EmitError` (Task 3 Step 3); the runner's existing `except (OSError, emit.EmitError)` then names the committed iteration. Pinned by `test_a_non_canonicalizable_task_raises_a_typed_emit_error`. *(This corrects the pre-review claim that the exception "cannot arise" — it can, and the counter-example was executed.)*
- `criterion_partition` always returns all four keys with `list[str]`, `list[str]`, `bool`, `False`.
- Schema/fallback agreement: `command` `str|null`; `code_digest`/`policy_digest` 64-hex-or-null (`_is_sha256_or_null` mirrors `pattern` + `["string","null"]`); `code_digest_basis` enum-or-null mirrors the schema `enum` including the literal `null` member — and `test_every_code_digest_basis_is_documented_and_in_the_schema` asserts set-equality between `CODE_DIGEST_BASES` and the enum so the two cannot drift.
- `emit.write_verify_evidence` returns `{"bundle": Path, "evidence": Path, "sha256": str}`; `dispatch_once` stringifies the path into its result dict (`"evidence": str`), consistent with the existing all-JSON-scalar result shape.
- `_self_verified` takes `Mapping[str, Any]` and returns `bool` with no exception path (every non-dict/non-str shape returns `False`; malformed records are already surfaced by `evidence_issues`).
- `_orphan_bundle_issues` returns `None` and appends only; it reads a directory that may not exist and returns early, so absent-everything is untouched.
- `_validate_evidence_records` returns `bool` matching the `checked.add(...)` convention of its three sibling blocks in `_validate_optional_records`.

**Open risks for the implementer:**
1. `dispatch_once`'s result dict gains an `"evidence"` key — grep for tests asserting the result dict by equality before Task 4 Step 7. `scripts/test_loop_simulate_cli.py:106` compares whole-dict only on the untouched `blocked` action, so it is safe; verify no other comparison is whole-dict.
2. Appending `("evidence", "loop-engineer/evidence@1")` to `_RECORD_SCHEMA_IDS` changes `schemas_checked` **only when records are present** and **only at the tail** — `scripts/test_contract_records.py:151` asserts `schemas_checked[:4]` and `:163` asserts full equality on a workspace with no record files, both of which appending preserves. Confirm no fixture happens to have `.loop/evidence/`.
3. `loop.evidence` importing `loop.verifier` (for `CODE_DIGEST_BASES`), `loop.emit` importing `loop.verifier` + `loop.paths` + `loop.chain`, and `loop.contract` lazily importing `loop.evidence` must all be verified with `python3 -c "import loop.contract, loop.evidence, loop.emit, loop.runner, loop.simulate"` after Task 2 and again after Task 5.
4. The per-file test counts in the Task 8 table are this plan's predictions, re-derived from the literal bodies during review. Re-tally per file at Task 8 and treat any mismatch in either direction as a stop-and-explain (Task 8 Step 8), not a number to adjust.
5. `_orphan_bundle_issues` fires on `.loop/artifacts/verify-iter<N>.json`. Before Task 5 Step 7, confirm no tracked fixture or example already contains a file matching that exact name without a sibling record — the two shipped examples do not (`verify-T1.json`, `verify-T2.json`, `verify-T1-iter1.json`, `verify-T2-iter1.json`), but re-grep rather than trusting this line.
6. `os.replace` of the staged bundle is the last write in the writer. On DrvFS confirm the staged `.staged` suffix is not picked up by `metrics._load_verify_bundles`'s `verify-*.json` rglob — it ends in `.json.staged`, so it is not, but the assertion in `test_a_failed_record_write_leaves_no_metrics_visible_bundle` is what proves it.
