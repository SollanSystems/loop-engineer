# Loop Engineer

**Your AI agent says it's done. Loop Engineer makes it prove it.**

[![CI](https://github.com/SollanSystems/loop-engineer/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/SollanSystems/loop-engineer/actions/workflows/ci.yml)
[![Python 3.10–3.12](https://img.shields.io/badge/python-3.10%E2%80%933.12-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Release](https://img.shields.io/badge/release-0.8.0-blue)](https://github.com/SollanSystems/loop-engineer/tags)

Long-running agents commit **false completion**. After context compaction they
forget what "done" meant, optimize to the visible test, patch in circles, and
report success with no independent evidence — and no typed way to say *blocked*,
*unverifiable*, or *underspecified* instead.

Loop Engineer is a **proof-of-done** layer that sits above your agent runtime. It
ships, on disk and runnable today:

- a **contract validator** (`doctor`) and **inspector** (`inspect`) that grade a
  loop's proof machinery on *invocation evidence*, not on a self-asserted flag;
- a **held-out gate** and an **anti-cheat scan** built to catch a loop gaming its
  own verifier;
- a runnable example whose `false_completion: false` is backed by a committed,
  real gate verdict — `.loop/artifacts/holdout-verdict.json`, not a hand-set flag.

![The inspector scores a self-asserted DIY loop 0/weak, then the gate-backed example 90/strong — both runs live](docs/demo.gif)

<sub>Filmed on the real tools ([`docs/demo.cast`](docs/demo.cast)); reproduce both
verdicts yourself: `python3 -m loop inspect examples/naive-loop` then
`examples/coverage-repair`.</sub>

```bash
# Score a loop's proof-of-done in 5 seconds — no install, no agent, no API key:
git clone https://github.com/SollanSystems/loop-engineer.git
cd loop-engineer
python3 -m loop inspect examples/coverage-repair
```

## Where it sits

    ┌──────────────────────────────────────────────────────────────┐
    │  Tier 3 · REFERENCE RUNNER                                    │
    │    9 Claude Code skills: design → contract → run → repair →   │
    │    flywheel                                                   │
    ├──────────────────────────────────────────────────────────────┤
    │  Tier 2 · PROOF TOOLCHAIN                                     │
    │    doctor · inspect · holdout_gate · anticheat_scan ·         │
    │    runtime_monitor                                            │
    ├──────────────────────────────────────────────────────────────┤
    │  Tier 1 · PORTABLE CONTRACT                                   │
    │    .loop/ state + SPEC/WORKFLOW/TASKS + schemas/ + templates/ │
    └──────────────────────────────────────────────────────────────┘

Tiers 1–2 are runtime-neutral: pure-stdlib Python over files on disk, readable by
any tool. Tier 3 (the 9 Claude Code skills) is the *reference* runner, not a
requirement — bring your own runtime (LangGraph, ruflo, OpenHands, native Claude
Code) and keep the contract and proof layer above it.

## How it compares

Different tools, different objects. The rows below are checkable facts, not
opinions.

| Project | ★ | What it is | Enforced proof-of-done? |
|---|---:|---|---|
| **Loop Engineer** (this repo) | — | operating contract + proof toolchain | **Yes** — 7 typed terminal states, held-out gate + anti-cheat scan, graded on invocation evidence |
| [cobusgreyling/loop-engineering](https://github.com/cobusgreyling/loop-engineering) | 4.9K | prompt-native loop-*design guidance*; owns the term "loop engineering" | Different object — design guidance, not a runtime or gate |
| [obra/superpowers](https://github.com/obra/superpowers) | 244K | phase-gating dev methodology (brainstorm → TDD → review) | No — gates dev phases, not a typed completion contract |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | 36K | stateful agent-graph runtime + checkpointing | No — completion is whatever the terminal node returns |

<sub>★ counts fetched via `gh api` on 2026-07-02; they drift over time.</sub>

What this suite owns:

- **7 typed terminal states** — a contract primitive, so no run ends in a silent "completed."
- **`false-completion-rate`** — measurable with the bundled held-out gate and anti-cheat scan; **0.0** on the shipped gate-backed example (see [Measured baseline](#measured-baseline)).
- **`repair-productivity`** — the fraction of repair attempts that measurably move verification forward; **1.0** on that example.
- **Repo-native loop state** — survives compaction, crashes, and handoff.
- **Deterministic-gate-before-rubric ordering** — model judges are advisory, not the first line of proof.

What is table-stakes rather than oversold: on-disk contracts, bounded repair
caps, and deterministic verification gates are shared with mature harnesses. Loop
Engineer's claim is the proof-of-done framing plus the typed termination and
loop-health metrics on top. It composes with those tools; it does not replace
their execution engines.

### Measured baseline

The two metrics are **derived by a tool, not quoted from prose.** The checked-in
scorecard [`docs/metrics-baseline.json`](docs/metrics-baseline.json) is computed
by `python3 -m loop metrics` over the gate-backed `examples/coverage-repair` run —
its `false_completion:false` is backed by a real `holdout_gate.py` verdict, and
its `productive` flag is recomputed from the repair record's own score delta, not
trusted:

| Metric | Baseline | Source |
|---|---:|---|
| `false-completion-rate` | **0.0** | RUNLOG success-claims × verify bundles, cross-checked against the held-out gate flag (both agree) |
| `repair-productivity` | **1.0** | one repair pass, `verification_after.score` 0.83 > `before` 0.74 (recomputed, agreed) |

The number ships with a `provenance` block naming every input file (including the
held-out verdict's sha256), so a skeptic can re-derive it. That committed verdict
is *evidence, not proof*: it is validated structurally, but a fully-fabricated,
internally-consistent artifact defeats offline shape-checking by construction —
tamper detection of the artifact itself belongs to the anti-cheat layer; the tool
does not claim the verdict is tamper-proof. Reproduce (and refuse to publish over a
non-gate-backed, inconsistent, vacuous, or unanchored run):

```bash
python3 -m loop metrics examples/coverage-repair            # print the scorecard
python3 -m loop metrics --baseline examples/coverage-repair # rewrite docs/metrics-baseline.json
```

---

## Proof-of-done, not self-assertion

The `inspect` and `doctor` commands accept either a workspace root or its `.loop/`
directory, and need no agent runtime to run.

`doctor` validates the contract objects (the real output also includes a
`paths` block listing every resolved contract file; omitted here for brevity):

```json
{
  "ok": true,
  "validation_mode": "structural-fallback",
  "schemas_checked": [
    "loop-engineer/manifest@1",
    "loop-engineer/state@1",
    "loop-engineer/tasks@1",
    "loop-engineer/terminal@1"
  ],
  "issues": []
}
```

`validation_mode` reports what actually ran: the pure-stdlib structural checks by
default, or real JSON-Schema validation against `schemas/*.json` when the
optional `jsonschema` dependency is present (`pip install -e ".[schemas]"`), in
which case it reads `"jsonschema"`.

`inspect` is a static contract linter: it scores the loop contract's structure —
what proof machinery is present and what is missing — without running the loop:

```json
{
  "target": "examples/coverage-repair",
  "score": 90,
  "terminal_states_covered": 7,
  "present": [
    "defines verifiable success criteria",
    "independent verification",
    "approval gates on side-effects",
    "false-completion defense (invoked)",
    "all 7 terminal states reachable"
  ],
  "gaps": [
    "no plan-then-execute discipline for untrusted/web reads (prompt-injection surface)"
  ],
  "verdict": "strong"
}
```

Note: `false-completion defense` credit is graded on *invocation evidence*, not
self-assertion. This example earns it the honest way — `scripts/verify-full`
invokes the real held-out gate (`scripts/holdout_gate.py`) over the toy target in
`examples/coverage-repair/target/`, and `run-example` records a Succeeded verdict
to `.loop/artifacts/holdout-verdict.json` — so a self-asserted flag is never what
scores. The one remaining gap is honest too: this low-risk, workspace-write loop
declares `plan_then_execute: false`, so it earns no prompt-injection-discipline
credit (correct for a loop that reads no untrusted input).

The prime directive:

> If a loop cannot define success, verification, or a terminal state, it stops
> as `FailedSpecGap` instead of pretending the next completion is done.

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
    terminal_state.json  # final exit record; written once — emit refuses overwrite without force=True
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

### A versioned, conformance-checkable standard

The on-disk contract is a **documented, versioned, tool-agnostic standard** — conformance is
defined by the published `schemas/*.schema.json` (`$id` `loop-engineer/<artifact>@<major>`,
additive within a major), and a runnable **conformance checklist** (A1–E1) lets any harness claim
*"emits a Loop-Engineer-conformant contract v1."* See
[`reference/repo-os-contract.md`](reference/repo-os-contract.md) §0 / §11 / §14.

---

## Install

### Portable validator / inspector

No Claude Code plugin is required to validate or inspect a loop contract:

```bash
uvx loop-engineer inspect .        # zero-install score of any repo's loop contract
pip install loop-engineer          # or install the CLI: `loop doctor`, `loop inspect`, ...
```

From a clone, `python3 -m loop <cmd>` and `pip install -e .` keep working; the
wheel is self-contained (schemas, templates, and the inspect/metrics tooling
ship inside it). The core is pure-stdlib — PyYAML/jsonschema are optional extras.

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

## Adopt in your stack

Three thin, enforcing on-ramps — each one makes a false "done" fail somewhere
that already exists in your workflow. Start where your loop lives:

**Claude Code** — the plugin ships a Stop-hook firewall: if the session's repo
holds a `.loop/` contract that claims `Succeeded` while `loop doctor` says
otherwise, the stop is blocked with the exact doctor issues. No-op without
`.loop/`, fail-open on error, zero config beyond installing the plugin.

**Any Python runtime** — `loop.emit` is a pure-stdlib writer for foreign
orchestrators (LangGraph, or anything that can call four functions):
`open_contract`, `append_iteration`, `append_receipt`, `terminate`. The writer
refuses an evidence-free `Succeeded` at write time. Recipe:
[docs/integrations/langgraph.md](docs/integrations/langgraph.md).

**CI** — one workflow step validates the contract and publishes a scorecard:

```yaml
- uses: SollanSystems/loop-engineer@v0.8.0
  with:
    path: "."
```

`doctor` failure fails the job (and the action installs the `[schemas]` extra so
`doctor` runs real JSON-Schema validation, not the structural fallback). The
inspect **score is an advisory heuristic** — useful as a trend, but a determined
author can game it, so it is warn-only unless you set `fail-under-score`;
**`loop doctor` is the hard gate.** The optional PR comment is sticky — it edits
one scorecard comment in place across re-runs. Pre-commit users: hook id
`loop-doctor` (its `additional_dependencies` pin the schema extras too). This repo
dogfoods the same action in CI against its flagship example contract
([`examples/coverage-repair`](examples/coverage-repair)) — the gate gates its maker.

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

- Version: `0.8.0`
- Release tag: `v0.8.0` (PyPI publish trigger; plugin tags through 0.6.0 used `loop-engineer--v<version>`)
- License: MIT
- Primary interface: Claude Code plugin
- Portable core: Python CLI + JSON schemas
- Current reference examples: `examples/coverage-repair`, `examples/flaky-test-triage`

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

Run the zero-install `inspect` command at the top of this README, then scaffold a
contract for your own loop with `/loop-contract` — or read
`reference/repo-os-contract.md` for the artifact schemas.

---

## License

MIT — Sollan Systems
