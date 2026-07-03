# ST3 — Integration Recipes & Optional Installable Adapters

> **Spec type:** design (plan/docs deliverable — no implementation in this doc).
> **Backlog item:** ST3 (`review/IMPROVEMENT-BACKLOG.md` rank 16, Impact H / Effort H, Strategic).
> **Source of truth:** `review/POSITIONING.md` §5 (three-tier stack) · `review/COMPETITIVE-ANALYSIS.md` (positioning map + whitespace) · `review/IMPROVEMENT-BACKLOG.md` ST3.
> **Date:** 2026-06-30 · **Status:** proposed, unimplemented.

---

## 1. Problem & wedge

The competitive scan is unambiguous (`COMPETITIVE-ANALYSIS.md`): the entire
agent-tooling market — **LangGraph (36k★), ruflo (62k★), OpenHands (79k★),
Temporal (21k★)**, plus AutoGen/CrewAI/native `/loop` — lives in the bottom two
tiers of the stack. They **execute** and **orchestrate** loops extremely well,
then hand *"is it actually finished?"* back to the agent's own say-so. None ships
a typed terminal-state taxonomy, an evidence-before-completion gate, or first-class
`false-completion-rate` / `repair-productivity`.

Loop Engineer owns the missing top tier (`POSITIONING.md` §5):

```
┌──────────────────────────────────────────────────────────────┐
│  CONTRACT    ← Loop Engineer: what "done" means, what proves  │
│               it, when repair is allowed, how it must end.    │
├──────────────────────────────────────────────────────────────┤
│  ORCHESTRATE ← LangGraph · AutoGen · CrewAI · ruflo           │
├──────────────────────────────────────────────────────────────┤
│  EXECUTE     ← OpenHands · Temporal · /loop · /goal           │
└──────────────────────────────────────────────────────────────┘
```

**The wedge for ST3: "composes, it doesn't compete."** The layer claim only
converts to adoption if a stranger already on LangGraph/ruflo/OpenHands/Temporal
can *bolt Loop Engineer on top in one file* without swapping their runtime. ST3
delivers exactly that: concrete recipes that wrap an existing engine's terminal
node in Loop Engineer's typed-termination + evidence gate, turning each 36k–79k★
competitor into **a complement that needs you**, not a rival that buries you.

**Non-goal (positioning discipline, `POSITIONING.md` §5, §7):** never re-implement
or replace an execution engine. Every recipe keeps the host engine as the executor
and adds only the contract/proof layer above it.

---

## 2. Objective & scope

**Objective.** Ship integration recipes for **≥2** of the four target engines,
each showing the *same two-part mapping*:

1. **engine terminal → one of Loop Engineer's 7 typed terminal states**, and
2. **engine run artifacts → a Loop Engineer evidence record** (`terminal_state.json`
   conforming to `schemas/terminal.schema.json`, plus `.loop/receipts/*.jsonl`
   per `schemas/receipt.schema.json`).

**In scope.**
- Four recipes (this spec designs all four; the acceptance bar requires ≥2 to ship
  runnable): LangGraph, Temporal, OpenHands, ruflo.
- A shared **adapter contract** (§4) so every recipe maps through one code path
  (no per-engine drift in how a terminal state or an evidence record is produced).
- An optional, **BYO-friendly** installable helper module (§6) — pure-stdlib,
  additive, zero framework lock-in — that each recipe imports; recipes must also
  degrade to a copy-paste-able snippet with no install.
- Docs home: `reference/integrations/<engine>.md` (per-recipe) + this spec.

**Out of scope (defer / other backlog items).**
- Publishing an FCR/RP *baseline* (ST1) — recipes emit the evidence trail ST1
  later aggregates, but ST3 ships **no headline numbers**.
- The versioned portable-contract spec + schema conformance CLI (ST2) — ST3
  *consumes* the existing `schemas/*.json` as-is and flags any gap it hits back
  to ST2.
- Any change to `loop/`, `scripts/`, `schemas/`, `templates/`, `evals/` — recipes
  are additive `reference/` docs + one optional helper module; they must not
  modify the core gate logic.

---

## 3. The mapping (the load-bearing design decision)

