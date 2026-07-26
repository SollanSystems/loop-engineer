# Evidence Wiring (Tamper-Evident Provenance, Slice 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the evidence a verified dispatch writes *load-bearing*: the artifacts are content-addressed and their digests are bound into the Slice-1 hash chain at append time; `loop doctor` hash-verifies every discovered record and compares its `policy_digest` against the live `TASKS.json` entry; and `Succeeded` gains an opt-in completion mode whose bar is evidence that is hash-verified, chain-bound (wherever a store exists to bind against) and agreeing with the live goalpost — rather than non-empty path strings. Every silence Slice 2 documented as "recorded, not checked" that this slice closes is named as a tier movement in §17; every silence it does **not** close stays pinned under its true name.

**Architecture:** `loop/emit.py` splits its writer into a **pure builder** (`build_verify_evidence` — computes the bundle text, the record text, the content-addressed object path via `loop.evidence.artifact_object_path`, and the three `{path, sha256}` artifact-hash entries, writing nothing) and the existing writer (`write_verify_evidence`, which now accepts a prebuilt result). `dispatch_once` builds **before** it appends, passes `artifact_hashes=` to `SQLiteEventStore.append` — a field already inside `loop/chain.py`'s twelve-field preimage (`loop/chain.py:16-20`) — and only then writes the files. `loop/runtime.py` grows an event-store-gated walk that re-hashes each bound path and reports `evidence_chain_mismatch` / `missing_bound_evidence`; `loop/contract.py` composes the already-shipped `verify_evidence()` (`loop/evidence.py:142`) over discovered records and adds a `policy_digest_mismatch` comparison against the live task entry; `loop/completion.py` gains a second completion mode that `emit.terminate`, `loop.contract`, `loop.reducer` and `loop.integrations` each enforce at their own layer.

**Tech Stack:** Python 3.10+ stdlib only (`hashlib`, `json`, `os`, `pathlib`, `sqlite3`). No new runtime dependencies. Tests via pytest under `uv run`.

**Baseline: `main` @ `7319dd2`** (the Slice-2 feature squash `c1a386b` plus its plan-docs commit `7319dd2`). PR #94's own gate numbers were **1143 passed / 16 skipped** (pyyaml+jsonschema) and **1058 / 101** (pyyaml-only), measured on the branch head, not on a fresh worktree — **Task 0 re-measures and those two measurements, not PR #94's, are what every later acceptance line adds to.** `pyproject.toml:7` still reads `0.10.0`, so the Slice-2 release cut (plan Task 9) has **not** run: this slice's release-cut task is version-flexible and operator-gated (see Task 10). Verified live at planning time: the only concurrent work in flight is dependabot; issues #37/#38/#39 are help-wanted and touch nothing here.

**Review status:** revised after a three-lens adversarial review (design-lint, kernel-reality, threat-honesty) — 1 BLOCKER, 2 MAJOR and 4 MINOR findings, all adjudicated; the applied changes and the rulings are in **Post-review design changes** below. Every "current text" citation against `reference/repo-os-contract.md` and `loop/` in this plan was re-verified against `origin/main` @ `7319dd2` during that revision; three citations had already drifted and are now recorded as discharged rather than as work.

## Global Constraints

- **Zero new runtime dependencies.** `loop/` imports stdlib + intra-package only; `pyproject.toml` `[project.optional-dependencies]` stays exactly `yaml`, `schemas`, `dev`.
- **event@1 and evidence@1 both stay `@1`, and this slice adds NO new event type.** `artifact_hashes` is already a specified event@1 property (`schemas/event.schema.json:21-32`) and already inside the hash preimage (`loop/chain.py:16-20`); binding evidence needs no new `type` enum member, no new payload row in `_PAYLOAD_REQUIRED_FIELDS` (`loop/events.py:21-31`), and no new structural-fallback branch. See binding decision 1 for the rejected alternative and its justification. **evidence@1 gains no new field at all** — the content-addressed object location is *derived* from `sha256` by `artifact_object_path`, not stored.
- **The one schema edit is `schemas/terminal.schema.json`'s `completion_policy.mode`**, whose `const: "all_required"` (`:80`) becomes a two-member `enum`. That is permissive-additive: every shipped record still validates, `required` is untouched, and terminal@1 stays `@1`.
- **Validation-mode parity.** Every new check runs identically in `jsonschema` and `structural-fallback` mode. A finding that fires in one mode and not the other is a bug, not a shortcut (`reference/repo-os-contract.md` commits to fallback parity).
- **Absent-everything doctor byte-stability.** With no `.loop/evidence/`, no runner bundle, and no `.loop/events.db`, `doctor_report` output is byte-identical to today's. This slice adds **no new top-level doctor key and no new key inside the `event_store` block**, so `scripts/test_doctor_eventstore.py:107` (`test_absent_event_store_matches_pre_slice_doctor_shape`) and `scripts/test_doctor_evidence.py:54` (`test_absent_evidence_directory_is_a_byte_stable_no_op`) both pass **unmodified**.
- **Typed fail-loud everywhere.** No new path may skip on error (R007: an errored verifier must FAIL, not skip). An unreadable object, a colliding object, a non-canonicalizable task, and an unverifiable terminal each raise a typed `EmitError`; a store that cannot be read keeps reporting its own `error_code` and never silently drops the binding walk.
- **Honest-recording, never proof.** Chain-binding inherits Slice 1's trust model *exactly*: a worker that can rewrite `.loop/` can rewrite the store too (`reference/repo-os-contract.md:592-595`, the DROP-TRIGGER limitation). Binding makes tampering **detectable against an anchor**, not impossible. The forbidden claim is "tamper-proof evidence"; the shipped claim is **"evidence whose bytes are bound into an anchorable chain"**. Docs and pinned honest-limitation tests must both carry it.
- **FLIP, never delete, a pinned honest limitation.** Slice 2 shipped ten `*_pinned` tests. Four of them describe silences this slice closes. They are **rewritten in place** — renamed to the new honest outcome, with the residual half retained and a docstring naming the release that changed it. Deleting one converts a documented limitation into an undocumented one (Slice-2 whole-branch review, T6 ledger row).
- **Succeeded tightening is opt-in, never retroactive.** Both shipped examples' terminals carry evidence entries that are *bundle paths*, not evidence@1 records (`examples/coverage-repair/terminal_state.json:9`, `examples/flaky-test-triage/.loop/terminal_state.json:9`), and `dispatch_once`'s auto-terminal writes `evidence: ["RUNLOG.md"]` (`loop/runner.py:225`). A blanket tightening would fail G1 on the repo's own dogfood in the same commit that ships it. The bar moves through a declared `completion_policy.mode`; see binding decision 6 and its compat table.
- **`evals/cases/structural.json` is untouched** — no new skill, reference, template, or *schema file* ships. Editing existing schemas is additive.
- **Version bumps live only in the release-cut PR** (Task 10). Tasks 0-9 land as one feature PR with no version change.
- Repo env quirks: no system pytest — run tests via `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider ...`; the Bash deny-list blocks `rm`, bare `cd`, `VAR=` prefixes, `timeout`, `printf`, `source` — use `git -C`, absolute paths, `bash -c`. A Rust `git` wrapper on PATH can serve **stale** `git log` tips; trust `git rev-parse` / `git cat-file`.

---

## Program context (what this plan is Slice 3 of)

Source: `review/2026-07-24-graph-engineering-report-assessment.md`. The accepted program is **tamper-evident provenance**; the "graph engineering" framing was rejected (assessment §2 blocker 5).

| Slice | Scope contract | Status |
|---|---|---|
| 1 | Hash-linked chain, `loop migrate`, doctor chain gate + `--expect-chain-head`, honest-limitation tests/docs. | **shipped v0.10.0** (`7002580` / `91bf36a`) |
| 2 | Verifier identity + independence: `verified_by.code_digest`/`policy_digest` on evidence@1, `produced_by.executor == verified_by.by` as a doctor finding, visible/held-out partition in verify bundles. | **merged as PR #94** (`c1a386b`); plan committed `7319dd2`. Release cut **not yet run** — `pyproject.toml` still reads `0.10.0`. |
| **3 (this plan)** | Wire evidence@1 into writer + doctor (the §17 deferral): content-addressed objects via `artifact_object_path`, doctor **hash-verifies** evidence referenced by criteria, doctor compares a record's `policy_digest` against the live TASKS.json entry, evidence artifacts bind into the hash chain, `Succeeded` tightens from non-empty paths to hash-verified evidence. Ships as **v0.12.0**, or **v0.11.0** if the operator has still not cut Slice 2 (Task 10 decides from `pyproject.toml`). | now |
| 4 | CI-attested verdict (in-toto Statement shape, GitHub OIDC keyless). Needs its own ADR. | after Slice 3 |
| 5 | Docs/interop pass (Mermaid in reference/docs only, trace-context-as-data, Cypher recipe). | anytime |

Rejected permanently (do not resurrect): `graph` CLI verbs + query DSL, FastAPI HTTP API/SDK, Neo4j/Qdrant integrations, unanchored Merkle checkpoints, local DSSE/HMAC signing.

**Assessment line this slice implements** — P3 (assessment:91): *"The real residue is the already-scheduled §17 wiring: evidence@1 into writer + doctor, tightening `Succeeded` from non-empty-paths to hash-verified evidence."* Assessment §1's accuracy nuance is the defect being closed: *"evidence@1 is NOT wired end-to-end … no production writer passes `artifact_hashes=`; `terminal.evidence` is plain path strings, not hashed records."* Slice 2 made the runner a production writer; this slice makes `artifact_hashes=` non-empty and makes the strings verifiable.

---

## Post-review design changes

Seven findings, each adjudicated below. The house rule applied to every conflict: **move toward threat-honesty** — when a cheaper option was to leave a limitation unnamed, the limitation is named and pinned instead.

