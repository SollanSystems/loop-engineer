# loop-engineer — Design Spec

- **Date:** 2026-06-20
- **Status:** Approved (brainstorming) — pending spec review
- **Author:** Sollan Systems
- **Repo:** `github.com/SollanSystems/loop-engineer` (private)
- **Source research:** "Designing a Loop Engineer Skill for Frontier Agent Workflows" (2026), synthesized from OpenAI Agents/Codex guidance, Anthropic "Effective harnesses for long-running agents," Google Conductor, and arXiv: PreFlect (2602.07187), SWE-Marathon (2606.07682), Web Agents Plan-Then-Execute (2605.14290), Plan Compliance (2604.12147), Code as Agent Harness (2605.18747).

---

## 1. Concept & operating contract

A **loop-engineer** is a reusable agent capability whose job is to **design, launch, verify, repair, and improve other agent loops** — it does **not** primarily solve the end task. Its first responsibility is to transform an underspecified objective into an **executable operating contract**: success criteria, task queue, tool boundaries, evaluation methods, stopping rules, approval gates, and persistent artifacts that let the loop resume across turns or sessions.

**Prime directive.** If it cannot define success, verification, or a terminal state, it treats the task as **underspecified** (`FailedSpecGap`) rather than pretending the next completion is "done." This directly defends against the #1 documented long-horizon failure mode — false completion / weak self-verification / verifier gaming (SWE-Marathon reports sub-30% success on ultra-long-horizon work).

**Interface contract (every loop the skill designs declares these explicitly, not in prose):**

| Element | Fields |
|---|---|
| Inputs | `goal`, `success_criteria[]`, `constraints[]`, `workspace_path`, `allowed_tools[]`, `risk_profile{low,med,high}`, `time_budget`, `cost_budget`, `approval_policy{never,on_side_effects,strict}` |
| Outputs | `plan`, `task_queue`, `current_state`, `verification_bundle`, `repair_actions`, `terminal_state`, `lessons_learned` |
| State | `iteration_id`, `plan_version`, `active_task`, `best_score`, `failure_mode`, `pending_approval`, `budget_remaining`, `checkpoint_path` |
| Memory | short-term compaction summary (continue-this-run) **vs** long-term lessons (improve-future-runs) |
| Permissions | read-only / workspace-write / network / external-side-effects / production-mutation |
| Approval gates | destructive commands, secret access, production changes, money movement, policy-sensitive outputs |

---

## 2. Scope decisions & non-goals

**Decisions (locked in brainstorming):**
1. **Target = Claude-Code-native, portable core.** Built on the Workflow tool, the Agent model-routing HARD CONTRACT, the existing `/verify-slice` loop, GSD, and superpowers — with the repo-OS contract kept engine-neutral so it degrades to Codex/Hermes (mirrors the Harmony "Claude-first, portable format" decision).
2. **Job = architect + operator (full lifecycle).** Designs the loop AND launches/runs it (approval-gated, explicit terminal states).
3. **Packaging = new `loop-engineer` local plugin (router + 6 spokes).** Calls existing assets; does not reimplement them.
4. **10/10 bar = suite + self-eval harness (dogfood) + worked example + adversarial review to ≥9.5/10.**

**Non-goals (YAGNI):**
- Not a general task-doer; it builds loops, it doesn't do the domain work.
- No tri-runner (Codex/Hermes runners) shipped in v1 — the *portable contract* is the cross-engine story; Harmony already covers live cross-engine execution. The Python-FSM-spine realization, when `loop-architect` recommends it, points to Harmony's existing `engine/cli.py` — v1 ships no new spine code.
- No new verification engine — delegates to `/verify-slice` / `/verify-milestone`.
- No always-on background daemon — runs are explicitly launched/resumed.

---

## 3. Architecture — plugin shape