Every recipe is a projection from an engine's native "the run ended" signal onto
the two Loop Engineer artifacts. The taxonomy is fixed (`loop/contract.py`
`TERMINAL_STATES`); the recipe's whole job is the projection function.

### 3.1 Engine terminal → 1 of 7 typed terminal states

Canonical target set (verbatim from `loop/contract.py:9-17`):
`Succeeded`, `FailedUnverifiable`, `FailedBlocked`, `FailedBudget`,
`FailedSafety`, `FailedSpecGap`, `AbortedByHuman`.

The projection is **never** "the engine said done → `Succeeded`." A raw engine
terminal maps to `Succeeded` **only** through Loop Engineer's own gate
(`scripts/holdout_gate.py` `decide()` + `scripts/anticheat_scan.py`). This is the
entire wedge: the engine's say-so is demoted to an *input*, not the verdict.

| Engine terminal signal | Gate result | → Typed terminal state |
|---|---|---|
| run reached its end node / workflow returned | holdout green + anticheat clean | **`Succeeded`** |
| run reached its end node | visible green, **holdout red** | **`FailedUnverifiable`** (the false-completion event) |
| run reached its end node | holdout not defined / not runnable | **`FailedUnverifiable`** (cannot certify) |
| anticheat: gate-tampering (CRITICAL) | — | **`FailedSafety`** |
| anticheat: hidden-answer / skip-injection (HIGH) | — | **`FailedUnverifiable`** |
| engine raised an unrecoverable external error / missing credential / locked resource | — | **`FailedBlocked`** |
| engine hit step/token/wall-clock/cost budget cap | — | **`FailedBudget`** |
| run finished but a SPEC criterion has no mapped check at all | — | **`FailedSpecGap`** |
| operator interrupt / human abort signal | — | **`AbortedByHuman`** |

`holdout_gate.decide()` already returns exactly the three verdicts the top rows
need (`Succeeded` / `FailedUnverifiable` / `NotReady`) plus a `false_completion`
boolean. The adapter's projection table is the *only* new logic; the gate is
reused verbatim.

### 3.2 Engine artifacts → evidence record

The recipe writes a `terminal_state.json` matching `schemas/terminal.schema.json`
(`terminal@1`), required keys: `schema, state, iteration_id, criteria_met,
evidence, false_completion, reason, lessons_ref`. Mapping:

- `state` ← §3.1 projection.
- `criteria_met` ← `{criterion_id: bool}` from mapping each SPEC criterion to a
  gate check id (a criterion with no check → `FailedSpecGap`, per §3.1).
- `evidence` ← list of on-disk paths the engine produced that the gate consumed
  (engine run log, test output, holdout gate JSON). Recipes **copy or reference**
  the engine's native artifacts into `.loop/artifacts/` rather than fabricating.
- `false_completion` ← `holdout_gate` result's `false_completion` (never a hand-set
  literal — this is the exact hole HI4/QW2 flag; recipes must source it from the
  gate call).
- Plus one `.loop/receipts/*.jsonl` line per dispatch (`receipt@1`: `role`, `model`,
  `outcome`, optional `tokens`/`cost_usd`) so ST1/`loop-flywheel` can later compute
  cost-per-success from the engine's own model calls.

> **Cross-check invariant (QW2 / gate-integrity HIGH).** A recipe MUST NOT emit
> `state: "Succeeded"` with `false_completion: true` or empty `criteria_met`. The
> adapter derives `Succeeded` only from a green gate, so this is structurally
> unreachable — but each recipe's test pins it.

---

## 4. Adapter contract (one code path for all recipes)

To prevent per-engine drift, every recipe funnels through one small, engine-neutral
projection surface. Conceptually (Python-shaped, pure-stdlib, no engine import):

```
# reference/integrations/_adapter.py  (optional installable helper — §6)

@dataclass(frozen=True)
class EngineOutcome:
    """Engine-agnostic description of how a host run ended."""
    reached_end: bool                 # engine's own terminal signal
    external_error: str | None        # unrecoverable env/credential/resource block
    budget_exhausted: bool            # step/token/wall-clock/cost cap hit
    human_abort: bool                 # operator interrupt
    artifacts: list[str]              # on-disk paths the run produced

def to_terminal_state(
    outcome: EngineOutcome,
    gate_verdict: dict,               # from holdout_gate.decide(...)
    anticheat: dict,                  # from anticheat_scan (findings, clean)
    criteria_met: dict[str, bool],    # SPEC-criterion -> mapped-check pass/fail
) -> dict:                            # a terminal_state.json body (terminal@1)
    ...
```

