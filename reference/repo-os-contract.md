# Repo-OS Contract

The **repo-OS contract** is the set of on-disk artifacts a loop-engineer scaffolds into a
workspace so that an agent loop can be designed, launched, verified, repaired, resumed across
sessions, and improved — *without* the loop's state living only in a chat context that
compaction or a crashed session can lose. State is **externalized to files**; the loop reads
its truth from disk on every turn.

This file is the canonical schema. It is scaffolded by `[[loop-contract]]`, consumed by
`[[loop-run]]` (which transitions `state.json`), repaired by `[[loop-repair]]`, measured by
`[[loop-evals]]`, and mined by `[[loop-flywheel]]`. The patterns that drive each artifact live
in `loop-patterns.md`; the safety/terminal semantics live in `safety-and-approvals.md`.

---

## 0. The contract is a versioned, tool-agnostic standard

This document is the **normative standard** for the repo-OS contract. It is not a
description of one tool's private file format: it is a **portable, tool-agnostic on-disk
standard**. Any surface that can read a repo, run a shell command, and write files can emit or
consume it — Loop Engineer is the *reference implementation*, not the only permitted producer.

- **Conformance is defined by the published JSON Schemas** in `schemas/*.schema.json`, not by
  any one validator's source code. Every schema-bearing artifact carries a `schema` key, and
  every schema an `$id`, of the form **`loop-engineer/<artifact>@<major>`**
  (e.g. `loop-engineer/state@1`). The major integer in that identifier is the version an
  external emitter targets.
- **Within a major, changes are strictly additive and optional.** Every artifact schema sets
  `"additionalProperties": true`, so a validator for major *N* accepts any artifact whose
  required keys and types match major *N* and **ignores unknown keys** — a newer emitter's
  extra fields never reject a valid v1 artifact. Adding an optional key, or a new optional
  file, does not bump the major.
- **Breaking changes get a new major and a new `$id`.** Removing or renaming a required key,
  changing a type, or tightening an enum ships as `loop-engineer/<artifact>@2` with a new
  `$id`. Both majors may be published and validated **side by side**.
- **Stability tiers.** The artifact table (§11) records each artifact's tier. For v1:
  **manifest / state / tasks / terminal are `stable`**; **receipt / repair-record /
  rollout-record are `provisional`** (the newest surfaces, whose additive shape may still be
  refined within `@1`).

A third-party harness whose output satisfies the §14 conformance checklist may claim it
**"emits a Loop-Engineer-conformant contract v1."**

---

## 1. The full repo-OS tree

```
<workspace>/
  AGENTS.md           # short table-of-contents of stable rules (points to the rest)
  SPEC.md             # success criteria, constraints, non-goals, evidence rules — the INTENT
  WORKFLOW.md         # loop policy, approval gates, budgets, terminal states — the STABLE RULES
  TASKS.json          # machine-readable task ledger — the QUEUE
  RUNLOG.md           # human-readable iteration history (one entry per loop) — the HISTORY
  EVALS/
    dataset/          # fixed eval inputs (golden cases, hidden canaries)
    rubrics/          # model-judge rubrics (fixed schema per artifact type)
    regressions/      # trace-derived regression cases harvested from failures
    traces/           # captured run traces (for loop-behavior analysis)
  scripts/
    verify-fast       # deterministic, cheap gate (tests/lint/typecheck subset) — blocking
    verify-full       # full deterministic gate — blocking
    verify-safety     # red-team / approval / injection checks — blocking
    judge-rubric      # rubric model-judge harness — advisory
    extract-trace-metrics  # turns traces into the loop-behavior + cost metrics
  .loop/
    state.json        # machine status: the live FSM cursor — the SOURCE OF MACHINE TRUTH
    terminal_state.json    # written exactly once, at loop end
    checkpoints/      # point-in-time snapshots of best-known-good state
    artifacts/        # intermediate work products (drafts, generated files)
    approvals/        # one file per approval request + its resolution
    repair/           # repair@1 records — scanned by doctor when present
    receipts/         # receipt@1 ledgers (*.jsonl) — scanned by doctor when present
    evidence/         # evidence@1 records — the declared location doctor scans (§17)
    memory/
      session-summary.md   # short-term: continue-this-run compaction summary (disposable at terminal)
      lessons.md           # long-term: durable lessons that improve future runs
```

Every artifact has exactly one owner concern (see §9). The split is deliberate: a turn that
needs "what does done mean" reads `SPEC.md`; a turn that needs "where am I" reads
`.loop/state.json`; neither file is overloaded with the other's job.

---

## 2. `AGENTS.md` — stable rules table-of-contents

**Purpose.** A *short* index the agent reads first every session. It does not contain the rules
themselves beyond a one-line each; it points at `SPEC.md`, `WORKFLOW.md`, and `scripts/`. This is
the engine-neutral entry point — the same file Codex Goal mode and Google Conductor read (see
`platform-map.md`), which is why the contract names it `AGENTS.md` rather than a Claude-specific
name.

**Minimal schema (Markdown, fixed section order):**

```markdown
# AGENTS — <project>
- **Intent:** see SPEC.md (success criteria + non-goals)
- **Loop policy:** see WORKFLOW.md (gates, budgets, terminal states, repair cap)
- **Verify:** scripts/verify-fast (cheap), scripts/verify-full, scripts/verify-safety
- **Task queue:** TASKS.json   **History:** RUNLOG.md   **Live state:** .loop/state.json
- **Resume rule:** if .loop/state.json exists, skip intake; continue from first incomplete state.
```

Keep it under ~20 lines. If it grows, the depth belongs in the file it points to.

---

## 3. `SPEC.md` — intent

**Purpose.** The single source of *what done means*. It is the contract against which every
verification and the prime directive are judged: if `SPEC.md` cannot state success, verification,
or a terminal condition, the loop is **underspecified** and terminates `FailedSpecGap` rather than
declaring the next completion "done." This is the primary defense against the documented #1
long-horizon failure mode — false completion / weak self-verification.

**Minimal schema (Markdown, fixed sections):**

| Section | Content |
|---|---|
| `## Goal` | One paragraph: the objective in outcome terms. |
| `## Success Criteria` | Numbered, each *independently checkable* (maps to a `verify-*` check or eval case). |
| `## Constraints` | Hard limits (perf, deps, files-not-to-touch, style). |
| `## Non-Goals` | Explicit out-of-scope (YAGNI fence). |
| `## Evidence Rules` | What counts as proof a criterion is met (which `scripts/verify-*` / which `EVALS/` case). No criterion without a stated evidence source. |

A `## Success Criteria` line with no corresponding evidence rule is itself a spec gap.

---

## 4. `WORKFLOW.md` — stable loop rules

**Purpose.** The loop's operating policy — separate from intent because it changes on a different
cadence (you tune gates and budgets far more often than you redefine success). Read by
`[[loop-run]]` to know how to behave and by `[[loop-repair]]` to read the repair cap.

**Minimal schema (Markdown, fixed sections):**

| Section | Content |
|---|---|
| `## Loop` | The state sequence: `intake → plan → critique-plan → queue-tasks → execute-task → verify → (repair | replan | approval-wait) → terminal`. |
| `## Approval Gates` | The side-effect boundaries that pause for approval (destructive commands, secret access, production changes, money movement, policy-sensitive output) and the `approval_policy` in force (`never` / `on_side_effects` / `strict`). |
| `## Budgets` | `time_budget`, `cost_budget` and the rule: exhausted budget → `FailedBudget`. |
| `## Repair Cap` | `max_repair_attempts` (default **2**), and what happens at the cap: replan / revert / approve / terminate. |
| `## Terminal States` | All **7**, verbatim, each with its trigger (see §8). |
| `## Dispatch` | Routing rule: every dispatched agent / Workflow `agent()` names an explicit `model:` (read→haiku, reason→sonnet, write→opus); the receipts each dispatch appends land in `.loop/receipts/*.jsonl` (schema: `schemas/receipt.schema.json`). |

`WORKFLOW.md` states policy; it never records run status — that is `.loop/state.json`'s job.

---

## 5. `TASKS.json` — the machine-readable task ledger

**Purpose.** The queue the loop executes against, machine-readable so `[[loop-run]]` can pick the
next task deterministically and `extract-trace-metrics` can count progress. Distinct from
`SPEC.md` (intent) and `RUNLOG.md` (narrative history): this is current queue *status*.

