# ST2 — Portable Loop-Engineer Contract: Versioned, Tool-Agnostic Standard

*Design spec. Report-only planning artifact — defines the target, does not implement it.*
*Compiled 2026-06-30. Backlog ID: ST2 (rank 17, Impact H / Effort H, Strategic).*
*Scope boundary: this document specifies. No code, schema, template, or `.loop/` runtime is
touched by writing it.*

---

## 1. Why this exists

Loop Engineer's defensible claim (verified in `review/COMPETITIVE-ANALYSIS.md` §Whitespace,
primitive #4) is that it ships an **engine-neutral repo-OS contract** — files on disk,
resumable from `.loop/state.json`, additive on top of any Q3/Q2 runtime. No verified rival
(Superpowers 242k★, ECC 224k★, OpenHands 79k★, ruflo 62k★, AutoGen, CrewAI, LangGraph,
Temporal) ships a portable on-disk evidence contract. That is the deepest moat available: if
the on-disk format is a *documented, versioned, tool-agnostic standard*, other harnesses can
emit and consume it, and Loop Engineer becomes the reference implementation rather than one
more harness.

Today the contract is **not** a published standard — it is an implicit format enforced by one
validator that is provably incomplete. The gate this spec closes is the LOW gate-integrity /
metric-honesty finding **M5**:

> `loop/contract.py:219-240` — `validate_contract()` calls only
> `_validate_manifest` / `_validate_state` / `_validate_tasks` / `_validate_terminal`.
> `schemas/receipt.schema.json` exists but is **never referenced** in `contract.py`, and **no
> repair-record schema exists at all**. So the contract-integrity gate is silent on whether
> the FCR/repair-productivity evidentiary trail (receipts, repair records) exists or is
> well-formed — a loop can "pass validation" while its metric inputs are missing or malformed.

The published schemas today are 5 (`schemas/*.schema.json`: manifest, state, tasks, terminal,
receipt); the validator checks 4 of them and no repair-record schema is published at all.
**Covering 4 of 5 while claiming a portable contract is the exact gap an external evaluator
finds first** when they open `contract.py` to decide whether the "layer above" claim is real.

---

## 2. The dogfood gaps this spec must fix first

Before ST2 can publish the contract as a standard, the standard must be internally
self-consistent. **Self-hosting this very roadmap surfaced three concrete inconsistencies**
between what the `templates/` scaffold emits and what `loop/contract.py` (and the published
`schemas/`) demand. A "portable standard" whose own templates fail its own validator is not a
standard — it is a bug. All three are confirmed against source below and are **in scope for
ST2 as the reconciliation layer**.

### DG-1 — Templates emit `schema_version`; the validator and schemas require `schema`

- **Evidence:**
  - `templates/state.json.tmpl:2` → `"schema_version": "1.0"`.
  - `templates/terminal_state.json.tmpl:2` → `"schema_version": "1.0"`.
  - But `loop/contract.py:134` (`_validate_state`) calls `_require_schema(data,
    "loop-engineer/state@1", …)` which checks `data.get("schema")`; `contract.py:170`
    (`_validate_terminal`) checks `data.get("schema") == "loop-engineer/terminal@1"`.
  - `schemas/state.schema.json` and `schemas/terminal.schema.json` both `required` the key
    `"schema"` with a `const` value, not `schema_version`.
- **Consequence:** A state or terminal file scaffolded verbatim from the shipped template
  fails `validate_contract`/`doctor` with a `schema_mismatch` (got `None`). The scaffold the
  suite ships cannot pass the gate the suite ships.
- **Note the split:** `templates/TASKS.json.tmpl:2` (`"schema": "loop-engineer/tasks@1"`) and
  `templates/manifest.yaml.tmpl:4` (`schema: loop-engineer/manifest@1`) are **already
  correct** — the drift is isolated to the two JSON state templates. The fix is a one-key
  rename in each, plus a version note (see §6).

### DG-2 — The `terminal_state` template omits `criteria_met`, `evidence`, and `false_completion`

- **Evidence:** `templates/terminal_state.json.tmpl` carries `verification_evidence` (object),
  `lessons_learned` (array), `succeeded`, `failure_reason` — but **none** of the three fields
  the validator and schema make load-bearing:
  - `loop/contract.py:175-180` requires `criteria_met` (dict), `evidence` (list),
    `false_completion` (bool).
  - `schemas/terminal.schema.json:6` `required`: `schema`, `state`, `iteration_id`,
    `criteria_met`, `evidence`, `false_completion`, `reason`, `lessons_ref`.
