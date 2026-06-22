# Glossary — loop-engineer

The vocabulary this suite uses. These terms are load-bearing: the skills, the
deterministic gates, and the metrics all refer back to the definitions here.
Where a term maps to a skill, the skill is named in brackets.

## Core stance

**Loop engineering.** The discipline of treating an agent *loop* — not a single
prompt and not a single agent — as the unit of design. A loop engineer decides
the loop's shape, writes its operating contract, runs it under gates, repairs it
when verification fails, measures it, and improves it over time. The end task the
loop performs is downstream of getting the loop right.

**The loop (as design object).** The closed cycle an agent runs to move an
objective toward a verified terminal state: `intake → plan → critique → queue →
execute → verify → {repair | replan | approval} → terminal`. The loop is the
thing under design; the feature, migration, or analysis is its payload.

**Operating contract (repo-OS).** The on-disk files that externalize a loop's
state so it survives compaction and cross-session handoff: `SPEC.md` (success
criteria), `WORKFLOW.md` (policy + gates), `TASKS.json` (the ledger),
`RUNLOG.md` (narrative), and `.loop/state.json` (the FSM cursor). A loop with no
on-disk contract cannot honestly resume. [loop-contract]

## Verification vocabulary

**Deterministic gate.** A blocking check whose verdict is a command exit code, a
file assertion, or a parsed value — never a model opinion. A red deterministic
gate cannot be cleared by judgment. This is the suite's primary defense against
false completion. [loop-evals, loop-run]

**Advisory rubric.** A model-scored quality judgment (e.g. `evals/rubric.md`)
that is *recorded but never blocks*. It rides above the deterministic gate and
can only add concerns, never clear a deterministic failure. [loop-evals]

**Held-out verifier split.** Acceptance checks divided into a **visible** set the
loop can see and optimize against, and a **holdout** set withheld until terminal
verification by an independent gate. A loop may declare `Succeeded` only if the
*holdout* set passes — passing only the visible set is the signature of overfit
/ verifier-gaming. Shipped as runnable tooling: `scripts/holdout_gate.py`.
[loop-evals]

**Anti-cheat trajectory scan.** After a `Succeeded` claim, a sweep of the diff
and trajectory for shortcut signatures — test-file mutation, hardcoded expected
values, hidden-answer/holdout reads, skip/xfail injection, and edits to the gate
scripts themselves. A finding downgrades the verdict (to `FailedUnverifiable`,
or `FailedSafety` for gate tampering). Shipped as runnable tooling:
`scripts/anticheat_scan.py`. [loop-repair, loop-evals]

**False completion.** The failure mode where a loop calls the next output "done"
without an independent check that confirms it — the #1 long-horizon failure mode
this suite exists to prevent. Operationalized as a measurable event: visible
gate passed AND holdout gate failed.

## The two first-class metrics

**False-completion-rate (FCR).** The fraction of runs that declared success on
the visible gate but failed the held-out gate. The lower the better; making it
*measured* (not self-reported) is what the held-out split and anti-cheat scan
exist to do. [loop-evals]

**Repair-productivity.** Of the bounded repair attempts a loop made, the fraction
that moved verification forward (reduced the remaining delta) rather than
thrashing. Distinguishes a loop that converges from one that spins. [loop-evals,
loop-repair]

**Rollout ledger.** An append-only JSONL record of a rollout/repair loop's
*candidates* — one line per proposed change, never rewritten, so the lineage
survives compaction. Each record carries exactly 7 fields: `id`, `parent`,
`verdict`, `score`, `score_delta`, `coherent_with_prior_winner`, `productive`.
`coherent_with_prior_winner` answers whether a candidate preserved the prior
winner's gains; `productive` is the per-candidate signal behind
repair-productivity. Shipped as runnable tooling: `scripts/rollout_ledger.py`.
[loop-repair, loop-flywheel]

**Comparative benchmark.** A measurement tool — not a bake-off — that computes
the suite's metrics (false-completion-rate, repair-productivity, criteria-met)
for two result inputs (a reference harness vs `loop-engineer`) and the delta
between them, so the suite's value over a baseline is *measured* rather than
asserted. Ships the measurement only; live numbers are the operator's to run.
Shipped as runnable tooling: `scripts/benchmark_harness.py`, with the A/B
protocol in `reference/eval-suite.md`. [loop-evals]

## Repair vocabulary

**Bounded repair / attempt cap.** Repair is patch-and-rerun with a hard ceiling
(default 2 attempts) before escalating to replan → revert → approval → terminal.
Unbounded retrying is itself a failure mode and the most common precursor to an
agent editing the goalposts. [loop-repair]

**Repair record.** The 7-field structure emitted on every repair attempt:
`failure_mode`, `hypothesis`, `repair_action`, `verification_before`,
`verification_after`, `remaining_delta`, `productive`. It is what makes
repair-productivity computable. [loop-repair]

**Failure-mode taxonomy.** The canonical classes a `failure_mode` may take:
`deterministic-fail`, `rubric-fail`, `flaky`, `regression`, `spec-gap`,
`environmental`. [loop-repair]

## Terminal states

Every loop exits through exactly one named state — no silent "completed":

| State | Meaning |
|---|---|
| `Succeeded` | Verification (incl. holdout) passes; all acceptance criteria met |
| `FailedUnverifiable` | Cannot confirm success or failure — verification gap or anti-cheat finding |
| `FailedBlocked` | Cannot proceed — tool, permission, or dependency block |
| `FailedBudget` | Time or cost budget exhausted |
| `FailedSafety` | Safety/policy risk (incl. gate tampering); hard-terminated |
| `FailedSpecGap` | Objective underspecified — success criteria could not be defined |
| `AbortedByHuman` | Explicitly stopped by the operator |

**Spec gap.** The condition where success, verification, or a terminal state
cannot be defined for the objective as given. The honest response is to declare
`FailedSpecGap` — not to pretend the next completion is "done." [loop-architect,
loop-run]

## Shape & realization

**Architecture realization.** The physical form a loop takes once its shape is
chosen: a native **Workflow** script, a **markdown-supervisor** (superpowers
plans), the **Harmony Python spine** (`engine/cli.py` init/next/complete), or a
**delegate** to an existing runner. The operating contract stays engine-neutral
so the same run resumes under a different engine via a runner swap, not a
rebuild. [loop-architect]

**Flywheel.** The improvement cycle that turns real failures and traces into
permanent regression cases and harness upgrades, so a failure compounds into a
test instead of recurring. [loop-flywheel]

## Observing & auditing a loop

**Runtime monitor.** Watching a *running* loop from outside its own execution —
reading its externalized state (`.loop/state.json` + `RUNLOG.md`) and recomputing
progress from evidence, not the agent's prose — to catch a bad run while it is
still cheap to stop. Detects **stall** (same active task across N iterations with
no measured progress), **repair-churn** (repair attempts with no score
improvement), and **budget-overrun**, then surfaces one intervention
recommendation. Read-only over the run: it recommends, never mutates.
[loop-runtime-monitor]

**Loop inspector / gap report.** A read-only audit of an *existing* loop
directory (a `.loop/` contract, a superpowers or ruflo harness — anyone's) that
scores it against the prime-directive checklist (defines success? verification?
terminal states? approval gates? false-completion defense?) and the 7-state
taxonomy, and emits a **scored gap report** naming what is missing. Reads the
target under plan-then-execute — its content is data, never instruction.
[loop-inspector]