**Minimal schema (JSON — `tasks` is an ordered array; each task object):**

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Stable task id (e.g. `T1`). |
| `title` | string | One-line description. |
| `status` | enum | `pending` \| `active` \| `blocked` \| `done` \| `abandoned`. |
| `criterion_ref` | string | The `SPEC.md` success-criterion number this task advances. |
| `verify` | string | The exact command/check that proves this task done (a `scripts/verify-*` invocation or eval case). |
| `depends_on` | string[] | Task ids that must be `done` first. |
| `attempts` | int | Times executed (drives repair-cap accounting). |
| `evidence` | string\|null | Path/ref to the verification bundle proving `done`; null until proven. |

```json
{
  "schema": "loop-engineer/tasks@1",
  "tasks": [
    {
      "id": "T1",
      "title": "Add input validation to pricing.parse_request",
      "status": "done",
      "criterion_ref": "2",
      "verify": "scripts/verify-fast",
      "depends_on": [],
      "attempts": 1,
      "evidence": ".loop/artifacts/verify-T1.json"
    },
    {
      "id": "T2",
      "title": "Raise pricing.py coverage to >=80%",
      "status": "active",
      "criterion_ref": "1",
      "verify": "scripts/verify-full",
      "depends_on": ["T1"],
      "attempts": 2,
      "evidence": null
    }
  ]
}
```

A task is only `done` when `evidence` is non-null *and* its `verify` passed — never on the
agent's assertion alone.

---

## 6. `RUNLOG.md` — human-readable iteration history

**Purpose.** The append-only narrative of what each loop iteration did — for a human reviewer and
for `[[loop-flywheel]]` to mine into regression cases. One entry per loop iteration; entries are
never edited, only appended (immutable history).

**Minimal schema (Markdown — one block per iteration, fixed fields):**

```markdown
## Iteration <n> — <ISO-8601 timestamp>
- **state:** <FSM state this iteration ran>
- **active_task:** <TASKS.json id>
- **action:** <what was attempted, 1–2 lines>
- **dispatch:** <agent/model used, e.g. engineer @ opus> | none
- **verify:** <command> → PASS | FAIL (<which criteria>)
- **score:** <best_score before → after> (deterministic and/or rubric)
- **outcome:** advanced | repaired | replanned | approval-wait | terminal:<state>
- **evidence:** <path to verification bundle>
```

Per-iteration fields (`state`, `active_task`, `action`, `dispatch`, `verify`, `score`,
`outcome`, `evidence`) are required so a trace transform can parse the log mechanically.

---

## 7. `.loop/state.json` — the live FSM cursor

**Purpose.** The **source of machine truth** for resume. Serialized after *every* state
transition so a fresh session reconstitutes the loop exactly: the resume rule is — if
`state.json` exists, skip intake and continue from the first incomplete state. This is the
file-backed realization of a portable Python FSM spine pattern (init / next / complete +
serialize-after-transition; ~100 lines); the loop-engineer does **not** ship a new spine — when the
Python-FSM realization is chosen, implement the ~100-line pattern or reuse the author's
`harmony-agent` `engine/cli.py` reference impl.

