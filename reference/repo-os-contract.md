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
refuse mutation or removal of a committed row, regardless of caller.
`loop.reducer.reduce_events()` is a pure, resumable left-fold that projects an
ordered event stream into a deterministic state/runlog/receipts view — the
same input sequence always produces a byte-identical result.

**Scope boundary:** unlike manifest/state/tasks/terminal (§11), `event@1` is
**not yet** an artifact `loop doctor` reads from a scaffolded workspace, and
no workspace-relative on-disk location (e.g. `.loop/events.db`) has been
decided. The execution-runtime milestone that wires a live event log into
`scaffold`/`emit`/`doctor` will make that call.

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
tampered or foreign-sourced event stream still cannot talk past.

---

Sources: "Designing a Loop Engineer Skill for Frontier Agent Workflows" (2026), synthesizing
Anthropic guidance on long-running agent harnesses (anthropic.com, 2025), OpenAI Agents/Codex guidance, Google
Conductor, and arXiv PreFlect (2602.07187), SWE-Marathon (2606.07682), Web Agents
Plan-Then-Execute (2605.14290), Plan Compliance (2604.12147), and Code as Agent Harness
(2605.18747).