```
loop-engineer/
├── .claude-plugin/{plugin.json, marketplace.json}
├── skills/
│   ├── loop-engineer/        # ROUTER — broad intent → spokes + decision map
│   ├── loop-architect/       # scenario classification → architecture + realization
│   ├── loop-contract/        # scaffold the repo-OS operating contract
│   ├── loop-run/             # operator: run the state machine (approval-gated)
│   ├── loop-repair/          # patch-and-repair loop
│   ├── loop-evals/           # eval-suite designer + the two missed metrics
│   └── loop-flywheel/        # improvement flywheel + memory compaction
├── reference/                # architecture-matrix, loop-patterns, repo-os-contract,
│                             #   prompt-templates, eval-suite, safety-and-approvals, platform-map
├── templates/                # scaffoldable files (SPEC/WORKFLOW/TASKS.json/RUNLOG/.loop/state.json/verify-*/EVALS)
├── evals/                    # self-eval: rubric + cases (dogfood)
├── examples/                 # one runnable end-to-end worked scenario
├── scripts/                  # validate_frontmatter.py, self_eval.py
├── README.md, CHANGELOG.md
```

Each skill: one `SKILL.md`, narrow trigger surface, `[[other-skill]]` cross-links. Router lists all spokes. Depth lives in `reference/` (loaded on demand), not in the SKILL.md bodies.

---

## 4. The core — scenario → architecture → realization

