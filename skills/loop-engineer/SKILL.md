---
name: loop-engineer
description: "Router for designing, launching, verifying, repairing, and improving agent loops. Use for broad agent-loop intent — design an agent loop, build a verification harness, set up a repair loop, optimize my agent system, run a long-running goal, create an agent harness, create an agent loop, make my agentic coding more robust. Points to the right spoke (loop-architect, loop-contract, loop-run, loop-repair, loop-evals, loop-flywheel) and defers to existing verification/execution assets."
---

# loop-engineer

**The loop is the design object — not the prompt.** A loop-engineer designs, launches, verifies, repairs, and improves *other* agent loops; it does not primarily solve the end task. Its first job is to turn an underspecified objective into an **executable operating contract** — success criteria, task queue, tool boundaries, evaluation methods, stopping rules, approval gates, and persistent artifacts that survive across turns and sessions.

**Prime directive.** If you cannot define success, verification, or a terminal state, the task is **underspecified** (`FailedSpecGap`) — say so, do not call the next completion "done." This is the central defense against the #1 long-horizon failure mode: false completion / weak self-verification / verifier gaming.

This skill is the **router**. It maps broad intent onto eight focused spokes — six that own the loop lifecycle (architect → contract → run → repair → evals → flywheel) and two diagnostic spokes (runtime-monitor, inspector) that observe a loop live or audit its contract. Read the matching spoke's `SKILL.md`; depth lives in `reference/` (loaded on demand).

## When to use this router

Reach here for broad agent-loop intent: "design an agent loop", "build a verification harness", "set up a repair loop", "optimize my agent system", "long-running goal", "agent harness", "make my agentic coding more robust." If you already know the phase (architecting vs running vs repairing vs measuring vs improving), skip straight to that spoke below.

The router's only job is to send you to the right spoke — it does **not** design, scaffold, run, or repair a loop itself; the spokes do. Two signals say you are in the right place: the work is about the *loop* (its shape, contract, execution, verification, or improvement) rather than the end task the loop performs, and the request is broad enough that the phase is not yet obvious. If the actual work is the domain task — writing the feature, doing the UI, running the migration — this is the wrong entry point; route to the matching domain skill and let the loop wrap it.

## The 8-spoke decision map

Six spokes own one phase each of the loop lifecycle; pick by where you are, not by what you hope to produce. The phases run in order for a new loop and are re-entered out of order as a run hits failures, approval boundaries, or improvement opportunities. The last two spokes are diagnostic — reach for them to watch a running loop or audit an existing one, at any point in the lifecycle.

