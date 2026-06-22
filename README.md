# loop-engineer

**Design, launch, verify, repair, and improve agent loops.**

A Claude-Code-native skill suite that treats the *loop itself* as the design object — not the prompt, not the agent. Its job is to transform an underspecified objective into an executable operating contract (success criteria, task queue, tool boundaries, verification methods, stopping rules, approval gates, persistent artifacts) and then run it.

Prime directive: if it cannot define success, verification, or a terminal state, it flags the task as `FailedSpecGap` rather than pretending the next completion is "done."

---

## The 7 Skills

| Skill | One line |
|---|---|
| **loop-engineer** (router) | Broad intent → spoke map; the entry point for every loop question |
| **loop-architect** | Classifies the scenario and selects the architecture + physical realization |
| **loop-contract** | Scaffolds the repo-OS operating contract (SPEC/WORKFLOW/TASKS/RUNLOG/.loop/) |
| **loop-run** | Runs the state machine iteration by iteration, approval-gated, calling `/verify-slice` |
| **loop-repair** | Patch-and-repair loop with a structured repair record and a max-attempt cap |
| **loop-evals** | Designs the 7-layer eval suite and makes false-completion-rate + repair-productivity first-class |
| **loop-flywheel** | Turns traces and failures into new eval cases; manages memory compaction |

---

## Install

```bash
# 1. Register the local marketplace
claude plugin marketplace add /mnt/c/Dev/projects/loop-engineer

# 2. Install the plugin
claude plugin install loop-engineer@loop-engineer-local

# 3. Restart Claude Code — all 7 skills are now discoverable
```

---

## Decision Quickstart

**Starting a new loop?**
```
/loop-engineer → /loop-architect (classify) → /loop-contract (scaffold) → /loop-run (execute)
```

**Loop is failing?**
```
/loop-repair
```

**Need to measure or build eval criteria?**
```
/loop-evals
```

**Want to improve the loop over time?**
```
/loop-flywheel
```

**Not sure which spoke to reach for?**
```
/loop-engineer  ← always safe starting point; it routes you
```

### Terminal states

Every loop exits through one of exactly 7 named states — no silent "completed":

| State | When |
|---|---|
| `Succeeded` | Verification passes; all acceptance criteria met |
| `FailedUnverifiable` | Cannot confirm success or failure (verification gap) |
| `FailedBlocked` | Loop cannot proceed (tool, permission, or dependency block) |
| `FailedBudget` | Time or cost budget exhausted |
| `FailedSafety` | Safety or policy risk detected; hard-terminated |
| `FailedSpecGap` | Objective underspecified — success criteria could not be defined |
| `AbortedByHuman` | Explicitly stopped by the operator |

---

## Reuse — what this suite does NOT reimplement

| Capability | Existing asset used |
|---|---|
| Acceptance verification | `/verify-slice` + `/verify-milestone` (claude-code-orchestration) |
| State-machine / resume spine | Harmony `engine/cli.py` (init / next / complete; `state.json` serialize) |
| Grader / judge split | `launch-local-agent` (objective gate then rubric judge) |
| Dispatch + cost tracking | Agent model-routing HARD CONTRACT; `model_routing.py` / `workflow_routing.py`; `.gsd/audit/receipts/*.jsonl` |
| Planning surface | GSD (`.gsd/`); superpowers (writing-plans, executing-plans, verification-before-completion) |

`loop-engineer` calls these assets. It does not duplicate them.

---

## How it compares

The *loop-as-design-object* niche is essentially unoccupied — no existing Claude Code plugin sits in it. The adjacent work splits into three clusters, and `loop-engineer` is positioned deliberately **above** all three rather than against any one of them.