`loop-architect` is the brain. It classifies the task and selects **both** the architecture (research's 5-candidate matrix) **and** the physical realization on Claude Code primitives:

| Scenario signal | Architecture | Realization |
|---|---|---|
| Bounded, parallelizable, single-session fan-out | multi-agent / modular | **Workflow tool** (deterministic JS spine; `agent()` with explicit `model:`) |
| Long-horizon, multi-session, repo-backed, resumable | repository-OS-integrated / supervisor | **repo-OS contract + markdown supervisor** (state externalized to files; clean cross-session handoff) |
| Max-determinism / cross-engine resume required | supervisor + portable spine | **Python FSM spine** (Harmony `engine/cli.py` pattern: init/next/complete + `state.json`) |
| Acceptance-gated slice (spec + plan exist) | (delegation) | **`/verify-slice`** + `engineer` agent (don't reimplement) |
| Early prototype, single maintainer | single-skill | inline supervisor, minimal contract |

This selection logic — emitted as a structured **architecture decision record** — *is* the "creates loops based on the scenario and situation" requirement. The matrix dimensions (complexity, reliability, verifiability, parallelism, cost, ease-of-adoption) come from the research and are encoded in `reference/architecture-matrix.md`.

**Loop pattern library** (`reference/loop-patterns.md`), selected per scenario: pre-execution reflection (PreFlect), milestone loop with explicit progress accounting, patch-and-repair loop, improvement flywheel, manager-orchestrator delegation, and **plan-then-execute** (default for untrusted/web environments to reduce prompt-injection surface).

---

## 5. Reuse contract — integrates, does not duplicate

| Capability | Reuses | How |
|---|---|---|
| Acceptance verification | `claude-code-orchestration` `/verify-slice` (2-iteration fix loop + Codex cross-review + escalate-to-flag), `/verify-milestone` (Workflow batch) | `loop-evals` *designs* criteria; `loop-run` *calls* the gate |
| State machine / resume | Harmony `engine/cli.py` spine (init/next/complete; `state.json` serialize; resume-from-disk) | the Python-spine realization references this pattern |
| Grader loop | `launch-local-agent` objective-gate-then-judged-grader split | `loop-evals` separates deterministic gate (binary, blocking) from rubric judge (advisory) |
| Dispatch + cost | Agent model-routing HARD CONTRACT; `model_routing.py` / `workflow_routing.py`; `.gsd/audit/receipts/*.jsonl`; `/routing` modes + escalation valve | every dispatched agent names `model:`; receipts emitted; routing modes honored |
| Planning surface | GSD (`.gsd/`), superpowers (writing-plans, executing-plans, subagent-driven-development, verification-before-completion, TDD) | the markdown-supervisor realization composes these |

---

## 6. Repo-OS contract & terminal states

Scaffolded by `loop-contract` (templates in `templates/`):

```
<workspace>/
  AGENTS.md         # short table-of-contents of stable rules (points to the rest)
  SPEC.md           # success criteria, constraints, non-goals, evidence rules
  WORKFLOW.md       # loop policy, approval gates, budgets, terminal states
  TASKS.json        # machine-readable task ledger
  RUNLOG.md         # human-readable iteration history (one entry per loop)
  EVALS/{dataset,rubrics,regressions,traces}/
  scripts/{verify-fast, verify-full, verify-safety, judge-rubric, extract-trace-metrics}
  .loop/{state.json, checkpoints/, artifacts/, approvals/, memory/}
```

Separation of concerns: stable rules (`AGENTS.md`, `WORKFLOW.md`) ≠ intent (`SPEC.md`) ≠ machine status (`TASKS.json`, `.loop/state.json`) ≠ history (`RUNLOG.md`) ≠ proof (`scripts/verify-*`, `EVALS/`).

**Terminal states (few, explicit — no silent "completed"):** `Succeeded`, `FailedUnverifiable`, `FailedBlocked`, `FailedBudget`, `FailedSafety`, `FailedSpecGap`, `AbortedByHuman`.

**State machine:** intake → plan → critique-plan → queue-tasks → execute-task → verify → (repair | replan | approval-wait) → terminal. Externalized to `.loop/state.json` after every transition (resume rule: `state.json` exists → skip intake, continue from first incomplete state).

---

## 7. Safety / approval model (`reference/safety-and-approvals.md`)

- **Escalation ladder:** deterministic fail → patch & rerun; rubric fail → critique & targeted repair; same failure mode repeats without measurable improvement → re-plan; side-effect boundary → pause for approval, resume from same run state; policy/safety risk → hard-terminate (`FailedSafety`); **detected verifier-gaming → hard-terminate + log as security failure**.
- **Approval lifecycle:** approval gates pause-and-resume from run state; they never spawn a fresh untracked attempt.
- **Plan-then-execute:** precommit the execution graph whenever the environment is adversarial / semantically-typed tools exist (web, untrusted page content).
- **Anti-cheat:** high-value regression tasks carry hidden canary checks + adversarial probes.

---

## 8. Eval suite, metrics & self-eval (dogfood)

**Seven-layer suite** (`reference/eval-suite.md`, designed by `loop-evals`):

| Layer | Mechanism | Key metric |
|---|---|---|
| Deterministic correctness | tests, lint, typecheck, schema/contract validation | pass rate, constraint-violation count |
| Artifact quality | rubric-based model judge (fixed schema) | rubric mean, per-dimension score |
| Human calibration | adjudicated sample review | judge-human agreement, false accept/reject |
| Loop behavior | trace analysis over runs | plan compliance, repair depth, premature-stop rate |
| Security/governance | red-team scenarios, approval tests, injection tests | escape rate, approval-bypass rate |
| Regression resistance | regression dataset + trace-derived cases | regression failure count |
| Cost/efficiency | token/latency/tool logs | cost per success, wall-clock to success |

**Two under-tracked metrics made first-class:** **false-completion rate** (claims success while verification disagrees) and **repair productivity** (fraction of repair passes that measurably improve the score vs churn).

**Self-eval harness (`evals/` + `scripts/self_eval.py`) — the suite graded by its own methodology:**
- Deterministic structural checks: every SKILL.md frontmatter parses via `yaml.safe_load`; `name:` == directory; all 7 skills present; every `[[link]]` resolves; every `reference/` file referenced by ≥1 skill; the 7 terminal states present in `loop-run`; contract templates complete; any dispatched-agent example names `model:`.
- Rubric (10 dimensions, weighted) scored by an LLM judge.
- Meta-metrics: structural pass rate (must be 100%), rubric mean (target ≥9.5/10).

---

## 9. Per-spoke I/O contracts

- **loop-architect** — in: raw objective + context; out: architecture decision record (chosen architecture + realization + selected loop patterns + which spokes to run + risk profile). Read-only/advisory.
- **loop-contract** — in: architecture decision + goal; out: scaffolded repo-OS files (SPEC/WORKFLOW/TASKS.json/RUNLOG/.loop/state.json/verify-* skeletons) + pre-execution reflection record.
- **loop-run** — in: contract files; out: executed iterations (RUNLOG entries, state.json transitions, verification bundles), terminal_state.json. Approval-gated; dispatches via Agent/Workflow with model routing; calls `/verify-slice`.
- **loop-repair** — in: failing verification + best prior state + diff; out: structured repair record (`failure_mode`, `hypothesis`, `repair_action`, `verification_before/after`, `remaining_delta`); enforces a max-attempt cap (default N=2, configurable in `WORKFLOW.md`) then replan/revert/approve/terminate.
- **loop-evals** — in: SPEC + artifacts; out: `scripts/verify-*` + `EVALS/` rubrics + the metric definitions.
- **loop-flywheel** — in: RUNLOG + traces + memory; out: new eval cases from failures, harness-change proposals, compacted memory (short-term summary + long-term lessons).

---

## 10. Packaging & install

- `.claude-plugin/plugin.json`: `name: loop-engineer`, version `0.1.0`, author, MIT.
- `.claude-plugin/marketplace.json`: marketplace `name: loop-engineer-local`, one plugin entry `source: "./"`.
- Frontmatter rule: `description:` must be **quoted** (avoids the colon-space YAML-discovery break); `scripts/validate_frontmatter.py` (`yaml.safe_load` gate) enforces parse + dict + name==dir.
- Install: `claude plugin marketplace add /mnt/c/Dev/projects/loop-engineer` → `claude plugin install loop-engineer@loop-engineer-local` → restart.

---

## 11. Acceptance criteria (checkable)

1. Plugin registers and all **7** skills (router + 6 spokes) are discoverable after install.
2. `scripts/validate_frontmatter.py` passes 7/7 SKILL.md (parse + dict + `name`==dir + quoted description).
3. `loop-architect` encodes the full scenario→architecture→realization decision table and emits a structured architecture decision record.
4. `loop-contract` scaffolds **all** repo-OS artifacts; templates exist for each.
5. `loop-run` enumerates the **7** terminal states and the approval pause/resume rule; dispatched-agent examples name `model:`.
6. `loop-repair` produces the structured repair record schema and enforces a max-N attempt cap with escalation.
7. `loop-evals` documents all **7** eval layers plus false-completion-rate and repair-productivity.
8. `loop-flywheel` documents the trace→eval→harness loop and the short-term/long-term memory split.
9. Reuse contract is explicit: skills reference `/verify-slice`, Harmony spine, model-routing contract, receipts — no duplicate verification engine.
10. `examples/` contains one runnable end-to-end scenario (architecture decision → scaffolded contract → ≥2 RUNLOG iterations → a repair record → a terminal state).
11. `scripts/self_eval.py`: structural checks 100% pass; rubric mean ≥9.5/10.
12. No secrets; no hardcoded credentials; every dispatched agent/`agent()` names an explicit `model:`.

---

## 12. Build approach & model routing

spec → `writing-plans` → parallel **Opus** authors (disjoint skills/files, no git-worktree isolation — Apex hazard; central path-scoped commits) → **Sonnet** skeptic verify per skill → **Opus** fix-where-broken → `self_eval.py` + frontmatter gate → adversarial review loop until ≥9.5/10 → register marketplace + verify discovery → commit + push to private origin. Reads/exploration → **Haiku**.

## 13. Risks & open questions

- **GateGuard friction:** every new-file Write triggers the fact-forcing gate; subagent prompts must include a GateGuard fact template so authors don't stall.
- **Hook firing in subagents:** confirm PreToolUse hooks (`pre_tool_use.py`, model_routing, GateGuard) fire for subagent writes; plan assumes yes.
- **Self-eval rubric judge** is an LLM call — keep the deterministic structural gate as the hard pass/fail; rubric is advisory toward the ≥9.5 target.
- **Portable-core claim** is contract-level only in v1 (no live Codex/Hermes runner) — `reference/platform-map.md` documents the mapping, not a tested runner.
