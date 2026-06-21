# Architecture Matrix — choosing the loop's shape

Reference for [[loop-architect]]. This is the decision substrate behind the
*scenario → architecture → realization* call. The job is two separable
choices: **(A) the architecture** (how many agents, how much orchestration)
and **(B) the realization** (which Claude-Code primitive physically runs it).
`loop-architect` emits both as an architecture decision record (ADR).

Companion: [[loop-contract]] scaffolds whichever shape is chosen; the loop
patterns selected per scenario live in `reference/loop-patterns.md`.

---

## Rule 0 — maximize a single agent first

> **Add orchestration only when a single agent provably overloads.** Default
> to one well-scoped agent with a tight toolset and a clean contract; reach
> for multi-agent / supervisor structure **only** when one of these overload
> signals is real (not anticipated):
>
> - **Tool overload** — the agent needs so many tools that selection accuracy
>   drops, or tools have conflicting semantics that confuse one instruction set.
> - **Instruction overload** — the system prompt is juggling several distinct
>   jobs (plan + implement + verify + report) and the agent drifts between them.
> - **Routing overload** — sub-tasks need genuinely different models/tiers,
>   permissions, or working directories that one agent can't cleanly hold.
> - **Context overload** — a single run can't hold the working set, so state
>   must be externalized and handed across turns/sessions.

This mirrors the harness guidance: *the loop is the design object, not the
prompt* — and the cheapest reliable loop is the smallest one that still
verifies. Every step up the matrix below adds reliability-of-decomposition at
the cost of complexity and coordination overhead. Climb only on a real signal.

The matrix dimensions and the single-agent-first default are drawn from the
source research's frontier-harness synthesis (Anthropic long-running-agent
harness guidance + OpenAI Agents/Codex orchestration patterns); the
parallelism and cost columns track the empirical long-horizon results
(SWE-Marathon, Code-as-Agent-Harness).

---

## The 5 candidate architectures

Rated `Low / Med / High` per dimension. **Verifiability** = how naturally the
shape supports independent acceptance checks. **Parallelism** = how much
independent work can run concurrently. **Cost** = relative token + coordination
overhead (Low is cheaper). **Ease-of-adoption** = effort to stand up and keep
running.

| Architecture | Complexity | Reliability | Verifiability | Parallelism | Cost | Ease | Best use |
|---|---|---|---|---|---|---|---|
| **1. Single-skill** (one agent, inline loop, minimal contract) | Low | Low–Med | Low | None | Low | High | Early prototype, single maintainer, bounded one-shot task where success is self-evident; throwaway exploration. |
| **2. Modular-skills-library** (one driver agent, calls focused skills/sub-skills) | Low–Med | Med | Med | Low | Low–Med | High | A solo agent whose job decomposes into reusable steps (lint→build→test) but stays single-threaded and single-session. |
| **3. Supervisor-skill** (a controller agent runs an explicit state machine, externalizes state, gates approvals) | Med | High | High | Low–Med | Med | Med | Long-horizon, multi-session, repo-backed work that must resume cleanly and pause for approval; the workhorse for real loops. |
| **4. Multi-agent-skillset** (manager + parallel workers + a verifier, fan-out/fan-in) | High | Med–High | High | High | High | Med | Bounded, decomposable, parallelizable work where independent workers don't share mutable state and a separate verifier gates the join. |
| **5. Repository-OS-integrated** (state lives in the repo: SPEC/WORKFLOW/TASKS/RUNLOG/.loop; any engine drives it) | Med–High | High | High | Med | Med | Med–Low | The most durable long-horizon shape — survives session loss, model changes, and engine switches; the portable end-state for anything that must outlive one run. |

**Reading the table.** Reliability rises with explicit state + an independent
verifier (rows 3–5); it is *not* maximized by raw agent count — row 4's
reliability is capped Med–High because coordination and verifier-gaming risk
grow with worker count (the documented #1 long-horizon failure is
false-completion / weak self-verification, SWE-Marathon). Row 5 trades a bit of
adoption ease for the only shape that is engine-neutral and crash-safe.

These are not mutually exclusive: a real system is often **row 5 as the
substrate** (repo-OS state) with a **row 3 supervisor** driving it, spawning
**row 4 fan-out** for the one phase that parallelizes. The matrix picks the
*dominant* shape; composition is expected.

---

## Scenario → architecture → realization

Once the architecture is chosen, bind it to a Claude-Code realization. This is
the core decision table (spec §4):