**Minimal schema (JSON — fields are the spec's State row):**

| Field | Type | Meaning |
|---|---|---|
| `iteration_id` | int | Monotonic loop counter (matches latest `RUNLOG` entry). |
| `state` | enum | Current FSM state: `intake`, `plan`, `critique-plan`, `queue-tasks`, `execute-task`, `verify`, `repair`, `replan`, `approval-wait`, or `terminal`. `loop/fsm.py` is normative for the transition table. |
| `updated_at` | string\|null | ISO-8601 UTC timestamp of the last write by a `loop.emit` writer; additive/optional and absent on legacy artifacts. |
| `plan_version` | int | Bumped on every replan (lets traces detect churn). |
| `active_task` | string\|null | `TASKS.json` id currently in flight. |
| `best_score` | number\|null | Best verification score so far (repair productivity is measured against this). |
| `failure_mode` | string\|null | Classified failure of the last failed verify (drives `[[loop-repair]]`). |
| `pending_approval` | string\|null | `.loop/approvals/` filename if paused at a gate, else null. |
| `budget_remaining` | object | `{ "time": <unit>, "cost": <unit> }`; hitting zero → `FailedBudget`. |
| `checkpoint_path` | string\|null | Latest `.loop/checkpoints/` snapshot (best-known-good to revert to). |
| `terminal_state` | string\|null | Null while running; set to one of the 7 at end. |

```json
{
  "schema": "loop-engineer/state@1",
  "iteration_id": 2,
  "state": "repair",
  "plan_version": 1,
  "active_task": "T2",
  "best_score": 0.74,
  "failure_mode": "deterministic-fail",
  "pending_approval": null,
  "budget_remaining": { "time": "18m", "cost": "0.62usd" },
  "checkpoint_path": ".loop/checkpoints/iter1-good.json",
  "terminal_state": null
}
```

`pending_approval` is how an approval gate pauses *and resumes from the same run state* — the gate
sets it; resolution clears it; the loop never spawns a fresh untracked attempt (see
`safety-and-approvals.md`).

---

## 8. `terminal_state.json` — the single end record

**Purpose.** Written exactly once, when the loop reaches a terminal state. It is the definitive
"how did this loop end" record — no silent "completed." Its `state` MUST be one of the canonical
**7 terminal states (verbatim):**

`Succeeded`, `FailedUnverifiable`, `FailedBlocked`, `FailedBudget`, `FailedSafety`,
`FailedSpecGap`, `AbortedByHuman`.

| Terminal state | Fires when |
|---|---|
| `Succeeded` | All `SPEC.md` success criteria verified with evidence. |
| `FailedUnverifiable` | Work seems done but no `verify-*`/eval can prove it (cannot confirm success). |
| `FailedBlocked` | A hard external blocker (missing dep, unavailable system) the loop cannot clear. |
| `FailedBudget` | `time_budget` or `cost_budget` exhausted before success. |
| `FailedSafety` | Policy/safety risk, or detected verifier-gaming → hard-terminate + logged as a security failure. |
| `FailedSpecGap` | Success / verification / terminal condition could not be defined (underspecified — the prime directive). |
| `AbortedByHuman` | A human stopped the run (e.g. declined an approval and chose to abort). |

**Minimal schema (JSON):**

| Field | Type | Meaning |
|---|---|---|
| `state` | enum | One of the 7 above. |
| `iteration_id` | int | Final iteration count. |
| `terminated_at` | string | ISO-8601 UTC timestamp stamped by `loop.emit.terminate()`; additive/optional, so legacy records without it remain valid. |
| `criteria_met` | object | `{ "<criterion#>": true\|false }` for every `SPEC.md` criterion. |
| `completion_policy` | object | Completion rule for the criteria map. v1 supports `{ "mode": "all_required" }`; legacy records without the field are interpreted the same way. Optional (additive). Note: a pre-migration `Succeeded` record whose criteria map contains any `false` value fails this rule and needs re-verification. |
| `evidence` | string[] | Paths to the verification bundles backing the verdict. |
| `false_completion` | bool | True if the loop had earlier *claimed* success that verification later refuted (feeds the false-completion-rate metric). |
| `reason` | string | One line: why this terminal state, especially for any `Failed*`/`Aborted*`. |
| `lessons_ref` | string\|null | Path into `.loop/memory/` long-term lessons for `[[loop-flywheel]]`. |

```json
{
  "schema": "loop-engineer/terminal@1",
  "state": "Succeeded",
  "iteration_id": 2,
  "criteria_met": { "1": true, "2": true },
  "completion_policy": { "mode": "all_required" },
  "evidence": [".loop/artifacts/verify-T2.json", ".loop/artifacts/verify-T1.json"],
  "false_completion": false,
  "reason": "All SPEC criteria verified: coverage 0.83 >= 0.80; validation tests pass.",
  "lessons_ref": ".loop/memory/lessons.md"
}
```

---

## 9. Separation-of-concerns rationale

The artifacts are deliberately partitioned so that **no file carries two jobs** and each can
evolve on its own cadence:

| Concern | Owner | Why isolated |
|---|---|---|
| **Stable rules** | `AGENTS.md`, `WORKFLOW.md` | Policy changes (gates/budgets) churn far more than intent; keep them out of `SPEC.md`. |
| **Intent** | `SPEC.md` | The success contract is the one thing every verification judges against — it must be unambiguous and not buried under loop mechanics. |
| **Machine status** | `TASKS.json`, `.loop/state.json` | Read/written every turn by code; machine-readable and small so resume is deterministic and cheap. |
| **History** | `RUNLOG.md` | Append-only narrative — separating it from live state keeps `state.json` tiny and lets the flywheel mine a clean log. |
| **Proof** | `scripts/verify-*`, `EVALS/`, `terminal_state.json` | Verification must be *independent* of the agent's self-report; the proof surface is its own files so success is established by evidence, not assertion. |

Three properties fall out of this split:

1. **Resumability.** Because machine truth lives in `.loop/state.json` (not chat context), any
   session — even a different engine — reconstitutes the loop from disk. Compaction or a crash
   loses no loop state.
2. **Verifiability over assertion.** Intent (`SPEC.md`) and proof (`scripts/verify-*`,
   `terminal_state.json`) are separate files owned by separate spokes (`loop-contract` writes
   intent; `loop-evals` writes proof), so "done" is always evidence-backed — the structural guard
   against false completion.
3. **Portability.** The contract is plain Markdown + JSON + shell, engine-neutral by
   construction. `AGENTS.md` is the shared entry point and the same artifacts map onto Codex,
   Hermes, and Google surfaces (see `platform-map.md`); v1 specifies the contract, not a live
   cross-engine runner.

---

## 10. YAML skill-manifest example

A loop *declares* its operating contract explicitly (never in prose). This manifest is the
machine-readable face of the inputs/outputs/policies/terminal-states the contract enforces; a
loop-engineer emits it alongside the scaffold so the interface contract is checkable, not implied.

```yaml
# .loop/manifest.yaml — the explicit operating contract for one loop
loop: pricing-coverage-and-validation
schema: loop-engineer/manifest@1

inputs:
  goal: "Bring pricing.py to >=80% coverage and add input validation."
  success_criteria:
    - "1: pricing.py line coverage >= 80% (scripts/verify-full)"
    - "2: parse_request rejects malformed input with a typed error (scripts/verify-fast)"
  constraints:
    - "Do not modify existing public function signatures."
    - "No new third-party dependencies."
  workspace_path: "./"
  allowed_tools: [read, workspace-write]      # NOT network, NOT external-side-effects
  risk_profile: low                           # low | med | high
  time_budget: "30m"
  cost_budget: "1.00usd"
  approval_policy: on_side_effects            # never | on_side_effects | strict

outputs:
  plan: SPEC.md
  task_queue: TASKS.json
  current_state: .loop/state.json
  verification_bundle: .loop/artifacts/
  repair_actions: .loop/repair/<iteration_id>.json
  terminal_state: .loop/terminal_state.json
  lessons_learned: .loop/memory/lessons.md

permissions:                                  # least-privilege tiers
  - read-only
  - workspace-write
  # network / external-side-effects / production-mutation are OFF for this loop

approval_gates:                               # each pauses-and-resumes from run state
  - destructive_commands
  - secret_access
  - production_changes

policies:
  repair_cap: 2                               # then replan | revert | approve | terminate
  plan_then_execute: false                    # set true for untrusted/web environments
  verifier_gaming: hard_terminate_as_security_failure

terminal_states:                              # the canonical 7, verbatim
  - Succeeded
  - FailedUnverifiable
  - FailedBlocked
  - FailedBudget
  - FailedSafety
  - FailedSpecGap
  - AbortedByHuman
```

The `inputs`/`outputs`/`permissions`/`approval_gates`/`terminal_states` keys mirror the spec's
interface-contract table directly; `[[loop-contract]]` scaffolds this manifest from the
architecture decision record that `[[loop-architect]]` emits.

---

## 11. Artifact & schema reference

Every schema-bearing artifact in the contract, its on-disk location, the schema that defines it,
its embedded `$id`, its **required keys** (read verbatim from `schemas/*.schema.json` — an
emitter MUST supply all of them), its lifecycle role, and its stability tier (§0). Required keys
are the floor; `additionalProperties: true` means an artifact may carry more.

| Artifact | Contract path | Schema file | `$id` | Required keys | Lifecycle role | Tier |
|---|---|---|---|---|---|---|
| manifest | `.loop/manifest.yaml` | `schemas/manifest.schema.json` | `loop-engineer/manifest@1` | `schema`, `loop`, `policies`, `terminal_states` | The explicit, machine-readable operating contract for one loop (§10). | **stable** |
| state | `.loop/state.json` | `schemas/state.schema.json` | `loop-engineer/state@1` | `schema`, `iteration_id`, `state`, `plan_version`, `budget_remaining` | The live FSM cursor — the source of machine truth for resume (§7). | **stable** |
| tasks | `TASKS.json` *(workspace root)* | `schemas/tasks.schema.json` | `loop-engineer/tasks@1` | `schema`, `tasks`; each task: `id`, `title`, `status`, `criterion_ref`, `verify`, `depends_on`, `attempts`, `evidence` | The machine-readable task queue (§5). | **stable** |
| terminal | `.loop/terminal_state.json` | `schemas/terminal.schema.json` | `loop-engineer/terminal@1` | `schema`, `state`, `criteria_met`, `evidence`, `false_completion` | The single end record, written once at loop end (§8). | **stable** |
| receipt | `.loop/receipts/*.jsonl` | `schemas/receipt.schema.json` | `loop-engineer/receipt@1` | `schema`, `iteration_id`, `role`, `model`, `outcome` | Append-one-per-line dispatch/cost trail (role vs model, cost-per-success). | *provisional* |
| repair-record | `.loop/repair/<iteration_id>.json` | `schemas/repair-record.schema.json` | `loop-engineer/repair@1` | `schema`, `iteration_id`, `attempt`, `failure_mode`, `hypothesis`, `repair_action`, `verification_before`, `verification_after`, `remaining_delta`, `productive` | One bounded repair pass (diagnosis shape); the canonical repair-productivity input (§13). | *provisional* |
| rollout-record | `.loop/rollout.jsonl` | `schemas/rollout-record.schema.json` | `loop-engineer/rollout@1` | `id`, `parent`, `verdict`, `score`, `score_delta`, `coherent_with_prior_winner`, `productive` | One candidate adjudication in a rollout / genetic-hardening ledger (§13). | *provisional* |

The rollout-record's required set is the only one that does **not** require a `schema` envelope
key (the ledger writer today emits bare records); the schema permits one via
`additionalProperties`, but does not demand it. `doctor` validates receipts and repair/rollout
records **only when the files are present** (§14 C1–C3): an in-flight loop that has not yet
produced a trail still conforms.

---

## 12. Lifecycle vocabulary

The 7 terminal states (§8) are the **frozen** set of ways a loop *ends*. Before it ends, a loop
also holds non-terminal lifecycle values while it is *scaffolded but not started* or *running*.
These non-terminal values are **not** terminal states and never appear in the 7-member
`terminal_state` enum. Two rules make an in-flight loop a first-class, conformant state.

### 12.1 The terminal-file-iff rule

`terminal_state.json` is required **iff** `state.json`'s `terminal_state` is non-null.

- While `state.json` reports `terminal_state: null`, the **absence** of `.loop/terminal_state.json`
  is **conformant** — the loop is in-flight, not failing validation. (`validate_contract` gates
  the terminal-file read on `state.terminal_state`; a null with no file is treated as an
  in-flight loop, not a `missing_file` issue.)
- A non-null `terminal_state` **without** the terminal file is a `missing_file` failure.

**Why the iff, not "always require a terminal file":** a gate that demands a terminal record from
a live loop pushes an operator to *write a terminal state onto a loop that has not terminated* —
a fabricated end record. That is exactly the false completion this contract exists to prevent.
The iff rule removes the incentive: an honest in-flight loop is green without inventing an ending.

### 12.2 The `doctor` lifecycle line

`doctor` (`validate_contract`) adds a `lifecycle` field to its report so an operator sees *why*
no terminal file is expected. It is derived (total and pure — never an issue source) as:

1. **`terminated:<X>`** — if `state.json` parsed with a non-null `terminal_state`, **or**
   `.loop/terminal_state.json` exists. `<X>` is the terminal file's `state` value when the file
   parses to a dict with a string `state`; else `state.json`'s `terminal_state` when that is a
   string; else `unknown`.
2. **`planned`** — else, if `state.json` parsed and its `iteration_id` is `0` (or `"0"`):
   scaffolded, not yet run.
3. **`running`** — else, if `state.json` parsed: executing.
4. **`unknown`** — else (no parseable `state.json`).

`planned`, `running`, and `unknown` are lifecycle-report values only; none is a terminal state,
and no terminal state ever surfaces as one of them. The `terminated:<X>` form is the only overlap
point, and there `<X>` is always drawn from the frozen 7 (or `unknown`).

---

## 13. Two distinct record shapes — repair-record vs rollout-record

The repair-record and the rollout-record are **different artifacts** that share only a
`productive` boolean; they must not be conflated (this section exists so no one conflates them
again). They differ in shape, location, and what `productive` measures:

| | repair-record (`loop-engineer/repair@1`) | rollout-record (`loop-engineer/rollout@1`) |
|---|---|---|
| **Shape** | **Diagnosis** of one bounded repair pass | **Ledger** entry adjudicating one rollout candidate |
| **Location** | `.loop/repair/<iteration_id>.json` (one JSON object per file) | `.loop/rollout.jsonl` (append one JSON object per line) |
| **Key fields** | `failure_mode`, `hypothesis`, `repair_action`, `verification_before`, `verification_after`, `remaining_delta`, `productive` | `id`, `parent`, `verdict`, `score`, `score_delta`, `coherent_with_prior_winner`, `productive` |
| **`productive` means** | repair-productivity: `verification_after.score > verification_before.score` | rollout-productivity: `score_delta` is not null and `> 0` |
| **Feeds** | the repair-productivity metric / baseline (`loop-repair`) | the flywheel's candidate-hardening view (`loop-flywheel`) |

The repair-record is the diagnosis shape the repair skill prescribes and the eval structural
invariant pins; the rollout-record is genome/candidate bookkeeping. Publishing them as two `$id`s
resolves the historic "two 7-field shapes both called *the* repair record" ambiguity.

---

## 14. Conformance checklist

A harness that satisfies **every** item below may claim it **"emits a Loop-Engineer-conformant
contract v1."** Each item is a third-party-checkable statement against the published schemas.
Items **C1–C3 are checked-when-present** — an in-flight loop that has not yet emitted a receipt,
repair, or rollout trail still conforms. `scripts/test_conformance.py` executes this checklist in
CI against the flagship example ([`examples/coverage-repair`](../examples/coverage-repair)) and a
fresh template scaffold, so a drift between this doc, the schemas, and the shipped scaffold cannot
land silently.

**A. Artifacts present & well-formed**
- **A1** — `.loop/manifest.yaml` validates against `loop-engineer/manifest@1` (including the
  canonical 7 `terminal_states`, verbatim and in order).
- **A2** — `.loop/state.json` validates against `loop-engineer/state@1`.
- **A3** — `TASKS.json` validates against `loop-engineer/tasks@1`; no duplicate task ids; no task
  marked `done` without `evidence`.
- **A4** — `RUNLOG.md` is present.

**B. Lifecycle honesty**
- **B1** — Exactly one of: (`state.terminal_state` is null **and** no `terminal_state.json`) **or**
  (`terminal_state` is one of the canonical 7 **and** `terminal_state.json` is present and valid).
- **B2** — `terminal_state.json`, when present, validates against `loop-engineer/terminal@1` with a
  `criteria_met` object, an `evidence` list, and an explicit `false_completion` boolean; a
  `Succeeded` terminal additionally has `false_completion=false`, every declared criterion true
  under `completion_policy.mode=all_required` (legacy records without the field are interpreted
  the same way), and non-empty `evidence`.

**C. Evidentiary trail (checked when present)**
- **C1** — every `.loop/receipts/*.jsonl` line validates against `loop-engineer/receipt@1`.
- **C2** — every `.loop/repair/*.json` validates against `loop-engineer/repair@1`.
- **C3** — `.loop/rollout.jsonl`, when present, validates against `loop-engineer/rollout@1`.

**D. Versioning**
- **D1** — every artifact's `schema` key names a published, current-major schema `$id`.
- **D2** — unknown keys are tolerated (additive fields never reject a v1 artifact).

**E. Lifecycle report**
- **E1** — `doctor` reports a `lifecycle` value consistent with B1: `terminated:<state>` iff the
  terminal pair is present and valid; `planned` / `running` otherwise (§12.2).

---

## 15. `loop-engineer/plan@1` — the Loop Plan IR

`schemas/plan.schema.json` defines a canonical, validated description of a
goal, its tasks, and its policies — the document a future execution runtime
interprets (ADR 0001). It is authored and linted as a **standalone JSON
file**, validated by `loop plan-lint <file>` / `loop.plan.validate_plan()`.

**Scope boundary:** unlike manifest/state/tasks/terminal (§11), plan@1 is
**not yet** an artifact `loop doctor` reads from a scaffolded workspace —
it has no `.loop/`-relative home today. The execution-runtime milestone
that materializes a plan into a live `TASKS.json` will make that call.

**Task kinds:** `agent | tool | gate | approval | join | subloop | human |
terminal` — each carries a common `id`/`kind`/`title`/`depends_on` base
plus kind-specific required fields (`loop/plan.py::_KIND_REQUIRED_FIELDS`).

**Capability-based model policy** (issue #56, ADR 0001 consequence 5): an
optional top-level `model_policy` maps roles (`read`/`reason`/`write`/
`verify`) to capabilities (`fast_low_cost`/`deep_reasoning`/
`code_generation`/`independent_review`) — never a vendor model name. An
`agent`-kind task declares a `role`; a provider profile resolves the
capability to an actual model **outside** the portable contract, recorded
to a receipt for reproducibility, not to the plan.

**Cross-field rules JSON Schema cannot express** (enforced by
`loop/plan.py`, in both validation modes): task-id and
acceptance-criteria-id uniqueness, dangling `depends_on`/`join_on`
references, dependency-graph acyclicity, per-kind required fields, and
`approval_gates` referential integrity.

Golden examples: `examples/plans/coverage-repair.plan.json` (valid, all 8
kinds); `examples/plans/invalid/` (deliberately broken fixtures used by
the negative tests).

---

## 16. `loop-engineer/event@1` — EventStore + deterministic reducer

`schemas/event.schema.json` defines one immutable, append-only fact in a run's
event log (ADR 0001). `loop.events.SQLiteEventStore` persists events in a
SQLite database in WAL mode with `synchronous=FULL` (every committed `append()`
survives a crash) and DB-level `BEFORE UPDATE`/`BEFORE DELETE` triggers that
refuse mutation or removal of a committed row **through the store API**,
regardless of caller; a process with direct write access to the database file
can `DROP TRIGGER` — the triggers are an anti-footgun, not a security control
(see Integrity boundary).
`loop.reducer.reduce_events()` is a pure, resumable left-fold that projects an
ordered event stream into a deterministic state/runlog/receipts view — the
same input sequence always produces a byte-identical result.

**Scope boundary:** `loop doctor` reads `event@1` when `.loop/events.db`
exists (§22) by composing the exact `status`/`replay` read-only verbs, not by
duplicating their logic; an absent store is conformant and adds no issues
(§12.1's terminal-file-iff rule has an analogous "absent is fine" shape). One
run is discovered per store; multi-run support remains deferred.

**Dispatch crash boundary:** `loop run` verifies first, then commits its
`iteration_appended` (or `terminal_written`) event with a compare-and-swap
sequence. That committed event is the source of truth; only afterwards are
`RUNLOG.md` and `.loop/state.json` materialized from the exact recorded
payload. A later `loop run` replays missing legacy materialization before
selecting work, so a crash after the event commit never duplicates a dispatch.
TASKS.json is read-only declarative input for dispatch: event-log
`task_passed` facts supply dynamic completion and dispatch does not rewrite
task status or evidence.

**Verifier isolation:** A declared task verifier runs through
`subprocess.run(shell=False, cwd=workspace, timeout=...)`, so it receives an
argv rather than shell-interpreted input and cannot share the runner process.
A timeout or nonzero exit becomes `VerifyOutcome(False, ...)`, never an
exception. `VerifierExecutionError`, `VerifierNotImplementedError`, and
`RunModeNotImplementedError` are the typed cases where dispatch could not be
attempted.

**Event types:** `contract_opened | iteration_appended | receipt_appended |
terminal_written` — one-to-one with `loop.emit`'s four writer operations
(`open_contract`/`append_iteration`/`append_receipt`/`terminate`), so a
future write-through migration targets an already-matching payload shape.

**Two-layer enforcement, deliberately split:** the store validates event@1
envelope/payload *shape* only (`loop/events.py::validate_event`, both
validation modes, both type-checked in structural fallback); the reducer
enforces *domain* semantics at replay time — FSM transition legality
(`loop.fsm.is_legal_transition`), G1 completion
(`loop.completion.criteria_satisfy_completion`), and terminal immutability
(no event may follow a `terminal_written`) — reusing the exact functions
`loop.contract`/`loop.emit` already enforce at file-write time, never
re-implemented. A store back-end therefore never needs domain awareness to be
conformant; the reducer is a second, independent enforcement point that a
tampered or foreign-sourced event stream still cannot talk past **without
constructing a stream that is itself FSM-legal, G1-satisfying and
hash-chain-consistent; a determined in-workspace rewriter can construct one —
see Integrity boundary.**

### Hash chain (v0.10.0+)

`event@1` carries two **additive, optional** fields: `prev_event_hash` — the
immediately preceding event's `event_hash` within the same run, `null` at
genesis — and `event_hash`, this event's own digest. Both are
`["string", "null"]` constrained to `^[0-9a-f]{64}$`. A fresh v0.10.0 store
declares `PRAGMA user_version = 2`, chains every append, and holds
`event_hash NOT NULL` at the database layer; a pre-existing unchained store is
widened by the explicit `loop migrate` verb (§22), which never rewrites rows.

**Canonical form (normative).** `event_hash` is the lowercase-hex SHA-256 of
the UTF-8 encoding of

```python
json.dumps(preimage, sort_keys=True, separators=(",", ":"),
           ensure_ascii=False, allow_nan=False)
```

where `preimage` is exactly these **twelve** fields:

`schema`, `run_id`, `sequence`, `event_id`, `type`, `actor`, `ts`,
`causation_id`, `correlation_id`, `payload`, `artifact_hashes`,
`prev_event_hash`.

Insertion order is irrelevant (`sort_keys=True` fixes the serialized order).
`event_hash` is never part of its own preimage. An **absent optional field is
hashed as `null`, never omitted** — the preimage object always carries all
twelve keys. A genesis event (the run's `sequence` 0) hashes
`prev_event_hash: null`.

Two caveats for non-Python re-implementations. (1) Floats serialize through
Python's shortest-round-trip `repr`, which other languages' default float
formatting does not necessarily reproduce; keep payload numbers integral or
string-encoded if you need cross-language digests. `allow_nan=False` means
`NaN`/`Infinity` are a hard error, not a serialized token. (2)
`ensure_ascii=False` emits non-ASCII characters literally in UTF-8 and
`sort_keys` orders keys by code point, so **ASCII-only object keys are
recommended** for interop.

**Conformance vectors.** Three records and their digests, generated by
`loop/chain.py` and pinned against it by
`scripts/test_event_chain.py::test_documented_conformance_vectors` — docs and
code cannot drift. Each `Preimage` line is the exact canonical string that is
UTF-8 encoded and SHA-256'd.

*Vector 1 — genesis (`prev_event_hash: null`):*

```json
{"schema":"loop-engineer/event@1","run_id":"run-1","sequence":0,"event_id":"e0","type":"contract_opened","actor":"operator","ts":"2026-07-24T00:00:00+00:00","causation_id":null,"correlation_id":null,"payload":{"workspace":"ws"},"artifact_hashes":[],"prev_event_hash":null}
```

Preimage: `{"actor":"operator","artifact_hashes":[],"causation_id":null,"correlation_id":null,"event_id":"e0","payload":{"workspace":"ws"},"prev_event_hash":null,"run_id":"run-1","schema":"loop-engineer/event@1","sequence":0,"ts":"2026-07-24T00:00:00+00:00","type":"contract_opened"}`

`event_hash` = `3ca65d4da7d87a98616441a86c6866ff39b5513ccd156d8526abfd6df7ec88a7`

*Vector 2 — second event, linked to vector 1:*

```json
{"schema":"loop-engineer/event@1","run_id":"run-1","sequence":1,"event_id":"e1","type":"iteration_appended","actor":"operator","ts":"2026-07-24T00:00:01+00:00","causation_id":null,"correlation_id":null,"payload":{"iteration_id":1,"outcome":"task_passed","state":"execute-task"},"artifact_hashes":[],"prev_event_hash":"3ca65d4da7d87a98616441a86c6866ff39b5513ccd156d8526abfd6df7ec88a7"}
```

Preimage: `{"actor":"operator","artifact_hashes":[],"causation_id":null,"correlation_id":null,"event_id":"e1","payload":{"iteration_id":1,"outcome":"task_passed","state":"execute-task"},"prev_event_hash":"3ca65d4da7d87a98616441a86c6866ff39b5513ccd156d8526abfd6df7ec88a7","run_id":"run-1","schema":"loop-engineer/event@1","sequence":1,"ts":"2026-07-24T00:00:01+00:00","type":"iteration_appended"}`

`event_hash` = `bb40984d1b98bda565d93dd90a39ea212be999078a66cf013f37cbed650c155d`

*Vector 3 — non-ASCII payload (pins `ensure_ascii=False`):*

```json
{"schema":"loop-engineer/event@1","run_id":"run-1","sequence":2,"event_id":"e2","type":"receipt_appended","actor":"operator","ts":"2026-07-24T00:00:02+00:00","causation_id":null,"correlation_id":null,"payload":{"iteration_id":1,"note":"café — naïve ✅","summary":"日本語"},"artifact_hashes":[],"prev_event_hash":"bb40984d1b98bda565d93dd90a39ea212be999078a66cf013f37cbed650c155d"}
```

Preimage: `{"actor":"operator","artifact_hashes":[],"causation_id":null,"correlation_id":null,"event_id":"e2","payload":{"iteration_id":1,"note":"café — naïve ✅","summary":"日本語"},"prev_event_hash":"bb40984d1b98bda565d93dd90a39ea212be999078a66cf013f37cbed650c155d","run_id":"run-1","schema":"loop-engineer/event@1","sequence":2,"ts":"2026-07-24T00:00:02+00:00","type":"receipt_appended"}`

`event_hash` = `0d0413aa0a1903a46a802f98f0a28abafd10ca09d5e312622f729482cfc40a19`

**Third-party re-verification.**
`loop.chain.verify_chain(events, expected_head=...)` is the normative entry
point for re-verifying a chain outside this package's store code: it is pure,
I/O-free, imports no other `loop` module, and accepts any ordered sequence of
event mappings (a SQLite read, a JSONL export, a JSON API response). It
returns `{ok, issues, chained_events, unchained_prefix, head}`, and with
`expected_head` set it additionally fails when the stream's final chained head
is absent or differs. **Scope:** `verify_chain` verifies a *complete run
stream beginning at sequence 0*. It cannot validate a suffix or a slice — a
window that starts mid-run has no genesis to anchor `prev_event_hash: null`
against, and its first record's link is unverifiable by construction.

**Interop rule (normative).** Populating the chain fields is optional per run
but all-or-nothing after the first chained event: once an event carries
`event_hash`, every later event in that run must too and must match the
canonical preimage exactly, or the reference implementation hard-fails the
store.

**Resume rule (normative).** `reduce_events(events, initial=snapshot)` folds a
suffix onto a caller-supplied projection, and the chain is anchored by that
snapshot's `chain_head`. A snapshot that predates v0.10.0 has no `chain_head`
key at all, so a suffix whose first event is chained with a non-null
`prev_event_hash` has nothing to link against: that is refused as an
`EventReplayError` naming the stale snapshot, never as a `ChainBreakError` —
an honest resume is not a tamper report. Re-fold from sequence 0, or carry
`chain_head` in the snapshot. A suffix that begins at a chain genesis
(`prev_event_hash: null`), and a fully unchained suffix, resume unchanged.

**Compatibility rule.** A pre-0.10.0 writer must not append to a chained
store. A fresh v0.10.0 store refuses such an append at the database
(`event_hash NOT NULL`); a migrated store cannot, and an unchained row
appended after a chained prefix is reported as `event_chain_broken` and is
unrepairable, because UPDATE is trigger-blocked. Pin your loop-engineer (and
action) version per store.

### Integrity boundary

The chain is **tamper-evident relative to an anchored head**. That is a
detection property, not a prevention one, and it is scoped to the anchor:
nothing here stops a writer from changing the log. Stating the boundary in
both directions is part of the contract — a reader must know exactly which
claims a clean chain supports.

**It detects:** splicing an event into the middle of a log; reordering events;
editing a committed row without recomputing every downstream digest; byte
corruption of any hashed field; and — given an externally remembered anchor —
*any* divergence of the log from the head that anchor names, including
truncation of the tail and wholesale replacement of the history. Note the
asymmetry: truncation is detected **only** with an anchor, because deleting
trailing events leaves a shorter but internally valid chain.

**It does not detect:**

- **A full in-workspace recompute.** A process with write access to the
  workspace can rewrite history, re-chain from genesis, and forge
  `.loop/state.json` and `terminal_state.json` to agree. With no anchor
  supplied, the event-store block of such a report is wholly clean —
  `state_json_agrees`, `deterministic`, and `legal_sequence` all `true`, a
  `FailedBlocked` run laundered into `Succeeded` — as pinned by
  `scripts/test_adversarial_chain.py::test_full_rewrite_with_recompute_passes_without_anchor_pinned`.
  (In the probe that produced that fixture the report was also globally `ok`
  with zero issues. What the committed pin actually asserts is narrower and
  event-store-scoped: that `event_chain_broken` is absent, that the three
  projection-disagreement codes `state_field_mismatch`,
  `desynced_terminal_window` and `terminal_state_mismatch` stay absent, and
  that the three event-store cleanliness flags `state_json_agrees`,
  `deterministic` and `legal_sequence` stay `true`. A future standalone
  event-store cross-check — a new issue code appended directly to `issues`, as
  `chain_columns_missing` is — would not move any of those, so it must be added
  to this pin's assertions when it is introduced.)
- **A chain-column downgrade.** Dropping `event_hash`/`prev_event_hash`, or
  rebuilding the store without them, silently downgrades a chained history to
  an unchained one. An unchained or legacy doctor report is *not* proof of
  provenance. The `chain_columns_missing` check catches only the lazy variant
  — columns dropped while `user_version` still declares generation 2; a
  downgrade that also resets `user_version` leaves nothing but the anchor.
- **Deleting the store outright**, when no SQLite sidecars remain and no
  `--expect-chain-head` is supplied: a bare `loop doctor` reads that as a
  valid never-ran contract (§22).
- **Well-formed lies.** Nothing in the chain judges whether a payload is
  *true*. A truthfully-recorded, correctly-hashed event asserting a test
  passed when it did not is chain-clean by construction; that is the job of
  evidence@1, the held-out gate, and the verifier — not of the digest.
- **Anything in a never-migrated prefix.** Rows written before migration have
  no hashes to break, so there is no retroactive coverage: doctor reports them
  as `unchained_prefix` and never elides them.

**The mid-run window.** An anchor certifies the log only up to the anchored
head. Everything appended after the last externally-read anchor — including a
rewrite of the suffix — is unverified until the next anchor is read and
remembered outside the workspace. The chain narrows the tampering window; it
does not close it.

Three closing notes. The append-only `BEFORE UPDATE`/`BEFORE DELETE` triggers
are an anti-footgun, not a security control: any writer holding the database
file can `DROP TRIGGER` first. The chain is one of several cross-checks a full
rewrite must satisfy *simultaneously* — `_state_divergence` (state.json
agreement), `_terminal_desync` (terminal-file agreement), and G1 completion
all still apply, which raises the cost of a convincing forgery without
bounding it. And `scripts/test_adversarial_chain.py` pins **both** sides of
this boundary: the attacks that are caught, and four `PINNED LIMITATION`
cases that are not — the full in-workspace rewrite, tail truncation without an
anchor, tampering inside a never-migrated prefix, and the chain-column
downgrade.

---

## 17. `loop-engineer/evidence@1` — hashed evidence + artifact provenance

`schemas/evidence.schema.json` defines a standalone, hashed record that names
an evidence artifact by workspace-relative URI, SHA-256 digest, media type,
producer, optional verifier, and optional policy result. `loop.evidence`
validates that portable record in either JSON Schema or complete structural
fallback mode; `verify_evidence()` additionally resolves the URI beneath a
workspace, rejects traversal and symlink escapes, and verifies the file hash.
`artifact_object_path()` supplies the v1 content-addressed object layout under
`.loop/artifacts/objects/` without writing it.

**Scope boundary:** `loop doctor` reads evidence@1 records from the declared
location `.loop/evidence/*.json` and validates them; it does **not** yet
hash-verify the artifacts they reference, does **not** compare any recorded
digest against anything, and `Succeeded` still requires non-empty evidence
*paths*, not verified hashes. Those tightenings are the next slice.

**Artifact provenance:** `kind` remains an open vocabulary (for example,
`verify-bundle`, `log`, `diff`, `screenshot`, or `report`), while `produced_by`
identifies the run, task, attempt, and executor that produced it. Verification
does not trust a path string: resolution and containment provide one mechanism
for rejecting both `..` traversal and symlink escapes before a 64 KiB-chunked
SHA-256 comparison is attempted.

### Verifier identity (v0.11.0+)

**The four fields.** `verified_by` gains four additive, nullable fields —
`command`, `code_digest`, `code_digest_basis`, and `policy_digest` — recording
what verified a task and how. `required` on `verified_by` stays `["by",
"at"]`; all four fields are optional and nullable, and both the JSON Schema
mode and the structural-fallback mode type-check them identically.

**The code-digest honesty rule.** `code_digest` hashes argv[0] of the declared
`verify` command only when it resolves to a readable regular file inside the
workspace; every other case is `null`, and `code_digest_basis` names exactly
why. The nine bases are the complete enumeration:

| basis | when | digest |
|---|---|---|
| `workspace_file` | argv[0] is a regular file under the workspace and was readable | hex sha256 |
| `path_lookup` | argv[0] has no path separator (`pytest`, `python3`, `true`) — the OS resolved it through `PATH`, so a same-named workspace file is *not* what ran | `null` |
| `outside_workspace` | argv[0] resolved to a real file outside the workspace (`/usr/bin/python3`, a symlink escaping the tree) | `null` |
| `not_a_file` | argv[0] does not resolve to an existing regular file (missing path, directory, dangling symlink) | `null` |
| `unresolvable` | resolving argv[0] raised `OSError` (or pathlib's `RuntimeError` on Python ≤3.12 for a symlink loop), permission-denied parent, or name too long — the honest "could not determine" | `null` |
| `unreadable` | the file exists inside the workspace but could not be read | `null` |
| `unparseable_command` | `shlex.split` raised | `null` |
| `empty_command` | `verify` is absent, blank, or splits to zero words | `null` |
| `injected_verifier` | the caller injected a verifier callable, so **no declared command ran** — recording one would be a fabrication | `null` |

`python3 -m pytest -q` has no hashable workspace script; `null` with basis
`path_lookup` is the truthful record, and a fabricated digest would be worse
than none. When a caller injects a verifier callable the declared command does
not run at all: `command` and `code_digest` are `null` with basis
`injected_verifier`. These nine values co-move across four surfaces:
`CODE_DIGEST_BASES` (`loop/verifier.py`), the `enum` in
`schemas/evidence.schema.json`, the structural-fallback check in
`loop/evidence.py`, and this table.

**The policy digest.** `policy_digest` is sha256 over
`loop.chain.canonical_json` of `{criterion_ref, depends_on, id, verify}` — the
TASKS.json entry's declared goalpost. Run state (`status`, `attempts`,
`evidence`) is excluded because it changes for non-policy reasons and would
make the digest noise; `id` binds *which* goalpost the digest names, and
`depends_on` binds its declared ordering, so both are included.

The digest binds the criterion **reference**, not the criterion **text** —
editing `SPEC.md`'s acceptance wording leaves it unchanged. Binding criterion
text is the evidence-wiring slice.

**Conformance vector.** Over the task entry

```python
{"id": "T-1", "title": "ignored", "status": "pending", "criterion_ref": "C-1",
 "verify": "./scripts/verify-fast.sh", "depends_on": [], "attempts": 0, "evidence": None}
```

`verification_policy` produces the canonical JSON

```
{"criterion_ref":"C-1","depends_on":[],"id":"T-1","verify":"./scripts/verify-fast.sh"}
```

and `verification_policy_digest` produces

```
cb28ced25ec75a20a153f821e7335464a1734eb781146a9d36a598e713caa9fe
```

`scripts/test_conformance.py` pins both literals against the live
implementation.

**The bundle/record pair.** A verified dispatch writes two files:
`.loop/artifacts/verify-iter<N>.json` (the bundle — carries `outcome`/`passed`
per the metrics green-marker convention, `verifier` including `source`, and
`partition`) and `.loop/evidence/evidence-iter<N>.json` (evidence@1 — commits
to the bundle bytes via `sha256`). An evidence record MUST NOT be named
`verify-*.json` — a record in the bundle namespace is read by metrics as a
bundle with no green marker, i.e. a phantom failing gate. `verifier.source` is
`declared_command` only when the task's declared `verify` command was
executed. A bundle whose source is `injected_callable` carries a
caller-supplied verdict and is not gate evidence. `scripts/metrics.py` does not
read `verifier.source` today, so an injected-callable bundle counts toward FCR
exactly like a declared-command bundle — enforcing that distinction is Slice 3
scope. Before this slice the runner wrote no bundles at all, so a
runner-driven contract's FCR input set changes with this release. `loop
simulate` predicts decisions, not writes: it reports `legacy_sync_would_write`
because that write is conditional, but it does not enumerate the bundle and
record a dispatch always writes.

**The partition.** `visible` defaults to the task's `criterion_ref`;
`holdout` is empty unless the task declares `holdout_criteria`; both fields
are optional `array of string` on tasks@1; `holdout_executed` is always
`false` because the runner executes exactly the declared `verify` command.
Running a holdout set remains `scripts/holdout_gate.py`'s job and its verdict
keeps its own canonical shape. A misspelled field name validates (tasks@1 is
`additionalProperties: true`) and yields `declared: false` — an undeclared
partition and a mistyped one are indistinguishable.

**The independence rule.** A record whose `produced_by.executor` equals its
`verified_by.by` (compared strip+casefold) declares that the producer
verified its own work. `loop doctor` reports `self_verified_evidence` and
fails. On the `loop run` path both identities are operator-supplied
(`--executor`, `--verifier-identity`); their defaults (`unattributed`,
`loop.run`) never collide, so a default run cannot manufacture the finding.

**The integrity boundary, in four honest tiers** — not a single "surfaces /
does not surface" pair:

- **Fails `loop doctor`:** a record declaring self-verification
  (`self_verified_evidence`); a runner-written bundle whose record is absent
  (`missing_evidence_record`); a malformed or unparseable record
  (`invalid_evidence` — an errored check fails, it never skips).
- **Recorded for later comparison, not checked by any shipped surface:**
  `policy_digest` and `code_digest`. Nothing in v0.11.0 compares either
  against the live TASKS.json entry or re-hashes the verifier file, so a moved
  goalpost or a swapped verify script is *legible in a diff of two records*
  and nothing more. Automated comparison is the evidence-wiring slice.
- **Detectable only by explicitly calling `verify_evidence()`:** a swapped
  bundle. `loop doctor` does not hash-verify referenced artifacts in this
  release.
- **Not surfaced at all:** a worker that writes a false `verified_by.by`; a
  worker that omits its executor identity; a hand-written record whose
  digests are invented (doctor validates their *shape*, never their truth); a
  rewrite or deletion of the record **and** its bundle together. **Both
  artifacts are plain files outside the hash chain: a worker with write
  access to `.loop/` can rewrite or remove them and `loop doctor` will not
  notice.** Binding the record digest into the chain requires a new event
  type and is the evidence-wiring slice. A record whose referenced bundle is
  absent also passes `loop doctor` clean: `missing_evidence_record` is
  one-directional (it walks bundles looking for their record, never the
  reverse), so doctor never checks that a record's `uri` resolves. And an
  iteration committed to the event log with no evidence written at all — the
  sanctioned crash window between the durable append and the evidence write —
  is undetectable, because the tripwire needs a bundle to fire before it can
  notice anything missing. Closing both gaps is Slice 3 scope.

This does not prove independence. It surfaces **declared** self-verification,
and it records — honestly, with nulls where the process could not know —
what verified the work.

---

## 18. `terminal_superseded` — administrative terminal corrections

`terminal_superseded` is an append-only administrative event that corrects the
currently effective terminal record while preserving the original decision and
every later correction in the reducer projection's oldest-first
`superseded_history`. Each correction carries the corrected terminal fields,
non-empty `justification`, and `{by, at}` `authority`, and its `causation_id`
must identify the terminal event it corrects; chained corrections therefore
remain auditable without replacing any record.

**Scope boundary:** this is a fifth event type with no corresponding
`loop.emit` writer operation — deliberately: unlike the other four,
`terminal_superseded` is administrative and event-log-only; §16's
“one-to-one with `loop.emit`'s four writer operations” describes the other four
types and predates this addition. It is not file-based `terminal@1` replacement
or an `emit`/`doctor` workflow.

**Domain enforcement:** the EventStore validates envelope and payload shape
only; the reducer alone admits this type after a terminal, verifies its
causation anchor, and reuses G1 completion checks when a correction sets
`state` to `Succeeded`. All other event types remain forbidden after a terminal.

---

## 19. Run-control events

`approval_requested`, `approval_resolved`, `run_paused`, and `run_resumed` are
event@1 run-control primitives. `approval_requested` records a non-empty
request, moves the reducer projection to `approval-wait`, and records a pending
approval anchor. `approval_resolved` cites that anchor through `causation_id`;
an approved resolution supplies a legal non-terminal FSM resume target, while a
denied resolution leaves the projected state at `approval-wait` and clears the
pending request.

`run_paused` and `run_resumed` are projection overlays: they set and clear the
projection's `paused` flag and pause reason without changing the FSM state, so
resume preserves the exact prior state. These types, like every non-
`terminal_superseded` event, are forbidden after a terminal record.

**Interop note:** the pre-existing lightweight
`iteration_appended(outcome="approval_requested", state="approval-wait")`
path remains valid. It has no structured request or pending-approval anchor,
so it cannot be consumed by `approval_resolved`; CLI emission policy remains
out of scope for event@1.

---

## 20. `loop simulate` — read-only dispatch prediction

`loop simulate [--mode basic|strict|release] <workspace>` projects the event
store and reports what one `loop run` step would do, without dispatching a
task, invoking its verifier, repairing legacy files, or writing any workspace
artifact. It uses the event store's immutable-first read path; when a crash
left a WAL sidecar, `events.db-shm` is the sole permitted coordination-file
difference and durable event content remains unchanged.

The report includes normal projection health (`divergence`, `terminal_desync`,
and `ok`), plus a `would` object. Its action vocabulary is deliberately
predictive: `would_dispatch`, `would_write_terminal`, `would_block`,
`would_refuse`, or `already_terminal`. `would_dispatch` exposes the declared
verify command and parsed argv, but never executes it. `would_refuse` carries
the matching runner refusal text; `would_block` has no invented refusal text.
For terminal completion prediction, `predicted_terminal` is the payload a real
dispatch would append.

`would.legacy_sync_would_write` identifies whether a real dispatch would enter
one of its legacy reconciliation writes. Its calculation follows the runner's
terminal-first branch structure: terminal reconciliation is assessed only for
terminal projections, iteration lag only for `execute-task`, and all other
non-terminal states report false. A missing or unreadable required state file
is reported as null rather than repaired.

---

## 21. `loop architect` — typed fail-loud deferral

`loop architect` is a permanent typed refusal, not a scaffold. Architecture
classification and ADR authorship — choosing the loop's shape, its
Claude-Code realization, its loop patterns, its risk profile, its
terminal-state plan — is agentic judgment the loop-architect skill performs,
and this deterministic CLI does not call an LLM to reproduce it. A
placeholder ADR file with `REPLACE` fields for the decision itself
(architecture, realization, risk profile) would carry no real information
while looking like a completed judgment artifact to whatever consumes it
next — that is a silent stub in disguise, not a scaffold, so this verb does
not write one.

Every invocation of `loop architect`, with any argv shape (a target, no
target, a nonexistent target, any `--mode` value, any other flag), exits `2`
before parsing a target or a validation mode and prints a single typed message
to stderr pointing at the loop-architect skill and at `loop scaffold` as the
deterministic next step once a real architecture decision record exists. It
performs zero filesystem or event-store I/O: no `sqlite3.connect`, no
`subprocess.run`, no read of `.loop/state.json` or `TASKS.json`. There is no
`0` or `1` exit path — every path is the same typed `2` refusal.

Sources: "Designing a Loop Engineer Skill for Frontier Agent Workflows" (2026), synthesizing
Anthropic guidance on long-running agent harnesses (anthropic.com, 2025), OpenAI Agents/Codex guidance, Google
Conductor, and arXiv PreFlect (2602.07187), SWE-Marathon (2606.07682), Web Agents
Plan-Then-Execute (2605.14290), Plan Compliance (2604.12147), and Code as Agent Harness
(2605.18747).

---

## 22. `loop doctor` — event-store consistency gate

When `.loop/events.db` exists, `loop doctor` composes the exact read-only
`status`/`replay` verbs (§16, §20) — never duplicating their fold/divergence
logic — and folds their findings into its own `issues`/`ok`. An absent store
**with no SQLite sidecar residue and no `--expect-chain-head`** is conformant:
doctor reports `"event_store": {"present": false}` and every other key is
byte-identical to a store-less report; sidecar residue
(`missing_event_store`) or a supplied anchor (`chain_anchor_mismatch`) fails
doctor. When an absent store *does* raise one of those, the block gains the
residue flag — `{"present": false, "sidecar_residue": true}` for a deleted
store whose `-wal`/`-shm` files remain, and `sidecar_residue: false` when the
only finding is the anchor. A present, readable store adds
`"event_store": {"present": true, "readable": true, "run_id", "event_count",
"state_json_agrees", "deterministic", "legal_sequence", "chain"}`; any of
`state_field_mismatch`, `desynced_terminal_window`, `terminal_state_mismatch`,
`illegal_event_sequence`, `event_chain_broken`, `chain_columns_missing`, or
`chain_anchor_mismatch` fails doctor (`ok: false`) with the identical issue
code the `status`/`replay` verbs already use. A store that cannot be read at
all — `corrupt_store`, `empty_store`, `invalid_event`, or `ambiguous_run_id` —
also fails doctor rather than being silently skipped; `"event_store"` reports
`{"present": true, "readable": false, "error_code": <code>}` in that case.
Note the ordering consequence: event@1 validation runs before the fold, so a
tamper that *also* breaks the envelope or payload shape (a payload edit that
drops a required field, say) surfaces as `invalid_event` on an unreadable
store, never as `event_chain_broken`.

**The `chain` block.** A present, readable store nests
`"chain": {"head": {"sequence", "event_hash"} | null, "unchained_prefix": <int>}`
under `event_store`. `head` is `null` for a store with no chained events at
all (a legacy or fully downgraded store) **and also for a store whose chain is
broken**, because the fold stops at the break and never establishes a head. The
block alone therefore does not distinguish "never chained" from "chain broken";
the `event_chain_broken` issue is what separates them, and a `null` head with
no such issue is the honest never-chained case. `unchained_prefix` counts the
leading events that carry no `event_hash`; it is **never elided** — a migrated
store legitimately reports a non-zero prefix, and silently hiding it would let
a legacy tail read as chained provenance. A prefix is not an issue by itself;
it is the honest statement of how much of the log the chain does not cover.

**New issue codes.**

| Code | Meaning |
|---|---|
| `event_chain_broken` | A link check failed: `prev_event_hash` mismatch, recomputed `event_hash` mismatch, an unhashable record, or an unchained row appended after a chained prefix. Unrepairable — UPDATE is trigger-blocked. |
| `chain_anchor_mismatch` | `--expect-chain-head` was supplied and the store's actual head is absent, unreadable, unchained, or a different digest. |
| `chain_columns_missing` | The store declares `user_version >= 2` but the chain columns are gone — the lazy downgrade. A downgrade that also resets `user_version` is invisible here; the anchor is the real control. |
| `missing_event_store` | `events.db` is absent but `-wal`/`-shm` sidecars remain — the store was deleted. Distinct from the pre-existing `missing_store`, which `status`/`replay`/`run`/`migrate` raise when a verb that *requires* a store is pointed at a workspace that has none; `missing_event_store` is a doctor finding about a store that evidently once existed. |
| `self_verified_evidence` | A discovered evidence@1 record declares `produced_by.executor == verified_by.by` (strip+casefold) — the producer verified its own work. Enforces the independence rule of `reference/safety-and-approvals.md` §5, which was prose-only before v0.11.0. |
| `missing_evidence_record` | A runner-written verify bundle `.loop/artifacts/verify-iter<N>.json` exists with no matching `.loop/evidence/evidence-iter<N>.json`. Residue of a removed provenance record, in the same family as `missing_event_store`. Fires only when a bundle is present, so an absent-everything contract stays byte-identical. |

**Evidence discovery (v0.11.0+).** `loop doctor` scans `.loop/evidence/*.json`
when the directory exists; an absent directory with no runner bundle is a
no-op that leaves every doctor key byte-identical (no new top-level key was
added). A malformed or unparseable record **fails** doctor rather than being
skipped, and `loop-engineer/evidence@1` joins `schemas_checked` when at least
one record was read.

**`loop migrate`.** `loop migrate <workspace>` is the only store-upgrade path:
explicit, idempotent, and non-rewriting. It widens `events` with the two
nullable chain columns and stamps `user_version = 2`; it never backfills
hashes onto existing rows, because the append-only triggers forbid UPDATE and
a backfilled digest would be an assertion about history the store cannot
support. Pre-migration rows therefore remain an unchained prefix forever, and
the first post-migration append is a chain genesis
(`chained_from_sequence` in the migrate report names it). Because migrated
columns stay nullable, a migrated store — unlike a fresh one — cannot refuse a
pre-0.10.0 writer at the database layer (see §16's compatibility rule).

**Concurrency assumption.** The read verbs assume no concurrent writer — the
sidecar-free guarantee holds only for a store whose last writer closed
cleanly. `loop doctor`/`status`/`replay`/`simulate` open the store read-only
and immutable when no WAL sidecar exists, so a clean store is read without
leaving a byte behind; against a store with a live or crashed writer, a
`-wal`/`-shm` sidecar is the sole permitted coordination-file difference (§20)
and durable event content still never changes.

### Anchor trust assumptions

`--expect-chain-head` (valid on `doctor`, and identically on its `validate`
and `verify` aliases) fails hard when the store is missing, unreadable, has no
chained head, or has a head that differs from the supplied digest. It is the
only cross-run tamper control in the toolchain — and it is only as trustworthy
as the place the anchor is read from. The anchor is outside the worker's trust
domain when **all three** hold:

1. **The gate is not installed from the worker's own checkout.** The
   `loop-engineer` GitHub Action is pinned to a released tag or SHA of a repo
   the worker cannot write, **and** its `version` input is non-empty — with an
   empty `version` the `Install loop-engineer` step takes its fallback branch
   and installs the kernel from `github.action_path`, i.e. the checkout under
   test, so the code doing the verifying is code the worker may have edited.
2. **The invoking workflow is protected from worker edits** — a required
   workflow, CODEOWNERS on `.github/`, or a branch ruleset. For a same-repo
   pull request the workflow that runs is *the PR head's*, so an unprotected
   workflow file is an unprotected anchor.
3. **The expected head is remembered outside the workspace** — a repository
   variable, a protected environment, or an operator's own record. A digest
   read out of the tree it is meant to certify certifies nothing.

State it plainly: **with the default empty `expect-chain-head`, this action
performs no cross-run tamper detection; it records the head for a comparison
someone else must make.** That recording is the action's `chain-head` output
and a line in its step summary — the place an operator reads the observed head
in order to re-anchor the next run. When an anchor *is* supplied and does not
match, the mismatch itself surfaces in doctor's issue list as
`chain_anchor_mismatch`.

Always pass an anchor in CI. A bare `loop doctor` treats a fully deleted
store — no database, no sidecars — as a valid never-ran contract, so
"delete the evidence" is a passing run without one.
