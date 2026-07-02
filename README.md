# Loop Engineer

*Your agent says it's done. Loop Engineer makes it prove it.*

Executable operating contracts for AI agent loops.

Loop Engineer turns long-running AI work from a fragile chat transcript into a
repo-native contract: success criteria, task queue, verification gates, repair
policy, terminal states, run history, and machine-readable state.

It ships as:

- a portable **Loop Contract Protocol**,
- a Python validator and inspector,
- and a Claude Code reference skill suite.

The prime directive:

> If a loop cannot define success, verification, or a terminal state, it stops
> as `FailedSpecGap` instead of pretending the next completion is done.

---

## Why this exists

Long-running agents fail in predictable ways:

- they forget what "done" meant after context compaction,
- they optimize to visible tests,
- they keep patching without measurable progress,
- they declare success without independent evidence,
- they have no typed way to say blocked, unsafe, unverifiable, or underspecified.

Loop Engineer makes those failure modes explicit contract states instead of
vibes — a concrete, gate-backed reference implementation of **loop engineering**:
contracts, typed termination, and health metrics for long-running agent loops.

---

## 30-second demo

```bash
git clone https://github.com/SollanSystems/loop-engineer.git
cd loop-engineer

python3 -m loop doctor examples/coverage-repair
python3 -m loop inspect examples/coverage-repair
```

`doctor` validates the contract objects (the real output also includes a
`paths` block listing every resolved contract file; omitted here for brevity):

```json
{
  "ok": true,
  "schemas_checked": [
    "loop-engineer/manifest@1",
    "loop-engineer/state@1",
    "loop-engineer/tasks@1",
    "loop-engineer/terminal@1"
  ],
  "issues": []
}
```

`inspect` is a static contract linter: it scores the loop contract's structure —
what proof machinery is present and what is missing — without running the loop:

```json
{
  "target": "examples/coverage-repair",
  "score": 76,
  "terminal_states_covered": 7,
  "present": [
    "defines verifiable success criteria",
    "independent verification",
    "approval gates on side-effects",
    "all 7 terminal states reachable"
  ],
  "gaps": [
    "no false-completion defense: no recorded holdout/anti-cheat invocation (a self-asserted false_completion flag or prose mention earns no credit)",
    "no plan-then-execute discipline for untrusted/web reads (prompt-injection surface)"
  ],
  "verdict": "ok"
}
```

Note: `false-completion defense` credit is graded on *invocation evidence*, not
self-assertion. This example declares `false_completion: false` and an anti-cheat
policy in prose but records no holdout/anti-cheat run, so it earns no credit and
the gap is flagged honestly — wire a `scripts/verify-*` gate that invokes a
holdout / anti-cheat check (or record a run in `RUNLOG.md` / `.loop/receipts`) to
earn it.

Both commands accept either a workspace root or its `.loop/` directory.

---

## Core guarantees

- **Typed termination:** every run exits through exactly one of 7 terminal states.
- **Evidence before completion:** a task is done only when it maps to a success criterion, a verifier passes, and evidence is recorded — not when the agent stops talking.
- **Externalized state:** loop status lives in files, not chat memory.
- **Bounded repair:** repair attempts are capped and measured.
- **False-completion defense:** held-out gates and anti-cheat scans designed to catch verifier gaming.

---

## Contract anatomy

A loop contract is a repo-native directory — a small on-disk "repo-OS" — that
externalizes intent, queue state, runtime state, verification, approvals, and
terminal outcome:

```text
<workspace>/
  AGENTS.md              # short entrypoint: where to find the contract
  SPEC.md                # what done means: success criteria + evidence rules
  WORKFLOW.md            # gates, budgets, repair cap, terminal states
  TASKS.json             # machine-readable task queue
  RUNLOG.md              # append-only iteration history
  EVALS/                 # datasets, rubrics, regressions, traces
  scripts/
    verify-fast          # cheap deterministic gate
    verify-full          # full deterministic gate
    verify-safety        # safety / approval / injection checks
    judge-rubric         # advisory rubric judge
  .loop/
    manifest.yaml        # contract metadata
    state.json           # live FSM cursor
    terminal_state.json  # final exit record, written once
    artifacts/           # evidence bundles and intermediate outputs
    approvals/           # approval requests and resolutions
    checkpoints/         # recoverable snapshots
    memory/              # run summaries and durable lessons
```