| Scenario signal | Architecture | Realization |
|---|---|---|
| Bounded, parallelizable, single-session fan-out | Multi-agent / modular (row 4/2) | **Workflow tool** — deterministic JS spine; `agent()` calls each name an explicit `model:`; intermediate results stay in script vars, off the main context. |
| Long-horizon, multi-session, repo-backed, resumable | Repository-OS-integrated / supervisor (row 5/3) | **Repo-OS contract + markdown supervisor** — state externalized to files; clean cross-session handoff; the supervisor reads `state.json` and continues. |
| Max-determinism / cross-engine resume required | Supervisor + portable spine (row 3 over row 5) | **Python FSM spine** — Harmony's existing `engine/cli.py` pattern (init/next/complete + `state.json` serialize). v1 ships **no new spine code**; it points at Harmony. |
| Acceptance-gated slice (spec + plan already exist) | (delegation) | **`/verify-slice`** + the `engineer` agent (`claude-code-orchestration`) — don't reimplement; the slice loop already does the 2-iteration fix + Codex cross-review + escalate-to-flag. |
| Early prototype, single maintainer | Single-skill (row 1) | Inline supervisor, minimal contract — just enough SPEC + a verify command; skip the full repo-OS scaffold until the loop earns it. |

The emitted ADR records: chosen architecture (+ which rows compose), chosen
realization, the loop patterns selected from `reference/loop-patterns.md`, the
risk profile, the planned terminal-state set, and which spokes run next
(`[[loop-contract]]` → `[[loop-run]]` → `[[loop-repair]]` / `[[loop-evals]]`).

---

## When to pick each realization

### Workflow tool (deterministic fan-out)
Pick when work is **bounded and parallelizable in a single session** and you
want determinism + cost control: tens–hundreds of independent sub-tasks, a
fixed join, no cross-session resume needed. The JS spine is the control flow;
agents do judgment. Every `agent()` call **must** name `model:` (read→haiku,
reason→sonnet, write→opus) — `workflow_routing.py` enforces this at runtime and
the omission inherits the costly main-loop model.

```js
// fan-out 20 file audits → join → one synthesis (illustrative)
const findings = await Promise.all(files.map(f =>
  agent({ model: "haiku", prompt: `Audit ${f} for the rule in SPEC.md; return JSON.` })));
const report = await agent({ model: "sonnet", prompt: `Synthesize: ${JSON.stringify(findings)}` });
```

Avoid when the run must survive a session boundary or switch engines — Workflow
state is in-process and Claude-specific.

### Markdown-supervisor (repo-OS contract)
Pick for the **common real loop**: long-horizon, multi-session, repo-backed,
must resume after compaction or a fresh session, must pause for approval. State
externalizes to `SPEC/WORKFLOW/TASKS.json/RUNLOG/.loop/state.json` (see
`reference/repo-os-contract.md`); the supervisor is a Claude agent that reads
`state.json`, continues from the first incomplete state, and writes one RUNLOG
entry per iteration. This is the default unless a signal pushes you up to a
Python spine or down to an inline prototype. Dispatched sub-work still names
`model:`; verification calls `/verify-slice`.

```text
resume rule: state.json exists → skip intake → continue from first incomplete state
```

### Harmony Python-spine (max determinism / cross-engine)
Pick **only** when you need a tested deterministic state machine that an engine
other than Claude can also drive (true cross-engine resume), or when drift
between runners is unacceptable. Realization = Harmony's `engine/cli.py` spine
(init/next/complete, `state.json` after every transition, one resume rule in a
thin per-engine runner). **v1 reuses Harmony — it ships no new spine.** If a
scenario "needs a runtime," that is the over-engineering trap Harmony already
closed: reach for the existing spine, not a new one.

### Delegate to /verify-slice (acceptance-gated slice)
Pick when a **spec + plan already exist** and the unit of work is an
acceptance-gated slice — i.e. the loop *is* "implement this slice until its
`## Acceptance Criteria` + per-task `Verify:` commands pass." Do **not** build a
loop here; hand off to `/verify-slice` (independent verifier ∥ Codex
cross-review + auto-fix, max 2 then escalate) and, for a milestone batch,
`/verify-milestone`. `loop-engineer` *designs* the criteria and *calls* the
gate; it never reimplements verification (spec §5 reuse contract). Receipts land
in `.gsd/audit/receipts/*.jsonl` under the model-routing contract.

---

## Decision shortcut

1. Can one agent do it with a tight toolset and a self-evident check? → **row 1, inline** (or, if a plan exists, **delegate to `/verify-slice`**).
2. Single session, lots of independent units, fixed join? → **row 4/2, Workflow tool**.
3. Spans sessions / needs resume / needs approval gates? → **row 5/3, markdown-supervisor + repo-OS contract** (the default real loop).
4. Must a non-Claude engine resume the exact state, or is runner-drift unacceptable? → **row 3-over-5, Harmony Python-spine** (reuse, don't build).

When unsure, choose the **lower-complexity** row and let `[[loop-repair]]` /
`[[loop-flywheel]]` escalate the architecture if overload signals actually
appear — the same fail-cheap-then-climb discipline the loop itself uses.

---

Sources: "Designing a Loop Engineer Skill for Frontier Agent Workflows" (2026), synthesizing OpenAI Agents/Codex orchestration guidance, Anthropic "Effective harnesses for long-running agents," Google Conductor, and arXiv PreFlect (2602.07187), SWE-Marathon (2606.07682), Web Agents Plan-Then-Execute (2605.14290), Plan Compliance (2604.12147), Code as Agent Harness (2605.18747).
