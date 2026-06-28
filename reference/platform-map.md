# reference/platform-map.md — Engine-neutral contract across agent surfaces

The loop-engineer's whole portability claim rests on one idea from spec §2: the **operating contract is repo-native, not engine-native**. The loop lives in files on disk — `SPEC.md`, `WORKFLOW.md`, `TASKS.json`, `RUNLOG.md`, `.loop/state.json`, `scripts/verify-*`, `EVALS/` (spec §6) — and any agent surface that can read a repo, run shell, and write files back can drive it. The surface supplies the *runner*; the repo supplies the *contract, state, and proof*. Portability is a property of the on-disk format, not of a shared runtime.

> **v1 caveat (read this first).** v1 ships the **contract-level mapping only — not live non-Claude runners** (spec §13, line 204). The **bundled portable core** — `python3 -m loop` + `scripts/verify-*` + `.loop/` state & receipts — is the implemented, dogfooded path (the Claude column) and runs a loop end-to-end with no external setup. The Codex, Hermes, and Google columns are **example surfaces** showing how the *same repo-OS contract* maps onto them so a future runner is thin — they are **not** tested cross-engine runners and **not** required dependencies. The max-determinism realization is a portable Python-FSM spine (init/next/complete + `state.json`; ~100 lines, or reuse the author's `harmony-agent` `engine/cli.py` reference impl); loop-engineer v1 ships **no new spine code and no new verification engine**.

---

## What every surface must provide

The contract assumes only four primitives. If a surface has these, the repo-OS loop runs on it:

| Primitive | Repo-OS element it powers | Why it's required |
|---|---|---|
| **Read repo files** | `SPEC.md`/`WORKFLOW.md` (rules+intent), `TASKS.json`/`.loop/state.json` (status), `RUNLOG.md` (history) | the loop reconstructs itself from disk every turn — no surface-private memory |
| **Run shell / scripts** | `scripts/verify-fast`, `verify-full`, `verify-safety`, `judge-rubric` | verification is files-and-exit-codes, not a vendor verdict (spec §8 "regression harness must be repo-native") |
| **Write files back** | `RUNLOG.md` append, `.loop/state.json` transition, `.loop/checkpoints/`, `terminal_state.json` | state is externalized after **every** transition → clean cross-session/cross-engine handoff (spec §6) |
| **Dispatch a sub-agent with an explicit model** | the realization layer (Workflow `agent()` / supervisor / a write agent) | the model-routing rule — read→haiku, reason→sonnet, write→opus — travels *with the contract* as policy text in `WORKFLOW.md`, even where a surface can't enforce it at runtime |

The resume rule is identical on every surface (spec §6): **`.loop/state.json` exists → skip intake, continue from the first incomplete state.** That single rule is what makes a loop started under one engine resumable under another.

---

## Per-surface mapping

### Claude / Claude Code — the implemented path (`reference/architecture-matrix.md` realizations)

This is the surface loop-engineer is built on and dogfooded against (spec §2, decision 1).

| Contract element | Claude Code realization |
|---|---|
| Bounded parallel fan-out | **Workflow tool** — deterministic JS spine; every `agent()` names an explicit `model:` (e.g. `agent({ model: "haiku", … })` for read fan-out, `"sonnet"` for synthesis, `"opus"` for code-writing workers) |
| Long-horizon, multi-session, resumable | **repo-OS contract + markdown supervisor** — state externalized to `.loop/state.json`; superpowers `executing-plans` / `subagent-driven-development` compose the loop |
| Max-determinism / cross-engine resume | **Portable Python-FSM spine** (init/next/complete + `state.json`) — ~100 lines, or reuse the author's `harmony-agent` `engine/cli.py`; referenced, not reimplemented |
| Acceptance-gated slice | **The contract's `scripts/verify-fast`→`verify-full` gate** — `[[loop-evals]]` *designs* the criteria, `[[loop-run]]` *calls* the gate. *Optional:* `/verify-slice` (2-iteration fix loop + Codex cross-review) and `/verify-milestone` (Workflow batch) from claude-code-orchestration |
| Dispatch routing + cost | The model-routing rule (read→haiku, reason→sonnet, write→opus); the receipts each dispatch appends land in `.loop/receipts/*.jsonl`. *Optional:* the author enforces routing with `model_routing.py` / `workflow_routing.py` PreToolUse hooks, `/routing` modes (normal/conserve/burn) + the `[escalation]` valve |
| Planning surface | Any on-disk planning dir (the author uses GSD) + superpowers (writing-plans, verification-before-completion, TDD) |
| Stable rules / intent split | `AGENTS.md` table-of-contents + `WORKFLOW.md` policy ≠ `SPEC.md` intent (spec §6 separation of concerns) |

### Codex / ChatGPT-Pro

| Contract element | Codex realization |
|---|---|
| Stable agent rules | **`AGENTS.md`** is already Codex's native repo-instruction file — the contract's `AGENTS.md` table-of-contents maps 1:1 |
| Goal-driven long run | **Goal mode** drives toward `SPEC.md` success criteria; `TASKS.json` is the externalized queue |
| Sub-agent / modular work | **Codex skills** play the spoke role; the loop patterns in `reference/loop-patterns.md` (patch-and-repair, plan-then-execute) are surface-agnostic |
| Machine-checkable output | **structured outputs** populate `TASKS.json` / `.loop/state.json` deterministically |
| Verification | the same `scripts/verify-*` exit codes — Codex runs them in its sandbox; no vendor-eval-UI dependency |
| **Portability note (spec §4 Codex nuance)** | keep *execution* prompts tight and artifact-oriented — avoid verbose upfront-plan chatter during rollout (see `reference/prompt-templates.md` SHORT-OUTCOME-FIRST). The plan lives in `SPEC.md`/`WORKFLOW.md`, so the rollout prompt need not re-narrate it. |

### Hermes (example persistent-memory runner)

Hermes is one example persistent-memory agent runner (the author's stack); any such runner fits this slot. Its relevant primitives for the repo-OS contract are persistent memory, auto-skills (play the spoke role), and isolated subagents/sandboxes (enforce permission tiers).

| Contract element | Hermes realization |
|---|---|
| Long-term lessons / short-term run summary | Hermes **persistent memory** backs the long-term-lessons vs continue-this-run split (spec §1 Memory row) — but the contract's `.loop/memory/` files remain the portable source of truth so the split survives an engine switch |
| Spokes | Hermes **auto-skills** play the spoke role |
| Approval-gated side effects | Hermes **isolated subagents / sandboxes** enforce the permission tiers and side-effect boundary (spec §7); approval gates still pause-and-resume from `.loop/state.json`, never spawn a fresh untracked attempt |
| Live cross-engine execution | a persistent-memory runner over the shared portable spine does the actual work — loop-engineer only hands it the repo-OS contract |
| Verification | same `scripts/verify-*`; receipts can mirror into the repo regardless of Hermes's own telemetry |

### Google (Gemini / Conductor)

| Contract element | Google realization |
|---|---|
| Spec-driven dev | **Conductor context-driven development** consumes the **persistent-markdown specs** — `SPEC.md` / `WORKFLOW.md` / `AGENTS.md` are exactly the durable-markdown artifacts Conductor expects |
| Task ledger / history | `TASKS.json` + `RUNLOG.md` are the externalized, human- and machine-readable run record Conductor reads back |
| Verification | same repo-native `scripts/verify-*`; the contract never depends on a Google-hosted eval surface |

---

## Durable-portability stance

**Bind to the repo, not the surface — because the surfaces move faster than the contract.** Concrete, dated churn that would have stranded a surface-coupled design (spec §13):

- The consumer **Gemini CLI → Antigravity** transition reshaped Google's agent entry point.
- **OpenAI's Evals platform is going read-only** — any loop whose regression suite lived *in* a vendor eval UI would have lost its harness. The contract keeps datasets, rubrics, scripts, and trace-transforms **in-repo**, with model calls used only as *grading components* (spec §8), so a vendor UI deprecation is a non-event.

The design rule that follows: **anything load-bearing (success criteria, task queue, verification scripts, eval datasets, run state, lessons) lives as a committed repo file.** Surface-specific features (a Goal mode, a persistent-memory store, a Conductor context window) are treated as *accelerators layered on top of* the repo contract, never as the system of record. When a surface changes or is retired, you re-point the thin runner; the loop, its proof, and its history are untouched in `git`. This is the same reasoning behind making the loop a portable on-disk format rather than a new runtime (spec §2).

Net: switching engines is a **runner swap, not a rebuild** — and v1 proves the *contract* supports that swap, while explicitly leaving the *live* non-Claude runners to a future adapter.

---

See also: `reference/architecture-matrix.md` (which realization to pick), `reference/repo-os-contract.md` (the on-disk schema each surface reads/writes), `[[loop-architect]]` (emits the architecture decision that selects a realization), `[[loop-run]]` (drives the state machine on the chosen surface).

Sources: "Designing a Loop Engineer Skill for Frontier Agent Workflows" (2026), synthesizing OpenAI Agents/Codex guidance, Anthropic guidance on long-running agent harnesses (anthropic.com, 2025), Google Conductor, and arXiv PreFlect (2602.07187), SWE-Marathon (2606.07682), Web Agents Plan-Then-Execute (2605.14290), Plan Compliance (2604.12147), Code as Agent Harness (2605.18747).