The contract split is deliberate:

- `SPEC.md` defines success.
- `WORKFLOW.md` defines how the loop is allowed to operate.
- `TASKS.json` defines the executable queue.
- `RUNLOG.md` records human-readable history.
- `.loop/state.json` is the machine source of truth while the loop runs.
- `.loop/terminal_state.json` records the final outcome (the resolver also
  accepts it at the workspace root).

A task is not done because an agent says it is done. A task is done only when it
maps to a success criterion, its verifier passes, and evidence is recorded.

See `reference/repo-os-contract.md` for the canonical artifact schemas.

---

## Honest termination model

Loop Engineer does not allow a vague "completed." Every run exits through
exactly one named state:

| State | When |
|---|---|
| `Succeeded` | Verification passes; all acceptance criteria are met. |
| `FailedUnverifiable` | Success or failure cannot be confirmed because verification is insufficient. |
| `FailedBlocked` | The loop cannot proceed because of a tool, permission, dependency, or external blocker. |
| `FailedBudget` | Time or cost budget is exhausted. |
| `FailedSafety` | Safety, policy, or approval risk is detected. |
| `FailedSpecGap` | The objective is underspecified; success criteria cannot be defined. |
| `AbortedByHuman` | The operator explicitly stops the run. |

---

## Install

### Portable validator / inspector

No Claude Code plugin is required to validate or inspect a loop contract. From
the cloned repo root:

```bash
python3 -m loop doctor /path/to/workspace
python3 -m loop inspect /path/to/workspace
```

To run it against a loop in any other directory, install the core once
(editable):

```bash
pip install -e .            # optional faster manifest parsing: pip install -e ".[yaml]"
python3 -m loop doctor /path/to/workspace
```

`python3 -m loop` resolves the bundled `loop/` package from the repo root;
`pip install -e .` puts it on your path so the CLI works from any directory. The
core is pure-stdlib — PyYAML is an optional extra, not a requirement.

The portable core lives in `loop/` and validates schema-bearing artifacts in
`schemas/`:

- `loop-engineer/manifest@1`
- `loop-engineer/state@1`
- `loop-engineer/tasks@1`
- `loop-engineer/terminal@1`

### Claude Code plugin

```bash
claude plugin marketplace add SollanSystems/loop-engineer
claude plugin install loop-engineer@loop-engineer
```

Restart Claude Code to load all 9 skills. (Local dev: clone the repo and run
`claude plugin marketplace add "$PWD"` instead.)

**Requirements:** Python 3.10+ for the portable validator/inspector; Claude Code
for the plugin — no other dependencies. Optional integrations (e.g.
`claude-code-orchestration` for `/verify-slice`) are layered on when present and
never required; every skill runs on the bundled core alone.

---

## Claude Code reference workflow

The Claude Code plugin is the reference UI over the portable loop contract.

```text
/loop-engineer
→ /loop-architect
→ /loop-contract
→ /loop-run
→ /loop-repair when a gate fails
→ /loop-flywheel after terminal state
```

### Design

| Skill | One line |
|---|---|
| **loop-engineer** | Router: broad intent → the right spoke map. |
| **loop-architect** | Classifies the scenario and selects the loop architecture + physical realization. |
| **loop-contract** | Scaffolds the repo-OS operating contract: `SPEC.md`, `WORKFLOW.md`, `TASKS.json`, `RUNLOG.md`, `.loop/`. |

### Run

| Skill | One line |
|---|---|
| **loop-run** | Runs the state machine iteration by iteration, approval-gated, running the contract's verify gate (optionally `/verify-slice`). |
| **loop-repair** | Runs a bounded patch-and-repair loop with a structured repair record. |
| **loop-runtime-monitor** | Watches an in-flight run from outside; flags stall, repair-churn, and budget overrun. |

### Improve

