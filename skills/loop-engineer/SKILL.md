---
name: loop-engineer
description: "Router for designing, launching, verifying, repairing, and improving agent loops. Use for broad agent-loop intent — design an agent loop, build a verification harness, set up a repair loop, optimize my agent system, run a long-running goal, create an agent harness, make my agentic coding more robust. Points to the right spoke (loop-architect, loop-contract, loop-run, loop-repair, loop-evals, loop-flywheel) and defers to existing verification/execution assets."
---

# loop-engineer

**The loop is the design object — not the prompt.** A loop-engineer designs, launches, verifies, repairs, and improves *other* agent loops; it does not primarily solve the end task. Its first job is to turn an underspecified objective into an **executable operating contract** — success criteria, task queue, tool boundaries, evaluation methods, stopping rules, approval gates, and persistent artifacts that survive across turns and sessions.

**Prime directive.** If you cannot define success, verification, or a terminal state, the task is **underspecified** (`FailedSpecGap`) — say so, do not call the next completion "done." This is the central defense against the #1 long-horizon failure mode: false completion / weak self-verification / verifier gaming.

This skill is the **router**. It maps broad intent onto six focused spokes. Read the matching spoke's `SKILL.md`; depth lives in `reference/` (loaded on demand).

## When to use this router

Reach here for broad agent-loop intent: "design an agent loop", "build a verification harness", "set up a repair loop", "optimize my agent system", "long-running goal", "agent harness", "make my agentic coding more robust." If you already know the phase (architecting vs running vs repairing vs measuring vs improving), skip straight to that spoke below.

## The 6-spoke decision map

| Spoke | Reach for it when… |
|---|---|
| **[[loop-architect]]** | You have a raw objective and need to decide the loop's shape — one agent or many, which architecture, which physical realization (Workflow / markdown-supervisor / Harmony Python-spine / delegate). The brain: classifies the scenario and emits an **architecture decision record**. Read-only/advisory. |
| **[[loop-contract]]** | The architecture is chosen and you need to scaffold the **repo-OS operating contract** — `SPEC.md`, `WORKFLOW.md`, `TASKS.json`, `RUNLOG.md`, `.loop/state.json`, `verify-*` skeletons — plus the pre-execution reflection record. |
| **[[loop-run]]** | The contract exists and you need to **operate the loop** — run the state machine (intake→plan→critique→queue→execute→verify→repair/replan/approval→terminal), honor the 7 terminal states, pause/resume on approval, dispatch with explicit `model:`, and call the acceptance gate. |
| **[[loop-repair]]** | Verification failed and you need to **patch and rerun** — classify the failure mode, make the smallest bounded repair, emit a structured repair record, and cap attempts (default N=2) before replan/revert/approve/terminate. |
| **[[loop-evals]]** | You need to **measure the loop** — design the 7-layer eval suite and the two first-class metrics (**false-completion-rate**, **repair-productivity**), with deterministic gates before rubric judges. |
| **[[loop-flywheel]]** | You want the loop to **get better over time** — mine traces/RUNLOG into new eval cases, propose harness changes, and compact memory (short-term continue-run summary vs long-term lessons). |

## Quickstart — pick a path

- **New loop (start here):** [[loop-architect]] → [[loop-contract]] → [[loop-run]]. Architect classifies the scenario and writes the ADR; contract scaffolds the repo-OS files; run executes the state machine under approval gates.
- **A loop is failing:** [[loop-repair]] — diagnose the failure mode, make a bounded fix, rerun the gate, escalate at the attempt cap.
- **Measuring a loop:** [[loop-evals]] — stand up the eval layers and the two missed metrics; deterministic checks block, rubric judges advise.
- **Improving a loop:** [[loop-flywheel]] — turn failures and traces into regression cases and harness upgrades; compact memory.

The canonical seven terminal states every loop declares (no silent "completed"): `Succeeded`, `FailedUnverifiable`, `FailedBlocked`, `FailedBudget`, `FailedSafety`, `FailedSpecGap`, `AbortedByHuman`.

## Reuse — this suite integrates, it does not duplicate

It composes existing assets rather than rebuilding them. Defers to:

- **`/verify-slice` and `/verify-milestone`** (claude-code-orchestration) — the acceptance-verification engine. `loop-evals` *designs* the criteria; `loop-run` *calls* the gate. No new verification engine is shipped here.
- **Harmony `engine/cli.py` spine** — the tested init/next/complete + `state.json`-resume FSM. When `loop-architect` picks the max-determinism / cross-engine realization, it points to this; v1 ships no new spine code.
- **[[launch-local-agent]]** — its objective-gate-then-judged-grader split is the model for separating the deterministic (blocking) gate from the rubric (advisory) judge.
- **Model-routing HARD CONTRACT** (`model_routing.py` / `workflow_routing.py`, `/routing` modes, `.gsd/audit/receipts/*.jsonl`) — every dispatched agent names an explicit `model:` (read→haiku, reason→sonnet, write→opus), receipts are emitted, routing modes are honored.
- **superpowers** — `writing-plans`, `executing-plans`, `subagent-driven-development`, `verification-before-completion`, `test-driven-development` compose the markdown-supervisor realization. GSD (`.gsd/`) is the planning surface.

Routing example (the contract every dispatch in this suite follows): a read-only scenario scan dispatches an `Explore` agent with `model: haiku`; a plan critique dispatches with `model: sonnet`; a code-writing repair dispatches `engineer` with `model: opus`. Never omit `model:`.

## Where the depth lives

Start with the architecture/realization picker: **`reference/architecture-matrix.md`** (the 5-candidate matrix + the scenario→architecture→realization decision table + the "maximize a single agent first" rule). Each spoke links its own deeper references (`loop-patterns.md`, `repo-os-contract.md`, `prompt-templates.md`, `eval-suite.md`, `safety-and-approvals.md`, `platform-map.md`).