- **Consequence:** The terminal template is missing the *entire proof surface* — the exact
  fields (`criteria_met`, `evidence`, `false_completion`) that carry the differentiator. A
  terminal file scaffolded from it fails validation on three `invalid_terminal` issues and, if
  hand-patched to pass, still cannot express the false-completion signal the product sells.
- **Interaction with the wedge:** `false_completion` is the field HI4/QW2 are hardening. If the
  template does not even emit it, every downstream honesty fix has nothing to bind to. **DG-2
  is a prerequisite for the metric-honesty work, not merely cosmetic.**

### DG-3 — No non-terminal lifecycle state; `doctor` forces a terminal file onto an unstarted loop

- **Evidence:** `loop/contract.py:225` reads `paths.terminal` unconditionally, and
  `_read_json` (`contract.py:34-36`) appends a `missing_file` issue whenever the file is
  absent. There is no contract-level concept of "this loop has not terminated yet, and that is
  a valid, conformant state."
- **Consequence:** A freshly-scaffolded or mid-flight loop (`.loop/state.json` present,
  `terminal_state` = `null`, no `terminal_state.json` yet — the *correct* representation of an
  unstarted or in-progress run) **fails `doctor`** with `missing RUNLOG.md`-class
  `missing_file` on the terminal path. To make `doctor` green, an operator is pushed to write a
  terminal file onto a loop that has not terminated — i.e. to fabricate a terminal state. The
  gate incentivizes exactly the false completion the product exists to prevent.
- **Root shape:** the state schema already models non-terminal life correctly
  (`schemas/state.schema.json:18-21`: `terminal_state` may be `null`). The gap is that
  `validate_contract` treats the *terminal file* as unconditionally required rather than
  "required iff `state.json.terminal_state != null`."

---

## 3. Goals / non-goals

### Goals

1. **Publish the on-disk contract as a versioned, tool-agnostic standard** — a single
   normative spec doc plus a complete set of published JSON Schemas that any harness (not just
   Loop Engineer) can emit and validate against.
2. **Close M5** — extend `validate_contract` to check receipts and repair records against
   published schemas when present, so the FCR/repair-productivity evidentiary trail is covered.
3. **Reconcile templates ↔ validator ↔ schemas** — fix DG-1, DG-2, DG-3 so the shipped
   scaffold passes the shipped gate, and add regression coverage so the drift cannot silently
   return.
4. **Add a non-terminal lifecycle state** so an unstarted / in-progress loop is a first-class
   *conformant* state, not a validation failure.
5. **Publish a conformance checklist + version/stability note** so a third party can claim
   "emits a Loop-Engineer-conformant contract v1" and know exactly what that means.

### Non-goals

- **Not** a runtime rewrite. The state machine, the 7 terminal states, and the file layout are
  unchanged. This is a *format-standardization + validator-completeness* effort.
- **Not** the FCR/RP baseline itself (that is ST1, which depends on this).
- **Not** the integration recipes (ST3).
- **Not** re-litigating the 7 terminal states — they are canonical and frozen
  (`loop/contract.py:9-17`).
- **Not** the honesty-enforcement fixes themselves (QW2 terminal cross-check, HI4 inspector
  credit, HI5 `productive` recompute) — this spec makes the *schemas and validator surface*
  those fixes bind to, and declares the dependency, but does not implement the cross-field
  semantic rules (those are their own backlog items).

---

## 4. The contract standard — versioning & stability model

### 4.1 One normative document

Publish a single canonical spec, `reference/repo-os-contract.md` already partially exists (the
manifest template at `templates/manifest.yaml.tmpl:2` cites `reference/repo-os-contract.md §10`
as the canonical schema source). ST2 promotes it to the **normative standard**: it must
enumerate every file in the contract, its schema `$id`, its required keys, and its lifecycle
role. The spec is the human-readable companion to the machine-readable `schemas/`.

### 4.2 Schema identity and versioning

The contract already uses embedded, versioned schema identifiers of the form
`loop-engineer/<artifact>@<major>` (`loop/contract.py:19-24`, and each `schemas/*.schema.json`
`$id`). ST2 formalizes this into a stability contract:

- **Version is a single integer major**, embedded in the `$id` and in the `schema` key of every
  artifact (`loop-engineer/state@1`, …). This is the version an external emitter targets.