| Skill | One line |
|---|---|
| **loop-evals** | Designs the 7-layer eval suite and makes false-completion-rate + repair-productivity first-class. |
| **loop-flywheel** | Turns traces and failures into new eval cases; manages memory compaction. |
| **loop-inspector** | Audits an existing loop directory read-only; emits a scored gap report. |

Not sure which spoke to use? Start with `/loop-engineer`; it routes the task.

---

## What ships

- `loop/` — portable contract core and CLI: `doctor` (aliases: `validate`, `verify`) and `inspect`.
- `schemas/` — JSON schemas for contract artifacts.
- `skills/` — Claude Code skill suite.
- `reference/` — protocol, architecture, eval, safety, and platform reference docs.
- `scripts/` — validators, runtime monitor, anti-cheat scanner, benchmark harness, rollout ledger.
- `examples/` — sample loop contracts, including `examples/coverage-repair`.

Loop Engineer deliberately composes with existing agent runtimes and workflow
harnesses. It defines the loop contract above them; it does not try to replace
their execution engines.

---

## How it compares

- `/goal`, `/loop`, and agent runtimes execute loops.
- LangGraph, AutoGen, ruflo, claude-code-flow, and similar tools orchestrate agents.
- Superpowers-style harnesses gate software-development phases.

Loop Engineer defines the operating contract above those engines: what success
means, what evidence proves it, when repair is allowed, and how the loop must
terminate.

What this suite owns:

- **7 typed terminal states** — a contract primitive, so no run ends in a silent "completed."
- **`false-completion-rate`** — measurable with the bundled held-out gate and anti-cheat scan (computed from real runs; no baseline ships yet).
- **`repair-productivity`** — the fraction of repair attempts that measurably move verification forward.
- **Repo-native loop state** — survives compaction, crashes, and handoff.
- **Deterministic-gate-before-rubric ordering** — model judges are advisory, not the first line of proof.

What is table-stakes rather than oversold: on-disk contracts, bounded repair
caps, and deterministic verification gates are shared with mature harnesses.
Loop Engineer's claim is the loop-as-design-object framing plus the typed
termination and loop-health metrics on top.

---

## Verification

Release readiness is gate-backed, not asserted by README prose.

```bash
uv run --with pyyaml python3 -B scripts/validate_frontmatter.py
uv run --with pyyaml python3 -B scripts/self_eval.py
uv run --with pyyaml --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts
python3 -m py_compile loop/*.py scripts/*.py
claude plugin validate --strict .claude-plugin/plugin.json
```

The structural self-eval checks skill presence, frontmatter, cross-links,
terminal-state coverage, repair-record fields, eval metrics, templates, secret
patterns, dispatch examples, the bring-your-own-verifier default, the MIT
license, and README differentiation.

---

## Status

- Version: `0.3.4`
- Release tag: `loop-engineer--v0.3.4` (cut at publish)
- License: MIT
- Primary interface: Claude Code plugin
- Portable core: Python CLI + JSON schemas
- Current reference example: `examples/coverage-repair`

---

## Reference docs

Deep content lives in `reference/` and is loaded on demand by the skills:

- `reference/architecture-matrix.md` — architecture comparison + scenario→realization table.
- `reference/loop-patterns.md` — PreFlect, milestone, patch-and-repair, flywheel, manager-orchestrator, plan-then-execute.
- `reference/repo-os-contract.md` — repo-OS layout, artifact schemas, state machine.
- `reference/prompt-templates.md` — bootstrap, goal-launch, repair-loop, and short prompt templates.
- `reference/eval-suite.md` — 7-layer eval suite, first-class metrics, flywheel schedule.
- `reference/safety-and-approvals.md` — escalation ladder, approval lifecycle, anti-cheat.
- `reference/platform-map.md` — portable-core mapping across Claude, Codex, Hermes, and Google.

---

## Get started

```bash
git clone https://github.com/SollanSystems/loop-engineer.git
cd loop-engineer
python3 -m loop inspect examples/coverage-repair
```

Then scaffold a contract for your own loop with `/loop-contract`, or read
`reference/repo-os-contract.md` for the artifact schemas.

---

## License

MIT — Sollan Systems