`to_terminal_state` implements §3.1 precedence **safety → human → blocked →
budget → spec-gap → gate verdict** and assembles the §3.2 evidence record. It
imports nothing from any engine; the recipes adapt each engine's native result
object into an `EngineOutcome` and pass the gate outputs through. This keeps the
"how a terminal state is decided" logic in exactly one tested place — recipes only
translate *shapes*, never *policy*.

Precedence rationale: `FailedSafety` (tampering) and `AbortedByHuman` must win over
any green gate so a gamed or human-killed run can never launder itself into
`Succeeded`.

---

## 5. Recipes

Each recipe ships as `reference/integrations/<engine>.md` with: (a) a 3-line
"what this composes" header naming the tier, (b) the mapping table specialized to
the engine's terminal signal, (c) a runnable snippet outline, (d) the resulting
`terminal_state.json` + one receipt line, (e) a copy-paste test asserting the
false-completion invariant.

### 5.1 LangGraph terminal-node → typed terminal state  *(flagship, ship first)*

**Composes:** the ORCHESTRATE tier. LangGraph's graph runs to a terminal node and
returns whatever the node returns; Loop Engineer replaces "return the state" with
"gate the state, then emit a typed terminal."

Snippet outline:

```python
from langgraph.graph import StateGraph, END
from loop_engineer.integrations import EngineOutcome, to_terminal_state
from scripts.holdout_gate import decide
from scripts import anticheat_scan  # trajectory + diff sweep

def certify_node(state: dict) -> dict:
    # 1. run the SAME visible/holdout split the loop optimized against
    gate = decide(visible=state["visible_results"], holdout=state["holdout_results"])
    ac   = anticheat_scan.scan(diff=state["diff"], trajectory=state["tool_trail"])
    # 2. project the graph's terminal into a typed state + evidence
    terminal = to_terminal_state(
        outcome=EngineOutcome(reached_end=True, external_error=None,
                              budget_exhausted=state["step"] >= state["max_steps"],
                              human_abort=False, artifacts=state["artifacts"]),
        gate_verdict=gate, anticheat=ac, criteria_met=state["criteria_met"],
    )
    write_terminal_state(terminal)          # -> terminal_state.json (terminal@1)
    append_receipt(role="orchestrate", model=state["model"], outcome="ok")
    return {**state, "terminal": terminal}

graph.add_node("certify", certify_node)
graph.add_edge("certify", END)             # certify IS the only path to END
```

