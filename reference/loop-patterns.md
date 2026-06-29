# Loop Patterns

The pattern library `loop-architect` selects from once a scenario is classified. A
pattern is **how the loop iterates** (its inner control flow); the architecture
(see `architecture-matrix.md`) is **where it runs** (Workflow tool, markdown
supervisor, portable Python spine, or a delegated acceptance gate). One architecture
usually composes two or three of these patterns — e.g. a repository-OS supervisor
runs PreFlect once at intake, a milestone loop across the run, and patch-and-repair
inside each milestone.

Every pattern below shares one non-negotiable from the prime directive: **no silent
"completed."** Each iteration ends in a verification verdict or one of the seven
terminal states (`Succeeded`, `FailedUnverifiable`, `FailedBlocked`, `FailedBudget`,
`FailedSafety`, `FailedSpecGap`, `AbortedByHuman`). A loop with no terminal state is
a bug, not a pattern.

The skeletons are pseudocode control-flow, not literal scripts. They reuse — they do
not reimplement — the contract's `scripts/verify-*` gate (optionally `/verify-slice`),
a portable Python FSM spine (or the author's `harmony-agent` `engine/cli.py`), and the
`.loop/receipts` trail. See `[[loop-architect]]` to pick a pattern,
`[[loop-run]]` to execute it, `[[loop-repair]]` for the repair inner loop, and
`[[loop-evals]]` for the verification each pattern calls.

---

## 1. Pre-execution reflection (PreFlect)

**What:** Before the first irreversible action, the agent reflects on the goal,
surfaces hidden assumptions, ambiguities, and likely failure modes, and writes that
reflection to a durable artifact (`.loop/memory/preflect.md` or the SPEC's evidence
rules). Catching an underspecified objective *here* is what produces a clean
`FailedSpecGap` instead of a confident-but-wrong rollout. This is the loop's first
defense against false completion: you cannot verify success you never defined.

**When to use:** Always run it at intake for any non-trivial loop; it is the cheapest
guard against the dominant long-horizon failure mode (false completion / weak
self-verification). Make it mandatory for high-risk, ambiguous, or
side-effect-bearing goals.

**A/B trigger policy:** the reflection step has a cost/benefit knob — a design choice of
this suite. PreFlect (arXiv 2602.07187) reflects on every plan unconditionally and shows
reflect-before-act lifts long-horizon success (with a token-cost-vs-performance analysis,
§4.7); the conditional knob below is how this suite trades that cost off.

- **Policy A — always reflect:** unconditional pre-execution reflection. Default for
  high-risk / underspecified / production-mutating goals where a wrong first move is
  expensive.
- **Policy B — reflect-on-uncertainty:** reflect only when an uncertainty signal
  fires (ambiguous success criteria, missing constraints, conflicting requirements,
  or the architect's risk profile is `med`/`high`). Default for bounded, well-specified,
  low-risk tasks, where unconditional reflection is mostly latency tax.

`loop-architect` records the chosen policy (A or B) in the architecture decision
record so `loop-contract` and `[[loop-run]]` apply it consistently.

```text
reflect(goal, context) -> {assumptions[], ambiguities[], risks[], success_is_verifiable: bool}
if not success_is_verifiable: terminate(FailedSpecGap)   # do not start an unverifiable run
else: write .loop/memory/preflect.md ; proceed to plan
```

---

## 2. Milestone loop with explicit progress accounting

**What:** Decompose the goal into a small ordered queue of milestones in `TASKS.json`;
each iteration advances exactly one milestone, verifies it, and writes a `RUNLOG.md`
entry that records *measured* progress (tests passing, criteria met) — never a prose
"making good progress." Explicit accounting is the antidote to the ultra-long-horizon
collapse where an agent loses the thread and either thrashes or declares victory
early; honest per-milestone status is how a long run stays grounded over many
sessions.

**When to use:** Long-horizon, multi-step, or multi-session goals — the default outer
loop for any repository-OS-integrated architecture. Pair it with a budget so the loop
can reach `FailedBudget` rather than grinding indefinitely.

```text
while queue.has_incomplete() and budget.remaining():
    m = queue.next_incomplete(); execute(m); v = verify(m)   # runs the contract's verify-* gate
    runlog.append({milestone: m.id, verdict: v, criteria_met: v.count, evidence: v.bundle})
    if v.failed: invoke patch-and-repair(m)   # pattern 3
terminal = Succeeded if queue.all_complete() else (FailedBudget | FailedUnverifiable)
```

---

## 3. Patch-and-repair loop

**What:** When verification fails, run a bounded inner loop: classify the failure
mode, form one hypothesis, apply the **smallest** targeted patch, re-verify, and
compare the before/after score. It is capped (default **N=2**, set in `WORKFLOW.md`);
on cap-out it escalates rather than looping forever — replan, revert to best prior
state, pause for approval, or terminate. Crucially it never widens scope and never
edits the tests/criteria to make a red bar go green (doing so is verifier-gaming →
hard-terminate `FailedSafety`). This is the structured form of the self-anneal repair
loop and is the home of the **repair-productivity** metric: the fraction of repair
passes that *measurably* improve the score versus churn.

**When to use:** Inside any loop that has a deterministic gate that can fail — the
standard response to a red `verify-*` inside a milestone or slice. Owned by
`[[loop-repair]]`; produces the structured repair record.

```text
attempts = 0
while verify().failed and attempts < N:           # N from WORKFLOW.md, default 2
    rec = {failure_mode, hypothesis, repair_action, verification_before}
    apply_smallest_patch(rec); rec.verification_after = verify(); attempts += 1   # no scope-widening, no editing tests
return Succeeded if verify().passed else escalate(replan | revert | approval | terminate)
```

---

## 4. Improvement flywheel

**What:** A *between-runs* meta-loop (not an inner step). It mines `RUNLOG.md` and the
trace/receipt history, turns observed failures into new regression eval cases,
proposes harness/prompt changes, and compacts memory — splitting short-term
continue-this-run summaries from long-term improve-future-runs lessons. Each turn of
the flywheel raises the floor so the same failure cannot recur silently. This is the
mechanism behind regression resistance and the long-term half of the memory split.

**When to use:** After a run completes (any terminal state, but especially failures),
and on a cadence for any loop that will run repeatedly. Owned by `[[loop-flywheel]]`;
feeds new cases back into `[[loop-evals]]`. Run it as a deterministic fan-out when
trace volume is high — e.g. a Workflow `agent()` with an explicit
`model: "sonnet"` to cluster failures into candidate eval cases (reason → Sonnet),
with cheap extraction passes on `model: "haiku"` (read → Haiku).

```text
on run_complete(terminal_state):
    failures = mine(RUNLOG.md, traces, receipts); new_cases = synthesize_regressions(failures)
    EVALS/regressions += new_cases ; propose_harness_changes(failures)
    memory.long_term += distill_lessons(failures) ; memory.short_term = compact(run_summary)
```

---

## 5. Manager-orchestrator delegation

**What:** A manager loop holds the plan and the verification authority but does the
work by delegating bounded sub-tasks to worker agents, then integrating and verifying
their results — it routes, it does not itself do the heavy lifting. This is the
pattern behind the multi-agent / Workflow realization. Adopt it only when a single
agent is genuinely overloaded on tools, instructions, or context; the standing rule
(see `architecture-matrix.md`) is **maximize one agent first, add orchestration only
when the overload justifies it.** Every delegated agent names an explicit `model:`
per the model-routing rule, and the receipt each dispatch appends lands in
`.loop/receipts`.

**When to use:** Bounded, parallelizable fan-out within a session; or a long plan with
cleanly separable workstreams. Avoid for tightly-coupled work where hand-off overhead
and integration risk exceed the parallelism gain.

```text
plan = manager.decompose(goal)                       # manager keeps plan + verify authority
results = parallel([ agent(task=t, model="opus")     # write workers → Opus; read scouts → Haiku
                     for t in plan.independent_tasks ])
integrated = manager.integrate(results); v = verify(integrated)   # runs the contract's verify-* gate
```

---

## 6. Plan-then-execute

**What:** Separate the loop into two phases — first *plan* (precommit a concrete
execution graph of steps and tool calls), then *execute* the precommitted graph with
the planner's judgment locked. Because the action sequence is fixed before any
untrusted content is read, malicious page/tool output encountered during execution
cannot rewrite the agent's goals or insert new actions — it shrinks the
prompt-injection attack surface. This is the structural counterpart to the safety
model's "precommit the execution graph whenever the environment is adversarial /
semantically-typed tools exist."

**When to use:** **The default for untrusted or web environments** — any loop that
reads attacker-influenceable content (web pages, third-party tool output, untrusted
files) or operates over semantically-typed external tools. For fully-trusted,
local-only work the interleaved milestone loop (pattern 2) is usually enough and
plan-then-execute's rigidity is unnecessary overhead.

```text
graph = plan(goal, allowed_tools)                    # precommit steps + tool calls BEFORE reading untrusted input
freeze(graph)                                         # execution may not add/rewrite steps from page/tool content
for step in graph: out = execute(step); verify(step) # injected content can't redirect a frozen graph
```

---

## Plan-compliance caveat

Patterns 2 and 6 both lean on a precommitted plan, and pattern 5's manager holds one
— but **a plan only helps when it is a good plan.** Forcing strict compliance with a
flawed, over-phased, or mis-scoped plan actively *hurts*: the agent burns iterations
satisfying the wrong structure and can perform worse than with no fixed plan at all.
Two guards follow from this:

- **Critique the plan before committing to it.** PreFlect (pattern 1) and the
  `critique-plan` state in the loop machine exist precisely to catch a bad plan before
  it is frozen. Right-size phases — neither one giant step nor twenty micro-steps.
- **Allow principled replanning.** When the same failure mode repeats across repair
  attempts *without measurable improvement*, that is the signal the plan — not the
  patch — is wrong; the escalation ladder routes to **replan**, not another repair
  pass. Plan compliance is a tool for staying on a good course, not a cage that
  preserves a bad one.

This is why every plan-bearing pattern is gated by a critique step and a replan exit:
the loop commits to a plan, but never blindly.

---

**Sources:** synthesized from the loop-engineer design spec (`docs/superpowers/specs/2026-06-20-loop-engineer-design.md`, §4 pattern library, §6 terminal states, §7 safety) and its cited research — PreFlect pre-execution reflection (arXiv 2602.07187), SWE-Marathon ultra-long-horizon failure modes (arXiv 2606.07682), Web Agents Plan-Then-Execute (arXiv 2605.14290), Plan Compliance (arXiv 2604.12147), Code as Agent Harness (arXiv 2605.18747), plus OpenAI Agents/Codex guidance, Anthropic guidance on long-running agent harnesses (anthropic.com, 2025), and Google Conductor.
