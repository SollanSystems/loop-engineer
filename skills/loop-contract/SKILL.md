---
name: loop-contract
description: "Scaffold the repo-OS operating contract for an agent loop — SPEC/WORKFLOW/TASKS.json/RUNLOG/.loop/state.json + verify-* skeletons — from an architecture decision, then run the pre-execution reflection before the first change. Use when someone says scaffold the loop contract, set up SPEC/WORKFLOW/TASKS, create the operating contract, initialize a loop, or initialize the repo-OS files for a new agent loop."
---

# loop-contract — scaffold the repo-OS operating contract

Turn an architecture decision into the **on-disk operating contract** an agent loop reads its
truth from every turn. State lives in files, not chat context, so the loop survives compaction,
a crashed session, and even a different engine. This is the externalized-state ("code as agent
harness") discipline: the loop is the design object, and the contract is its persistent form.

This spoke **writes intent and structure**; it does not run the loop and it does not write the
verification logic. `[[loop-run]]` executes against what you scaffold; `[[loop-evals]]` fills the
`scripts/verify-*` proof surface. Keep those concerns out of here.

## When to run

Run **after** `[[loop-architect]]` emits the architecture decision record (ADR). The ADR tells
you the architecture, the realization, the selected loop patterns, the risk profile, and the
terminal-state plan — that is the input. If there is no ADR yet, go to `[[loop-architect]]` first;
scaffolding without a chosen architecture produces a contract that does not match the loop.

You also run here to **re-scaffold or extend** an existing contract (new criteria, new gates) —
but never overwrite a live `.loop/state.json`; that is machine truth a run owns.

## What you produce

The full repo-OS tree (canonical schema: `reference/repo-os-contract.md`), scaffolded from
`templates/`:

```
<workspace>/
  AGENTS.md         # short ToC of stable rules → points at the rest (engine-neutral entry)
  SPEC.md           # success criteria, constraints, non-goals, evidence rules — INTENT
  WORKFLOW.md       # loop policy, approval gates, budgets, the 7 terminal states — STABLE RULES
  TASKS.json        # machine-readable task ledger — the QUEUE
  RUNLOG.md         # human-readable iteration history (one entry per loop) — HISTORY
  EVALS/{dataset,rubrics,regressions,traces}/
  scripts/{verify-fast,verify-full,verify-safety,judge-rubric,extract-trace-metrics}
  .loop/{state.json, terminal_state.json, checkpoints/, artifacts/, approvals/, memory/}
```

Plus a `.loop/manifest.yaml` (the explicit machine-readable operating contract — inputs /
outputs / permissions / approval_gates / terminal_states) and an **iteration-0 RUNLOG entry**
recording the pre-execution reflection. Each artifact has exactly one owner concern — no file
carries two jobs (rationale: `reference/repo-os-contract.md` §9).

The two deterministic gates `verify-fast` and `verify-full` scaffold as runnable stubs; the
three deeper proof-surface scripts (`verify-safety`, `judge-rubric`, `extract-trace-metrics`)
ship in `templates/` as stubs you copy into `scripts/` and wire as the SPEC criteria earn them —
`[[loop-evals]]` owns that proof logic, not this spoke.

## How to fill each template

Map the ADR + goal onto the templates in `templates/` (the `{{PLACEHOLDER}}` tokens are the fill
points). Use the **BOOTSTRAP** prompt in `reference/prompt-templates.md` to drive this end-to-end.

| Template | Fill with | Rule |
|---|---|---|
| `AGENTS.md.tmpl` | Project name + the resume rule | Keep under ~20 lines; it only points at the others. |
| `SPEC.md.tmpl` | `## Goal`, numbered `## Success Criteria`, `## Constraints`, `## Non-Goals`, `## Evidence Rules` | Every success criterion MUST name an evidence source (a `verify-*` check or `EVALS/` case). A criterion with no evidence rule is itself a spec gap. |
| `WORKFLOW.md.tmpl` | Approval gates, `time_budget`/`cost_budget`, repair cap (default **N=2**), the loop sequence | MUST enumerate all **7** terminal states verbatim (see below). |
| `TASKS.json.tmpl` | One task object per bounded unit (`id`, `title`, `status`, `criterion_ref`, `verify`, `depends_on`, `attempts`, `evidence`) | A task is `done` only when `evidence` is non-null and its `verify` passed — never on assertion. |
| `state.json.tmpl` | Initial cursor (`iteration_id:0`, first incomplete `state`, `terminal_state: null`) | Carries every field from the spec State row; serialized after every transition by `[[loop-run]]`. |
| `RUNLOG.md.tmpl` | The iteration-0 reflection entry | Append-only; never edit past entries. |
| `terminal_state.json.tmpl` | Leave as the template | Written exactly once, at loop end, by `[[loop-run]]`. |
| `manifest.yaml.tmpl` | `inputs` (goal, success_criteria, constraints, allowed_tools, risk_profile, budgets, approval_policy) + `outputs` + least-privilege `permissions` + `approval_gates` + `policies` (repair_cap, plan_then_execute) + the 7 `terminal_states` | The explicit machine-readable operating contract; keys mirror the ADR. Canonical schema: `reference/repo-os-contract.md` §10. |
| `verify-fast.sh` / `verify-full.sh` | Wire the deterministic checks the SPEC criteria demand | Runnable stubs; `[[loop-evals]]` owns the real proof logic. |
| `EVALS-rubric.md.tmpl` | Per-artifact rubric schema | Advisory judge; deterministic gates remain the hard pass/fail. |

Fill `.loop/manifest.yaml` from `manifest.yaml.tmpl` (above), mapping each `{{PLACEHOLDER}}` to the
ADR — the canonical schema for every key is `reference/repo-os-contract.md` §10.

## Pre-execution reflection (do BEFORE queueing tasks)

The contract is not "done" the moment the files exist. Before the first change, **critique the
plan** — the PreFlect reflect-before-act pass (it lifts long-horizon success and cuts wasted
edits). For each planned task ask:

1. Is it independently **verifiable** (does a `verify-*` check or eval case prove it)?
2. Is it the **smallest safe step**, or does it bundle several changes?
3. Does it cross a **side-effect boundary** (destructive command, secret, production, money) that
   needs an approval gate in `WORKFLOW.md`?
4. Does the plan **over-phase** the work? An over-decomposed plan can *hurt* (the plan-compliance
   caveat) — collapse needless phases.

Record the critique and any revisions as **iteration 0 in `RUNLOG.md`**, then write the revised
`TASKS.json` and set `.loop/state.json` to the first incomplete state. Bootstrap is read/scaffold
only — emit nothing to production in this step. The reflection itself is a *reasoning* pass, so
dispatch it at the reasoning tier:

```text
Agent(
  subagent_type: "general-purpose",
  model: "sonnet",                     # reason → sonnet (model-routing rule)
  prompt: "Critique this loop plan against SPEC.md success_criteria and WORKFLOW.md gates.
           List unverifiable tasks, over-phasing, and missing approval gates. Output a
           revised TASKS.json only — do not implement. [pre-execution reflection]"
)
```

## The 7 terminal states (put all of them in WORKFLOW.md, verbatim)

`Succeeded`, `FailedUnverifiable`, `FailedBlocked`, `FailedBudget`, `FailedSafety`,
`FailedSpecGap`, `AbortedByHuman`. No silent "completed." Their triggers and the approval
lifecycle live in `reference/safety-and-approvals.md`; `[[loop-run]]` enforces them.

## The underspecified → FailedSpecGap rule (the prime directive)

This is the load-bearing check. If, while writing `SPEC.md`, you **cannot state how a success
criterion would be verified** — a command, an assertion, an artifact check — the objective is
**underspecified**. Do **not** invent acceptance criteria to make the contract look complete.
Instead, write `terminal_state = FailedSpecGap` into `.loop/state.json` with the missing facts,
and surface the gap to the user. A contract that cannot define "done" is the #1 long-horizon
failure mode (false completion / weak self-verification) waiting to happen; catching it here, at
scaffold time, is cheaper than catching it after a run claims a hollow success.

## Hand-off

A complete, reflected contract → `[[loop-run]]` (it reads these files, advances the state machine,
and calls the verification gate). Failing verification later → `[[loop-repair]]`. Measuring or
hardening the gate → `[[loop-evals]]`. Mining the resulting RUNLOG into new eval cases →
`[[loop-flywheel]]`.

---

Reference: `reference/repo-os-contract.md` (canonical artifact schemas, incl. the manifest schema in
§10), `reference/prompt-templates.md` (the BOOTSTRAP prompt), `reference/safety-and-approvals.md`
(terminal-state triggers), and the scaffoldable files in `templates/` (incl. `templates/manifest.yaml.tmpl`).