Mapping specialization: LangGraph's `END` is reachable **only** through
`certify_node`; the graph can no longer terminate on the agent's own return. A
`GraphRecursionError` (LangGraph's own step cap) maps to `FailedBudget`; a caught
tool/credential exception maps to `FailedBlocked`.

### 5.2 Temporal workflow → repo-OS contract  *(flagship, ship first)*

**Composes:** the EXECUTE tier (durable execution). Temporal guarantees the run
*survives crashes*; it says nothing about whether the work is *correct*
(`COMPETITIVE-ANALYSIS.md`: low on the verification axis by design). Loop Engineer
adds the correctness/termination contract on top.

Snippet outline: a final **`certify` activity** at the end of the workflow (activities
can do I/O; the workflow stays deterministic):

```python
@activity.defn
async def certify_activity(run: RunArtifacts) -> dict:
    gate = decide(visible=run.visible, holdout=run.holdout)
    ac   = anticheat_scan.scan(diff=run.diff, trajectory=run.trail)
    terminal = to_terminal_state(
        outcome=EngineOutcome(reached_end=True, external_error=run.error,
                              budget_exhausted=run.attempts >= run.cap,
                              human_abort=run.cancelled, artifacts=run.artifacts),
        gate_verdict=gate, anticheat=ac, criteria_met=run.criteria_met,
    )
    write_terminal_state(terminal); append_receipt(...)
    return terminal

@workflow.defn
class GoalWorkflow:
    @workflow.run
    async def run(self, spec) -> dict:
        artifacts = await workflow.execute_activity(do_work, spec, ...)
        return await workflow.execute_activity(certify_activity, artifacts, ...)
```

Mapping specialization: a Temporal `CancelledError` (workflow cancellation) →
`AbortedByHuman`; an activity that exhausts its `RetryPolicy` on an external
dependency → `FailedBlocked`; the workflow's own timeout → `FailedBudget`. The
`.loop/state.json` (`state@1`) is written from the workflow's durable state so a
resumed workflow resumes the *same* contract — this is the "repo-OS contract"
mapping: Temporal owns durability, Loop Engineer owns the on-disk success/evidence
truth.

### 5.3 OpenHands run → FCR gate  *(alternate)*

**Composes:** the EXECUTE tier (autonomous coding runtime). OpenHands writes, runs,
and tests code in a sandbox — incidental verification, but "done" is still the
agent stopping. Loop Engineer wraps the run's exit in the false-completion gate.

Snippet outline: a post-run hook that reads the OpenHands trajectory (event
stream / final state) as the `anticheat` trajectory input, runs the holdout split
against the sandbox, and projects:

```python
result = openhands.run(task=spec)          # sandboxed agent run
gate = decide(visible=run_visible(result), holdout=run_holdout(result))
ac   = anticheat_scan.scan(diff=result.git_diff, trajectory=result.event_paths)
terminal = to_terminal_state(
    outcome=EngineOutcome(reached_end=result.finished, external_error=result.fatal,
                          budget_exhausted=result.iterations >= result.max_iterations,
                          human_abort=False, artifacts=[result.log_path]),
    gate_verdict=gate, anticheat=ac, criteria_met=map_criteria(result),
)
```

Mapping specialization: OpenHands' `AgentStuckError` / max-iteration stop →
`FailedBudget`; a sandbox that touched a holdout/answer-key path (HIGH anticheat
finding) → `FailedUnverifiable` — the exact "the runtime ran tests but the agent
peeked" case OpenHands can't itself catch.

### 5.4 ruflo swarm → acceptance gate  *(alternate)*

**Composes:** the ORCHESTRATE tier (multi-agent swarm). A swarm's terminal is
"the coordinator decided the objective is met" — pure self-report across N agents.
Loop Engineer adds a single acceptance gate the swarm must pass *as a whole*.

Snippet outline: register the gate as the swarm's terminal hook (ruflo exposes
hooks / an MCP coordination server), so no individual agent can declare the swarm
done — the acceptance gate does:

```python
swarm_result = ruflo.orchestrate(objective=spec, agents=[...])
gate = decide(visible=swarm_result.visible, holdout=swarm_result.holdout)
ac   = anticheat_scan.scan(diff=swarm_result.merged_diff,
                           trajectory=swarm_result.agent_trails)
terminal = to_terminal_state(
    outcome=EngineOutcome(reached_end=swarm_result.converged, external_error=None,
                          budget_exhausted=swarm_result.rounds >= swarm_result.max_rounds,
                          human_abort=False, artifacts=swarm_result.artifacts),
    gate_verdict=gate, anticheat=ac, criteria_met=swarm_result.criteria_met,
)
```

Mapping specialization: swarm non-convergence within max rounds → `FailedBudget`;
a criterion no agent was assigned → `FailedSpecGap` (the swarm literally never
worked on it — a failure mode a self-reporting coordinator hides).

---

## 6. Optional installable adapter (BYO, additive)