| # | Lens / severity | Finding | Ruling |
|---|---|---|---|
| 1 | design-lint MAJOR | Task 3's stated test count is wrong. | **Applied** — duplicate of #2; adjudicated there. |
| 2 | kernel-reality MAJOR | Task 3's literal test block defines 8 single tests + 2 `parametrize(_MODES)` tests = **12** collected items, not 11; the Task 9 row and grand total inherit the error. | **Applied.** Task 3 now reads 12 extras / 10 passed 2 skipped fallback; the Task 9 row reads 12. The grand total is recomputed from scratch (it also absorbs the new tests from #6 and #7): **90 collected / 82 fallback passes / 8 jsonschema skips.** Re-counted every other task's block the same way while making the fix; Tasks 1/2/4/6/8 were already exact. |
| 3 | threat-honesty **BLOCKER** | The strict completion mode requires each `Succeeded` evidence entry to hash-verify, but never that the record is **chain-bound** or that its `policy_digest` agrees with the live task. A worker with `.loop/` write access can hand-write a bundle, its digest, and a matching record, and satisfy `all_required_verified_evidence` with **zero dispatch and zero event**. The plan's headline claim did not name that residual anywhere. | **Applied, closing rather than only pinning.** New **decision 14**: at the two layers that hold a workspace (`emit.terminate`, `loop.contract`) the strict mode additionally requires (a) every cited record to be **chain-bound** whenever an event store exists, and (b) the record's `policy_digest` to equal the live goalpost whenever it names a live TASKS.json task. The irreducible residuals — a **store-less** contract (writer-API-only) can never chain-bind, and the reducer/`to_terminal_state` layers are pure and can only check shape — are now **pinned** (Task 7 pins 13-14, Task 5's two new refusal tests) and named in §17's completion-mode subsection (Task 8 Step 4). Rejected: requiring a store unconditionally, which would make the mode unusable for the writer-API path this plan pins as supported; rejected equally: leaving the gap and only writing a sentence, because the gap is the slice's headline capability. |
| 4 | threat-honesty MAJOR | Two Slice-2 review items — M-7 (§17's `unresolvable` row) and ledger row T6 (workspace-root symlink-loop pin unpinned) — appear nowhere in the carry-forward table, breaking the table's own "explicit task or recorded exclusion" discipline. | **Applied, split by verification.** M-7 was re-checked against `origin/main`: `reference/repo-os-contract.md:869` **already** reads *"raised `OSError` (or pathlib's `RuntimeError` on Python ≤3.12 for a symlink loop)"* — fixed in Slice 2's pre-merge wave, so it lands as carry-forward row **10: already resolved, no action**, not as doc work. T6 is genuinely open (`scripts/test_verifier_identity.py:65` pins the argv[0] symlink loop; `loop/verifier.py:64` resolves the workspace root inside the same `try`, so the workspace-root variant is covered behaviorally but unpinned) → carry-forward row **11**, discharged by new **Task 7 Step 2b**. |
| 5 | kernel-reality MINOR | Carry-forward row 7 claims Task 1 "incidentally fixes" M-1 (`_EVIDENCE_SCHEMA_ID` literal fork). `loop/emit.py:32` on `origin/main` already reads `from .evidence import EVIDENCE_SCHEMA_ID`. | **Applied.** Row 7 now records M-1 as **already resolved on `origin/main`**; Task 1 Step 3's rationale keeps only M-2 (verified still open — `origin/main`'s `loop/emit.py` contains no `validate_evidence` call). A PR body claiming "fixed M-1" would have been false. |
| 6 | kernel-reality + threat-honesty MINOR (×2) | Task 8 Step 5 tells the implementer to fix a heading that says "three honest tiers"; `reference/repo-os-contract.md:951` already says **four**. | **Applied.** The heading clause is struck (M-12 recorded discharged in row 7), and Task 8 gains a standing instruction to re-diff every quoted "current" sentence against the live file immediately before editing it — the same discipline Task 0 already applies to test counts. |
| 7 | kernel-reality MINOR | Task 4 Step 4's Implement snippet omits, in code, the "only for records with no structural issues" gate its own prose requires; `verify_evidence()` re-runs `validate_evidence` internally, so an unconditional call double-reports a malformed record. | **Applied.** The snippet now shows the captured `record_issues` and the `if not record_issues:` guard literally. |

---

## Carry-forwards from Slice 2 (each is an explicit task or a recorded exclusion)

Sources: PR #94's "Deferred (issues to be filed post-merge)" list, and the whole-branch review's sections (b) Findings and (c) Ledger triage.

| # | Carry-forward | Where it lands |
|---|---|---|
| 1 | **FLIP, never delete**, `test_rewriting_the_evidence_record_to_independent_identities_leaves_doctor_clean_pinned` (`scripts/test_adversarial_verifier_identity.py:81`) and `test_deleting_both_bundle_and_record_leaves_doctor_clean_pinned` (`:67`) when chain-binding lands. | Task 7 Step 1 — both rewritten in place, both halves kept |
| 2 | **`missing_verify_bundle` counterpart** — a committed iteration with no bundle becomes detectable (review I-2, second silence; ledger T4 W1). | Task 3 — `missing_bound_evidence`; naming ruling in binding decision 4 |
| 3 | **Reverse record-without-bundle check** — a record whose `uri` does not resolve (review I-2, first silence). | Task 4 — composed `verify_evidence()` surfaces `missing_evidence_path` verbatim |
| 4 | **`scripts/metrics.py` reads `verifier.source`** so injected-callable bundles stop counting as gate evidence — the §17 sentence added in the Slice-2 fix wave (`reference/repo-os-contract.md:926-929`) promises exactly this. | Task 6 |
| 5 | **`policy_digest` live comparison** closes the recorded-not-checked tier for goalposts. | Task 4 |
| 6 | Review M-4: `_RUNNER_BUNDLE_RE` uses `\d+`, admitting Unicode digits (`loop/contract.py:637`). | **Already fixed** in the merged branch — the live regex is `verify-iter([0-9]+)\.json`. Recorded as discharged; the wider `re.fullmatch` convention sweep stays a separate follow-up. |
| 7 | Review M-1 `_EVIDENCE_SCHEMA_ID` literal fork; M-2 writer does not self-validate; M-3 bare `KeyError` on malformed `code_identity`; M-12 §17 heading "three honest tiers" over four bullets. | **M-1 and M-12 are already resolved on `origin/main`** — re-verified during the post-review pass: `loop/emit.py:32` reads `from .evidence import EVIDENCE_SCHEMA_ID` (used at `:462`), and `reference/repo-os-contract.md:951` already reads "in four honest tiers". Both were fixed in Slice 2's pre-merge wave, after the review transcript this table cites; **no action, and neither may be claimed as fixed in this slice's PR body.** M-2 is verified still open (no `validate_evidence` call anywhere in `origin/main`'s `loop/emit.py`) and Task 1 Step 3 discharges it *incidentally*, because the builder validates its own record before returning. M-3 stays **excluded** and open: a foreign mapping should still fail loudly, and `KeyError` is loud. |
| 8 | Review M-5 non-UTF-8 record → uncaught `UnicodeDecodeError`; M-6 unimplemented tasks@1 fallback type-check; M-9 unstripped CLI identities; M-10 `_USAGE` echo parity; M-11 `test_conformance.py` import hygiene; M-13 README null-digest nuance. | **Excluded** — recorded here so the exclusion is deliberate. None is a false claim; each is a separate small PR. |
| 9 | Review M-8: "an evidence record MUST NOT be named `verify-*.json`" is unenforced. | **Excluded, with a reason:** the enforcement point is `metrics.py`, and Task 6 already changes that file's bundle-loading contract. Stacking a second behavioral change on the same function in the same slice makes the FCR delta unattributable. |
| 10 | Review M-7: §17's `unresolvable` row says "resolving argv[0] raised `OSError`" while a symlink loop raises pathlib's `RuntimeError` on Python ≤3.12. | **Already resolved** — `reference/repo-os-contract.md:869` on `origin/main` reads *"resolving argv[0] raised `OSError` (or pathlib's `RuntimeError` on Python ≤3.12 for a symlink loop), permission-denied parent, or name too long"*, matching the code comment at `loop/verifier.py:76-79`. Recorded as discharged; **no Task-8 edit.** (This row exists because the review's Minor list omitted it from the original table — the omission, not the finding, was the defect.) |
| 11 | Review ledger T6: the **workspace-root** symlink-loop pin is unpinned (the argv[0] variant is pinned at `scripts/test_verifier_identity.py:65`). | **Task 7 Step 2b** — one test added to `scripts/test_verifier_identity.py`. `loop/verifier.py:64` resolves `Path(workspace).resolve()` **inside** the same `try` whose `except (OSError, RuntimeError)` returns `unresolvable`, so the behavior is already correct on both 3.10-3.12 and 3.13; what is missing is the pin that keeps it correct. Cheap, in-charter for a slice whose product is an honest boundary, and it removes the last untriaged review item. |

---

## Design decisions (binding)

1. **Chain-binding uses the existing `artifact_hashes` envelope field on `iteration_appended`, NOT a new event type.** Slice 2's decision 15 and `reference/repo-os-contract.md:972-973` both assert that binding "requires a new event type"; that was an assumption, and the live tree refutes it. `artifact_hashes` is a specified event@1 property (`schemas/event.schema.json:21-32`), is validated structurally today (`loop/events.py:210-219`), and is field #11 of the twelve-field canonical preimage (`loop/chain.py:16-20`) — so a digest placed there is *already* covered by `event_hash` and by `--expect-chain-head`. A new type would additionally require: a `type` enum edit, a `_PAYLOAD_REQUIRED_FIELDS` row, a structural-fallback branch, a reducer projection branch, a terminal-immutability rule (`loop/reducer.py:96-100` rejects any post-terminal event but `terminal_superseded`), and a **second append per dispatch** — breaking the load-bearing invariant commented at `loop/runner.py:208` ("each `dispatch_once` invocation appends at most one event") and introducing a new half-committed failure mode. **Ruling: reuse the field.** `loop/events.py` and `schemas/event.schema.json` are untouched by this slice; `loop/reducer.py` changes only for decision 6's structural half.
2. **The builder is pure and runs before the append; the writer runs after.** `build_verify_evidence()` performs zero I/O beyond reading `.loop/state.json` for the contract precondition, and returns a frozen `BuiltEvidence` carrying the exact bytes that will be written plus their digests. `dispatch_once` orders: identity → verifier → `iteration_id` → **build** → **append (with `artifact_hashes`)** → **write**. Consequences: (a) a build failure (non-canonicalizable task, bad `code_identity`) now aborts **before** anything is committed, which is strictly better than Slice 2's committed-then-failed path; (b) the pre-commit crash pin `test_crash_injection_before_iteration_event_commit_leaves_no_partial_dispatch` (`scripts/test_runner_dispatch.py`) still sees a byte-identical tree, because the builder writes nothing; (c) the post-commit crash window is unchanged in *existence* but no longer silent — the committed event names artifacts that are missing, which is exactly `missing_bound_evidence`.
3. **Three artifacts are bound, and the object is derived, never declared.** `artifact_hashes` carries, in this order: the bundle (`.loop/artifacts/verify-iter<N>.json` → bundle sha256), the content-addressed object (`artifact_object_path(workspace, bundle_sha)` → the same sha256), and the record (`.loop/evidence/evidence-iter<N>.json` → record sha256). The object's location is a pure function of the digest (`loop/evidence.py:217-219`), so **evidence@1 needs no `object_uri` field** and a third-party reader can find the object from `record["sha256"]` alone. The object is the recovery source when the friendly-named bundle is swapped: the swap fails doctor *and* the original bytes are still on disk.
4. **Issue codes reuse `verify_evidence()`'s vocabulary verbatim; only four codes are new.** `reference/repo-os-contract.md:1109` sets the doctrine — doctor composes a verb and surfaces "the identical issue code the `status`/`replay` verbs already use". Doctor therefore reports `hash_mismatch`, `missing_evidence_path`, `workspace_escape`, `not_a_file` and `invalid_uri` straight out of `verify_evidence` (`loop/evidence.py:155-213`). The `missing_verify_bundle` counterpart the Slice-2 review asked for **is** `missing_evidence_path` — recorded here so the carry-forward is visibly discharged rather than silently renamed, and given its own "do not confuse with `missing_evidence_record`" row in §22. The four genuinely new codes are `evidence_chain_mismatch`, `missing_bound_evidence`, `policy_digest_mismatch`, `unverified_evidence_terminal`.
5. **`policy_digest` is compared only against the LATEST record per `task_id`, and only when that task still exists in TASKS.json.** A run legitimately produces several records for one task (attempt 1 red, attempt 2 green); the older ones describe goalposts that were current when they were written, and comparing them would make every honest re-verification a permanent doctor failure. The latest record (highest `iteration_id` parsed from the record filename, ties broken by filename sort) is the one currently backing the task's claim, so it is the one that must agree with the live entry. A record naming a `task_id` absent from TASKS.json is **not** compared (a renamed or removed task is a replan, not a forgery) — pinned as an honest limitation. The remedy for a legitimately-moved goalpost is therefore constructive and does not require deleting evidence: re-verify under the new goalpost and the new record becomes the latest. `code_digest` is **not** compared against a live re-hash — the verifier file legitimately changes between runs and a comparison without a declared baseline would fire on every honest edit. That non-movement is named in §17.
6. **`Succeeded`'s evidence bar moves through a declared completion mode, enforced at four layers at the strength each layer can honestly reach.** `loop/completion.py` gains `all_required_verified_evidence` alongside `all_required`; `criteria_satisfy_completion` treats both identically (the criteria half is unchanged) and a new pure predicate `policy_requires_verified_evidence(policy)` names the difference. Enforcement:
   - `emit.terminate` (write time, has the workspace) — every `evidence[]` entry must resolve to a readable evidence@1 record that `validate_evidence` accepts and `verify_evidence` hash-verifies; otherwise `EmitError`. **Extended by decision 14** (post-review): this layer also requires chain-boundness when a store exists, and goalpost agreement when the record names a live task. Read decision 14 before implementing this bullet — decision 6's bar alone is satisfiable by a fabricated record.
   - `loop.contract` (read time, has the workspace) — the same check **including decision 14's two additions**, reported as `unverified_evidence_terminal`. "The same check" is literal: one shared predicate, two callers (Task 5 Step 4).
   - `loop.reducer` (pure fold, no I/O) — the **structural half only**: under the strict mode every evidence entry must be a workspace-relative `.loop/evidence/*.json` path. This is exactly §16's "two-layer enforcement, deliberately split" (`reference/repo-os-contract.md:629-642`): the reducer cannot touch a filesystem and must not pretend to.
   - `loop.integrations.to_terminal_state` (pure projection, no workspace) — the same structural half, returning `FailedUnverifiable` rather than raising, matching its existing fail-closed style (`loop/integrations.py:170-173`).

   Compat: `normalize_completion_policy(None)` still returns `{"mode": "all_required"}` (`loop/completion.py:30-31`), so every record written before this slice — including both dogfood examples, which carry no `completion_policy` at all — is untouched.
7. **`dispatch_once`'s auto-terminal adopts the strict mode only when it can honestly satisfy it.** When every task in TASKS.json has at least one evidence record from this run, the terminal is written with `completion_policy: {"mode": "all_required_verified_evidence"}` and `evidence` listing those records; otherwise it keeps `{"mode": "all_required"}` and `evidence: ["RUNLOG.md"]`, and its `reason` says which tasks had no record. Choosing the weaker policy silently would be a self-serving downgrade; saying so in the record is the honest form. Both branches are pinned.
8. **Doctor's binding walk lives in `loop/runtime.py`, the evidence walk stays in `loop/contract.py`.** `missing_bound_evidence` and `evidence_chain_mismatch` are event-store consistency findings and belong beside `chain_columns_missing` inside `event_consistency_issues` (`loop/runtime.py:282-332`), which is already gated on the store existing — so absent-store byte-stability is preserved for free. `hash_mismatch` / `missing_evidence_path` / `policy_digest_mismatch` need no store and stay in `_validate_evidence_records` (`loop/contract.py:684-711`), preserving Slice-2 decision 8. Neither adds a reported key.
9. **The binding walk pays for one extra read-only fold, deliberately.** `event_consistency_issues` already calls `status_report` and `replay_report`, each of which does its own `_events()` read. The walk needs the raw events (it reads envelope-level `artifact_hashes`, which no report returns) and adding a field to either report's dict would leak into the `loop status` / `loop replay` CLI JSON. A third `_read_store` pass through the existing read-only, sidecar-free helper is the low-blast-radius choice; the cost is recorded rather than hidden.
10. **A legacy event with empty `artifact_hashes` is never a finding.** Every event committed before this slice carries `artifact_hashes: []`. The binding walk is driven by what an event *declares*, so an old dispatch is silent and a new one is checked. The consequence — a pre-Slice-3 iteration whose evidence was deleted is still undetectable — is a named residual, not an oversight, and it cannot be repaired: the append-only triggers forbid UPDATE (`loop/events.py:50-57`), so no backfill is possible. Same reasoning as `loop migrate`'s refusal to backfill hashes (`reference/repo-os-contract.md:1150-1159`).
11. **Object writes are create-once and collision-loud.** The object is written with `_atomic_create_text` (`loop/emit.py:97-115`, the same hard-link create-once primitive the immutable terminal uses). A `FileExistsError` is resolved by re-reading the existing object: identical bytes → idempotent success (a re-run of the same dispatch); different bytes → `EmitError` naming the digest, because a sha256 collision or a corrupted object store must never be silently accepted.
12. **`loop simulate` stays decision-level.** `_empty_prediction` gains no field, per Slice-2 decision 16. A dispatch always writes the bundle, record and object, so a boolean predicting `True` every time carries no information. Restated in §17 so a reader does not infer that simulate enumerates the object store.
13. **`metrics.py` excludes only an explicit `injected_callable` source.** A bundle with no `verifier` block (every bundle written before Slice 2, including both shipped examples' four) has an unknown source and keeps counting — grandfathering by absence, not by guess. Only `verifier.source == "injected_callable"` is excluded, and the excluded names are reported under `provenance` so the exclusion is visible rather than a silent FCR shift.
14. **The strict mode's bar is hash-verified *and chain-bound and goalpost-agreeing*, at every layer that can honestly reach it.** *(Added post-review: BLOCKER, threat-honesty.)* Decision 6's original bar — `validate_evidence` + `verify_evidence` per entry — proves only that a record is *internally self-consistent*: the file it points at exists and hashes to the digest the record declares. Both halves of that pair are worker-writable, and `verification_policy_digest` is a public pure function over public TASKS.json data, so a worker with `.loop/` write access could hand-write a bundle, its digest, a matching record and a correct-looking `policy_digest`, then call `terminate(..., completion_policy=VERIFIED_EVIDENCE_MODE)` with **no dispatch, no verifier execution and no event ever appended** — and both `emit` and `doctor` would accept it. Shipping the slice's headline capability with that unnamed would be exactly the false-completion class this repo exists to close. The bar is therefore extended at the two workspace-bearing layers:
    - **`emit.terminate` and `loop.contract`** additionally require, per cited entry, that (a) the record's workspace-relative path appears in the set of artifacts some event bound into the chain, **and its bound digest equals the record file's current sha256** — evaluated only when `.loop/events.db` exists; and (b) when `produced_by.task_id` names a task that is still in TASKS.json, the record's `verified_by.policy_digest` equals `verification_policy_digest` of that live entry. Failure is `EmitError` at write time and `unverified_evidence_terminal` at read time, with a message naming which of the three sub-checks failed (unverified / unbound / stale goalpost).
    - **The `policy_digest` half here is per-cited-record, not latest-per-task** — deliberately stricter than decision 5's doctor-wide rule, and the difference is named in §17. Decision 5's rule protects an *incidental* older record from a permanent failure; a terminal that *cites* a record is asserting that this record backs `Succeeded` right now, so a stale goalpost in a cited record is a false completion, not an artifact of history.
    - **`loop.reducer` and `loop.integrations.to_terminal_state` are unchanged** — still the structural `.loop/evidence/*.json` half. They are pure and hold no workspace; making them *appear* to enforce binding would be the same pretending decision 6 already refuses.
    - **Two residuals, both pinned and both documented.** (i) A contract with **no event store** — the writer-API path this plan pins as supported — cannot chain-bind anything, so there the strict mode degrades to hash-verification + goalpost agreement, and a hand-written record satisfies it. That degradation is *silent by construction* but not undocumented: doctor's existing `missing_event_store` tripwire (`loop/runtime.py:293`) is what catches deleting a store out from under a real run, and §17 says plainly that the strict mode's strength is store-dependent. (ii) Chain-binding still proves *bytes*, never *provenance*: a worker who can rewrite `.loop/` can rewrite the store, so without `--expect-chain-head` a full rewrite of artifacts **and** chain satisfies the strict mode. Pins 13 and 14 in Task 7 hold both, each with a positive control.
    - **Rejected:** requiring a store unconditionally (breaks the pinned writer-API path and would fail `test_a_record_written_outside_a_dispatch_is_never_chain_bound_pinned`'s own contract); and leaving the gap closed only by prose (a sentence in §17 with no test is exactly the "recorded, not checked" tier this slice exists to drain).

---

## File structure

| File | Change | Responsibility |
|---|---|---|
| `loop/emit.py` | modify (~406-484) | `BuiltEvidence` + `build_verify_evidence()`; content-addressed object write; `write_verify_evidence(..., built=)`; strict-mode evidence bar in `terminate`. |
| `loop/runner.py` | modify (~245-276, ~219-233) | Build before append; pass `artifact_hashes=`; auto-terminal policy selection. |
| `loop/runtime.py` | modify (append + ~311) | `bound_artifact_digests()` (shared lookup, decision 14); `_bound_evidence_issues()`; composed into `event_consistency_issues`. |
| `loop/contract.py` | modify (~684-711, + new helpers, + `validate_contract` call site ~814) | Hash-verify discovered records; `policy_digest_mismatch`; `unverified_evidence_terminal`. |
| `loop/completion.py` | modify | `all_required_verified_evidence`; `policy_requires_verified_evidence()`. |
| `loop/reducer.py` | modify (~32-50) | Structural half of the strict evidence bar. |
| `loop/integrations.py` | modify (~170-173) | Structural half, fail-closed projection. |
| `schemas/terminal.schema.json` | modify (`:78-82`) | `completion_policy.mode` const → two-member enum. |
| `scripts/metrics.py` | modify (~230-252, ~458-460) | Read `verifier.source`; partition gate-evidence bundles; report exclusions. |
| `scripts/test_verify_evidence_objects.py` | **create** | Builder purity, object store, artifact-hash set, atomicity. |
| `scripts/test_evidence_binding_runner.py` | **create** | Runner build→append→write ordering and the bound digests. |
| `scripts/test_doctor_evidence_binding.py` | **create** | `evidence_chain_mismatch`, `missing_bound_evidence`, legacy silence, zero-write. |
| `scripts/test_doctor_evidence_verification.py` | **create** | Hash verification and `policy_digest_mismatch` (both modes). |
| `scripts/test_completion_verified_evidence.py` | **create** | The new mode across all four enforcement layers. |
| `scripts/test_metrics_verifier_source.py` | **create** | Gate-evidence partition and the published example metrics. |
| `scripts/test_adversarial_evidence_binding.py` | **create** | 14 pins: what binding does and does not catch (13-14 are decision 14's residuals). |
| `scripts/test_adversarial_verifier_identity.py` | modify (4 tests rewritten in place) | The mandated flips. |
| `scripts/test_verifier_identity.py` | modify (+1 test) | Carry-forward 11 — the workspace-root symlink-loop pin (Task 7 Step 2b). |
| `scripts/test_doctor_evidence.py` | modify (helpers only) | Fixtures must produce hash-consistent pairs; test bodies unchanged. |
| `scripts/test_conformance.py` | extend | Artifact-binding vector + three doc pins. |
| `reference/repo-os-contract.md` | modify §16, §17, §22 | Binding, tier movements, four new codes, the stale event-type list. |
| `reference/safety-and-approvals.md` | modify §5 | One sentence: the goalpost check is now live. |
| `loop/evidence.py`, `schemas/evidence.schema.json` | modify (docstring / description only) | Retire the "does not yet hash-verify" claims. |
| `README.md` | modify | One capability sentence + one honest clause (Task 8); version surfaces (Task 10). |
| `CHANGELOG.md`, `pyproject.toml`, `.claude-plugin/plugin.json`, `scripts/test_docs_version.py` | modify (Task 10) | Release cut. |

Interfaces produced (exact signatures):

```python
# loop/emit.py
@dataclass(frozen=True)
class BuiltEvidence:
    bundle_path: Path
    record_path: Path
    object_path: Path
    bundle_text: str
    record_text: str
    sha256: str                                  # of bundle_text
    record_sha256: str                           # of record_text
    artifact_hashes: tuple[dict[str, str], ...]  # ({"path","sha256"}) bundle, object, record

def build_verify_evidence(target: str | Path, *, run_id: str, iteration_id: int,
                          task: Mapping[str, Any], passed: bool,
                          code_identity: Mapping[str, Any], summary: str = "",
                          executor: str | None = None, verifier_identity: str | None = None,
                          attempt: int | None = None) -> BuiltEvidence: ...

def write_verify_evidence(target, *, run_id, iteration_id, task, passed, code_identity,
                          summary="", executor=None, verifier_identity=None,
                          attempt=None, built: BuiltEvidence | None = None) -> dict[str, Any]: ...
# {"bundle": Path, "evidence": Path, "object": Path, "sha256": str}   ("object" is new)

# loop/completion.py
VERIFIED_EVIDENCE_MODE: Final[str] = "all_required_verified_evidence"
def policy_requires_verified_evidence(policy: object | None = None) -> bool: ...
def evidence_entry_is_record_shaped(entry: object) -> bool: ...   # pure, no I/O

# loop/runtime.py
def _bound_evidence_issues(target: str | Path, mode: str | None) -> list[dict[str, Any]]: ...
def bound_artifact_digests(target: str | Path, mode: str | None = None) -> dict[str, str] | None: ...
#   {workspace-relative POSIX path: sha256} for every artifact any event bound.
#   None means "no event store" (caller degrades and says so, decision 14);
#   {} means "a store exists and bound nothing"; RuntimeStoreError on an unreadable store.

# loop/contract.py
def _verify_discovered_record(record, paths, record_path, issues) -> None: ...
def _policy_digest_issues(paths, records: list[tuple[int, Path, dict]], issues) -> None: ...
def _check_verified_evidence_terminal(terminal, paths, issues) -> None: ...
def _strict_evidence_failure(entry: str, paths, bound: dict[str, str] | None) -> str | None: ...
#   Shared decision-14 predicate: None when the entry passes all three sub-checks,
#   else a human-readable detail naming which one failed. emit.terminate raises on it;
#   loop.contract reports it as unverified_evidence_terminal. One definition, two callers.
# new issue codes: evidence_chain_mismatch, missing_bound_evidence,
#                  policy_digest_mismatch, unverified_evidence_terminal
```

---

### Task 0: Branch setup and baseline measurement

**Files:** none.

- [ ] **Step 1:** Confirm the branch point with `git -C /mnt/c/Dev/projects/loop-engineer rev-parse origin/main` and `git -C ... cat-file -p origin/main` — **not** `git log`, whose tip a Rust wrapper on PATH can serve stale.
- [ ] **Step 2:** `git -C /mnt/c/Dev/projects/loop-engineer checkout -b feat/evidence-wiring main` (main protection blocks direct pushes; all work lands via PR).
- [ ] **Step 3:** Create the baseline worktree **detached** (`git worktree add <path> <branch>` refuses a branch already checked out): `git -C /mnt/c/Dev/projects/loop-engineer worktree add --detach /mnt/c/Dev/projects/loop-engineer/.tmp/s3-base feat/evidence-wiring`.
- [ ] **Step 4:** Extras baseline: `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider /mnt/c/Dev/projects/loop-engineer/.tmp/s3-base/scripts`.
- [ ] **Step 5:** Fallback baseline in the same worktree: `uv run --with pyyaml --with pytest python3 -B -m pytest -q -p no:cacheprovider /mnt/c/Dev/projects/loop-engineer/.tmp/s3-base/scripts`.
- [ ] **Step 6:** Record both `(passed, skipped)` pairs at the top of the PR draft as `BASE_EXTRAS` and `BASE_FALLBACK`, each with its dependency set named. Do **not** reuse PR #94's 1143/16 and 1058/101 — those were branch-head numbers and the live checkout reads ±2 against a fresh worktree. `--with hypothesis` (CI installs it) swings ~+10/−1; never compare across dependency sets.
- [ ] **Step 7:** Record the pre-change dogfood metrics so Task 6 has a before: `uv run --with pyyaml python3 -B scripts/metrics.py examples/flaky-test-triage` and `... examples/coverage-repair`. Note FCR, RP and `evidence_backed` verbatim.

**Acceptance:** two recorded `(passed, skipped)` pairs, two recorded metric scorecards, detached worktree left in place for Task 9.

---

### Task 1: `loop/emit.py` — pure builder, content-addressed object, bound digests

**Files:** Modify `loop/emit.py`; Create `scripts/test_verify_evidence_objects.py`.

- [ ] **Step 1: Write the failing tests** — `scripts/test_verify_evidence_objects.py`:

```python
"""build_verify_evidence purity, the content-addressed object, and the bound digest set."""
from __future__ import annotations

import hashlib
import json

import pytest

from loop import emit
from loop.evidence import artifact_object_path
from loop.verifier import executed_verifier_identity


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


def _tree(workspace):
    return {str(p.relative_to(workspace)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in workspace.rglob("*") if p.is_file()}


def _build(workspace, *, iteration_id=1, task=None, passed=True, **kwargs):
    task = task or _task()
    kwargs.setdefault("code_identity", executed_verifier_identity(task["verify"], workspace))
    return emit.build_verify_evidence(workspace, run_id="run-1", iteration_id=iteration_id,
                                      task=task, passed=passed, **kwargs)


def test_build_writes_nothing(tmp_path):
    workspace = _ws(tmp_path)
    before = _tree(workspace)
    _build(workspace)
    assert _tree(workspace) == before


def test_build_and_write_agree_on_every_byte(tmp_path):
    workspace = _ws(tmp_path)
    built = _build(workspace)
    written = emit.write_verify_evidence(workspace, run_id="run-1", iteration_id=1,
                                         task=_task(), passed=True,
                                         code_identity=executed_verifier_identity(
                                             _task()["verify"], workspace),
                                         built=built)
    assert written["bundle"].read_text(encoding="utf-8") == built.bundle_text
    assert written["evidence"].read_text(encoding="utf-8") == built.record_text


def test_write_places_the_content_addressed_object(tmp_path):
    workspace = _ws(tmp_path)
    built = _build(workspace)
    written = emit.write_verify_evidence(workspace, run_id="run-1", iteration_id=1,
                                         task=_task(), passed=True,
                                         code_identity=executed_verifier_identity(
                                             _task()["verify"], workspace), built=built)
    assert written["object"].is_file()
    assert hashlib.sha256(written["object"].read_bytes()).hexdigest() == built.sha256


def test_object_path_matches_artifact_object_path(tmp_path):
    workspace = _ws(tmp_path)
    built = _build(workspace)
    assert built.object_path == artifact_object_path(workspace, built.sha256)


def test_artifact_hashes_cover_bundle_object_and_record(tmp_path):
    workspace = _ws(tmp_path)
    built = _build(workspace)
    by_path = {entry["path"]: entry["sha256"] for entry in built.artifact_hashes}
    assert len(built.artifact_hashes) == 3
    assert by_path[".loop/artifacts/verify-iter1.json"] == built.sha256
    assert by_path[".loop/evidence/evidence-iter1.json"] == built.record_sha256
    assert by_path[built.object_path.relative_to(workspace).as_posix()] == built.sha256


def test_artifact_hashes_entries_are_workspace_relative_posix(tmp_path):
    built = _build(_ws(tmp_path))
    for entry in built.artifact_hashes:
        assert not entry["path"].startswith("/") and "\\" not in entry["path"]
        assert len(entry["sha256"]) == 64


def test_record_sha256_still_commits_to_the_bundle_bytes(tmp_path):
    built = _build(_ws(tmp_path))
    record = json.loads(built.record_text)
    assert record["sha256"] == hashlib.sha256(built.bundle_text.encode("utf-8")).hexdigest()


def test_rewriting_the_bundle_leaves_the_object_intact(tmp_path):
    workspace = _ws(tmp_path)
    built = _build(workspace)
    written = emit.write_verify_evidence(workspace, run_id="run-1", iteration_id=1,
                                         task=_task(), passed=True,
                                         code_identity=executed_verifier_identity(
                                             _task()["verify"], workspace), built=built)
    written["bundle"].write_text('{"outcome": "PASS", "passed": true}', encoding="utf-8")
    assert hashlib.sha256(written["object"].read_bytes()).hexdigest() == built.sha256


def test_a_second_identical_build_reuses_the_object_without_error(tmp_path):
    workspace = _ws(tmp_path)
    identity = executed_verifier_identity(_task()["verify"], workspace)
    first = emit.write_verify_evidence(workspace, run_id="run-1", iteration_id=1,
                                       task=_task(), passed=True, code_identity=identity)
    second = emit.write_verify_evidence(workspace, run_id="run-1", iteration_id=1,
                                        task=_task(), passed=True, code_identity=identity)
    assert first["object"] == second["object"] and first["sha256"] == second["sha256"]


def test_an_object_collision_with_different_bytes_raises_emit_error(tmp_path):
    workspace = _ws(tmp_path)
    built = _build(workspace)
    built.object_path.parent.mkdir(parents=True, exist_ok=True)
    built.object_path.write_text("not the bundle", encoding="utf-8")
    with pytest.raises(emit.EmitError, match="object store"):
        emit.write_verify_evidence(workspace, run_id="run-1", iteration_id=1, task=_task(),
                                   passed=True,
                                   code_identity=executed_verifier_identity(
                                       _task()["verify"], workspace), built=built)


def test_a_non_canonicalizable_task_raises_a_typed_emit_error_at_build_time(tmp_path):
    workspace = _ws(tmp_path)
    with pytest.raises(emit.EmitError, match="canonical"):
        _build(workspace, task=_task(criterion_ref=float("nan")))


def test_a_failed_record_write_leaves_no_metrics_visible_bundle_and_no_partial_object(tmp_path):
    workspace = _ws(tmp_path)
    built = _build(workspace)
    (workspace / ".loop" / "evidence").mkdir(parents=True, exist_ok=True)
    (workspace / ".loop" / "evidence" / "evidence-iter1.json").mkdir()   # write must fail
    with pytest.raises((OSError, emit.EmitError)):
        emit.write_verify_evidence(workspace, run_id="run-1", iteration_id=1, task=_task(),
                                   passed=True,
                                   code_identity=executed_verifier_identity(
                                       _task()["verify"], workspace), built=built)
    assert not list((workspace / ".loop" / "artifacts").glob("verify-*.json"))
```

- [ ] **Step 2: Run it — expect collection to pass and 12 failures** (`AttributeError: module 'loop.emit' has no attribute 'build_verify_evidence'`): `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_verify_evidence_objects.py`.
- [ ] **Step 3: Implement.** In `loop/emit.py`: extend the existing `from .evidence import EVIDENCE_SCHEMA_ID` at `:32` with `artifact_object_path` (M-1's literal fork was **already fixed before PR #94 merged** — that import is live on `origin/main` and is used at `:462`; do not claim it as this slice's work), add `from dataclasses import dataclass`, and factor the body of today's `write_verify_evidence` (`:410-484`) into `build_verify_evidence`, which:
  1. calls `_require_contract(target)`, computes `policy_digest` with the existing `ChainHashError → EmitError` conversion (`:430-433`);
  2. builds the identical `identity`/`bundle`/`record` dicts (`:435-475`) — **no field changes**, so a Slice-2 record and a Slice-3 record for the same input are byte-identical;
  3. serializes both with the existing `json.dumps(..., indent=2, sort_keys=True) + "\n"`;
  4. validates its own record with `validate_evidence(record, mode="basic")` and raises `EmitError` when it is not `ok` (discharges review M-2 — every other schema'd writer validates at write time);
  5. returns `BuiltEvidence` with `object_path=artifact_object_path(paths.workspace, sha256)` and the three-entry `artifact_hashes` tuple, each `path` computed as `p.relative_to(paths.workspace).as_posix()`.

  `write_verify_evidence` keeps its signature, adds `built: BuiltEvidence | None = None`, builds when `built is None`, then writes in this order: **object → staged bundle → record → `os.replace(staged, bundle)`**. The object write is `_atomic_create_text`, wrapped:

```python
    try:
        built.object_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_create_text(built.object_path, built.bundle_text)
    except FileExistsError:
        existing = hashlib.sha256(built.object_path.read_bytes()).hexdigest()
        if existing != built.sha256:
            raise EmitError(
                f"object store holds different bytes for {built.sha256}: refusing to overwrite "
                f"a content-addressed object (found {existing})")
    except OSError as exc:
        raise EmitError(f"object store write failed at {built.object_path}: {exc}") from exc
```

  The `except BaseException` cleanup around the record write (`:480-482`) also unlinks nothing from the object store: the object is immutable and correct by construction, and removing it would destroy the recovery copy. Return dict gains `"object": built.object_path`.
- [ ] **Step 4: Guard the return-shape change.** `grep -rn "write_verify_evidence" scripts/ loop/` and confirm no caller compares the returned dict by equality (Slice-2 callers index `["bundle"]`/`["evidence"]`/`["sha256"]`). Any equality comparison found is a stop-and-explain.
- [ ] **Step 5: Run the gate.** `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_verify_evidence_objects.py scripts/test_verify_evidence_writer.py scripts/test_emit.py scripts/test_evidence.py` — the new file **12 passed**, the three Slice-2 files unchanged and green.
- [ ] **Step 6:** Commit: `feat(emit): pure evidence builder, content-addressed object store, bound digest set`.

**Acceptance:** +12 passed in both dependency sets; `scripts/test_verify_evidence_writer.py`, `scripts/test_emit.py`, `scripts/test_evidence.py` byte-unmodified and green; `git diff --stat` shows `loop/emit.py` as the only kernel file touched.

---

### Task 2: `loop/runner.py` — build before append, bind at append

**Files:** Modify `loop/runner.py`; Create `scripts/test_evidence_binding_runner.py`.

- [ ] **Step 1: Write the failing tests** — `scripts/test_evidence_binding_runner.py`. Read `scripts/test_runner_dispatch.py:21-39` first and reuse its existing `_ws`/`_task`/`_pass` helpers by import if they are module-level, else copy them verbatim into the new file (there is no `conftest.py` anywhere in the tree; per-file helpers are the repo convention).

```python
"""dispatch_once binds its evidence digests into the iteration event before writing them."""
from __future__ import annotations

import hashlib
import json

import pytest

from loop import emit
from loop.chain import compute_event_hash
from loop.events import SQLiteEventStore
from loop.runner import RunnerError, VerifyOutcome, dispatch_once


def _events(workspace, run_id="run-1"):
    return SQLiteEventStore(workspace / ".loop" / "events.db").read(run_id)


def _iteration_events(workspace):
    return [e for e in _events(workspace) if e["type"] == "iteration_appended"]


def test_dispatch_binds_the_evidence_digests_into_the_iteration_event(ready_workspace):
    dispatch_once(ready_workspace)
    hashes = _iteration_events(ready_workspace)[-1]["artifact_hashes"]
    paths = {entry["path"] for entry in hashes}
    assert len(hashes) == 3
    assert ".loop/artifacts/verify-iter1.json" in paths
    assert ".loop/evidence/evidence-iter1.json" in paths


def test_bound_digests_match_the_files_on_disk(ready_workspace):
    dispatch_once(ready_workspace)
    for entry in _iteration_events(ready_workspace)[-1]["artifact_hashes"]:
        blob = (ready_workspace / entry["path"]).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == entry["sha256"]


def test_the_bound_event_hash_covers_the_artifact_hashes(ready_workspace):
    dispatch_once(ready_workspace)
    event = _iteration_events(ready_workspace)[-1]
    assert compute_event_hash(event) == event["event_hash"]
    tampered = {**event, "artifact_hashes": []}
    assert compute_event_hash(tampered) != event["event_hash"]


def test_a_build_failure_commits_no_event(ready_workspace):
    tasks_path = ready_workspace / "TASKS.json"
    data = json.loads(tasks_path.read_text(encoding="utf-8"))
    data["tasks"][0]["criterion_ref"] = float("nan")
    tasks_path.write_text(json.dumps(data), encoding="utf-8")
    before = len(_events(ready_workspace))
    with pytest.raises(RunnerError):
        dispatch_once(ready_workspace)
    assert len(_events(ready_workspace)) == before


def test_an_evidence_write_failure_after_the_commit_is_still_loud(ready_workspace, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(emit, "write_verify_evidence", boom)
    with pytest.raises(RunnerError, match="committed to the event log"):
        dispatch_once(ready_workspace)
    assert len(_iteration_events(ready_workspace)) == 1


def test_dispatch_result_names_the_object_and_the_record(ready_workspace):
    result = dispatch_once(ready_workspace)
    assert result["evidence"].endswith("evidence-iter1.json")
    assert "objects" in result["object"]


def test_injected_verifier_dispatch_binds_its_own_bundle(ready_workspace):
    dispatch_once(ready_workspace, verifier=lambda task, ws: VerifyOutcome(True, "injected"))
    bundle = json.loads((ready_workspace / ".loop" / "artifacts" / "verify-iter1.json")
                        .read_text(encoding="utf-8"))
    entry = next(e for e in _iteration_events(ready_workspace)[-1]["artifact_hashes"]
                 if e["path"].endswith("verify-iter1.json"))
    assert bundle["verifier"]["source"] == "injected_callable"
    assert entry["sha256"] == hashlib.sha256(
        (ready_workspace / entry["path"]).read_bytes()).hexdigest()


def test_two_dispatches_bind_distinct_artifact_sets(two_task_workspace):
    dispatch_once(two_task_workspace)
    dispatch_once(two_task_workspace)
    first, second = _iteration_events(two_task_workspace)[:2]
    assert {e["path"] for e in first["artifact_hashes"]} != {e["path"] for e in second["artifact_hashes"]}


def test_terminal_written_carries_no_artifact_hashes(ready_workspace):
    dispatch_once(ready_workspace)
    dispatch_once(ready_workspace)
    terminal = [e for e in _events(ready_workspace) if e["type"] == "terminal_written"]
    assert terminal and terminal[-1]["artifact_hashes"] == []
```

  Define `ready_workspace` (a scaffolded contract with an events.db projected to `execute-task`, one passing task whose `verify` is a real workspace script) and `two_task_workspace` as module-level `@pytest.fixture`s built from `scripts/test_runner_dispatch.py`'s existing setup helper — read that file and reuse, do not reinvent.

- [ ] **Step 2: Run it — expect 9 failures** (`artifact_hashes == []`, `KeyError: 'object'`).
- [ ] **Step 3: Implement** in `dispatch_once` (`loop/runner.py:245-276`). Move `iteration_id = projection["iteration_id"] + 1` above the build, then:

```python
    built = emit.build_verify_evidence(
        target, run_id=run_id, iteration_id=iteration_id, task=task,
        passed=outcome.passed, summary=outcome.summary, code_identity=code_identity,
        executor=executor, verifier_identity=verifier_identity, attempt=attempt)
    store = SQLiteEventStore(paths.loop_dir / "events.db")
    _store_append(store, run_id, "iteration_appended", payload, actor="loop.run",
                  artifact_hashes=list(built.artifact_hashes),
                  expected_sequence=projection["last_sequence"] + 1)
    try:
        written = emit.write_verify_evidence(
            target, run_id=run_id, iteration_id=iteration_id, task=task,
            passed=outcome.passed, summary=outcome.summary, code_identity=code_identity,
            executor=executor, verifier_identity=verifier_identity, attempt=attempt,
            built=built)
    except (OSError, emit.EmitError) as exc:
        raise RunnerError(
            f"iteration {iteration_id} is committed to the event log but its verify "
            f"bundle could not be written: {exc}"
        ) from exc
```

  Wrap the `build_verify_evidence` call in `except emit.EmitError as exc: raise RunnerError(f"cannot build the verify evidence for iteration {iteration_id}: {exc}") from exc` — the message must **not** say "committed", because nothing is. Extend the result dict with `"object": str(written["object"])`.
- [ ] **Step 4: Guard the event-shape change.** `grep -rn "artifact_hashes" scripts/` and confirm no existing test asserts `artifact_hashes == []` on a *dispatched* iteration; `grep -rn "dispatch_once(" scripts/ | head -40` and confirm no whole-dict equality on the `dispatched` action (`scripts/test_loop_simulate_cli.py` compares whole-dict only on `blocked`, per the Slice-2 audit — re-verify rather than trusting this line).
- [ ] **Step 5: Run the gate.** `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_evidence_binding_runner.py scripts/test_runner_dispatch.py scripts/test_adversarial_process.py scripts/test_loop_simulate_zero_writes.py` — the new file **9 passed**; the three existing files green and byte-unmodified. The crash-injection pin is the one that matters: the builder writes nothing, so a SIGKILL at the pre-commit `COMMIT` still leaves a byte-identical tree.
- [ ] **Step 6:** Commit: `feat(runner): bind evidence digests into the iteration event before writing them`.

**Acceptance:** +9 passed in both sets; `scripts/test_runner_dispatch.py`, `scripts/test_adversarial_process.py`, `scripts/test_loop_simulate_zero_writes.py` byte-unmodified and green.

---

### Task 3: `loop/runtime.py` — the bound-evidence walk

**Files:** Modify `loop/runtime.py`; Create `scripts/test_doctor_evidence_binding.py`.

- [ ] **Step 1: Write the failing tests** — `scripts/test_doctor_evidence_binding.py`:

```python
"""Doctor's chain-binding walk: bound artifacts must still be the bytes that were bound."""
from __future__ import annotations

import json

import pytest

from loop.contract import doctor_report
from loop.runner import dispatch_once

try:                                  # the repo's fallback-mode convention
    import jsonschema                 # noqa: F401
    _HAS_JSONSCHEMA = True
except ImportError:                   # pragma: no cover - exercised in the fallback leg
    _HAS_JSONSCHEMA = False

_MODES = [pytest.param("basic"),
          pytest.param("strict", marks=pytest.mark.skipif(not _HAS_JSONSCHEMA,
                                                          reason="jsonschema not installed"))]


def _codes(report):
    return {issue["code"] for issue in report["issues"]}


def _tree(workspace):
    return sorted(str(p.relative_to(workspace)) for p in workspace.rglob("*") if p.is_file())


def test_absent_store_adds_no_binding_issue(scaffolded_workspace):
    assert doctor_report(scaffolded_workspace)["event_store"] == {"present": False}


@pytest.mark.parametrize("mode", _MODES)
def test_a_clean_runner_dispatch_is_doctor_clean(ready_workspace, mode):
    dispatch_once(ready_workspace)
    report = doctor_report(ready_workspace, mode=mode)
    assert report["ok"] is True and report["issues"] == []


def test_rewriting_a_bound_bundle_is_reported(ready_workspace):
    dispatch_once(ready_workspace)
    (ready_workspace / ".loop" / "artifacts" / "verify-iter1.json").write_text(
        json.dumps({"outcome": "PASS", "passed": True}), encoding="utf-8")
    assert "evidence_chain_mismatch" in _codes(doctor_report(ready_workspace))


def test_rewriting_a_bound_record_is_reported(ready_workspace):
    dispatch_once(ready_workspace)
    path = ready_workspace / ".loop" / "evidence" / "evidence-iter1.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["verified_by"]["by"] = "somebody-else"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert "evidence_chain_mismatch" in _codes(doctor_report(ready_workspace))


def test_deleting_a_bound_pair_is_reported(ready_workspace):
    dispatch_once(ready_workspace)
    (ready_workspace / ".loop" / "artifacts" / "verify-iter1.json").unlink()
    (ready_workspace / ".loop" / "evidence" / "evidence-iter1.json").unlink()
    assert "missing_bound_evidence" in _codes(doctor_report(ready_workspace))


def test_the_object_survives_and_is_named_as_the_recovery_source(ready_workspace):
    dispatch_once(ready_workspace)
    (ready_workspace / ".loop" / "artifacts" / "verify-iter1.json").write_text("{}", encoding="utf-8")
    messages = " ".join(issue["message"] for issue in doctor_report(ready_workspace)["issues"])
    assert "objects/" in messages
    assert any(p.startswith(".loop/artifacts/objects/")
               for p in _tree(ready_workspace))


@pytest.mark.parametrize("mode", _MODES)
def test_a_legacy_event_without_artifact_hashes_is_not_a_finding(legacy_workspace, mode):
    report = doctor_report(legacy_workspace, mode=mode)
    assert "missing_bound_evidence" not in _codes(report)
    assert "evidence_chain_mismatch" not in _codes(report)


def test_binding_check_writes_nothing(ready_workspace):
    dispatch_once(ready_workspace)
    before = _tree(ready_workspace)
    doctor_report(ready_workspace)
    assert _tree(ready_workspace) == before


def test_binding_issues_never_add_a_doctor_key(ready_workspace):
    dispatch_once(ready_workspace)
    (ready_workspace / ".loop" / "artifacts" / "verify-iter1.json").unlink()
    report = doctor_report(ready_workspace)
    assert set(report["event_store"]) == {
        "present", "readable", "run_id", "event_count", "state_json_agrees",
        "deterministic", "legal_sequence", "chain"}


def test_a_store_that_cannot_be_read_still_reports_its_own_error_code(corrupt_store_workspace):
    report = doctor_report(corrupt_store_workspace)
    assert report["event_store"]["readable"] is False
    assert "missing_bound_evidence" not in _codes(report)
```

  `legacy_workspace` is a dispatched contract whose `artifact_hashes` were emptied by rebuilding the store from an unbound append (append the same payload with `artifact_hashes=None`); `corrupt_store_workspace` reuses the fixture shape already used by `scripts/test_doctor_eventstore.py` — read it and copy.

- [ ] **Step 2: Run it — expect exactly 4 failing items** out of the **12** collected: the two rewrite cases, the delete-pair case, and the object-recovery-message case. The other eight (absent-store, clean-dispatch ×2, legacy ×2, zero-write, key-shape, unreadable-store) pass **vacuously** today — with no detector wired, doctor reports nothing, and "reports nothing" is what seven of them assert. That is the signal to watch: a vacuous pass here is only meaningful because Step 4's mutation probe (Task 7 Step 4) later proves the four detection items die when the detector is stubbed. *(Counts recomputed during the post-review pass; the earlier "6 failures" over "11 collected" was arithmetic drift.)*
- [ ] **Step 3: Implement** in `loop/runtime.py`. Append:

```python
def _bound_evidence_issues(target: str | Path, mode: str | None) -> list[dict[str, Any]]:
    """Re-hash every artifact an event bound into the chain.

    Driven by what each event DECLARES: a legacy event carries an empty
    artifact_hashes list and is silent by construction, because the append-only
    triggers make a retroactive binding impossible (repo-os-contract.md #22).
    """
    _, _run_id, events, _validation = _events(target, mode)
    workspace = resolve_loop_paths(target).workspace
    issues: list[dict[str, Any]] = []
    for event in events:
        for entry in event.get("artifact_hashes") or []:
            path = workspace / entry["path"]
            try:
                blob = path.read_bytes()
            except OSError:
                issues.append(ContractIssue(
                    "missing_bound_evidence",
                    f"event {event['event_id']} (sequence {event['sequence']}) bound "
                    f"{entry['path']} into the chain but it is absent or unreadable"))
                continue
            actual = hashlib.sha256(blob).hexdigest()
            if actual != entry["sha256"]:
                issues.append(ContractIssue(
                    "evidence_chain_mismatch",
                    f"{entry['path']} does not match the digest bound at sequence "
                    f"{event['sequence']}: expected {entry['sha256']}, found {actual} — "
                    f"the original bytes may remain at "
                    f".loop/artifacts/objects/{entry['sha256'][:2]}/{entry['sha256']}"))
    return issues
```

  Add `import hashlib` at the top. Add the shared lookup decision 14 needs beside it — one traversal, two consumers, so the binding walk and the strict completion mode can never disagree about what "bound" means:

```python
def bound_artifact_digests(target: str | Path, mode: str | None = None) -> dict[str, str] | None:
    """{workspace-relative POSIX path: sha256} for every artifact any event bound.

    None means there is no event store, and the caller MUST degrade explicitly and say
    so (decision 14) rather than treat absence as satisfaction. An empty dict means a
    store exists and bound nothing. An unreadable store raises RuntimeStoreError — an
    errored check fails, it never skips (R007).
    """
    if not (resolve_loop_paths(target).loop_dir / "events.db").is_file():
        return None
    _, _run_id, events, _validation = _events(target, mode)
    return {entry["path"]: entry["sha256"]
            for event in events for entry in event.get("artifact_hashes") or []}
```

  Compose the walk inside `event_consistency_issues` at the readable branch (`loop/runtime.py:311`), immediately after `issues = list(status["divergence"]) + list(replay["findings"])`:

```python
    issues.extend(_bound_evidence_issues(target, mode))
```

  It runs only inside the readable branch, so an absent or unreadable store is untouched and the returned `event_store` dict is unchanged (decision 8). The extra read-only fold is decision 9's recorded cost.
- [ ] **Step 4: Run the gate.** `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_doctor_evidence_binding.py scripts/test_doctor_eventstore.py scripts/test_loop_cli_status_replay.py` — the new file **12 passed** (extras) / **10 passed 2 skipped** (fallback); the two existing files byte-unmodified and green.

  The count is 12, not 10: the block above defines ten `def test_`s, two of which carry `@pytest.mark.parametrize("mode", _MODES)` and contribute **two** collected items each (`basic` + `strict`), so 8×1 + 2×2 = **12**. The `strict` halves are the two that skip without jsonschema. Re-derive this yourself before accepting the number — a stated count that disagrees with `pytest --collect-only -q` is a stop-and-explain under Task 9 Step 8.
- [ ] **Step 5:** Commit: `feat(doctor): verify the evidence digests bound into the event chain`.

**Acceptance:** +12 passed extras / +10 passed +2 skipped fallback; `scripts/test_doctor_eventstore.py` byte-unmodified, including its absent-store byte-stability pin at `:107`.

---

### Task 4: `loop/contract.py` — hash-verify records, compare the policy digest

**Files:** Modify `loop/contract.py`, `scripts/test_doctor_evidence.py` (helpers only); Create `scripts/test_doctor_evidence_verification.py`.

- [ ] **Step 1: Repair the Slice-2 fixtures FIRST — this is a predictable, planned break.** `scripts/test_doctor_evidence.py:17-46` builds records whose `sha256` is the literal `"c" * 64` while `_ws` writes bundles containing `{"outcome": "PASS", "passed": true}`. Once doctor hash-verifies, every one of that file's record-bearing tests gains a `hash_mismatch` and roughly eight assertions break. Replace the two helpers so the pair is consistent, changing **no test body and adding no test**:

```python
_BUNDLE_TEXT = json.dumps({"outcome": "PASS", "passed": True})
_BUNDLE_SHA = hashlib.sha256(_BUNDLE_TEXT.encode("utf-8")).hexdigest()


def _record(executor="worker-a", by="ci", **overrides):
    record = {
        "schema": "loop-engineer/evidence@1", "id": "e1", "kind": "verify-bundle",
        "uri": ".loop/artifacts/verify-iter5.json", "sha256": _BUNDLE_SHA,
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
    artifacts = target / ".loop" / "artifacts"
    if records:
        directory = target / ".loop" / "evidence"
        directory.mkdir(parents=True, exist_ok=True)
        for index, record in enumerate(records):
            text = record if isinstance(record, str) else json.dumps(record)
            (directory / f"evidence-iter{index}.json").write_text(text, encoding="utf-8")
        # Every _record() names this uri; doctor now hash-verifies it, so it must exist
        # with exactly the bytes the record commits to.
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "verify-iter5.json").write_text(_BUNDLE_TEXT, encoding="utf-8")
    for bundle_name in bundles:
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / bundle_name).write_text(_BUNDLE_TEXT, encoding="utf-8")
    return target
```

  `verify-iter5.json` now always exists when records do, so `test_a_bundle_whose_record_was_deleted_is_reported` (`:115`) must keep passing a bundle name that has no record — re-run that file and reconcile before moving on. The scaffolded TASKS.json contains no task `T-1`, so decision 5's live-entry rule keeps every one of those tests out of the `policy_digest_mismatch` path.

- [ ] **Step 2: Write the failing tests** — `scripts/test_doctor_evidence_verification.py` (same `_MODES` preamble as Task 3):

```python
"""Doctor hash-verifies discovered records and compares their policy digest to TASKS.json."""
from __future__ import annotations

import hashlib
import json

import pytest

from loop.contract import doctor_report
from loop.scaffold import scaffold
from loop.verifier import verification_policy_digest

# ... _MODES / _codes preamble as in Task 3 ...

_TASK = {"id": "T-1", "title": "t", "status": "pending", "criterion_ref": "C-1",
         "verify": "./scripts/verify-fast.sh", "depends_on": [], "attempts": 0, "evidence": None}


def _ws(tmp_path, *, records, bundle_text='{"outcome": "PASS", "passed": true}', tasks=(_TASK,)):
    target = tmp_path / "workspace"
    scaffold(target)
    (target / "TASKS.json").write_text(json.dumps(
        {"schema": "loop-engineer/tasks@1", "project": "p", "tasks": list(tasks)}), encoding="utf-8")
    (target / ".loop" / "artifacts").mkdir(parents=True, exist_ok=True)
    (target / ".loop" / "artifacts" / "verify-iter1.json").write_text(bundle_text, encoding="utf-8")
    directory = target / ".loop" / "evidence"
    directory.mkdir(parents=True, exist_ok=True)
    for iteration_id, record in records:
        (directory / f"evidence-iter{iteration_id}.json").write_text(
            json.dumps(record), encoding="utf-8")
    return target


def _record(*, iteration_id=1, policy_digest=None, uri=".loop/artifacts/verify-iter1.json",
            sha256=None, task_id="T-1"):
    text = '{"outcome": "PASS", "passed": true}'
    return {
        "schema": "loop-engineer/evidence@1", "id": f"run-1:{iteration_id}:verify",
        "kind": "verify-bundle", "uri": uri,
        "sha256": sha256 or hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "media_type": "application/json", "created_at": "2026-07-25T00:00:00+00:00",
        "produced_by": {"run_id": "run-1", "task_id": task_id, "attempt": 1,
                        "executor": "worker-a"},
        "verified_by": {"by": "ci", "at": "2026-07-25T00:00:00+00:00",
                        "command": "./scripts/verify-fast.sh", "code_digest": None,
                        "code_digest_basis": "path_lookup",
                        "policy_digest": policy_digest or verification_policy_digest(_TASK)},
    }


@pytest.mark.parametrize("mode", _MODES)
def test_a_hash_verified_record_is_clean(tmp_path, mode):
    target = _ws(tmp_path, records=[(1, _record())])
    assert doctor_report(target, mode=mode)["ok"] is True


@pytest.mark.parametrize("mode", _MODES)
def test_a_swapped_bundle_fails_doctor_with_hash_mismatch(tmp_path, mode):
    target = _ws(tmp_path, records=[(1, _record())])
    (target / ".loop" / "artifacts" / "verify-iter1.json").write_text("{}", encoding="utf-8")
    assert "hash_mismatch" in _codes(doctor_report(target, mode=mode))


def test_a_record_whose_uri_is_absent_reports_missing_evidence_path(tmp_path):
    target = _ws(tmp_path, records=[(1, _record(uri=".loop/artifacts/gone.json"))])
    assert "missing_evidence_path" in _codes(doctor_report(target))


def test_a_record_whose_uri_escapes_the_workspace_reports_workspace_escape(tmp_path):
    target = _ws(tmp_path, records=[(1, _record(uri="../escape.json"))])
    assert _codes(doctor_report(target)) & {"workspace_escape", "missing_evidence_path"}


@pytest.mark.parametrize("mode", _MODES)
def test_policy_digest_mismatch_against_the_live_task(tmp_path, mode):
    moved = dict(_TASK, verify="true")
    target = _ws(tmp_path, records=[(1, _record())], tasks=(moved,))
    assert "policy_digest_mismatch" in _codes(doctor_report(target, mode=mode))


def test_policy_digest_agreement_is_silent(tmp_path):
    target = _ws(tmp_path, records=[(1, _record())])
    assert "policy_digest_mismatch" not in _codes(doctor_report(target))


def test_only_the_latest_record_per_task_is_compared(tmp_path):
    stale = _record(iteration_id=1, policy_digest="d" * 64)
    current = _record(iteration_id=2)
    target = _ws(tmp_path, records=[(1, stale), (2, current)])
    assert "policy_digest_mismatch" not in _codes(doctor_report(target))


def test_a_record_naming_an_unknown_task_is_not_compared(tmp_path):
    target = _ws(tmp_path, records=[(1, _record(task_id="T-404", policy_digest="d" * 64))])
    assert "policy_digest_mismatch" not in _codes(doctor_report(target))


def test_a_record_without_a_policy_digest_is_not_compared(tmp_path):
    record = _record()
    record["verified_by"]["policy_digest"] = None
    target = _ws(tmp_path, records=[(1, record)])
    assert "policy_digest_mismatch" not in _codes(doctor_report(target))


@pytest.mark.parametrize("mode", _MODES)
def test_evidence_schema_id_still_joins_schemas_checked(tmp_path, mode):
    target = _ws(tmp_path, records=[(1, _record())])
    assert "loop-engineer/evidence@1" in doctor_report(target, mode=mode)["schemas_checked"]
```

- [ ] **Step 3: Run it — expect 5 failures** (`hash_mismatch`, `missing_evidence_path`, `workspace_escape`, and the two `policy_digest_mismatch` items).
- [ ] **Step 4: Implement** in `loop/contract.py`, inside `_validate_evidence_records` (`:684-711`). The hash-verification call is **guarded** — it runs only for records that produced **no** structural issues. This is not optional tidiness: `verify_evidence()` internally re-runs `validate_evidence(record, mode="basic")` and emits its own `invalid_evidence`/`invalid_uri` issues, so calling it unconditionally would report a malformed record twice and break `scripts/test_doctor_evidence.py`'s existing single-finding assertions. Capture the per-record result of the existing loop instead of discarding it:

```python
        from .evidence import verify_evidence   # local: loop.evidence imports this module

        record_issues = evidence_issues(data, resolved_mode=mode)      # was an unbound loop
        for issue in record_issues:
            issues.append(ContractIssue(issue["code"],
                                        f"{record_path.name}: {issue['message']}", record_path))
        if not record_issues:                                          # <- the guard
            result = verify_evidence(data, workspace_root=paths.workspace)
            if not result["ok"]:
                for issue in result["issues"]:
                    issues.append(ContractIssue(issue["code"],
                                                f"{record_path.name}: {issue['message']}",
                                                record_path))
```

  Read `:684-711` before editing: the existing loop already appends its issues, so the change is to **bind** its result to `record_issues` rather than to add a second traversal. If the live shape differs from the sketch, keep the *semantics* — structural issues reported exactly once, hash verification attempted only on a structurally-valid record — and adapt the code (AC prose is normative; the sketch is illustrative).

  Collect `(iteration_id, record_path, data)` for every structurally-valid record, where `iteration_id` is the integer parsed from `evidence-iter([0-9]+)\.json` (`None` for any other filename — a foreign record is verified but never policy-compared), and pass the list to:

```python
def _policy_digest_issues(paths: LoopPaths, records, issues: list[dict]) -> None:
    """Compare the LATEST record per task against the live TASKS.json goalpost.

    Only the latest record backs the task's current claim; older records describe
    goalposts that were current when they were written, and comparing them would
    make every honest re-verification a permanent failure (plan decision 5).
    """
    from .verifier import verification_policy_digest

    tasks = _read_json(paths.tasks, [])
    entries = {t["id"]: t for t in (tasks or {}).get("tasks", [])
               if isinstance(t, dict) and isinstance(t.get("id"), str)}
    latest: dict[str, tuple[int, Path, dict]] = {}
    for iteration_id, record_path, data in records:
        task_id = data.get("produced_by", {}).get("task_id")
        if not isinstance(task_id, str) or task_id not in entries:
            continue
        key = (iteration_id if isinstance(iteration_id, int) else -1, record_path.name)
        if task_id not in latest or key > (latest[task_id][0], latest[task_id][1].name):
            latest[task_id] = (key[0], record_path, data)
    for task_id, (_iteration_id, record_path, data) in sorted(latest.items()):
        recorded = (data.get("verified_by") or {}).get("policy_digest")
        if not isinstance(recorded, str):
            continue
        try:
            live = verification_policy_digest(entries[task_id])
        except ChainHashError:
            continue          # a non-canonicalizable task entry is TASKS.json's own defect
        if live != recorded:
            issues.append(ContractIssue(
                "policy_digest_mismatch",
                f"{record_path.name}: the goalpost recorded for task {task_id!r} "
                f"({recorded}) is not the live TASKS.json goalpost ({live}) — "
                f"the declared verify/criterion_ref/depends_on/id changed after this "
                f"verification; re-verify to record the current goalpost",
                record_path))
```

  Import `ChainHashError` from `.chain` at the top of `contract.py`. Call `_policy_digest_issues` at the end of `_validate_evidence_records`, before its `return checked`.
- [ ] **Step 5: Dogfood check.** `uv run --with pyyaml python3 -B -m loop doctor examples/coverage-repair` and `... examples/flaky-test-triage` — both still `ok: true`. Neither ships a `.loop/evidence/` directory, so both are untouched by construction; verify rather than assume.
- [ ] **Step 6: Run the gate.** `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_doctor_evidence_verification.py scripts/test_doctor_evidence.py scripts/test_contract_records.py scripts/test_loop_contract_core.py` — the new file **14 passed** extras / **10 passed 4 skipped** fallback; `test_doctor_evidence.py` green at its **unchanged test count** (helpers only).
- [ ] **Step 7:** Commit: `feat(doctor): hash-verify discovered evidence and compare the recorded goalpost`.

**Acceptance:** +14 passed extras / +10 passed +4 skipped fallback; `scripts/test_doctor_evidence.py`'s diff touches `_record`/`_ws`/imports only (verify with `git diff -U0 scripts/test_doctor_evidence.py`); both dogfood examples doctor-clean.

---

### Task 5: `Succeeded` tightens — the verified-evidence completion mode

**Files:** Modify `loop/completion.py`, `loop/emit.py`, `loop/contract.py`, `loop/reducer.py`, `loop/integrations.py`, `loop/runner.py`, `schemas/terminal.schema.json`; Create `scripts/test_completion_verified_evidence.py`.

- [ ] **Step 1: Write the failing tests** — `scripts/test_completion_verified_evidence.py` (same `_MODES`/`_codes` preamble):

```python
"""all_required_verified_evidence: the same bar at four layers, each as strong as it can be."""
from __future__ import annotations

import hashlib
import json

import pytest

from loop import emit, integrations
from loop.completion import (VERIFIED_EVIDENCE_MODE, normalize_completion_policy,
                             policy_requires_verified_evidence)
from loop.contract import doctor_report
from loop.reducer import EventReplayError, reduce_events
from loop.runner import dispatch_once
from loop.verifier import verification_policy_digest

# ... _MODES / _codes preamble as in Task 3; _dispatched_workspace fixtures from Task 2 ...


def test_the_new_mode_is_supported_and_normalizes():
    assert normalize_completion_policy(VERIFIED_EVIDENCE_MODE) == {"mode": VERIFIED_EVIDENCE_MODE}
    assert policy_requires_verified_evidence({"mode": VERIFIED_EVIDENCE_MODE}) is True


def test_legacy_null_policy_still_normalizes_to_all_required():
    assert normalize_completion_policy(None) == {"mode": "all_required"}
    assert policy_requires_verified_evidence(None) is False


def test_terminate_refuses_unverified_evidence_under_the_new_mode(dispatched_workspace):
    with pytest.raises(emit.EmitError, match="verified evidence"):
        emit.terminate(dispatched_workspace, state="Succeeded", criteria_met={"C-1": True},
                       evidence=["RUNLOG.md"], completion_policy=VERIFIED_EVIDENCE_MODE)


def test_terminate_accepts_hash_verified_evidence_under_the_new_mode(dispatched_workspace):
    path = emit.terminate(dispatched_workspace, state="Succeeded", criteria_met={"C-1": True},
                          evidence=[".loop/evidence/evidence-iter1.json"],
                          completion_policy=VERIFIED_EVIDENCE_MODE)
    assert json.loads(path.read_text(encoding="utf-8"))["completion_policy"] == {
        "mode": VERIFIED_EVIDENCE_MODE}


def test_terminate_under_the_default_mode_is_unchanged(dispatched_workspace):
    path = emit.terminate(dispatched_workspace, state="Succeeded", criteria_met={"C-1": True},
                          evidence=["RUNLOG.md"])
    assert json.loads(path.read_text(encoding="utf-8"))["completion_policy"] == {
        "mode": "all_required"}


@pytest.mark.parametrize("mode", _MODES)
def test_doctor_reports_unverified_evidence_terminal(dispatched_workspace, mode):
    emit.terminate(dispatched_workspace, state="Succeeded", criteria_met={"C-1": True},
                   evidence=[".loop/evidence/evidence-iter1.json"],
                   completion_policy=VERIFIED_EVIDENCE_MODE)
    (dispatched_workspace / ".loop" / "artifacts" / "verify-iter1.json").write_text(
        "{}", encoding="utf-8")
    assert "unverified_evidence_terminal" in _codes(doctor_report(dispatched_workspace, mode=mode))


# --- decision 14: hash-verified is NOT enough when the layer can reach further ---

def _handwritten_record(workspace, *, name="evidence-iter9.json", task_id="T-1"):
    """A self-consistent, never-dispatched record: real bundle, real digest, real policy."""
    bundle = workspace / ".loop" / "artifacts" / "verify-iter9.json"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    text = '{"outcome": "PASS", "passed": true}'
    bundle.write_text(text, encoding="utf-8")
    tasks = json.loads((workspace / "TASKS.json").read_text(encoding="utf-8"))
    entry = next(t for t in tasks["tasks"] if t["id"] == task_id)
    record = {
        "schema": "loop-engineer/evidence@1", "id": "hand:9:verify", "kind": "verify-bundle",
        "uri": ".loop/artifacts/verify-iter9.json",
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "media_type": "application/json", "created_at": "2026-07-25T00:00:00+00:00",
        "produced_by": {"run_id": "run-1", "task_id": task_id, "attempt": 1,
                        "executor": "worker-a"},
        "verified_by": {"by": "ci", "at": "2026-07-25T00:00:00+00:00",
                        "command": entry["verify"], "code_digest": None,
                        "code_digest_basis": "path_lookup",
                        "policy_digest": verification_policy_digest(entry)},
    }
    path = workspace / ".loop" / "evidence" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return f".loop/evidence/{name}"


def test_terminate_refuses_a_hash_verified_but_unbound_record_when_a_store_exists(
        dispatched_workspace):
    """The BLOCKER case: self-consistency is not dispatch. No event bound this record."""
    entry = _handwritten_record(dispatched_workspace)
    with pytest.raises(emit.EmitError, match="not bound"):
        emit.terminate(dispatched_workspace, state="Succeeded", criteria_met={"C-1": True},
                       evidence=[entry], completion_policy=VERIFIED_EVIDENCE_MODE)


def test_terminate_refuses_a_cited_record_whose_goalpost_moved(dispatched_workspace):
    """Per-cited-record, deliberately stricter than doctor's latest-per-task rule."""
    tasks_path = dispatched_workspace / "TASKS.json"
    data = json.loads(tasks_path.read_text(encoding="utf-8"))
    data["tasks"][0]["verify"] = "true"
    tasks_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(emit.EmitError, match="goalpost"):
        emit.terminate(dispatched_workspace, state="Succeeded", criteria_met={"C-1": True},
                       evidence=[".loop/evidence/evidence-iter1.json"],
                       completion_policy=VERIFIED_EVIDENCE_MODE)


def test_doctor_reports_an_unbound_record_cited_by_a_strict_terminal(dispatched_workspace):
    """Read-time twin of the write-time refusal — same predicate, one definition.

    The terminal file is hand-written, not emitted: emit.terminate REFUSES this exact
    record (the test above), so the only way a strict terminal citing an unbound record
    reaches disk is a worker writing it directly — which is the adversary being modelled.
    """
    entry = _handwritten_record(dispatched_workspace)
    (dispatched_workspace / ".loop" / "terminal_state.json").write_text(json.dumps({
        "schema": "loop-engineer/terminal@1", "project": dispatched_workspace.name,
        "state": "Succeeded", "criteria_met": {"C-1": True},
        "completion_policy": {"mode": VERIFIED_EVIDENCE_MODE}, "evidence": [entry],
        "false_completion": False, "terminated_at": "2026-07-25T00:00:00+00:00",
        "reason": "hand-written"}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert "unverified_evidence_terminal" in _codes(doctor_report(dispatched_workspace))


def _terminal_event(evidence, mode):
    return [{"schema": "loop-engineer/event@1", "run_id": "r", "sequence": 0, "event_id": "e0",
             "type": "contract_opened", "actor": "op", "ts": "2026-07-25T00:00:00+00:00",
             "causation_id": None, "correlation_id": None, "payload": {"workspace": "ws"},
             "artifact_hashes": []},
            {"schema": "loop-engineer/event@1", "run_id": "r", "sequence": 1, "event_id": "e1",
             "type": "terminal_written", "actor": "op", "ts": "2026-07-25T00:00:01+00:00",
             "causation_id": None, "correlation_id": None, "artifact_hashes": [],
             "payload": {"state": "Succeeded", "criteria_met": {"C-1": True},
                         "evidence": evidence, "false_completion": False,
                         "completion_policy": {"mode": mode}}}]


def test_the_reducer_refuses_a_non_record_evidence_entry_under_the_new_mode():
    with pytest.raises(EventReplayError, match="verified evidence"):
        reduce_events(_terminal_event(["RUNLOG.md"], VERIFIED_EVIDENCE_MODE))


def test_the_reducer_accepts_record_shaped_evidence_under_the_new_mode():
    projection = reduce_events(
        _terminal_event([".loop/evidence/evidence-iter1.json"], VERIFIED_EVIDENCE_MODE))
    assert projection["terminal"]["state"] == "Succeeded"


def test_integrations_projection_refuses_non_record_evidence_under_the_new_mode():
    outcome = integrations.EngineOutcome(reached_end=True, artifacts=("RUNLOG.md",))
    body = integrations.to_terminal_state(
        outcome, {"verdict": "Succeeded", "passed_visible": True, "passed_holdout": True,
                  "false_completion": False,
                  "visible": [{"id": "C-1", "passed": True}],
                  "holdout": [{"id": "H-1", "passed": True}]},
        {"severity": "none", "findings": []}, {"C-1": True},
        completion_policy=VERIFIED_EVIDENCE_MODE)
    assert body["state"] == "FailedUnverifiable" and "verified evidence" in body["reason"]


def test_runner_auto_terminal_adopts_the_verified_mode_when_every_task_has_a_record(ready_workspace):
    dispatch_once(ready_workspace)
    dispatch_once(ready_workspace)
    terminal = json.loads((ready_workspace / ".loop" / "terminal_state.json")
                          .read_text(encoding="utf-8"))
    assert terminal["completion_policy"] == {"mode": VERIFIED_EVIDENCE_MODE}
    assert terminal["evidence"] == [".loop/evidence/evidence-iter1.json"]


def test_runner_auto_terminal_keeps_all_required_when_a_task_has_no_record(predone_workspace):
    dispatch_once(predone_workspace)
    terminal = json.loads((predone_workspace / ".loop" / "terminal_state.json")
                          .read_text(encoding="utf-8"))
    assert terminal["completion_policy"] == {"mode": "all_required"}
    assert terminal["evidence"] == ["RUNLOG.md"]
    assert "no evidence record" in terminal["reason"]


@pytest.mark.parametrize("mode", _MODES)
def test_terminal_schema_accepts_both_modes(dispatched_workspace, mode):
    emit.terminate(dispatched_workspace, state="Succeeded", criteria_met={"C-1": True},
                   evidence=[".loop/evidence/evidence-iter1.json"],
                   completion_policy=VERIFIED_EVIDENCE_MODE)
    assert doctor_report(dispatched_workspace, mode=mode)["ok"] is True
```

  `predone_workspace` is a contract whose only task is already `status: "done"` with a declared `evidence` string, so the auto-terminal fires with zero dispatched iterations. When hand-writing `terminal_state.json`, mirror the exact key set `emit.terminate` produces (`loop/emit.py:311-320`) — read it rather than copying the sketch above, or the record fails terminal@1 validation for the wrong reason and the test proves nothing.

- [ ] **Step 2: Run it — expect all 17 collected items to fail at import** (`ImportError: cannot import name 'VERIFIED_EVIDENCE_MODE'`); a collection-time failure is the honest starting point for a module that does not exist yet.
- [ ] **Step 3: Implement `loop/completion.py`.** `CompletionMode` becomes `Literal["all_required", "all_required_verified_evidence"]`; `SUPPORTED_COMPLETION_MODES` gains the new member; `criteria_satisfy_completion`'s branch becomes `if normalized["mode"] in SUPPORTED_COMPLETION_MODES:` with the identical all-required body (the criteria half is deliberately shared, and the `raise AssertionError` exhaustiveness guard stays). Add:

```python
VERIFIED_EVIDENCE_MODE: Final[CompletionMode] = "all_required_verified_evidence"
_RECORD_PREFIX = ".loop/evidence/"


def policy_requires_verified_evidence(policy: object | None = None) -> bool:
    """True when this policy's evidence bar is hash-verified records, not path strings."""
    return normalize_completion_policy(policy)["mode"] == VERIFIED_EVIDENCE_MODE


def evidence_entry_is_record_shaped(entry: object) -> bool:
    """The structural half of the bar — the most a pure, I/O-free layer can honestly check."""
    return (isinstance(entry, str) and entry.startswith(_RECORD_PREFIX)
            and entry.endswith(".json") and ".." not in entry)
```

- [ ] **Step 4: Implement the four enforcement layers.** The two workspace-bearing layers share **one** predicate — write it once as `loop/contract.py::_strict_evidence_failure(entry, paths, bound)` returning `None` or a detail string, and have `emit.terminate` import it function-locally. Two hand-written copies of a three-part security check will drift, and a drift here is a silent false completion.

  The three sub-checks, in order (decision 14):
  1. **Self-consistency** — the entry resolves under `paths.workspace`, `json.loads`, `validate_evidence(..., mode="basic")` is `ok`, and `verify_evidence(..., workspace_root=paths.workspace)` is `ok`. Detail: `"is not verified evidence: {…}"`.
  2. **Chain-boundness** — `bound = runtime.bound_artifact_digests(paths.workspace)` (function-local import; `loop/runtime.py` imports `loop/contract.py` at module level, so the reverse edge must stay local — the same rule the doctor-events wiring already follows). When `bound is not None`, the entry's path must be a key of `bound` **and** `bound[entry]` must equal the sha256 of the record file's current bytes. Detail: `"is not bound into the event chain"` / `"is bound at a different digest"`. When `bound is None` there is no store and this sub-check is **skipped** — the pinned store-less residual.
  3. **Goalpost agreement** — when `produced_by.task_id` names a task still present in TASKS.json, `verified_by.policy_digest` must equal `verification_policy_digest` of that live entry. Detail: `"records a goalpost that is not the live TASKS.json goalpost"`. Unlike doctor's latest-per-task rule (decision 5), this is per-cited-record: a terminal citing a record is asserting it backs `Succeeded` *now*.

  - `loop/emit.py::terminate`, inside the `state == "Succeeded"` block (`:294-304`), after the existing evidence check: when `policy_requires_verified_evidence(normalized_policy)`, call the predicate per entry and raise `EmitError(f"refusing Succeeded under {VERIFIED_EVIDENCE_MODE}: {entry} {detail}")` on the first failure. Note the ordering constraint: `paths` is resolved at `:306`, *after* the G1 block — move `paths = _require_contract(target)` above the `if state == "Succeeded":` block, which is safe because `_require_contract` only reads. A `RuntimeStoreError` from `bound_artifact_digests` becomes an `EmitError` — an unreadable store is a refusal, never a skip (R007).
  - `loop/contract.py`: new `_check_verified_evidence_terminal(terminal, paths, issues)` calling the same predicate and appending `ContractIssue("unverified_evidence_terminal", …)` with the returned detail; call it from `validate_contract` immediately after `records_checked = _validate_optional_records(...)` (`:814`), guarded by `if terminal is not None`. Here a `RuntimeStoreError` is **not** raised out of doctor: the unreadable-store path already reports its own `readable: False` + error code (`loop/runtime.py`), so catch it and append `unverified_evidence_terminal` with "the event store could not be read" as the detail — still a finding, never a silent pass.
  - `loop/reducer.py::_validate_terminal_payload_semantics` (`:47-49`): after the existing non-empty check, `if policy_requires_verified_evidence(payload.get("completion_policy")) and not all(evidence_entry_is_record_shaped(e) for e in evidence): raise EventReplayError("Succeeded terminal declares verified evidence but an entry is not a .loop/evidence record (G1)")`.
  - `loop/integrations.py::to_terminal_state` (`:170-173`): before the `if not artifacts:` branch, `if policy_requires_verified_evidence(normalized_policy) and not all(evidence_entry_is_record_shaped(a) for a in artifacts): return body("FailedUnverifiable", "green gate but an evidence artifact is not verified evidence — cannot certify")`.
- [ ] **Step 5: Implement the runner's auto-terminal** (`loop/runner.py:219-233`). Before building the payload, collect `records = [f".loop/evidence/evidence-iter{e['iteration_id']}.json" for e in projection["runlog_entries"] if e.get("outcome") == "task_passed"]` filtered to those that exist on disk, and map each to its task. When every task id in `tasks` has at least one such record, write `completion_policy: {"mode": VERIFIED_EVIDENCE_MODE}` with `evidence` = the sorted record list; otherwise keep `{"mode": "all_required"}`, `evidence: ["RUNLOG.md"]`, and set `payload["reason"] = "tasks with no evidence record: " + ", ".join(sorted(missing))`. Never silently downgrade without the reason (decision 7).
- [ ] **Step 6: `schemas/terminal.schema.json`** `:78-82`: `"mode": {"enum": ["all_required", "all_required_verified_evidence"]}`. `default` and `required` untouched.
- [ ] **Step 7: Compat sweep.** Run `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_completion_policy.py scripts/test_integrations.py scripts/test_reducer.py scripts/test_emit.py scripts/test_loop_contract_core.py` — all green and byte-unmodified. Then re-run the dogfood: both examples' terminals carry no `completion_policy`, normalize to `all_required`, and stay clean.
- [ ] **Step 8: Run the gate.** `uv run ... scripts/test_completion_verified_evidence.py` — **17 passed** extras / **15 passed 2 skipped** fallback. (17 = 15 single tests + one `parametrize(_MODES)` test contributing 2; the three decision-14 tests are single-mode because the predicate is mode-independent — it reads records and the store, not a schema.)
- [ ] **Step 9:** Commit: `feat(completion): all_required_verified_evidence — Succeeded on bound, hash-verified records`.

**Acceptance:** +17 passed extras / +15 passed +2 skipped fallback; the five compat suites byte-unmodified and green; both dogfood examples still `ok: true` with `completion_policy` absent from their records; `_strict_evidence_failure` has exactly **one** definition (`grep -rn "is not bound into the event chain" loop/` returns one file).

---

### Task 6: `scripts/metrics.py` — `verifier.source` decides gate evidence

**Files:** Modify `scripts/metrics.py`; Create `scripts/test_metrics_verifier_source.py`.

- [ ] **Step 1: Write the failing tests** — `scripts/test_metrics_verifier_source.py`:

```python
"""An injected-callable verdict is a caller's self-report, not gate evidence."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metrics import compute_metrics                                    # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent


def _bundle(source=None, *, green=True, task="T1", iteration_id=1):
    body = {"iteration_id": iteration_id, "task": task,
            "outcome": "PASS" if green else "FAIL", "passed": green, "score": 1.0 if green else 0.0}
    if source is not None:
        body["verifier"] = {"by": "loop.run", "source": source}
    return body


def _ws(tmp_path, bundles):
    target = tmp_path / "workspace"
    (target / ".loop" / "artifacts").mkdir(parents=True, exist_ok=True)
    (target / "RUNLOG.md").write_text(
        "# RUNLOG\n\n## Iteration 1 — 2026-07-25\n\n### Outcome\n\n`task_passed`\n",
        encoding="utf-8")
    (target / ".loop" / "state.json").write_text(json.dumps(
        {"schema": "loop-engineer/state@1", "state": "execute-task", "iteration_id": 1,
         "terminal_state": None}), encoding="utf-8")
    for name, body in bundles:
        (target / ".loop" / "artifacts" / name).write_text(json.dumps(body), encoding="utf-8")
    return target


def test_a_declared_command_bundle_is_gate_evidence(tmp_path):
    target = _ws(tmp_path, [("verify-iter1.json", _bundle("declared_command"))])
    assert compute_metrics(target)["false_completion_rate"] == 0.0


def test_an_injected_callable_bundle_is_not_gate_evidence(tmp_path):
    target = _ws(tmp_path, [("verify-iter1.json", _bundle("injected_callable"))])
    assert compute_metrics(target)["provenance"]["injected_verifier_bundles"] == ["verify-iter1.json"]


def test_an_injected_only_claim_is_a_false_completion(tmp_path):
    target = _ws(tmp_path, [("verify-iter1.json", _bundle("injected_callable"))])
    assert compute_metrics(target)["false_completion_rate"] == 1.0


def test_a_legacy_bundle_without_a_verifier_block_still_counts(tmp_path):
    target = _ws(tmp_path, [("verify-iter1.json", _bundle(None))])
    metrics = compute_metrics(target)
    assert metrics["false_completion_rate"] == 0.0
    assert metrics["provenance"]["injected_verifier_bundles"] == []


def test_excluded_bundles_are_named_under_provenance(tmp_path):
    target = _ws(tmp_path, [("verify-iter1.json", _bundle("injected_callable")),
                            ("verify-iter2.json", _bundle("declared_command", iteration_id=1))])
    assert compute_metrics(target)["provenance"]["injected_verifier_bundles"] == ["verify-iter1.json"]


def test_injected_bundles_do_not_anchor_a_repair(tmp_path):
    target = _ws(tmp_path, [("verify-iter1.json", _bundle("injected_callable", green=False)),
                            ("verify-iter2.json", _bundle("injected_callable"))])
    assert compute_metrics(target)["repair_productivity"] is None


def test_the_shipped_examples_keep_their_published_metrics():
    metrics = compute_metrics(_ROOT / "examples" / "flaky-test-triage")
    assert metrics["false_completion_rate"] == 0.0
    assert metrics["repair_productivity"] == 1.0
```

- [ ] **Step 2: Run it — expect 5 failures** (`KeyError: 'injected_verifier_bundles'` and the FCR/RP deltas).
- [ ] **Step 3: Implement.** In `_load_verify_bundles` (`scripts/metrics.py:230-252`), read the source alongside the green marker and carry it:

```python
        verifier = data.get("verifier")
        source = verifier.get("source") if isinstance(verifier, dict) else None
```

  and add `"source": source` to the appended dict. In `compute_metrics` (`:458`), partition immediately after loading:

```python
    all_bundles = _load_verify_bundles(loop_dir_path)
    injected = sorted(b["name"] for b in all_bundles if b["source"] == "injected_callable")
    bundles = [b for b in all_bundles if b["source"] != "injected_callable"]
```

  Everything downstream (`_assign_bundles_to_iters`, `_claim_is_clean`, `_anchor_repair`) keeps consuming `bundles` unchanged, so an injected-only claim has no attached bundle and `_claim_is_clean` returns `False` at `:507-508` — a false completion, which is the honest reading. Add `injected` to the `provenance` block as `"injected_verifier_bundles"`.
- [ ] **Step 4: Verify the dogfood numbers did not move.** Re-run Task 0 Step 7's two commands and diff against the recorded scorecards. Both examples' bundles carry no `verifier` block, so `source is None` and nothing is excluded — decision 13's grandfathering. A movement in either number is a stop-and-explain.
- [ ] **Step 5: Run the gate.** `uv run ... scripts/test_metrics_verifier_source.py scripts/test_metrics.py scripts/test_metrics_cli.py` — the new file **7 passed**; the two existing files byte-unmodified and green.
- [ ] **Step 6:** Commit: `feat(metrics): an injected-callable verdict is not gate evidence`.

**Acceptance:** +7 passed in both sets; `scripts/test_metrics.py` and `scripts/test_metrics_cli.py` byte-unmodified; both examples' FCR/RP/`evidence_backed` identical to the Task 0 recording.

---

### Task 7: Adversarial pins — the mandated flips and what binding still misses

**Files:** Modify `scripts/test_adversarial_verifier_identity.py` (4 tests rewritten in place, none deleted); Create `scripts/test_adversarial_evidence_binding.py`.

- [ ] **Step 1: Flip the four Slice-2 pins in place.** Each keeps its residual half and gains the detection half; each docstring names the release in which the behavior changed. Net new tests: **0**.

```python
def test_rewriting_the_evidence_record_is_caught_only_when_the_chain_binds_it(tmp_path, bound_workspace):
    """Was `..._leaves_doctor_clean_pinned` in v0.11.0. A record written by the writer API
    with no event store behind it is STILL a plain file and a rewrite is STILL invisible.
    A record a dispatch bound into the chain is not: its bytes are covered by event_hash.
    """
    workspace = _ws(tmp_path)                                   # writer API, no event store
    written = _write(workspace, executor="solo", verifier_identity="solo")
    record = json.loads(written["evidence"].read_text(encoding="utf-8"))
    record["verified_by"]["by"] = "ci"
    written["evidence"].write_text(json.dumps(record), encoding="utf-8")
    assert "evidence_chain_mismatch" not in _codes(doctor_report(workspace))   # residual
    bound = bound_workspace["record"]                           # dispatched, chain-bound
    data = json.loads(bound.read_text(encoding="utf-8"))
    data["verified_by"]["by"] = "ci"
    bound.write_text(json.dumps(data), encoding="utf-8")
    assert "evidence_chain_mismatch" in _codes(doctor_report(bound_workspace["workspace"]))


def test_deleting_both_bundle_and_record_is_caught_only_when_the_chain_binds_them(tmp_path, bound_workspace):
    """Was `..._leaves_doctor_clean_pinned` in v0.11.0. Without an event log nothing
    remembers the dispatch happened, so the pair-deletion is still invisible; with one,
    the committed event names artifacts that are gone (missing_bound_evidence).
    """
    workspace = _ws(tmp_path)
    written = _write(workspace, executor="w", verifier_identity="w")
    written["evidence"].unlink()
    assert "missing_evidence_record" in _codes(doctor_report(workspace))
    written["bundle"].unlink()
    assert doctor_report(workspace)["ok"] is True                              # residual
    bound_workspace["record"].unlink()
    bound_workspace["bundle"].unlink()
    assert "missing_bound_evidence" in _codes(doctor_report(bound_workspace["workspace"]))


def test_policy_digest_comparison_fires_only_against_a_live_task_entry(tmp_path):
    """Was `test_no_automated_digest_comparison_exists_pinned` in v0.11.0. The comparison
    now exists, and its two silences are the honest limitation: a record naming a task
    TASKS.json no longer declares, and any record that is not the latest for its task.
    """
    workspace = _ws(tmp_path)
    _write(workspace, iteration_id=1, task=_task())                # task T-1 is not in TASKS.json
    _write(workspace, iteration_id=2, task=_task(verify="true"))
    assert "policy_digest_mismatch" not in _codes(doctor_report(workspace))    # residual
    tasks = workspace / "TASKS.json"
    tasks.write_text(json.dumps({"schema": "loop-engineer/tasks@1", "project": "p",
                                 "tasks": [_task(status="pending")]}), encoding="utf-8")
    assert "policy_digest_mismatch" in _codes(doctor_report(workspace))


def test_doctor_hash_verifies_the_referenced_bundle(tmp_path):
    """Was `test_doctor_does_not_hash_verify_the_referenced_bundle_pinned` in v0.11.0.
    doctor now composes verify_evidence and surfaces its hash_mismatch verbatim.
    """
    workspace = _ws(tmp_path)
    written = _write(workspace, passed=False)
    written["bundle"].write_text(json.dumps({"outcome": "PASS", "passed": True}), encoding="utf-8")
    assert "hash_mismatch" in _codes(doctor_report(workspace))
```

  `test_hand_written_record_with_a_fabricated_code_digest_is_doctor_clean_pinned` (`:95`) keeps its name and body — a hand-written record whose `uri` resolves and whose digests are shaped correctly is still clean — but its docstring gains one sentence naming what *is* now checked (the bundle's bytes and, for a live task, the goalpost). The remaining five pins are unaffected; re-run them and confirm.

- [ ] **Step 2: Write the new pins** — `scripts/test_adversarial_evidence_binding.py`, 14 tests. Each `*_pinned` name states the honest limitation in its docstring; the non-pinned ones prove a real detection.

```python
"""What chain-bound evidence catches, and what it provably does not.

The claim this file defends is "evidence whose bytes are bound into an ANCHORABLE
chain", never "tamper-proof evidence". Binding inherits Slice 1's trust model
exactly: a worker who can rewrite .loop/ can rewrite the store (repo-os-contract
#16, Integrity boundary), so without an external anchor a full rewrite verifies.
"""
```

  1. `test_a_full_rewrite_of_artifacts_and_store_is_not_caught_without_an_anchor_pinned` — rewrite the bundle, recompute the record, `DROP TRIGGER`, rewrite the row's `artifact_hashes` and re-chain the tail; assert `doctor_report(ws)["ok"] is True`.
  2. `test_an_anchored_head_catches_the_full_rewrite` — the positive control: the same rewrite with `doctor_report(ws, expect_chain_head=<pre-rewrite head>)` reports `chain_anchor_mismatch`.
  3. `test_a_record_written_outside_a_dispatch_is_never_chain_bound_pinned` — `emit.write_verify_evidence` called directly leaves no event; rewriting it is invisible.
  4. `test_a_legacy_iteration_event_can_never_be_bound_retroactively_pinned` — an event committed with empty `artifact_hashes` stays silent; the append-only triggers forbid the UPDATE that would fix it.
  5. `test_doctor_does_not_re_hash_the_verifier_file_pinned` — editing `scripts/verify-fast.sh` after a dispatch leaves doctor clean; `code_digest` stays in the recorded-not-compared tier.
  6. `test_an_older_record_for_a_moved_goalpost_is_not_compared_pinned` — the latest-per-task rule's cost, with the positive control that the latest record *is* compared.
  7. `test_deleting_the_object_alone_is_reported` — the object is a bound artifact; deleting it fires `missing_bound_evidence`.
  8. `test_deleting_every_artifact_and_the_store_leaves_a_clean_doctor_pinned` — with sidecars removed too, a fully-deleted run is a valid never-ran contract (`reference/repo-os-contract.md:1200-1202`).
  9. `test_the_verified_evidence_mode_is_opt_in_and_not_retroactive_pinned` — a Succeeded terminal written under `all_required` with `evidence: ["RUNLOG.md"]` stays clean.
  10. `test_a_hand_written_record_pointing_at_a_real_file_still_passes_pinned` — hash verification proves the pointer, never the provenance.
  11. `test_criterion_text_is_still_unbound_pinned` — editing SPEC.md's acceptance wording changes no digest.
  12. `test_metrics_still_counts_a_hand_written_declared_command_bundle_pinned` — `verifier.source` is a self-declared string; writing `declared_command` by hand restores gate-evidence status.
  13. `test_the_strict_mode_accepts_a_hand_written_record_in_a_store_less_contract_pinned` — **decision 14's named residual.** Scaffold a contract with no `.loop/events.db`, write a self-consistent record through the writer API, and terminate under `all_required_verified_evidence`: it is **accepted**, because nothing can chain-bind where nothing records. Positive control in the same test: the identical hand-written record in a *store-bearing* contract is refused with "not bound". Without the control this pin would document a hole instead of bounding one.
  14. `test_a_full_rewrite_satisfies_the_strict_mode_without_an_anchor_pinned` — the headline residual restated at the completion layer: rewrite bundle, record and the store's `artifact_hashes` row, re-chain the tail, and `terminate(..., VERIFIED_EVIDENCE_MODE)` succeeds. Positive control: the same tree with `doctor_report(ws, expect_chain_head=<pre-rewrite head>)` reports `chain_anchor_mismatch`. This is the pin that keeps the shipped claim *"bound into an anchorable chain"* and forbids *"tamper-proof"*.

- [ ] **Step 2b: Discharge carry-forward 11** — add **one** test to `scripts/test_verifier_identity.py`, beside the existing argv[0] symlink-loop pin at `:65`: build a workspace whose **root** is a symlink loop, call `verifier_code_digest("./scripts/verify-fast.sh", workspace)`, and assert `(None, "unresolvable")`. `loop/verifier.py:64` resolves the root inside the same `try` as argv[0], so this passes on both 3.10-3.12 (pathlib `RuntimeError`) and 3.13 (`OSError` from `stat`) — the pin exists to keep that `try` boundary from being narrowed later, which is precisely how Slice 2's Task-1 Critical was born. Net new: **+1** collected item in an existing file.

- [ ] **Step 3: Run the gate.** `uv run ... scripts/test_adversarial_evidence_binding.py scripts/test_adversarial_verifier_identity.py scripts/test_verifier_identity.py` — **14 passed**; **19 passed** (the identity file's count is unchanged from Slice 2 — only four bodies moved); and `test_verifier_identity.py` at `BASE + 1`.
- [ ] **Step 4: Prove the pins are non-vacuous — deterministic mutation probes with stated kill counts.** Stub each detector, re-run, revert, and record the counts in the PR body:

```bash
bash -c "cd /mnt/c/Dev/projects/loop-engineer && \
  python3 - <<'PY'
import pathlib
p = pathlib.Path('loop/runtime.py'); s = p.read_text(encoding='utf-8')
p.write_text(s.replace('    issues.extend(_bound_evidence_issues(target, mode))',
                       '    pass  # mutation probe', 1), encoding='utf-8')
PY
  uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider \
    scripts/test_doctor_evidence_binding.py scripts/test_adversarial_evidence_binding.py \
    scripts/test_adversarial_verifier_identity.py; \
  git checkout -- loop/runtime.py"
```

  **Five probes, with predicted kill counts.** Every number below is a *prediction*, not an observation — run each probe, record the observed count next to the prediction in the PR body, and treat a shortfall as a lost control and an excess as an over-broad detector. **Neither is a number to quietly overwrite** (Task 9 Step 8's rule applies here too; the Slice-2 review's standing lesson is that negative-control claims must be confirmed empirically, not derived on paper).

  | # | Stub | Predicted kills |
  |---|---|---|
  | 1 | `issues.extend(_bound_evidence_issues(target, mode))` → `pass` | **7** — 4 in `test_doctor_evidence_binding.py` (rewrite-bundle, rewrite-record, delete-pair, object-recovery-message), 1 in `test_adversarial_evidence_binding.py` (#7 object deletion), 2 in `test_adversarial_verifier_identity.py` (both flipped pins' detection halves) |
  | 2 | `_policy_digest_issues` body → `return` | **3** — 2 in `test_doctor_evidence_verification.py`, 1 flipped pin |
  | 3 | the `verify_evidence` composition in `_validate_evidence_records` removed | **5** |
  | 4 | `_strict_evidence_failure`'s **chain-boundness** sub-check → always pass | **3** — the two decision-14 refusal tests in `test_completion_verified_evidence.py`, plus pin 13's positive control |
  | 5 | `_strict_evidence_failure`'s **goalpost** sub-check → always pass | **1** — `test_terminate_refuses_a_cited_record_whose_goalpost_moved` |

  Probes 4 and 5 are the ones that matter most: they are the only evidence that decision 14 is enforced rather than described. A probe that kills zero means that file is decorative. Confirm `git status` is clean after each.
- [ ] **Step 5:** Commit: `test(adversarial): flip the four closed pins and pin what binding still misses`.

**Acceptance:** +14 passed in `scripts/test_adversarial_evidence_binding.py` in both sets and +1 in `scripts/test_verifier_identity.py`; `scripts/test_adversarial_verifier_identity.py`'s collected count is unchanged from `BASE`; no `*_pinned` test was deleted (`git diff` shows four renames with bodies, not removals); all five mutation probes run, with predicted **and observed** kill counts recorded side by side in the PR body.

---

### Task 8: Docs — the tier movements, the four codes, the retired claims

**Files:** Modify `reference/repo-os-contract.md` (§16, §17, §22), `reference/safety-and-approvals.md`, `loop/evidence.py` (docstring), `schemas/evidence.schema.json` (description), `README.md`; extend `scripts/test_conformance.py`.

> **Standing instruction for every step in this task:** before editing any sentence this plan quotes as "current", re-read that line in the live file and confirm the quote still matches. Task 0 already applies this discipline to test counts; it applies here for the same reason. Three citations in the pre-review draft of this plan had already drifted — two of them (M-1's literal fork, M-12's "three honest tiers" heading) were fixed in Slice 2's own pre-merge wave *after* the review transcript this plan cites, and a fourth (M-7's `unresolvable` row) likewise. A quote that no longer matches is a **stop-and-record**, not a stop-and-edit: append it to the carry-forward table as already-resolved so the PR body cannot claim it.

- [ ] **Step 1: §16 — bind the artifacts, and fix the stale event-type list.** `reference/repo-os-contract.md:624-627` claims *"Event types: `contract_opened | iteration_appended | receipt_appended | terminal_written` — one-to-one with `loop.emit`'s four writer operations"*. The live enum has **nine** members (`loop/events.py:18-19`). Replace with the nine, noting that the first four are one-to-one with `loop.emit`'s writer operations and the rest are run-control and administrative corrections. Then add one paragraph under `### Hash chain (v0.10.0+)`: *"`artifact_hashes` is field eleven of the preimage, so any digest an appender places there is covered by `event_hash` and by `--expect-chain-head`. Since the evidence-wiring release a verified dispatch binds three entries — the verify bundle, its content-addressed object, and the evidence@1 record — computed **before** the append and written **after** it. An event that binds nothing (every event written before that release, and every append by a foreign writer) is silent by construction: the append-only triggers forbid the UPDATE a retroactive binding would need, exactly as `loop migrate` refuses to backfill hashes."*
- [ ] **Step 2: §17 — replace the scope boundary** (`:837-841`), which now states two false things. New text: *"`loop doctor` reads evidence@1 records from the declared location `.loop/evidence/*.json`, validates them, **hash-verifies the artifact each one references**, and compares the `policy_digest` of the latest record per task against the live `TASKS.json` entry. `Succeeded` still requires non-empty evidence *paths* under the default `all_required` policy; under the opt-in `all_required_verified_evidence` policy it requires every entry to be a hash-verified evidence@1 record that — where an event store exists — some event bound into the hash chain, and whose recorded goalpost matches the live task."*
- [ ] **Step 3: §17 — the content-addressed object and the bound set.** New subsection `### Bound evidence (v0.12.0+)` documenting: the three-entry `artifact_hashes` set and its order; that the object location is `artifact_object_path(workspace, record["sha256"])` — *derived, never stored, so evidence@1 gains no field* — and that the object is the recovery source when the friendly-named bundle is swapped; that objects are created once and a differing-bytes collision is a typed refusal, never an overwrite; and the ordering rule *"build (no I/O) → append (binds) → write (object, staged bundle, record, replace)"* with its two consequences: a build failure commits nothing, and a crash after the commit leaves a detectable `missing_bound_evidence` rather than a silent gap.
- [ ] **Step 4: §17 — the completion-mode subsection.** Document `all_required_verified_evidence`: the four enforcement layers and the honest reason each is as strong as it is (emit and doctor reach a workspace *and* the event store; the reducer and `to_terminal_state` check only the `.loop/evidence/*.json` shape because they are pure and must not pretend to touch a filesystem); that legacy and default records normalize to `all_required` and are untouched; and that `loop run`'s auto-terminal adopts the strict mode only when every task has an evidence record, and otherwise says in `reason` which tasks did not.

  **This subsection must carry decision 14's exact bar and its exact limits — one paragraph, no hedging.** The strict mode proves three things about every cited entry: the record is structurally valid, the artifact it names hashes to the digest it declares, and — *when an event store exists* — that record's bytes are the bytes some event bound into the hash chain; plus, when the record names a live task, that its recorded goalpost is the live one. It proves **none** of: that a human or an independent runner produced it (a hand-written record whose pointer resolves and whose digests are self-consistent still satisfies the mode in a **store-less** contract — say this plainly, and name `missing_event_store` as the tripwire that catches deleting a store out from under a real run); that the chain itself was not rewritten (a worker who can rewrite `.loop/` can rewrite the store, so **without `--expect-chain-head` a full rewrite satisfies the strict mode** — this is the same anchor dependency Slice 1 shipped, not a new one); or that the two pure layers enforce any of it (they check shape only). State that the mode's strength is therefore **store-dependent and anchor-dependent**, and that the pins holding each limit are `test_the_strict_mode_accepts_a_hand_written_record_in_a_store_less_contract_pinned` and `test_a_full_rewrite_satisfies_the_strict_mode_without_an_anchor_pinned`. Also name the deliberate asymmetry with decision 5: the terminal check is **per-cited-record**, doctor's general goalpost check is **latest-per-task**, and the reason is that citing a record is a present-tense claim.
- [ ] **Step 5: §17 — rewrite the integrity boundary, naming every tier movement.** Keep the four-tier shape. **The heading needs no fix** — `:951` already reads *"The integrity boundary, in four honest tiers"*; review finding M-12 was discharged before PR #94 merged (carry-forward row 7). Confirm that in the live file, then edit the four bullets' *content* only:
  - **Fails `loop doctor`** — now additionally: a discovered record whose referenced artifact does not match its `sha256` (`hash_mismatch`) or does not resolve at all (`missing_evidence_path`); a record whose recorded goalpost disagrees with the live task (`policy_digest_mismatch`); a chain-bound artifact whose bytes changed (`evidence_chain_mismatch`) or vanished (`missing_bound_evidence`); a Succeeded terminal under the strict policy whose evidence does not verify (`unverified_evidence_terminal`).
  - **Recorded for later comparison, not checked by any shipped surface** — now **only** `code_digest`, and the reason it stays: the verifier file legitimately changes between runs, so comparing it without a declared baseline would fire on every honest edit. `policy_digest` has left this tier.
  - **Detectable only by explicitly calling `verify_evidence()`** — this tier is now **empty**; doctor composes the call. Say so, and say which release moved it.
  - **Not surfaced at all** — retain: a false `verified_by.by`; an omitted executor; a hand-written record whose pointer resolves (verification proves the pointer, never the provenance); criterion *text*. Add the new residuals: a record written through the writer API with no event behind it is never bound; a legacy event can never be bound retroactively; an older record for a task whose goalpost moved is not compared; **a hand-written record satisfies `all_required_verified_evidence` in a contract that has no event store, because there is nothing to bind against** (decision 14's named degradation — `missing_event_store` is what catches removing a store from a run that had one); and — the headline — **a worker who can rewrite `.loop/` can rewrite the store, so without `--expect-chain-head` a full rewrite of artifacts *and* chain verifies clean, including under the strict completion mode.** Binding makes tampering detectable against an anchor, not impossible.
  - Close with: *"This does not make evidence tamper-proof. It binds evidence bytes into a chain someone outside the worker's trust domain can anchor, and it fails closed when what is on disk is not what was verified."*
- [ ] **Step 6: §17 — retire the FCR sentence.** `:926-929` currently says *"`scripts/metrics.py` does not read `verifier.source` today … enforcing that distinction is Slice 3 scope."* Replace: *"`scripts/metrics.py` reads `verifier.source`: a bundle whose source is `injected_callable` is excluded from the FCR input set and named under `provenance.injected_verifier_bundles`. A bundle with no `verifier` block at all has an unknown source and still counts — grandfathering by absence, not by guess. `verifier.source` is a self-declared string, so a hand-written `declared_command` restores gate-evidence status; that is pinned as a limitation."*
- [ ] **Step 7: §22 — four new rows**, in the existing table style at `:1134-1141`:

```
| `evidence_chain_mismatch` | An artifact whose digest an event bound into the hash chain no longer matches its bytes on disk. The original bytes may remain in the content-addressed object store. |
| `missing_bound_evidence` | An event bound an artifact path into the chain and that path is now absent or unreadable — a deleted pair, or the sanctioned crash window between the durable append and the evidence write. Only fires for events that bound something; a legacy event binds nothing and is silent. |
| `policy_digest_mismatch` | The latest evidence record for a task records a `policy_digest` that is not the live `TASKS.json` goalpost — the declared `verify`/`criterion_ref`/`depends_on`/`id` changed after the verification. Re-verify to record the current goalpost. |
| `unverified_evidence_terminal` | A `Succeeded` terminal declaring `completion_policy.mode: all_required_verified_evidence` has an evidence entry that fails one of the mode's three checks: it is not a hash-verified evidence@1 record; or (when an event store exists) no event bound those bytes into the chain; or the record's `policy_digest` is not the live `TASKS.json` goalpost for the task it names. The message names which. In a contract with no event store the middle check is skipped — the mode's strength is store-dependent by construction. |
```

  Plus a "do not confuse" note: `missing_evidence_record` walks bundles looking for their record; `missing_evidence_path` comes out of `verify_evidence` and means a *record's* `uri` does not resolve — the two are opposite directions of the same pair.
- [ ] **Step 8: Retire the false claims on the shipped surfaces.** `loop/evidence.py:3-8` and `schemas/evidence.schema.json:5` both still say doctor *"does not yet hash-verify the artifacts those records reference"*. Rewrite both to state what is now true and what still is not (no `code_digest` re-hash; no proof of provenance). `reference/safety-and-approvals.md` §5: append one sentence noting the goalpost half of the invariant now has a machine check too (`policy_digest_mismatch`), and that the protected-file and canary rules remain load-bearing because a rename still evades.
- [ ] **Step 9: README** — extend the event-sourced-runtime bullet with one sentence: *"a verified dispatch binds its evidence digests into the hash chain, and `loop doctor` re-hashes them"*, plus one honest clause: *"binding makes tampering detectable against an anchor, not impossible — without `--expect-chain-head` a worker who can rewrite `.loop/` can rewrite the chain too."* Do not touch the "how it compares" heading or the FCR/RP markers (`structural.json` `readme_differentiation` pins them).
- [ ] **Step 10: Pin the docs** — append 4 tests to `scripts/test_conformance.py`:

```python
def test_documented_artifact_binding_vector_matches_the_writer(tmp_path):
    """The three bound paths and their order are normative, not incidental."""
    workspace = _binding_fixture(tmp_path)
    built = emit.build_verify_evidence(workspace, run_id="run-1", iteration_id=1,
                                       task=_VECTOR_TASK, passed=True,
                                       code_identity=injected_verifier_identity())
    assert [entry["path"] for entry in built.artifact_hashes] == [
        ".loop/artifacts/verify-iter1.json",
        f".loop/artifacts/objects/{built.sha256[:2]}/{built.sha256}",
        ".loop/evidence/evidence-iter1.json"]
    doc = (ROOT / "reference" / "repo-os-contract.md").read_text(encoding="utf-8")
    assert ".loop/artifacts/objects/" in doc


def test_every_new_doctor_code_is_documented_in_section_22():
    doc = (ROOT / "reference" / "repo-os-contract.md").read_text(encoding="utf-8")
    for code in ("evidence_chain_mismatch", "missing_bound_evidence",
                 "policy_digest_mismatch", "unverified_evidence_terminal"):
        assert f"`{code}`" in doc


def test_no_shipped_surface_still_claims_evidence_is_unverified():
    for path in (ROOT / "loop" / "evidence.py", ROOT / "schemas" / "evidence.schema.json",
                 ROOT / "reference" / "repo-os-contract.md"):
        text = path.read_text(encoding="utf-8")
        assert "does not yet hash-verify" not in text
        assert "not checked by any shipped surface:** `policy_digest`" not in text
    # decision 14: the strict mode's two residuals must be named where the mode is
    # documented, not only in this plan. A capability paragraph without its limits is
    # the overclaim this slice exists to prevent.
    contract = (ROOT / "reference" / "repo-os-contract.md").read_text(encoding="utf-8")
    assert "no event store" in contract and "--expect-chain-head" in contract
    assert "detectable against an anchor" in contract
    # Deliberately NOT asserting the absence of "tamper-proof": §17 names it as the
    # forbidden claim, so a substring ban would fire on the honesty sentence itself.


def test_section_16_event_type_list_matches_the_code():
    from loop.events import EVENT_TYPES
    doc = (ROOT / "reference" / "repo-os-contract.md").read_text(encoding="utf-8")
    assert all(f"`{name}`" in doc or name in doc for name in EVENT_TYPES)
    assert "one-to-one with `loop.emit`'s four writer operations" not in doc
```

- [ ] **Step 11: Run the gates.** `uv run --with pyyaml python3 -B scripts/self_eval.py` (**13/13** — proves no structural pin was disturbed), `uv run --with pyyaml python3 -B scripts/validate_frontmatter.py` (**9/9**), and `uv run ... scripts/test_conformance.py scripts/test_docs_adoption.py scripts/test_docs_claims.py scripts/test_docs_baseline.py`.
- [ ] **Step 12:** Commit: `docs(contract): bound evidence, the verified-evidence policy, and the moved tiers`.

**Acceptance:** +4 passed in both sets; self_eval 13/13; frontmatter 9/9; §17's boundary heading matches its bullet count; the "Detectable only by explicitly calling `verify_evidence()`" tier is documented as empty with the release that emptied it named.

---

### Task 9: Full-suite gate + feature PR

**Files:** none new.

- [ ] **Step 1: Extras suite.** `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts` — expect `BASE_EXTRAS.passed + 90` passed, `BASE_EXTRAS.skipped` skipped.
- [ ] **Step 2: Fallback suite.** `uv run --with pyyaml --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts` — expect `BASE_FALLBACK.passed + 82` passed, `BASE_FALLBACK.skipped + 8` skipped.

| Task | new collected tests | jsonschema halves (skip in fallback) | how it decomposes |
|---|---|---|---|
| 1 | 12 | 0 | 12 single |
| 2 | 9 | 0 | 9 single |
| 3 | 12 | 2 | 8 single + 2 `parametrize(_MODES)` × 2 |
| 4 | 14 | 4 | 6 single + 4 `parametrize(_MODES)` × 2 = 6 + 8 |
| 5 | 17 | 2 | 15 single (incl. 3 decision-14 tests) + 1 `parametrize(_MODES)` × 2 |
| 6 | 7 | 0 | 7 single |
| 7 | 15 | 0 | 14 new pins + 1 in `test_verifier_identity.py` (Step 2b) |
| 8 | 4 | 0 | 4 single |
| **total** | **90** | **8** | |

  Arithmetic the implementer must reproduce: 12+9+12+14+17+7+15+4 = **90**; 90 − 8 = **82** fallback passes. Every row counts *collected items* — a `parametrize("mode", _MODES)` test contributes **2**, and its `strict` half is what skips without jsonschema. Task 7's four flips and Task 4's fixture repair contribute **0**: they rewrite existing items.

  **Derive each row yourself with `pytest --collect-only -q <file>` before trusting it.** The pre-review draft of this table stated 11 for Task 3 against a block that collects 12, and the error propagated into the grand total — exactly the wasted reconciliation cycle Step 8 exists to catch. The decomposition column exists so that a mis-add is visible in the row rather than inherited by the total.

- [ ] **Step 3: Fresh-worktree verification.** `git -C /mnt/c/Dev/projects/loop-engineer/.tmp/s3-base checkout --detach feat/evidence-wiring`, re-run Steps 1-2 against `/mnt/c/Dev/projects/loop-engineer/.tmp/s3-base/scripts`, record both numbers with their dependency sets, then `git -C /mnt/c/Dev/projects/loop-engineer worktree remove /mnt/c/Dev/projects/loop-engineer/.tmp/s3-base`.
- [ ] **Step 4: Zero-regression spot checks.** `scripts/test_doctor_eventstore.py`, `scripts/test_event_chain.py`, `scripts/test_eventstore.py`, `scripts/test_reducer.py`, `scripts/test_adversarial_chain.py`, `scripts/test_adversarial_process.py`, `scripts/test_loop_simulate_zero_writes.py`, `scripts/test_metrics.py`, `scripts/test_verify_evidence_writer.py` green **and** byte-unmodified in `git diff --stat`.
- [ ] **Step 5: Dogfood.** `loop doctor` clean on `examples/coverage-repair` and `examples/flaky-test-triage`; `loop inspect examples/coverage-repair` still scores **90**; `scripts/metrics.py` on both examples identical to Task 0 Step 7.
- [ ] **Step 6: Interpreter matrix.** Run the kernel-touching test files under 3.10 and 3.13 (`uv run --python 3.10 ...`, `--python 3.13`) — Slice 2's Task-1 Critical was a version-dependent pathlib exception class, and this slice adds new `OSError` paths in the binding walk and the object store.
- [ ] **Step 7:** Push and open the PR **non-draft** (single `opened` event — the CI-wedge lesson): `feat(kernel): bound, hash-verified evidence and the verified-evidence completion policy (slice 3/5)`. The body carries the four-tier integrity boundary verbatim, the **five** mutation probes with predicted *and* observed kill counts, both fresh-worktree baselines with dependency sets named, the four flipped pins listed by old and new name, the behavior matrix below, and — required — one paragraph stating the strict completion mode's exact bar and its two residuals (store-less contracts, and no-anchor full rewrites). It must **not** claim M-1, M-7 or M-12 as fixed by this slice: all three were already resolved on `origin/main` (carry-forward rows 7 and 10).
- [ ] **Step 8:** Any count mismatch in either direction at Steps 1-2 is a **stop-and-explain**, not a number to adjust: re-derive the offending file's collected count and reconcile against the table before touching an acceptance line.

**Behavior matrix — each row names the test that proves it:**

| Situation | Surface | Expected | Test |
|---|---|---|---|
| no evidence, no bundle, no store | doctor | byte-identical to today | `test_absent_event_store_matches_pre_slice_doctor_shape` (unmodified), `test_absent_evidence_directory_is_a_byte_stable_no_op` (unmodified) |
| clean runner dispatch | doctor (both modes) | `ok` | `test_a_clean_runner_dispatch_is_doctor_clean` |
| bound bundle rewritten | doctor | `evidence_chain_mismatch` | `test_rewriting_a_bound_bundle_is_reported` |
| bound record rewritten | doctor | `evidence_chain_mismatch` (was clean in v0.11.0) | `test_rewriting_the_evidence_record_is_caught_only_when_the_chain_binds_it` |
| bound pair deleted | doctor | `missing_bound_evidence` (was clean in v0.11.0) | `test_deleting_both_bundle_and_record_is_caught_only_when_the_chain_binds_them` |
| record written via the writer API, then rewritten | doctor | **no finding** (pinned residual) | `test_a_record_written_outside_a_dispatch_is_never_chain_bound_pinned` |
| legacy event, empty `artifact_hashes` | doctor | **no finding** (pinned, unrepairable) | `test_a_legacy_iteration_event_can_never_be_bound_retroactively_pinned` |
| swapped bundle | doctor | `hash_mismatch` (was `verify_evidence`-only) | `test_doctor_hash_verifies_the_referenced_bundle` |
| record `uri` absent | doctor | `missing_evidence_path` | `test_a_record_whose_uri_is_absent_reports_missing_evidence_path` |
| goalpost moved, latest record | doctor (both modes) | `policy_digest_mismatch` | `test_policy_digest_mismatch_against_the_live_task` |
| goalpost moved, older record | doctor | **no finding** (pinned) | `test_only_the_latest_record_per_task_is_compared`, `test_an_older_record_for_a_moved_goalpost_is_not_compared_pinned` |
| record names an unknown task | doctor | **no finding** (pinned) | `test_a_record_naming_an_unknown_task_is_not_compared` |
| verifier file edited after the run | doctor | **no finding** — `code_digest` stays uncompared (pinned) | `test_doctor_does_not_re_hash_the_verifier_file_pinned` |
| full rewrite of artifacts + store, no anchor | doctor | `ok` (pinned headline residual) | `test_a_full_rewrite_of_artifacts_and_store_is_not_caught_without_an_anchor_pinned` |
| same rewrite, `--expect-chain-head` supplied | doctor | `chain_anchor_mismatch` | `test_an_anchored_head_catches_the_full_rewrite` |
| bundle swapped | object store | original bytes survive | `test_rewriting_the_bundle_leaves_the_object_intact` |
| object collision, different bytes | writer | typed `EmitError`, never an overwrite | `test_an_object_collision_with_different_bytes_raises_emit_error` |
| non-canonicalizable task | dispatch | build fails, **nothing committed** | `test_a_build_failure_commits_no_event` |
| evidence write fails post-commit | dispatch | typed `RunnerError` naming the committed iteration | `test_an_evidence_write_failure_after_the_commit_is_still_loud` |
| crash before the iteration commit | dispatch | byte-identical tree (unchanged pin) | `test_crash_injection_before_iteration_event_commit_leaves_no_partial_dispatch` |
| Succeeded, default policy, path evidence | emit / doctor | accepted (unchanged) | `test_terminate_under_the_default_mode_is_unchanged` |
| Succeeded, strict policy, path evidence | emit | `EmitError` | `test_terminate_refuses_unverified_evidence_under_the_new_mode` |
| Succeeded, strict policy, swapped artifact | doctor (both modes) | `unverified_evidence_terminal` | `test_doctor_reports_unverified_evidence_terminal` |
| Succeeded, strict policy, non-record entry | reducer / integrations | `EventReplayError` / `FailedUnverifiable` | `test_the_reducer_refuses_a_non_record_evidence_entry_under_the_new_mode`, `test_integrations_projection_refuses_non_record_evidence_under_the_new_mode` |
| Succeeded, strict policy, self-consistent but **unbound** record, store present | emit | `EmitError` naming "not bound" | `test_terminate_refuses_a_hash_verified_but_unbound_record_when_a_store_exists` |
| same, terminal hand-written past emit | doctor | `unverified_evidence_terminal` | `test_doctor_reports_an_unbound_record_cited_by_a_strict_terminal` |
| Succeeded, strict policy, cited record's goalpost moved | emit | `EmitError` naming "goalpost" | `test_terminate_refuses_a_cited_record_whose_goalpost_moved` |
| same, **no event store** (writer-API contract) | emit | accepted — the mode degrades to hash-verify + goalpost (pinned residual) | `test_the_strict_mode_accepts_a_hand_written_record_in_a_store_less_contract_pinned` |
| full rewrite of artifacts + store, strict policy, no anchor | emit / doctor | accepted (pinned headline residual) | `test_a_full_rewrite_satisfies_the_strict_mode_without_an_anchor_pinned` |
| workspace root is a symlink loop | `verifier_code_digest` | `(None, "unresolvable")` on 3.10-3.13 | Task 7 Step 2b's new pin in `scripts/test_verifier_identity.py` |
| every task has a record | auto-terminal | strict mode + record evidence | `test_runner_auto_terminal_adopts_the_verified_mode_when_every_task_has_a_record` |
| a task has no record | auto-terminal | `all_required` + a reason naming it | `test_runner_auto_terminal_keeps_all_required_when_a_task_has_no_record` |
| injected-callable bundle | metrics | excluded from FCR, named in provenance | `test_an_injected_callable_bundle_is_not_gate_evidence`, `test_an_injected_only_claim_is_a_false_completion` |
| bundle with no `verifier` block | metrics | still counts (grandfathered) | `test_a_legacy_bundle_without_a_verifier_block_still_counts` |
| hand-written `declared_command` | metrics | counts (pinned limitation) | `test_metrics_still_counts_a_hand_written_declared_command_bundle_pinned` |
| shipped examples | metrics / doctor / inspect | unchanged | `test_the_shipped_examples_keep_their_published_metrics`, Task 9 Step 5 |

---

### Task 10: Release cut (separate PR, after Task 9 merges) — OPERATOR-GATED

**Files:** Modify `pyproject.toml`, `.claude-plugin/plugin.json`, `README.md`, `scripts/test_docs_version.py`, `CHANGELOG.md`.

- [ ] **Step 1: Determine the version from the tree, not from this plan.** Read `pyproject.toml` `version`. If it reads `0.10.0`, the Slice-2 cut never ran and **this cut is `0.11.0`**, and its CHANGELOG entry must cover PR #94 *and* this slice (the Slice-2 plan's Task-9 CHANGELOG bullets are the input for the first half). If it reads `0.11.0`, Slice 2 was cut and **this is `0.12.0`**. Record the determination and the reason in the PR body; every later step uses `<VERSION>`.
- [ ] **Step 2:** Branch `release/v<VERSION>` off updated main; bump `version` in `pyproject.toml` and `.claude-plugin/plugin.json`.
- [ ] **Step 3: README version surfaces** — the release badge, the documented action pin (`SollanSystems/loop-engineer@v0.10.0` → `@v<VERSION>`), and the release/tag table rows.
- [ ] **Step 4:** `scripts/test_docs_version.py`: retarget the pin at `:20` to `<VERSION>` and add `"## <VERSION>"` to the CHANGELOG-headings assertion at `:42`.
- [ ] **Step 5: CHANGELOG `## <VERSION>`** — the bound `artifact_hashes` set and the content-addressed object store; doctor's hash verification and the composed `verify_evidence` codes; `policy_digest_mismatch` and its latest-record-per-task rule; `evidence_chain_mismatch` / `missing_bound_evidence`; the `all_required_verified_evidence` completion mode, its four enforcement layers, its three-part bar (hash-verified + chain-bound-when-a-store-exists + goalpost-agreeing), and the terminal@1 schema widening; `metrics.py`'s `verifier.source` exclusion and the FCR-input change it implies for any loop that dispatched with an injected verifier; and these explicit honesty notes: (a) binding makes tampering **detectable against an anchor**, not impossible — without `--expect-chain-head` a worker who can rewrite `.loop/` can rewrite the chain; (b) a legacy event can never be bound retroactively, so evidence deleted from a pre-release run stays undetectable; (c) `code_digest` is still never compared against a live re-hash; (d) the Succeeded tightening is **opt-in and not retroactive** — every existing terminal record normalizes to `all_required` and is unaffected; (e) doctor still proves the *pointer*, never the provenance: a hand-written record whose artifact exists and hashes correctly passes; and (f) the strict completion mode's strength is **store-dependent and anchor-dependent** — in a contract with no event store there is nothing to bind against, so a self-consistent hand-written record satisfies it, and with a store but no `--expect-chain-head` a worker who rewrites artifacts *and* chain satisfies it too. Note (f) is not optional polish: it is the difference between "Succeeded now requires proven work" (false) and "Succeeded now requires evidence bound into an anchorable chain" (true).
- [ ] **Step 6: Gates.** Full suite in both dependency sets + `python3 -m loop --version` smoke + `self_eval` 13/13 + both dogfood examples doctor-clean.
- [ ] **Step 7: Land.** PR, required checks, merge.
- [ ] **Step 8: Publish.** `git tag v<VERSION> <squash-sha> && git push origin v<VERSION>` → PyPI publish. If Step 1 determined `0.11.0`, the operator's standing Slice-2 gate is discharged by this tag; if it determined `0.12.0`, confirm `v0.11.0` is already published first. Verify `uvx loop-engineer@<VERSION> inspect examples/coverage-repair` from a scratch clone.
- [ ] **Step 9: Refresh the harness.** `git archive HEAD | tar -x -C <cache-dir>`; `diff -rq` to verify; restart Claude Code.

**Acceptance:** tag published, PyPI funnel verified from a scratch clone, plugin cache `diff -rq` clean, and the version determination recorded with its reason.

---

## Self-review

**Spec coverage vs the Slice-3 scope contract:**

| Scope item | Where |
|---|---|
| Content-addressed objects via `artifact_object_path` | Task 1 (writer + object store), decision 3 (derived, never stored — evidence@1 gains no field) |
| Doctor **hash-verifies** evidence referenced by criteria | Task 4 Step 4 (composed `verify_evidence` over every discovered record) + Task 5 Step 4 (`unverified_evidence_terminal` for criteria-referenced evidence under the strict policy) |
| Doctor compares `policy_digest` against the live TASKS.json entry | Task 4 `_policy_digest_issues`, decision 5 (latest-record-per-task, with both silences pinned) |
| Evidence artifacts bind into the Slice-1 hash chain | Tasks 1-3; decision 1 rules the mechanism (`artifact_hashes`, **no new event type**) with the rejected alternative costed |
| `Succeeded` tightens from non-empty paths to hash-verified evidence | Task 5, decisions 6-7 **and 14** (hash-verified *and* chain-bound *and* goalpost-agreeing at the two workspace-bearing layers); compat proven against both shipped examples and the runner's own auto-terminal |
| Carry-forward 1: FLIP, never delete, the two honest-limitation pins | Task 7 Step 1 (four flips, zero deletions, count unchanged) |
| Carry-forward 2: `missing_verify_bundle` counterpart | Task 3 `missing_bound_evidence` + decision 4's naming ruling |
| Carry-forward 3: reverse record-without-bundle check | Task 4 (`missing_evidence_path`, surfaced verbatim) |
| Carry-forward 4: `metrics.py` reads `verifier.source` | Task 6; §17's promise retired in Task 8 Step 6 |
| Carry-forward 5: `policy_digest` live comparison | Task 4 |
| Inherited constraints (zero deps, `@1`, typed fail-loud, byte-stability, structural.json, env quirks) | Global Constraints |
| Compat analysis for the G1 behavioral change | Global Constraints + decision 6 + Task 5 Steps 4-7; the four G1 call sites (`loop/emit.py:294`, `loop/contract.py:278`, `loop/reducer.py:32`, `loop/integrations.py:163`) are each named with the strength they can honestly reach |
| Honest framing; the §17 four-tier boundary updated with each movement named | Task 8 Step 5 (two tiers gain members, one empties, one gains **five** new residuals — the fifth is decision 14's store-less degradation) |
| Adversarial/honest-limitation task with proven non-vacuity | Task 7 (14 new pins + 4 flips + 1 carry-forward pin + **five** mutation probes with predicted *and* observed kill counts) |
| Docs task | Task 8, with a standing re-diff-before-editing instruction |
| Operator-gated, version-flexible release cut | Task 10 Step 1 |
| Carry-forward 10 (M-7 `unresolvable` wording) | Recorded discharged — already fixed on `origin/main:869` |
| Carry-forward 11 (T6 workspace-root symlink-loop pin) | Task 7 Step 2b |
| Post-review adjudications | **Post-review design changes** table (7 findings: 1 BLOCKER, 2 MAJOR, 4 MINOR) |

**Deliberately absent, each with a reason:** no new event type (decision 1); no new evidence@1 field (decision 3); no `code_digest` live comparison (decision 5); no retroactive binding or backfill (decision 10); no `verify-*.json` naming enforcement (carry-forward 9); no `loop simulate` write prediction (decision 12); no CLI flag (nothing in this slice needs one); no change to `loop/events.py`, `loop/chain.py`, `schemas/event.schema.json`, `action.yml`, `ci.yml`, or `evals/cases/structural.json`. **Added post-review, and deliberately still absent:** the strict mode does **not** require an event store to exist (decision 14 — that would break the pinned writer-API path), does **not** enforce binding or goalposts in the reducer or `to_terminal_state` (they are pure), and does **not** require an anchor (`--expect-chain-head` stays the operator's call, as in Slice 1). All three are pinned, not merely stated: Task 7 pins 13-14 and Task 5's two refusal tests are the controls, and mutation probes 4-5 prove they have teeth.

**Placeholder scan:** grep for `TBD`, `TODO`, `...`, "similar to Task" in task bodies → the only ellipses are the two labelled `# ... preamble as in Task 3 ...` markers in Tasks 4-6, which name the exact block to copy, and Task 7 Step 2's numbered list, whose **fourteen** test names and one-line behaviors are fully specified but whose bodies are left to the implementer *because each is a two-to-six-line assertion over fixtures Tasks 1-5 already define*. Pins 13 and 14 each additionally name their positive control, so neither can be written as a bare "assert clean". Every other block is literal code or a literal command. Fixture names (`ready_workspace`, `two_task_workspace`, `dispatched_workspace`, `predone_workspace`, `legacy_workspace`, `corrupt_store_workspace`, `bound_workspace`, and decision 14's store-less scaffold) are new per-file fixtures built from `scripts/test_runner_dispatch.py`'s and `scripts/test_doctor_eventstore.py`'s existing setup helpers — read both files before writing them; there is no `conftest.py` in this tree.

**Type-consistency check:**
- `BuiltEvidence` is frozen and total: every field is populated in the single constructor call, so `write_verify_evidence` indexes it without `.get()` defaults and a foreign object fails loudly with `AttributeError`.
- `build_verify_evidence` raises exactly `EmitError` (from `ChainHashError` conversion or self-validation) and `OSError` never, because it performs no writes; `write_verify_evidence` raises `EmitError` or `OSError`, which is the tuple `dispatch_once` already catches (`loop/runner.py:267`).
- `artifact_hashes` entries are `dict[str, str]` with exactly `path` (workspace-relative POSIX, non-empty) and `sha256` (64 lowercase hex) — the two fields `schemas/event.schema.json:25-29` requires and `loop/events.py:214-219` type-checks in fallback mode, so no validation change is needed.
- `_bound_evidence_issues` returns `list[dict]` and never raises: `_events` failures are already caught by `event_consistency_issues`'s `RuntimeStoreError` branch (`loop/runtime.py:305`), and per-artifact `OSError` becomes a finding rather than an exception.
- `bound_artifact_digests` returns `dict[str, str] | None` and **does** raise `RuntimeStoreError` on an unreadable store — the tri-state is load-bearing: `None` (no store) is a documented degradation, `{}` (store, nothing bound) is a legitimate legacy run, and the raise is an errored check that must fail rather than skip (R007). Its two callers handle the raise differently and deliberately: `emit.terminate` converts it to `EmitError` (refuse the write); `loop.contract` converts it to `unverified_evidence_terminal` (report, because doctor's unreadable-store branch already carries its own `error_code` and must not start raising).
- `_strict_evidence_failure` returns `str | None` and is the single definition of the strict bar. It performs I/O (record read, artifact hash, store read) and therefore lives in `loop/contract.py` — not in `loop/completion.py`, which stays pure so the reducer and `to_terminal_state` can keep importing it without acquiring a filesystem dependency.
- `policy_requires_verified_evidence` and `evidence_entry_is_record_shaped` are pure and total; the former raises `CompletionPolicyError` only for a malformed policy, which every call site already handles.
- `_policy_digest_issues` swallows `ChainHashError` **only** for a non-canonicalizable *task entry* — that is TASKS.json's own defect and `_validate_tasks` is its reporter; it never swallows a record defect.
- `metrics._load_verify_bundles`'s dict gains `"source": str | None`; every downstream consumer (`_assign_bundles_to_iters`, `_claim_is_clean`, `_anchor_repair`) reads only keys it already read.

**Open risks for the implementer:**
1. `scripts/test_doctor_evidence.py`'s fixture repair (Task 4 Step 1) is the highest-blast-radius edit in the plan — roughly eight assertions in a Slice-2 file depend on it. Do it **first**, run that file alone, and reconcile before writing a line of Task 4's implementation.
2. `write_verify_evidence`'s return dict and `dispatch_once`'s result dict each gain a key. Grep for whole-dict equality on both before Tasks 1 and 2 (Task 1 Step 4, Task 2 Step 4). Slice 2's own audit found `scripts/test_loop_simulate_cli.py:106` compares whole-dict only on the untouched `blocked` action — re-verify rather than trusting that line.
3. Moving `paths = _require_contract(target)` above `terminate`'s G1 block (Task 5 Step 4) changes which error surfaces first for a workspace that is *both* contract-less and G1-violating. `_require_contract`'s message is the more actionable one, but a Slice-2 test may pin the other order — grep `scripts/test_emit.py` for `refusing Succeeded` before making the move.
4. The object store adds files under `.loop/artifacts/objects/`. Grep for tree-byte-equality assertions over a *dispatched* workspace (`rglob` + sha256 comparisons) before Task 1; the zero-write pins compare trees around read-only verbs and are safe, but a smoke test that dispatches and then compares would need its expectation updated, not its assertion weakened.
5. Task 3's binding walk performs a third read-only fold per `doctor` invocation (decision 9). If a benchmark pin exists in `scripts/test_benchmark_harness.py` that bounds doctor's runtime, check it before merging.
6. The per-file counts in Task 9's table are this plan's predictions. Re-tally per file at Task 9 and treat any mismatch in either direction as a stop-and-explain (Step 8), not a number to adjust. **One of these predictions was already wrong once** — the pre-review draft claimed 11 for Task 3 against a block that collects 12 — so treat the table as a hypothesis, not a fact.
7. Task 7's mutation probes edit `loop/runtime.py` and `loop/contract.py` in place via heredoc. Confirm `git status` is clean after each; a probe left applied would make the whole suite lie.
8. **Decision 14 adds an import edge `loop/emit.py → loop/runtime.py`, and `loop/runtime.py` imports `loop/contract.py` at module level.** Both new edges (`emit → contract._strict_evidence_failure` and `contract → runtime.bound_artifact_digests`) MUST be function-local, exactly as the shipped doctor-events wiring does it. Run `python3 -c "import loop.emit, loop.contract, loop.runtime, loop.runner"` in a fresh interpreter after Task 5 Step 4 and before the commit — a cycle here surfaces as an `ImportError` only on the *first* import order a user happens to hit, so a passing test suite is not proof.
9. Decision 14 makes `emit.terminate` read `.loop/events.db` under the strict mode. Confirm the read is opened through the existing **sidecar-free** read-only helper — v0.10.0 fixed `events.db-wal`/`-shm` residue from `mode=ro` readers (issue closed by PR #80/#82), and a new reader that reintroduces sidecars would break tree-byte-equality smokes and re-open a closed bug. Reuse `runtime`'s helper; do not open a connection in `emit`.
10. The three decision-14 tests in Task 5 depend on `dispatched_workspace` having a task whose id matches the hand-written record's `produced_by.task_id`. If the fixture's TASKS.json uses a different id than `T-1`, the goalpost sub-check silently does not fire and the test passes for the wrong reason. Assert the task id explicitly inside `_handwritten_record` rather than assuming it.