- **Additive changes are minor and MUST NOT bump the major.** Adding an *optional* key, or a
  new *optional* file, is backward compatible: every artifact schema already sets
  `"additionalProperties": true` (confirmed in all five `schemas/*.schema.json`), so a v1
  consumer tolerates unknown keys from a newer emitter.
- **Breaking changes (removing/renaming a required key, changing a type, tightening an enum)
  bump the major** to `@2` and get a new `$id`. Both majors may be published side by side.
- **A `SPEC_VERSION` / stability table** in the normative doc records, per artifact, the
  current major and its stability tier (`stable` | `provisional`). Recommendation for v1:
  manifest / state / tasks / terminal = **stable**; receipt / repair-record = **provisional**
  (they are the newest surfaces and ST1 may still shape them).

### 4.3 Stability note (normative text to publish)

> The Loop-Engineer contract is a **portable, tool-agnostic on-disk standard**. Any surface
> that can read a repo, run a shell command, and write files can emit or consume it. Conformance
> is defined by the published JSON Schemas at `schemas/*.schema.json` (schema `$id`
> `loop-engineer/<artifact>@<major>`). Within a major version, changes are strictly additive
> and optional; a validator for major *N* accepts any artifact whose required keys and types
> match major *N*, ignoring unknown keys. Breaking changes ship as a new major with a new `$id`.

---

## 5. Schema set — publish all six; canonicalize the repair record

ST2's published schema set is **six** artifacts. Five exist; two need work (receipt gets wired
in; repair-record is net-new), and every existing schema must be reconciled with its template.

| Artifact | Schema file | Status today | ST2 action |
|---|---|---|---|
| manifest | `schemas/manifest.schema.json` | published, validated | keep; confirm template parity (already correct) |
| state | `schemas/state.schema.json` | published, validated (partial) | **DG-1** template rename; widen validator to the schema's full `required` set (§6.3) |
| tasks | `schemas/tasks.schema.json` | published, validated | keep; template already correct |
| terminal | `schemas/terminal.schema.json` | published, validated | **DG-2** template completion; keep |
| receipt | `schemas/receipt.schema.json` | published but **never referenced** | **wire into `validate_contract`** (§7) — this is M5's core |
| **repair-record** | *(none)* | **does not exist** | **author + publish** (§5.1) — this is M5's other half |

### 5.1 Repair-record schema — resolve the two-shapes conflict (QW11 / M4) first

There are currently **two disjoint "7-field" shapes both branded "the" repair record**
(finding M4 / backlog QW11):

- `scripts/rollout_ledger.py` `RECORD_FIELDS`:
  `id` / `parent` / `verdict` / `score` / `score_delta` / `coherent_with_prior_winner` /
  `productive` — a rollout/ledger shape.
- `evals/cases/structural.json` `repair_record_fields`:
  `failure_mode` / `hypothesis` / `repair_action` / `verification_before` /
  `verification_after` / `remaining_delta` / `productive` — a repair-diagnosis shape
  (and the shape `skills/loop-repair/SKILL.md:71` prescribes).

They share only the count "7" and the field `productive`. **ST2 cannot publish a repair-record
schema until this is resolved — QW11 is a hard dependency.** Recommendation for the spec author
to ratify:

- **Canonical `repair-record@1` = the `structural.json` diagnosis shape**
  (`failure_mode` / `hypothesis` / `repair_action` / `verification_before` /
  `verification_after` / `remaining_delta` / `productive`). Rationale: it is the shape the
  repair *skill* prescribes, the shape the eval structural-invariant already pins, and the one
  the manifest template points at
  (`templates/manifest.yaml.tmpl:24` → `.loop/artifacts/repair-record.json`). The
  `rollout_ledger` shape is a *rollout-ledger* record (genome/rollout bookkeeping), which the
  standard should name distinctly (`rollout-record`), not conflate with the repair record.
- **`verification_before` / `verification_after`** are objects carrying at least `score`
  (number); `remaining_delta` is a number; `productive` is a boolean.