Per `POSITIONING.md` §3 (P2 persona: "Bring your own runtime. Loop Engineer is the
contract above it"), each recipe should work in two modes:

1. **Zero-install copy-paste** — the snippet inlines the ~15-line `to_terminal_state`
   projection; a reader on any stack pastes it. This is the default and the wedge
   demo (no framework lock-in, pure-stdlib).
2. **Installable helper** — `loop_engineer.integrations` (shipped by the existing
   editable `pyproject.toml`, no new dependency) exporting `EngineOutcome` +
   `to_terminal_state` + thin `write_terminal_state` / `append_receipt` writers.
   Optional convenience only; imports nothing from any engine, so installing it
   never pulls LangGraph/Temporal/etc.

**Discipline:** the helper is a *projection + writer*, never an executor. It must
not import, wrap, or vendor any engine — that would forfeit the "composes, doesn't
compete" claim. Engine packages stay the host app's own dependency.

---

## 7. Acceptance criteria

Mirrors `IMPROVEMENT-BACKLOG.md` ST3 ("recipes for ≥2 of {…}, each with a runnable
snippet and the resulting terminal-state/evidence mapping"):

1. `reference/integrations/` carries recipes for **≥2** target engines (LangGraph
   and Temporal are the flagship pair; OpenHands/ruflo may ship in the same PR or
   follow).
2. Each shipped recipe has: the specialized mapping table (engine terminal → 1 of
   7 states), a runnable snippet outline, and a concrete resulting
   `terminal_state.json` (valid against `terminal@1`) + one `receipt@1` line.
3. Each recipe includes a test (or worked example) asserting the **false-completion
   invariant**: a run whose visible checks pass but holdout fails maps to
   `FailedUnverifiable` with `false_completion: true`, and **never** to
   `Succeeded` — pinning QW2/HI4 at the integration boundary.
4. `Succeeded` is emitted only when `holdout_gate.decide()` returns `Succeeded`
   **and** anticheat is clean; `criteria_met` has ≥1 true entry. (Structurally
   guaranteed by §4; test-pinned.)
5. The optional helper imports zero engine packages; each recipe also works as a
   pure copy-paste snippet with no install. `self_eval.py` stays green; no file
   under `loop/ scripts/ schemas/ templates/ evals/` is modified.
6. Every recipe's prose frames the engine as a **complement** and never claims to
   replace it (`POSITIONING.md` §5/§7 discipline).

---

## 8. Risks & open questions

- **Engine API drift.** LangGraph/Temporal/OpenHands/ruflo APIs move fast; snippets
  are *outlines*, and per-engine version pins + a "verified against vX" note belong
  in each recipe (library-research discipline: confirm current API via Context7 /
  primary docs before finalizing a snippet). This spec does not pin versions.
- **Trajectory availability.** The anticheat sweep needs the engine's tool/path
  trail; engines expose it differently (LangGraph state, Temporal history,
  OpenHands event stream, ruflo agent trails). Where a trail is unavailable, the
  recipe must map to `FailedUnverifiable` (cannot certify), not silently skip the
  anticheat step — the same fail-closed posture as `holdout_gate` on an empty
  holdout set.
- **Depends-on / feeds-into.** ST3 is standalone-shippable but is strongest after
  QW2 + HI4 (so the gate the recipes call is itself honest) and feeds ST1 (the
  receipts/evidence trail it emits is what a published FCR baseline aggregates).
  It also surfaces the ST2 need: recipes want a *versioned* on-disk contract to
  target; any schema gap they hit is an ST2 input.
- **Which alternate ships.** OpenHands (79k★, largest EXECUTE community) vs ruflo
  (62k★, largest CC-native swarm) as the third recipe — decide by whichever
  community the launch (ST5) targets first.

---

## 9. Traceability

| This spec | Grounded in |
|---|---|
| Three-tier stack framing | `POSITIONING.md` §5 |
| "composes, doesn't compete" wedge | `POSITIONING.md` §1, §5, §7 · `COMPETITIVE-ANALYSIS.md` whitespace §4 |
| Target engines (LangGraph/Temporal/OpenHands/ruflo) as layers-below | `COMPETITIVE-ANALYSIS.md` ADJACENT table + positioning map Q3 |
| 7 typed terminal states | `loop/contract.py:9-17` · `schemas/terminal.schema.json` |
| holdout/false-completion gate reuse | `scripts/holdout_gate.py` `decide()` |
| anticheat → FailedSafety/FailedUnverifiable | `scripts/anticheat_scan.py` docstring |
| evidence + receipt record | `schemas/terminal.schema.json` · `schemas/receipt.schema.json` |
| false-completion invariant at the boundary | `IMPROVEMENT-BACKLOG.md` QW2, HI4 |
| Acceptance bar (≥2 recipes, runnable snippet + mapping) | `IMPROVEMENT-BACKLOG.md` ST3 |
