# ADR — pricing-coverage-and-validation

> Architecture Decision Record emitted by `[[loop-architect]]` (read-only / advisory).
> It is the durable input that `[[loop-contract]]`, `[[loop-run]]`, `[[loop-evals]]`, and
> `[[loop-repair]]` all consume. The matrix ratings + realization picker live in
> `reference/architecture-matrix.md`; the inner control flow in `reference/loop-patterns.md`.

## Intake (the operating contract)

| Field | Value |
|---|---|
| `goal` | Bring `pricing.py` to `>=80%` line coverage + typed `parse_request` validation |
| `success_criteria[]` | (1) coverage `>= 80%`; (2) malformed input raises typed `PricingError` |
| `constraints[]` | no signature changes; no new deps; do not edit the verifier |
| `workspace_path` | `./` |
| `allowed_tools[]` | `read`, `workspace-write` |
| `risk_profile` | `low` |
| `time_budget` / `cost_budget` | `30m` / `1.00usd` |
| `approval_policy` | `on_side_effects` |

## Prime-directive check

Both success criteria reduce to a concrete, runnable `scripts/verify-*` gate (coverage line-rate;
typed-rejection tests). Success, verification, and a terminal condition are all definable →
**not** `FailedSpecGap`. The loop is safe to greenlight.

## Rule 0 — maximize a single agent first

Default to one well-scoped agent. We climb to a supervisor only on a real overload signal:

- **Context overload — YES.** Coverage + validation is a measure → change → re-measure loop whose
  truth (best coverage so far, repair attempts, the failing line set) must survive across turns and
  a possible compaction. That working set does not belong in chat context; it must externalize to
  files. This is the one overload signal that justifies climbing from `single-skill` to
  `supervisor-skill`.
- Tool / instruction / routing overload — NO. Few tools, one clear job, two model tiers at most.

A single supervisor over an externalized contract is therefore the *lowest-complexity* shape that
still gives resumable, evidence-backed verification. We do **not** reach for multi-agent fan-out
(no independent parallel sub-tasks) or the Harmony Python spine (no cross-engine resume required).

## Decision

```json
{
  "goal": "Bring pricing.py to >=80% coverage and add typed input validation to parse_request.",
  "architecture": "supervisor-skill (single supervisor, row 3 over a row-5 repo-OS substrate)",
  "realization": "markdown-supervisor + repo-OS contract",
  "loop_patterns": ["preflect (policy A — critique before first change)", "milestone-loop", "patch-and-repair"],
  "risk_profile": "low",
  "approval_policy": "on_side_effects",
  "terminal_state_plan": ["Succeeded", "FailedUnverifiable", "FailedBlocked", "FailedBudget",
                          "FailedSafety", "FailedSpecGap", "AbortedByHuman"],
  "next_spokes": ["loop-contract", "loop-run", "loop-evals", "loop-repair", "loop-flywheel"],
  "rationale": "Single agent is enough for the work itself, but the measure-change-remeasure loop needs externalized state to resume and to prove 'done' by evidence rather than assertion — the context-overload signal that justifies one supervisor over the repo-OS contract. Cheaper shapes (inline single-skill) cannot survive compaction or guard against false completion; costlier shapes (multi-agent / Python spine) buy parallelism and cross-engine resume this task does not need."
}
```

## Why this realization over the alternatives

| Candidate | Verdict | Why |
|---|---|---|
| Single-skill (inline loop) | Rejected | No externalized state → loses the diff / best-score / repair history on compaction; weak guard against false completion. |
| **Supervisor-skill + markdown supervisor** | **Chosen** | Resumable from `.loop/state.json`; intent (`SPEC.md`) and proof (`scripts/verify-*`) are separate files, so "done" is evidence-backed. The workhorse shape for a real loop. |
| Multi-agent / Workflow fan-out | Rejected | No independent parallel sub-tasks with a fixed join; orchestration overhead unjustified. |
| Harmony Python FSM spine | Rejected | No max-determinism / cross-engine resume requirement; v1 ships no new spine — would only point at Harmony `engine/cli.py`. |
| Delegate to `/verify-slice` only | Partial | No pre-existing GSD spec+plan slice, so we scaffold the contract — but `loop-run` still *calls* `/verify-slice` for acceptance rather than building a verifier. |

## Loop patterns selected

- **Pre-execution reflection (PreFlect, policy A):** critique the plan and name the likely
  uncovered branches *before* the first edit — over-phasing or a wrong plan actively hurts.
- **Milestone loop with explicit progress accounting:** two milestones (T1 validation, T2
  coverage), each with its own `verify` gate; progress is the count of `done` tasks with non-null
  `evidence`.
- **Patch-and-repair:** on a red gate, hand to `[[loop-repair]]` for one bounded hypothesis →
  one change → re-verify, capped at N=2 (see `.loop/repair/iter-002.json`).

## Hand-off

`[[loop-contract]]` scaffolds this ADR into `SPEC.md` / `WORKFLOW.md` / `TASKS.json` /
`RUNLOG.md` / `.loop/state.json`; `[[loop-evals]]` fills the `scripts/verify-*` gates;
`[[loop-run]]` then operates the machine. After the run reaches `Succeeded`, `[[loop-flywheel]]`
mines `RUNLOG.md` + traces to promote the zero-qty / negative-price failures into the permanent
regression set so they can never silently return. See `README.md` for the artifact→spoke map.

Reference: `reference/architecture-matrix.md` (5-candidate ratings + realization picker),
`reference/loop-patterns.md` (the pattern library).