- **`productive` is derived, and the schema documents that it MUST equal
  `verification_after.score > verification_before.score`** (per `eval-suite.md:62` "derived,
  not self-reported"). The *schema* documents the invariant; the *recompute-and-reject
  enforcement* is HI5 (declared dependency, not implemented here).

Publishing this schema is what lets `validate_contract` check the repair trail (M5) and what
lets ST1 derive repair-productivity from a well-formed, single-shape record.

### 5.2 Receipt schema — already publishable

`schemas/receipt.schema.json` is well-formed and correctly describes the append-one-JSON-object-
per-line `.loop/receipts/*.jsonl` trail (role ∈ {read,reason,write,orchestrate}, model,
outcome ∈ {ok,fail,escalated}). ST2 does **not** reshape it; it wires it into the validator
(§7). Its `description` already states the portability intent ("Any JSONL receipt source that
carries these keys … works") — that sentence is the seed of the standard's cross-tool claim.

---

## 6. Template ↔ validator ↔ schema reconciliation

The single acceptance invariant for this section: **every file emitted verbatim from
`templates/` (placeholders filled with schema-valid values) passes `validate_contract` with
zero issues, and validates against its published JSON Schema.** A round-trip regression test
must pin this.

### 6.1 DG-1 fix — rename `schema_version` → `schema` in the two JSON state templates

- `templates/state.json.tmpl:2`: `"schema_version": "1.0"` → `"schema": "loop-engineer/state@1"`.
- `templates/terminal_state.json.tmpl:2`: `"schema_version": "1.0"` →
  `"schema": "loop-engineer/terminal@1"`.
- The human-facing "version" is now carried by the schema `$id` major, not a parallel
  `schema_version` key. If a scaffold timestamp/version is still wanted, keep it under a
  distinct optional key (e.g. `scaffold_version`) that no validator keys on.

### 6.2 DG-2 fix — complete the `terminal_state` template to the terminal schema

`templates/terminal_state.json.tmpl` must emit **all** `terminal.schema.json:6` required keys:
`schema`, `state`, `iteration_id`, `criteria_met`, `evidence`, `false_completion`, `reason`,
`lessons_ref`. Concretely add:

- `"criteria_met": { "{{CRITERION_1}}": {{CRITERION_1_MET}} }` (object of criterion→bool),
- `"evidence": ["{{EVIDENCE_PATH_1}}"]` (list of evidence paths/handles),
- `"false_completion": {{FALSE_COMPLETION}}` (bool),
- `"reason": "{{TERMINAL_REASON}}"`,
- `"lessons_ref": "{{LESSONS_REF}}"`.

The existing `verification_evidence` / `lessons_learned` / `succeeded` keys may remain as
optional convenience fields (they are tolerated by `additionalProperties: true`), but the
**canonical proof surface is `criteria_met` + `evidence` + `false_completion`**, and the
template must lead with them so a scaffolded terminal file is proof-complete by construction.

### 6.3 DG-1 corollary — widen `_validate_state` to the state schema's full required set, and fix `iteration_id` type

Two latent template↔schema mismatches surface while fixing DG-1:

- **`iteration_id` type.** `templates/state.json.tmpl:4` emits `"{{ITERATION_ID}}"` (a JSON
  *string*), but `schemas/state.schema.json:9` requires `integer, minimum 0`
  (`terminal.schema.json:10` likewise). ST2 must make the templates emit an unquoted integer
  placeholder (`"iteration_id": {{ITERATION_ID}}`) so the scaffold validates against the schema.
- **Validator/schema `required` divergence.** `_validate_state` (`contract.py:138`) checks only
  `iteration_id` / `state` / `plan_version` / `budget_remaining`, whereas
  `state.schema.json:6` requires eleven keys (adds `active_task`, `best_score`, `failure_mode`,
  `pending_approval`, `checkpoint_path`, `terminal_state`). ST2's standard resolves this by
  making the **published JSON Schema the single source of truth** and having `_validate_state`
  either (a) validate against the schema directly (preferred, see §7.2) or (b) check the same
  eleven keys. Either way, template, validator, and schema converge on one required set.

### 6.4 DG-3 fix — a non-terminal lifecycle state

Introduce a first-class **non-terminal / pre-terminal** lifecycle concept so an unstarted or
in-flight loop is conformant without a terminal file:

- **Contract rule:** `terminal_state.json` is **required iff `state.json.terminal_state !=
  null`.** When `state.json` reports a live (non-terminal) `state` and `terminal_state: null`,
  the *absence* of `terminal_state.json` is **conformant**, not a `missing_file` issue.
  `validate_contract` must gate the terminal read on the state's `terminal_state` field.
- **Lifecycle vocabulary (documented, not a new file schema):** the standard names the
  non-terminal lifecycle values a loop's `state` field may hold before termination — at minimum
  a **`Planned`** (contract scaffolded, not yet running) and **`Ready`/`Running`** (executing)
  band — and states that these are *not* terminal states and never appear in the frozen
  7-member `terminal_state` enum. This gives `doctor` a way to report "conformant, not yet
  terminated" instead of forcing a fabricated terminal file.
- **`doctor` output:** add a lifecycle line to the report (e.g. `"lifecycle": "planned"` |
  `"running"` | `"terminated:<TerminalState>"`) so an operator sees *why* no terminal file is
  expected, closing the incentive to fabricate one.
- **Regression:** a test that a scaffolded loop with `terminal_state: null` and **no**
  `terminal_state.json` passes `doctor` clean; and that a loop claiming a non-null
  `terminal_state` **without** the terminal file still fails.

---

## 7. Extending `validate_contract` (closing M5)

### 7.1 Receipts + repair records, checked when present

`validate_contract` (`contract.py:219-240`) gains two optional checks, invoked after the four
existing validators:

- **`_validate_receipts(paths, issues)`** — if `.loop/receipts/*.jsonl` exists, parse each line
  as JSON and validate against `receipt@1`. Malformed lines, wrong `schema`, or an out-of-enum
  `role`/`outcome` emit an issue. Absent receipts are **not** an error (optional trail).
- **`_validate_repair_records(paths, issues)`** — if the repair-record file(s) exist
  (`.loop/artifacts/repair-record.json` per manifest, and/or `.loop/artifacts/*repair*.json`),
  validate each against the canonical `repair-record@1` (§5.1). Absent records are **not** an
  error.
- **`schemas_checked`** in the return value (`contract.py:238`) must grow from the current 4
  (`SCHEMA_IDS`) to **all six** so the report honestly states its coverage. The "covers only 4
  of 5 shipped schemas" evidence for M5 is retired by this single change plus the new
  repair-record schema.

**"Optional when present" is the right severity:** a portable contract should validate a
mid-flight loop that has not yet produced receipts. ST2 makes malformed-trail a hard issue and
missing-trail a non-issue. (A future ST1 may layer a *stricter* profile that requires the trail
for a `Succeeded` terminal — noted as a hook, out of scope here.)

### 7.2 Recommended: validate against the published JSON Schemas directly

Today the validators are hand-rolled key checks that have already drifted from the published
schemas (§6.3). ST2 should make the published `schemas/*.schema.json` the **single source of
truth** and drive validation from them (a small pure-stdlib subset validator, or an optional
`jsonschema` dependency guarded like the optional-`yaml` import at `contract.py:106`). This
guarantees template↔validator↔schema can never diverge again, because there is exactly one
authority. If a full schema engine is undesirable in the stdlib core, the fallback is a
generated key/type check emitted *from* the schemas so drift is still mechanically impossible.
Either way, **the JSON Schema is normative; the validator conforms to it, not vice versa.**

---

## 8. Conformance checklist (publishable)

The standard ships a checklist a third party (or CI) can run to claim "Loop-Engineer contract
v1 conformant." Draft:

**A. Artifacts present & well-formed**
- [ ] `.loop/manifest.yaml` validates against `loop-engineer/manifest@1` (incl. the canonical
      7 `terminal_states`, verbatim and in order).
- [ ] `.loop/state.json` validates against `loop-engineer/state@1` (`schema` key present,
      `iteration_id` integer, all required keys present).
- [ ] `TASKS.json` validates against `loop-engineer/tasks@1`; no duplicate task ids; no task
      `status:"done"` without `evidence`.
- [ ] `RUNLOG.md` present.

**B. Lifecycle honesty**
- [ ] Exactly one of: (`terminal_state == null` **and** no `terminal_state.json`) **or**
      (`terminal_state ∈` canonical 7 **and** `terminal_state.json` present & valid). No
      terminal file on a non-terminated loop; no non-null `terminal_state` without the file.
- [ ] `terminal_state.json` (when present) validates against `loop-engineer/terminal@1` with a
      real `criteria_met`, non-empty `evidence`, and an explicit `false_completion` boolean.

**C. Evidentiary trail (checked when present)**
- [ ] Every `.loop/receipts/*.jsonl` line validates against `loop-engineer/receipt@1`.
- [ ] Every repair record validates against `loop-engineer/repair-record@1`, and `productive`
      equals `verification_after.score > verification_before.score` (the derivation invariant;
      hard-enforced by HI5).

**D. Versioning**
- [ ] Every artifact's `schema` / `$id` names a *published, current-major* schema.
- [ ] Unknown keys are tolerated (a v1 validator does not reject a newer emitter's additive
      fields).

**E. Cross-field integrity (declared, enforced by sibling items)**
- [ ] A `Succeeded` terminal has `false_completion == false` **and** ≥1 true entry in
      `criteria_met` (**QW2** — this spec surfaces the field; QW2 enforces the rule).

---

## 9. Acceptance criteria (for the ST2 implementation that follows this spec)

1. A single normative spec doc (`reference/repo-os-contract.md`, promoted) enumerates all six
   artifacts, their `$id`s, required keys, lifecycle roles, and the §4.3 stability note.
2. Six published JSON Schemas exist and are current: manifest, state, tasks, terminal, receipt,
   **repair-record** (net-new, canonical shape per §5.1, QW11 resolved).
3. `validate_contract` checks receipts and repair records against their schemas when present;
   `schemas_checked` reports all six; M5's "4 of 5" evidence no longer reproduces.
4. **DG-1**: state & terminal templates emit `schema` (not `schema_version`) and validate clean.
5. **DG-2**: the terminal template emits `criteria_met` + `evidence` + `false_completion`
   (+ `reason`, `lessons_ref`, `iteration_id`) and validates against `terminal@1`.
6. **DG-3**: a scaffolded loop with `terminal_state: null` and no `terminal_state.json` passes
   `doctor`; a non-null `terminal_state` without the file still fails; `doctor` reports a
   lifecycle line.
7. A round-trip regression test: **every `templates/*` artifact, filled and scaffolded, passes
   `validate_contract` and its JSON Schema** — the drift class of DG-1/DG-2/DG-3 cannot silently
   return.
8. A published conformance checklist (§8) exists and is runnable in CI against
   `examples/coverage-repair` (and any second example).
9. `loop-contract` scaffold output validates in CI (per the ST2 backlog acceptance).

---

## 10. Dependencies, risks, sequencing

- **QW11 (canonical repair record) is a hard prerequisite for §5.1.** Do not publish
  `repair-record@1` until the two-shapes conflict is ratified; publishing the wrong shape would
  bake ambiguity into a *versioned standard*, the most expensive place to be wrong.
- **HI5 (recompute & reject `productive`)** consumes this spec's repair-record schema. §5.1
  *documents* the `productive` invariant; HI5 *enforces* it. Ship the schema first, then HI5.
- **QW2 / HI4 (false-completion enforcement)** consume DG-2. This spec makes the terminal
  template *emit* `false_completion`; QW2 makes the validator *cross-check* it; HI4 makes the
  inspector *credit only on real gate invocation*. Order: DG-2 → QW2 → HI4.
- **ST1 (published FCR/RP baseline) depends on this entire spec** — a baseline requires a
  single well-formed repair-record shape (§5.1) and a validated receipt/repair trail (§7). Per
  the backlog: *do not publish a baseline until the inputs are schema-checked and gate-backed.*
- **Risk — validator/schema authority drift (§7.2).** If the hand-rolled validators are kept
  instead of driving from the schemas, the DG-class drift returns the next time a schema
  changes. Mitigation: make the JSON Schema normative and the validator generated-from / driven-
  by it, or at minimum add the §9.7 round-trip test as a CI gate.
- **Risk — over-scoping the receipt/repair check to "required."** Requiring the trail on every
  loop would break mid-flight and inspect-only conformance. Mitigation: "checked when present"
  (§7.1); a stricter "required-for-Succeeded" profile is a future, opt-in tier.
- **Competitive payoff is realized only if the standard is *documented for outsiders*.** The
  moat (COMPETITIVE §Whitespace #4) is other harnesses emitting the format. The normative doc +
  conformance checklist are what make that possible; schemas alone are necessary but not
  sufficient.

---

## 11. Out of scope (explicit)

- The FCR/RP metrics computation and baseline (ST1).
- Integration recipes for LangGraph/Temporal/OpenHands/ruflo (ST3).
- The cross-field *enforcement* of `Succeeded ⇒ ¬false_completion ∧ criteria_met` (QW2), the
  inspector-credit fix (HI4), the `productive` recompute (HI5), and the anticheat structural
  invariant (HI6) — all declared as dependents, none implemented here.
- Any change to the 7 terminal states or the file layout.