| Cluster | Examples | What they optimize | What `loop-engineer` adds |
|---|---|---|---|
| **Native execution primitives** | Claude Code `/goal` (runs across turns until a condition holds, grading after each turn), `/loop` | Driving one objective to a stopping condition | `/goal` is the *engine*; `loop-engineer` is the *design harness above it* — architect/operator roles, an on-disk operating contract, 7 typed terminal states, and measured false completion. It decides **what loop to run and how to know it worked**, then can hand execution to `/goal`. |
| **SDLC workflow harnesses** | [obra/superpowers](https://github.com/obra/superpowers) and other skills-based dev harnesses | Gating the *phases* of shipping code (plan → build → review) | These gate phases; `loop-engineer` treats the loop itself as the artifact — a terminal-state taxonomy, a structured repair record, first-class metrics. The two **compose**: a phase harness can run *inside* a `loop-engineer` contract. |
| **Swarm / orchestration engines** | ruflo, claude-code-flow, LangGraph, AutoGen | Coordinating many agents; the loop is execution mechanics | `loop-engineer` is engine-neutral design *over* such runtimes — it names the loop, its gates, and its stopping rule rather than providing the runtime. |

**What's genuinely differentiated (the suite owns these):**

- **A 7-state typed terminal taxonomy as a contract primitive** — every run ends in exactly one named state; no silent "completed." No operator harness in the survey prescribes one.
- **`repair-productivity` as a first-class metric** — the fraction of repair attempts that measurably move verification forward, so a *thrashing* loop is visible, not merely a slow one.
- **`false-completion-rate`, *measured* not self-reported** — via a held-out verifier split (`scripts/holdout_gate.py`) and an anti-cheat trajectory scan (`scripts/anticheat_scan.py`), a `Succeeded` claim must survive checks the loop never optimized against.
- **The loop *as the design object*** — not the prompt, not the agent.

**What's table-stakes (the suite has it, but does not oversell it):** an on-disk contract that survives compaction, a bounded repair cap, and deterministic-gate-before-rubric ordering are shared with mature harnesses (AGENTS.md, LangGraph, and the long-horizon agent-evaluation literature). `loop-engineer`'s claim is the *framing* and the *two metrics* on top — not these foundations.

This suite aims to be a concrete, gate-backed reference implementation of the emerging discipline of **loop engineering** (popularized by [Addy Osmani](https://addyosmani.com/blog/loop-engineering/), June 2026).

---

## Running the Quality Gates

### Frontmatter validation (structural hard gate)

Checks every `skills/*/SKILL.md`: frontmatter parses via `yaml.safe_load`, is a dict, `name:` matches the directory, `description:` is non-empty.

```bash
uv run --with pyyaml python3 scripts/validate_frontmatter.py
```

Exits `0` on clean, `1` with error lines on any failure. All 7 skills must pass before the plugin is considered release-ready.

### Self-eval (12 structural checks)

Verifies the suite against its own spec: skills present, frontmatter valid, reference files all cross-linked, `[[link]]` targets resolve, terminal-state tokens in `loop-run`, repair-record fields in `loop-repair`, 7 eval layers + 2 first-class metrics in `loop-evals`, all templates present, no secret patterns, model-routing compliance in dispatch examples, a real LICENSE file at repo root, and a README differentiation section.

```bash
uv run --with pyyaml python3 scripts/self_eval.py
```

Exits `0` with `structural_pass_rate: 1.0` when all 12 checks pass.

### Running both gates together

```bash
uv run --with pyyaml python3 scripts/validate_frontmatter.py && \
uv run --with pyyaml python3 scripts/self_eval.py
```

---

## Reference Depth

Deep content lives in `reference/` (loaded on demand by skills, not inline):

- `reference/architecture-matrix.md` — 5-candidate architecture comparison + scenario→realization decision table
- `reference/loop-patterns.md` — 6 loop patterns (PreFlect, milestone, patch-and-repair, flywheel, manager-orchestrator, plan-then-execute)
- `reference/repo-os-contract.md` — repo-OS layout, per-artifact schemas, state machine
- `reference/prompt-templates.md` — BOOTSTRAP / GOAL-LAUNCH / REPAIR-LOOP / SHORT prompt templates
- `reference/eval-suite.md` — 7-layer eval suite, first-class metrics, flywheel schedule
- `reference/safety-and-approvals.md` — escalation ladder, approval lifecycle, anti-cheat
- `reference/platform-map.md` — portable-core mapping across Claude / Codex / Hermes / Google

---

## License

MIT — Sollan Systems
