---
name: loop-architect
description: "Classify an agent-loop task and choose its architecture + realization — the brain of the loop-engineer suite. Use when deciding which loop architecture fits, designing the loop for a task, asking what agent system to build, or whether a job is one agent or many. Emits a structured architecture decision record (ADR) that names the architecture, the Claude-Code realization, the loop patterns, the risk profile, the terminal-state plan, and which spokes run next."
---

# loop-architect

The **brain** of the [[loop-engineer]] suite. It does **not** do the end task — it
turns an underspecified objective into a decision: *what shape should this loop be,
and what Claude-Code primitive physically runs it?* The output is an **architecture
decision record (ADR)** that the rest of the suite consumes. Read-only / advisory:
it decides, it does not scaffold or run.

Two separable choices (see `reference/architecture-matrix.md`):
- **(A) Architecture** — how many agents, how much orchestration.
- **(B) Realization** — which Claude-Code primitive (Workflow tool / markdown
  supervisor / portable Python FSM spine / delegate to an acceptance gate — the
  contract's `verify-fast`→`verify-full` by default, optionally `/verify-slice`).

## Prime directive

If you cannot define **success**, **verification**, or a **terminal state**, the task
is underspecified — record `FailedSpecGap` in the ADR rather than greenlighting a loop
that can only *claim* completion. Defining a verifiable success bar is the first
defense against the #1 long-horizon failure (false completion / weak self-verification).

## Rule 0 — maximize a single agent first

Default to **one** well-scoped agent with a tight toolset and a clean contract. Climb
the matrix to supervisor / multi-agent shapes **only** on a real overload signal, never
an anticipated one:

- **Tool overload** — too many tools; selection accuracy drops or semantics conflict.
- **Instruction overload** — one prompt juggling plan + implement + verify + report.
- **Routing overload** — sub-tasks need different model tiers, permissions, or CWDs.
- **Context overload** — one run can't hold the working set; state must externalize.

The loop is the design object, not the prompt. The cheapest reliable loop is the
smallest one that still verifies. When unsure, pick the **lower-complexity** shape and
let [[loop-repair]] / [[loop-flywheel]] escalate if overload actually appears.

## Step 1 — intake (the input contract)

Collect the operating contract before classifying. Missing fields are themselves a
classification signal (and a possible `FailedSpecGap`):

- `goal`, `success_criteria[]`, `constraints[]`, `workspace_path`, `allowed_tools[]`
- `risk_profile {low, med, high}`, `time_budget`, `cost_budget`
- `approval_policy {never, on_side_effects, strict}`

## Step 2 — scenario classification questions

1. **Bounded or open-ended?** Is success self-evident, or does it need an independent check?
2. **One session or many?** Must the run survive compaction / a fresh session / an engine switch?
3. **Parallelizable?** Are there many independent sub-tasks with a fixed join, no shared mutable state?
4. **Trusted or adversarial?** Does it read attacker-influenceable content (web pages, untrusted tool output)?
5. **Does a spec + plan already exist?** If yes, this is likely an acceptance-gated slice — delegate, don't build.
6. **Side effects?** Destructive commands, secrets, production mutation, money movement → approval gates + higher risk profile.

## Step 3 — scenario → architecture → realization

The core decision table (depth + the 5-candidate ratings live in
`reference/architecture-matrix.md`):

| Scenario signal | Architecture | Realization |
|---|---|---|
| Bounded, parallelizable, single-session fan-out | Multi-agent / modular | **Workflow tool** — JS spine; every `agent()` names an explicit `model:`; results stay off the main context. |
| Long-horizon, multi-session, repo-backed, resumable | Repository-OS / supervisor | **Repo-OS contract + markdown supervisor** — state in files; supervisor reads `state.json`, continues from first incomplete state. |
| Max-determinism / cross-engine resume required | Supervisor + portable spine | **Portable Python FSM spine** (init/next/complete + `state.json`). v1 ships **no spine code** — implement the ~100-line pattern, or reuse the author's `harmony-agent` `engine/cli.py`. |
| Acceptance-gated slice (spec + plan exist) | (delegation) | **The contract's `scripts/verify-fast`→`verify-full` gate** + a write agent — don't reimplement. *Optional:* `/verify-slice` (claude-code-orchestration) adds a 2-iteration fix + cross-review. |
| Early prototype, single maintainer | Single-skill | Inline supervisor, minimal contract — just a SPEC + a verify command. |

These compose: a real system is often row-5 repo-OS substrate, a row-3 supervisor
driving it, spawning row-4 fan-out for the one phase that parallelizes. Pick the
*dominant* shape; record the composition.

## Step 4 — select loop patterns

From `reference/loop-patterns.md`, choose the inner control flow (usually 2–3):
pre-execution reflection (PreFlect — record this suite's A/B trigger policy), milestone loop
with explicit progress accounting, patch-and-repair, improvement flywheel,
manager-orchestrator delegation, and **plan-then-execute** (the default for untrusted /
web environments — precommit the execution graph). Critique any precommitted plan
before freezing it: a flawed, over-phased plan actively hurts.

## Step 5 — emit the ADR

Output a structured architecture decision record:

```json
{
  "goal": "<one line>",
  "architecture": "supervisor-skill (row 3 over repo-OS row 5)",
  "realization": "markdown-supervisor + repo-OS contract",
  "loop_patterns": ["preflect (policy A)", "milestone-loop", "patch-and-repair"],
  "risk_profile": "med",
  "approval_policy": "on_side_effects",
  "terminal_state_plan": ["Succeeded", "FailedUnverifiable", "FailedBlocked",
                          "FailedBudget", "FailedSafety", "FailedSpecGap", "AbortedByHuman"],
  "next_spokes": ["loop-contract", "loop-run", "loop-evals", "loop-repair"],
  "rationale": "<why this shape over the cheaper one; which overload signal justified climbing>"
}
```

The `terminal_state_plan` is drawn from the canonical seven — every loop must be able
to reach an explicit terminal state; never a silent "completed."

## Routing note

Any agent dispatch you suggest in the ADR names an explicit `model:` (read → `haiku`,
reason → `sonnet`, write → `opus`) per the model-routing rule — a Workflow
`agent({ model: "sonnet", … })` fan-out, a write agent on `opus`. Omitting
`model:` inherits the costly main-loop model; the author blocks that with a PreToolUse hook
(`workflow_routing.py`), but the rule holds on any surface.

## Hand-off

Once the ADR is emitted, run [[loop-contract]] to scaffold the chosen shape into the
repo-OS operating contract, then [[loop-run]] to execute it. The ADR is the durable
input both consume.

If the realization must survive an engine switch (the cross-engine / portable-spine
row), map the chosen realization onto the target surface using
`reference/platform-map.md` — it translates each repo-OS contract element (read files /
run scripts / write state / dispatch with an explicit `model:`) onto Claude, Codex,
Hermes, and Google, keeping the ADR's realization a runner swap rather than a rebuild.

Deep dives: `reference/architecture-matrix.md` (5-candidate ratings + realization
picker), `reference/loop-patterns.md` (the 6-pattern library).

---

Sources: `reference/architecture-matrix.md` (the 5-candidate ratings + realization picker this skill emits) and "Designing a Loop Engineer Skill for Frontier Agent Workflows" (2026), synthesizing SWE-Marathon (arXiv 2606.07682 — long-horizon success rates motivating the verifiable-success bar), PreFlect (arXiv 2602.07187 — the pre-execution reflection policy), Plan Compliance (arXiv 2604.12147 — the scenario→architecture decision table), and Anthropic guidance on long-running agent harnesses (anthropic.com, 2025).
