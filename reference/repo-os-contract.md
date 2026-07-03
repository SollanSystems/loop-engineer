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
| `state` | enum | Current FSM state (`intake` … `verify` … `terminal`). |
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
| `criteria_met` | object | `{ "<criterion#>": true\|false }` for every `SPEC.md` criterion. |
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

Sources: "Designing a Loop Engineer Skill for Frontier Agent Workflows" (2026), synthesizing
Anthropic guidance on long-running agent harnesses (anthropic.com, 2025), OpenAI Agents/Codex guidance, Google
Conductor, and arXiv PreFlect (2602.07187), SWE-Marathon (2606.07682), Web Agents
Plan-Then-Execute (2605.14290), Plan Compliance (2604.12147), and Code as Agent Harness
(2605.18747).