| Spoke | Reach for it when… | Why this spoke |
|---|---|---|
| **[[loop-architect]]** | You have a raw objective and need to decide the loop's shape — one agent or many, which architecture, which physical realization (Workflow / markdown-supervisor / portable Python-spine / delegate). The brain: classifies the scenario and emits an **architecture decision record**. Read-only/advisory. | The cheapest reliable loop is the smallest one that still verifies, so the shape decision comes first and on evidence — picking a multi-agent fan-out for a job one agent can verify wastes budget and adds failure surface. |
| **[[loop-contract]]** | The architecture is chosen and you need to scaffold the **repo-OS operating contract** — `SPEC.md`, `WORKFLOW.md`, `TASKS.json`, `RUNLOG.md`, `.loop/state.json`, `verify-*` skeletons — plus the pre-execution reflection record. | Externalizing success criteria, the task ledger, and the FSM cursor to files is what lets the loop survive compaction and cross-session handoff; a loop with no on-disk contract cannot honestly resume. |
| **[[loop-run]]** | The contract exists and you need to **operate the loop** — run the state machine (intake→plan→critique→queue→execute→verify→repair/replan/approval→terminal), honor the 7 terminal states, pause/resume on approval, dispatch with explicit `model:`, and call the acceptance gate. | One transition per turn with `state` serialized after each keeps the run inspectable and resumable, and routing every action through an independent gate is the core defense against false completion. |
| **[[loop-repair]]** | Verification failed and you need to **patch and rerun** — classify the failure mode, make the smallest bounded repair, emit a structured repair record, and cap attempts (default N=2) before replan/revert/approve/terminate. | Bounded, recorded, capped repair is what makes a loop converge instead of thrash; unbounded retrying is itself a failure mode and the most common precursor to an agent editing the goalposts. |
| **[[loop-evals]]** | You need to **measure the loop** — design the 7-layer eval suite and the two first-class metrics (**false-completion-rate**, **repair-productivity**), with deterministic gates before rubric judges. | A loop is only as trustworthy as the checks that gate it, so the deterministic blocking gate is designed before the advisory rubric judge — a model score alone can never clear a deterministic failure. |
| **[[loop-flywheel]]** | You want the loop to **get better over time** — mine traces/RUNLOG into new eval cases, propose harness changes, and compact memory (short-term continue-run summary vs long-term lessons). | Every real failure should compound into a permanent regression case rather than recur, and separating short-term continue-run memory from long-term lessons keeps both the current run lean and the harness improving. |
| **[[loop-runtime-monitor]]** | A loop is mid-run and you need to **watch it live** — read `.loop/state.json` + `RUNLOG.md` to flag stall, repair-churn, or budget-overrun and recommend an intervention before the run thrashes or burns its budget. | Catching a degenerating run while it is still running is cheaper than adjudicating the wreckage afterward; live stall/churn/overrun signals are the early-warning layer that turns a silent runaway into a bounded intervention. |
| **[[loop-inspector]]** | You inherited (or finished) a loop and need to **audit its contract** — score an existing loop dir against the 7-state taxonomy and the prime-directive checklist (defines success? verification? terminal states? approval gates? false-completion defense?) and emit a gap report. | A loop you cannot verify is a false-completion risk by construction; scoring the contract against the prime directive surfaces the missing success/verification/terminal-state machinery before you trust the loop's "done." |

## Quickstart — pick a path

- **New loop (start here):** [[loop-architect]] → [[loop-contract]] → [[loop-run]]. Architect classifies the scenario and writes the ADR; contract scaffolds the repo-OS files; run executes the state machine under approval gates.
- **A loop is failing:** [[loop-repair]] — diagnose the failure mode, make a bounded fix, rerun the gate, escalate at the attempt cap.
- **Measuring a loop:** [[loop-evals]] — stand up the eval layers and the two missed metrics; deterministic checks block, rubric judges advise.
- **Improving a loop:** [[loop-flywheel]] — turn failures and traces into regression cases and harness upgrades; compact memory.
- **Must survive an engine switch:** start at [[loop-architect]] and ask for the cross-engine realization — the repo-OS contract stays engine-neutral so the same run resumes under Codex or Hermes via a runner swap, not a rebuild (`reference/platform-map.md`).

The canonical seven terminal states every loop declares (no silent "completed"): `Succeeded`, `FailedUnverifiable`, `FailedBlocked`, `FailedBudget`, `FailedSafety`, `FailedSpecGap`, `AbortedByHuman`.

Three anti-patterns this router exists to prevent: calling the next completion "done" without an independent check (the `FailedSpecGap`/false-completion guard), climbing to a multi-agent shape before a single agent has actually overloaded, and rebuilding a verifier, state machine, or dispatcher that the bundled core or your workspace already provides. If you catch yourself doing any of the three, stop and re-route through the matching spoke.

## How the suite connects to existing assets

This suite is **orchestration over composition** — it owns the loop lifecycle (architect → contract → run → repair → evals → flywheel) and delegates every capability that already exists in the workspace rather than reimplementing it. The split is deliberate, and it is what keeps the plugin small:

- **The spokes decide** *when* and *in what order* a capability runs, and persist the contract that makes the decision durable.
- **The bundled portable core does the work** — the contract's `scripts/verify-fast`→`verify-full` gate, the `python3 -m loop` CLI (`doctor`/`validate`/`verify`/`inspect`), and `.loop/` state + `.loop/receipts/*.jsonl` run a loop end-to-end with no external setup.
- **Net-new code stays small:** the `loop/` contract core + CLI, the structural gates (`validate_frontmatter.py`, `self_eval.py`), and the runtime-monitor / anti-cheat / benchmark scripts. The suite does not reimplement a planning or orchestration engine.
- **The payoff:** every loop runs on the bundled core alone; optional integrations (`/verify-slice`'s fix-loop, routing-receipt tooling, the superpowers planning surface) layer on for free *where you already have them*.

The bundled portable core runs every loop with no external setup: `python3 -m loop doctor|validate|verify|inspect`, the contract's `scripts/verify-fast`→`verify-full` gate, and `.loop/` state + `.loop/receipts/*.jsonl`. On top of that, the suite *composes with* optional integrations where you already run them — it never requires them:

- **`/verify-slice` and `/verify-milestone`** (claude-code-orchestration, *optional*) — auto-repair + cross-review layered on the contract's `verify-*` gate. `loop-evals` *designs* the criteria; `loop-run` *calls* the gate. No new verification engine is shipped here.
- **A portable Python FSM spine** (*optional*) — the init/next/complete + `state.json`-resume pattern for max-determinism / cross-engine resume; ~100 lines, or reuse the author's `harmony-agent` `engine/cli.py`. v1 ships no spine code.
- **The grader-split pattern** (as in the `launch-local-agent` skill) — an objective blocking gate in front of a judged advisory rubric; the model for keeping deterministic checks ahead of any model verdict.
- **The model-routing rule** — every dispatched agent names an explicit `model:` (read→haiku, reason→sonnet, write→opus) so cost is bounded and dispatches are auditable; receipts append to `.loop/receipts/*.jsonl`. *Optional:* the author enforces this with PreToolUse hooks (`model_routing.py` / `workflow_routing.py`) and `/routing` modes.
- **superpowers** (*optional*) — `writing-plans`, `executing-plans`, `subagent-driven-development`, `verification-before-completion`, `test-driven-development` compose the markdown-supervisor realization. Any on-disk planning dir works as the planning surface (the author uses GSD `.gsd/`).
- **ui/orchestration surfaces** — when a loop's actual work is UI/UX or general orchestration (not loop engineering), defer to the appropriate `ui-ux`/`orchestration` surface; this suite builds and runs the loop, it does not do that domain work.

Routing example (the contract every dispatch in this suite follows): a read-only scenario scan dispatches an `Explore` agent with `model: haiku`; a plan critique dispatches with `model: sonnet`; a code-writing repair dispatches `engineer` with `model: opus`. Never omit `model:`.

## Where the depth lives

This router stays deliberately thin; every detail lives one hop away in `reference/`, loaded on demand by the spoke that needs it. Start with the architecture/realization picker: **`reference/architecture-matrix.md`** (the 5-candidate matrix + the scenario→architecture→realization decision table + the "maximize a single agent first" rule). From there, each spoke links its own deeper reference — use this map to jump straight to the right depth:

- `reference/architecture-matrix.md` — owned by [[loop-architect]]; the 5-candidate ratings + the realization picker.
- `reference/loop-patterns.md` — [[loop-architect]]; the 6-pattern inner-control-flow library.
- `reference/repo-os-contract.md` — [[loop-contract]]; the repo-OS tree + per-artifact schema.
- `reference/prompt-templates.md` — [[loop-contract]] and [[loop-run]]; BOOTSTRAP / GOAL-LAUNCH / REPAIR / SHORT-OUTCOME-FIRST.
- `reference/eval-suite.md` — [[loop-evals]] and [[loop-flywheel]]; the 7 layers, the two first-class metrics, the flywheel schedule.
- `reference/safety-and-approvals.md` — [[loop-run]] and [[loop-repair]]; escalation ladder, approval lifecycle, terminal states, anti-cheat.
- `reference/platform-map.md` — [[loop-architect]]; the engine-neutral contract mapped onto Claude / Codex / Hermes / Google.

If a question is about *how* a step works rather than *which* step is next, you have left the router — open the reference above and read it there.
