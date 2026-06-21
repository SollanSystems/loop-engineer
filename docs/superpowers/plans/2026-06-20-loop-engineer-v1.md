# loop-engineer v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `loop-engineer` local plugin — a Claude-Code-native skill suite (1 router + 6 spokes) that designs, launches, verifies, repairs, and improves agent loops, plus a self-eval harness and a worked example.

**Architecture:** A local plugin (web-design-os pattern) of focused SKILL.md files that point to deep `reference/` docs and scaffoldable `templates/`. Skills *call* existing assets (`/verify-slice`, Harmony spine, model-routing contract, receipts) rather than reimplementing them. Two Python scripts (`validate_frontmatter.py`, `self_eval.py`) provide deterministic structural gates.

**Tech Stack:** Markdown (SKILL.md + reference), JSON (plugin/marketplace/templates), Python 3.12 (run via `uv run --with pyyaml python3`), pytest for the scripts.

**Source of truth:** `docs/superpowers/specs/2026-06-20-loop-engineer-design.md` (read it before any task).

## Global Constraints

Every task implicitly includes these (copied verbatim from the spec):

- **Model routing (HARD CONTRACT):** any `Agent` dispatch or Workflow `agent()` example names an explicit `model:` — read→`haiku`, reason→`sonnet`, write→`opus`, orchestrate→main-loop. Never omit `model:`.
- **Frontmatter:** `description:` MUST be wrapped in double quotes (avoids the colon-space YAML-discovery break); `name:` MUST equal the skill's directory name; both non-empty strings; the whole block must `yaml.safe_load` to a dict.
- **Terminal states (canonical, verbatim, exactly 7):** `Succeeded`, `FailedUnverifiable`, `FailedBlocked`, `FailedBudget`, `FailedSafety`, `FailedSpecGap`, `AbortedByHuman`. No silent "completed."
- **Eval layers (7):** deterministic-correctness, artifact-quality, human-calibration, loop-behavior, security/governance, regression-resistance, cost/efficiency. Plus two first-class metrics: **false-completion-rate**, **repair-productivity**.
- **Repair cap:** default N=2, configurable in `WORKFLOW.md`.
- **Reuse, don't reimplement:** reference `/verify-slice` + `/verify-milestone` (claude-code-orchestration), Harmony `engine/cli.py` spine, `launch-local-agent` grader split, `.gsd/audit/receipts/*.jsonl`, `model_routing.py`/`workflow_routing.py`, `/routing` modes. No new verification engine.
- **Cross-links:** spokes link siblings with `[[skill-name]]`; every `reference/` file must be referenced by ≥1 SKILL.md; the router lists all 6 spokes.
- **Skill brevity:** SKILL.md bodies stay tight (~80–200 lines); depth goes in `reference/`.
- **Security:** no secrets, tokens, or credentials in any file. Validate only at boundaries.
- **GateGuard (build-time):** the first Write of any new file is blocked by the fact-forcing gate; present the 4 facts (caller / no-existing-equivalent / data-shape / user-instruction) then retry the identical Write. Edits to existing files are not gated.

---

## File Structure

| Path | Responsibility |
|---|---|
| `.claude-plugin/plugin.json` | Plugin manifest (name `loop-engineer`, v0.1.0) |
| `.claude-plugin/marketplace.json` | Local marketplace (`loop-engineer-local`) |
| `scripts/validate_frontmatter.py` | Deterministic frontmatter gate (yaml.safe_load + name==dir) |
| `scripts/self_eval.py` | Deterministic structural self-eval (10 checks) + report |
| `skills/loop-engineer/SKILL.md` | Router: intent → spoke map + decision quickstart |
| `skills/loop-architect/SKILL.md` | Scenario → architecture + realization (the brain) |
| `skills/loop-contract/SKILL.md` | Scaffold the repo-OS operating contract |
| `skills/loop-run/SKILL.md` | Operator: run the state machine (approval-gated) |
| `skills/loop-repair/SKILL.md` | Patch-and-repair loop |
| `skills/loop-evals/SKILL.md` | Eval-suite designer + the 2 missed metrics |
| `skills/loop-flywheel/SKILL.md` | Improvement flywheel + memory compaction |
| `reference/architecture-matrix.md` | 5-candidate matrix + realization mapping |
| `reference/loop-patterns.md` | Loop pattern library (6 patterns) |
| `reference/repo-os-contract.md` | Repo-OS layout + per-artifact schema |
| `reference/prompt-templates.md` | BOOTSTRAP / GOAL-LAUNCH / REPAIR / SHORT prompts |
| `reference/eval-suite.md` | 7-layer suite + metrics + flywheel schedule |
| `reference/safety-and-approvals.md` | Approval lifecycle + plan-then-execute + anti-cheat |
| `reference/platform-map.md` | Portable-core mapping (Claude/Codex/Hermes) |
| `templates/*` | Scaffoldable contract files |
| `evals/rubric.md` | Self-eval rubric (10 weighted dimensions) |
| `evals/cases/structural.json` | Expected structural facts for self_eval |
| `examples/coverage-repair/*` | Worked end-to-end scenario artifacts |
| `README.md`, `CHANGELOG.md` | Docs |

---

## Phase 0 — Packaging + frontmatter gate

### Task 1: Plugin manifests

**Files:** Create `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`

- [ ] **Step 1: Write `plugin.json`**

```json
{
  "$schema": "https://json.schemastore.org/claude-code-plugin.json",
  "name": "loop-engineer",
  "version": "0.1.0",
  "description": "Design, launch, verify, repair, and improve agent loops. A Claude-Code-native architect+operator for long-running, verifiable, self-improving agentic-coding systems.",
  "author": { "name": "Sollan Systems", "url": "https://github.com/SollanSystems" },
  "license": "MIT"
}
```

- [ ] **Step 2: Write `marketplace.json`**

```json
{
  "$schema": "https://json.schemastore.org/claude-code-plugin-marketplace.json",
  "name": "loop-engineer-local",
  "owner": { "name": "SollanSystems" },
  "plugins": [
    { "name": "loop-engineer", "source": "./", "description": "Agent-loop architect+operator skill suite." }
  ]
}
```

- [ ] **Step 3: Commit** — `git -C <repo> add .claude-plugin && git -C <repo> commit -m "feat(pkg): plugin + marketplace manifests"`

**Acceptance:** both files `json.load` without error; `name` fields are `loop-engineer` / `loop-engineer-local`.

### Task 2: `scripts/validate_frontmatter.py` (TDD)

**Files:** Create `scripts/validate_frontmatter.py`, `scripts/test_validate_frontmatter.py`

**Produces:** `extract_frontmatter(text)->str`, `validate_skill(path)->list[str]` (errors), `main()->int` (0 ok, 1 fail). Scans `skills/*/SKILL.md`.

- [ ] **Step 1: Write failing tests**

```python
# scripts/test_validate_frontmatter.py
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("vf", pathlib.Path(__file__).parent / "validate_frontmatter.py")
vf = importlib.util.module_from_spec(spec); spec.loader.exec_module(vf)

def test_extracts_frontmatter():
    assert "name: x" in vf.extract_frontmatter("---\nname: x\ndescription: \"y\"\n---\nbody")

def test_unquoted_colon_space_is_error(tmp_path):
    d = tmp_path / "skills" / "demo"; d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: demo\ndescription: Use when: bad\n---\n")
    errs = vf.validate_skill(d / "SKILL.md")
    assert any("mapping" in e or "description" in e for e in errs)

def test_name_must_match_dir(tmp_path):
    d = tmp_path / "skills" / "demo"; d.mkdir(parents=True)
    (d / "SKILL.md").write_text('---\nname: wrong\ndescription: "ok"\n---\n')
    assert any("!= directory" in e for e in vf.validate_skill(d / "SKILL.md"))

def test_valid_skill_has_no_errors(tmp_path):
    d = tmp_path / "skills" / "demo"; d.mkdir(parents=True)
    (d / "SKILL.md").write_text('---\nname: demo\ndescription: "ok"\n---\n')
    assert vf.validate_skill(d / "SKILL.md") == []
```

- [ ] **Step 2: Run — expect FAIL** — `uv run --with pyyaml python3 -m pytest scripts/test_validate_frontmatter.py -v` → fails (module funcs missing).

- [ ] **Step 3: Implement**

```python
# scripts/validate_frontmatter.py
import sys, pathlib, yaml

def extract_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        raise ValueError("no frontmatter block")
    end = text.index("\n---", 3)
    return text[3:end]

def validate_skill(path) -> list:
    errors = []
    path = pathlib.Path(path)
    raw = path.read_text(encoding="utf-8")
    try:
        fm = yaml.safe_load(extract_frontmatter(raw))
    except Exception as e:
        return [f"{path}: frontmatter does not parse ({e}); likely a stray ': ' in an unquoted scalar"]
    if not isinstance(fm, dict):
        return [f"{path}: frontmatter is not a mapping (likely a stray ': ' in an unquoted scalar)"]
    for key in ("name", "description"):
        if not isinstance(fm.get(key), str) or not fm[key].strip():
            errors.append(f"{path}: missing/empty '{key}'")
    if isinstance(fm.get("name"), str) and fm["name"] != path.parent.name:
        errors.append(f"{path}: name '{fm['name']}' != directory '{path.parent.name}'")
    return errors

def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    skills = sorted((root / "skills").glob("*/SKILL.md"))
    all_errors = [e for s in skills for e in validate_skill(s)]
    for e in all_errors:
        print("FAIL:", e)
    print(f"checked {len(skills)} skills, {len(all_errors)} errors")
    return 1 if all_errors else 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run — expect PASS** — same pytest command → all pass.

- [ ] **Step 5: Commit** — `git -C <repo> add scripts/validate_frontmatter.py scripts/test_validate_frontmatter.py && git -C <repo> commit -m "feat(scripts): frontmatter validation gate (TDD)"`

---

## Phase 1 — Reference depth (7 files, parallelizable)

Each reference file is grounded in the spec + source research. **Acceptance for every reference file:** covers all listed required content; no placeholders; referenced by ≥1 SKILL.md (wired in Phase 3). Each ends with a "Sources" line citing the research.

### Task 3: `reference/architecture-matrix.md`
Required content: the 5 candidate architectures (single-skill, modular-skills-library, supervisor-skill, multi-agent-skillset, repository-OS-integrated) as a table rated across complexity / reliability / verifiability / parallelism / cost / ease-of-adoption / best-use (from spec §4 + research). The **scenario→architecture→realization** decision table (spec §4). The "maximize a single agent first; add orchestration only when tool/instruction/routing overload justifies it" rule. When to pick each realization (Workflow tool / markdown-supervisor / Harmony Python-spine / delegate-to-verify-slice).

### Task 4: `reference/loop-patterns.md`
Required content: the 6 patterns with when-to-use + a 3-line skeleton each: (1) pre-execution reflection (PreFlect; A/B trigger policy), (2) milestone loop with explicit progress accounting, (3) patch-and-repair loop, (4) improvement flywheel, (5) manager-orchestrator delegation, (6) plan-then-execute (default for untrusted/web — precommit the execution graph). Note plan-compliance caveat (bad/over-phased plans can hurt).

### Task 5: `reference/repo-os-contract.md`
Required content: the full repo-OS tree (spec §6); per-artifact purpose + minimal schema for `SPEC.md`, `WORKFLOW.md`, `TASKS.json` (task object fields), `RUNLOG.md` (per-iteration entry fields), `.loop/state.json` (state fields from spec §1), `terminal_state.json`. The YAML skill-manifest example (inputs/outputs/policies/terminal_states). The separation-of-concerns rationale.

### Task 6: `reference/prompt-templates.md`
Required content: the four templates adapted to Claude Code, each in a fenced block — BOOTSTRAP, GOAL-LAUNCH, REPAIR-LOOP, SHORT-OUTCOME-FIRST (from research). Add the Codex nuance as a portability note ("avoid verbose upfront-plan chatter during rollout — keep execution prompts tight/artifact-oriented"). Each template references the repo-OS files.

### Task 7: `reference/eval-suite.md`
Required content: the 7-layer table (layer / mechanism / key metric) from spec §8; the two first-class metrics (false-completion-rate, repair-productivity) with definitions; deterministic-first-then-rubric rule; judge calibration (human-labeled adjudication set, track agreement monthly + after model changes); regression harness must be repo-native (datasets/rubrics/scripts/trace-transforms in-repo, model calls as grading components — not tied to a vendor eval UI); the flywheel schedule (baseline → loop-hardening → regression-harness → freeze first scorecard).

### Task 8: `reference/safety-and-approvals.md`
Required content: the escalation ladder (spec §7); approval lifecycle (pause + resume from run state, never fresh attempt); the 7 terminal states + when each fires; plan-then-execute for adversarial/web; verifier-gaming → hard-terminate + log as security failure; anti-cheat (hidden canaries + adversarial probes on high-value regression tasks); permission tiers.

### Task 9: `reference/platform-map.md`
Required content: how the engine-neutral repo-OS contract maps onto each surface — **Claude** (Workflow tool, Agent routing, /verify-slice, GSD, superpowers, Harmony spine); **Codex/ChatGPT-Pro** (AGENTS.md, Goal mode, Codex skills, structured outputs); **Hermes** (Nous — persistent memory, auto-skills, isolated subagents/sandboxes); **Google** (Conductor context-driven dev, persistent-markdown specs). Note durable-portability stance (keep contract repo-native; surfaces move fast — e.g. consumer Gemini CLI→Antigravity transition; OpenAI Evals platform going read-only). v1 ships contract-level mapping, not live runners.

---

## Phase 2 — Templates

### Task 10: Contract templates
**Files:** Create `templates/AGENTS.md.tmpl`, `templates/SPEC.md.tmpl`, `templates/WORKFLOW.md.tmpl`, `templates/TASKS.json.tmpl`, `templates/RUNLOG.md.tmpl`, `templates/state.json.tmpl`, `templates/terminal_state.json.tmpl`, `templates/verify-fast.sh`, `templates/verify-full.sh`, `templates/EVALS-rubric.md.tmpl`

- Each template uses `{{PLACEHOLDER}}` tokens (these ARE intended placeholders for scaffolding — exempt from the no-placeholder rule, which applies to the plan, not to template files).
- `state.json.tmpl` carries every field from spec §1 State row + `terminal_state: null`.
- `WORKFLOW.md.tmpl` enumerates the 7 terminal states + the repair cap (N=2) + approval policy.
- `verify-fast.sh` / `verify-full.sh` are runnable stubs (`#!/usr/bin/env bash`, `set -euo pipefail`, echo + exit 0) with comment markers for where real checks go.

**Acceptance:** `TASKS.json.tmpl` + `state.json.tmpl` + `terminal_state.json.tmpl` parse as JSON after `{{...}}` tokens are replaced **type-aware** (not by a single naive string swap — these templates carry un-quoted numeric/boolean placeholders such as `"plan_version": {{PLAN_VERSION}}`, `"best_score": {{BEST_SCORE}}`, `"repair_cap": {{REPAIR_CAP}}`, `"succeeded": {{SUCCEEDED}}`, `"score": {{FINAL_SCORE}}`, which a `{{...}}`→`placeholder` swap would render invalid). Two-pass substitution test recipe: quoted placeholders (`"{{X}}"`) → `"sample"`; bare placeholders (`: {{X}}`) → `0` (or `false` for the boolean `succeeded`/`pending_approval` fields). Then `json.loads` must succeed. Shell stubs are `bash -n` clean.

---

## Phase 3 — Skills (router + 6 spokes, parallelizable)

**Acceptance for every SKILL.md:** quoted `description:`; `name:` == dir; body ≤ ~200 lines; cross-links siblings with `[[...]]`; references ≥1 `reference/` file; passes `validate_frontmatter.py`. Spokes do real work via existing tools (Agent/Workflow/Skill), naming `model:` in any dispatch example.

### Task 11: `skills/loop-architect/SKILL.md`
Frontmatter triggers: "which loop architecture", "design the loop for this task", "what agent system should I build", "is this one agent or many". Body: intake (the input contract from spec §1), scenario classification questions, the scenario→architecture→realization table, the **architecture decision record (ADR)** output schema (chosen architecture, realization, selected loop patterns, risk profile, which spokes to run next, terminal-state plan), the maximize-single-agent-first rule. Links: `[[loop-contract]]`, `reference/architecture-matrix.md`, `reference/loop-patterns.md`.

### Task 12: `skills/loop-contract/SKILL.md`
Triggers: "scaffold the loop contract", "set up SPEC/WORKFLOW/TASKS", "create the operating contract", "initialize a loop". Body: when to run (after ADR), the repo-OS layout, the pre-execution-reflection step (critique plan before first change), how to fill each template, the underspecified→`FailedSpecGap` rule. Links: `[[loop-architect]]`, `[[loop-run]]`, `reference/repo-os-contract.md`, `reference/prompt-templates.md`, `templates/`.

### Task 13: `skills/loop-run/SKILL.md`
Triggers: "run the loop", "launch the goal", "execute the agent loop", "start the long-running run". Body: the state machine (intake→plan→critique→queue→execute→verify→repair/replan/approval→terminal), per-iteration output contract, the **7 terminal states**, approval pause/resume rule, dispatch realization (Agent/Workflow with explicit `model:`; calls `/verify-slice`), plan-then-execute for untrusted, resume-from-`state.json`. Links: `[[loop-repair]]`, `[[loop-evals]]`, `reference/safety-and-approvals.md`, `reference/prompt-templates.md`.

### Task 14: `skills/loop-repair/SKILL.md`
Triggers: "repair the loop", "the loop is failing", "verification failed", "fix and rerun". Body: the REPAIR-LOOP procedure, failure-mode classification, smallest-bounded-repair, the structured repair-record schema (`failure_mode`/`hypothesis`/`repair_action`/`verification_before`/`verification_after`/`remaining_delta`), max-N (default 2) → replan/revert/approve/terminate, no-scope-widening + no-editing-tests rules. Links: `[[loop-run]]`, `reference/safety-and-approvals.md`.

### Task 15: `skills/loop-evals/SKILL.md`
Triggers: "evaluate the loop", "build the eval harness", "verification suite", "how do I measure this loop". Body: the 7-layer suite, false-completion-rate + repair-productivity, deterministic-first-then-rubric, judge calibration, repo-native regression harness, delegation to `/verify-slice` + `/verify-milestone`. Links: `[[loop-flywheel]]`, `reference/eval-suite.md`.

### Task 16: `skills/loop-flywheel/SKILL.md`
Triggers: "improve the loop", "mine traces", "make the loop better over time", "turn failures into evals". Body: the flywheel (traces/RUNLOG → new eval cases → harness changes), memory compaction (short-term continue-run summary vs long-term lessons), the improvement schedule, when to freeze a scorecard. Links: `[[loop-evals]]`, `reference/eval-suite.md`.

### Task 17: `skills/loop-engineer/SKILL.md` (ROUTER — do last)
Triggers: "design an agent loop", "build a verification harness", "set up a repair loop", "optimize my agent system", "long-running goal", "create an agent loop", "agent harness", "make my agentic coding more robust". Body: the concept (the loop is the design object, not the prompt); the 6-spoke decision map (one line each: when to reach for it); a quickstart (new loop → architect→contract→run; failing loop → repair; measuring → evals; improving → flywheel); the defers-to note (verify-slice, Harmony, launch-local-agent, superpowers, ui/orchestration); link to `reference/architecture-matrix.md`. Lists all 6 spokes via `[[...]]`.

---

## Phase 4 — Self-eval harness

### Task 18: `scripts/self_eval.py` (TDD) + `evals/`
**Files:** Create `scripts/self_eval.py`, `scripts/test_self_eval.py`, `evals/rubric.md`, `evals/cases/structural.json`

**Produces:** `run_checks(root)->dict` returning `{checks:[{name,ok,detail}], structural_pass_rate:float, passed:bool}`.

The 10 deterministic checks:
1. all 7 skills present (router + 6 spokes)
2. every SKILL.md passes frontmatter validation (import `validate_frontmatter`)
3. every `reference/*.md` is referenced by ≥1 SKILL.md
4. every `[[link]]` in skills resolves to an existing skill dir
5. `loop-run/SKILL.md` contains all 7 terminal-state tokens
6. `loop-repair/SKILL.md` contains the 7 repair-record fields (`evals/cases/structural.json` is richer than spec §9: it splits `verification_before`/`verification_after` into two and adds `productive`, so the count is 7, not the spec's compounded 5 — plan text, structural.json, and the self_eval output string all read 7)
7. `loop-evals/SKILL.md` contains all 7 eval-layer names + both missed metrics
8. all template files exist (the Phase-2 set)
9. no obvious secret patterns in any tracked file (reuse a simple regex set)
10. every dispatched-agent example (`subagent_type`/`agent(`) co-occurs with `model:` (routing compliance)

- [ ] **Step 1: Write failing tests** (`scripts/test_self_eval.py`)

```python
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location("se", pathlib.Path(__file__).parent / "self_eval.py")
se = importlib.util.module_from_spec(spec); spec.loader.exec_module(se)

def test_run_checks_returns_schema():
    root = pathlib.Path(__file__).resolve().parent.parent
    r = se.run_checks(root)
    assert set(r) >= {"checks", "structural_pass_rate", "passed"}
    assert len(r["checks"]) == 10

def test_all_pass_on_real_repo():
    root = pathlib.Path(__file__).resolve().parent.parent
    r = se.run_checks(root)
    failed = [c["name"] for c in r["checks"] if not c["ok"]]
    assert r["passed"], f"failing checks: {failed}"
```

- [ ] **Step 2: Run — expect FAIL** (`test_all_pass_on_real_repo` fails until all content exists).
- [ ] **Step 3: Implement `self_eval.py`** with the 10 checks (each a small function returning `(ok, detail)`; `run_checks` aggregates; `main()` prints a table + the structural pass rate and exits non-zero if not all pass).
- [ ] **Step 4: Run — expect PASS** once all skills/references/templates are in place (run after Phase 3).
- [ ] **Step 5: Author `evals/rubric.md`** — 10 weighted dimensions (research-fidelity, scenario-routing-correctness, contract-completeness, reuse-not-duplication, safety/terminal-state rigor, eval-suite depth, flywheel/memory clarity, frontmatter/trigger quality, brevity/altitude, worked-example quality), each with a 1–10 anchor description; target mean ≥9.5.
- [ ] **Step 6: Author `evals/cases/structural.json`** — the expected facts (7 skill names, 7 reference files, 7 terminal states, 7 repair fields, template list) for check inputs.
- [ ] **Step 7: Commit** — `git -C <repo> add scripts/self_eval.py scripts/test_self_eval.py evals && git -C <repo> commit -m "feat(eval): structural self-eval harness + rubric (TDD)"`

**Acceptance:** `uv run --with pyyaml python3 scripts/self_eval.py` exits 0 with structural_pass_rate == 1.0.

---

## Phase 5 — Worked example

### Task 19: `examples/coverage-repair/`
A self-contained narrative + artifacts demonstrating the full arc for a concrete fictional target ("bring `pricing.py` to 80% coverage + add input validation, via a repair loop").
**Files:** Create `examples/coverage-repair/README.md` (the walkthrough), `ADR.md` (the architecture decision record loop-architect would emit), `SPEC.md`, `WORKFLOW.md`, `TASKS.json`, `RUNLOG.md` (≥2 iterations), `.loop/state.json`, `repair-record.json` (one structured repair), `terminal_state.json` (Succeeded).
Required: ADR shows architecture=single-supervisor + realization=markdown-supervisor; RUNLOG shows iteration 1 (verify fail) → repair-record → iteration 2 (verify pass); terminal_state Succeeded with verification evidence. README ties each artifact to the spoke that produced it.

**Acceptance:** all JSON parses; RUNLOG has ≥2 dated iterations; terminal_state.json `state == "Succeeded"`.

---

## Phase 6 — Docs + wire references

### Task 20: `README.md` + `CHANGELOG.md`
- `README.md`: what it is, the 7 skills (one line each), install commands (marketplace add + install), the decision quickstart, the reuse note, how to run the gates (`validate_frontmatter.py`, `self_eval.py`).
- `CHANGELOG.md`: `## 0.1.0 — 2026-06-20` with the v1 feature list.
- [ ] Commit — `git -C <repo> add README.md CHANGELOG.md && git -C <repo> commit -m "docs: README + CHANGELOG"`

---

## Phase 7 — Adversarial review + install + verify (orchestration)

Not file-authoring tasks; executed by the build orchestrator:
1. Run `validate_frontmatter.py` (7/7) + `self_eval.py` (100% structural).
2. Per skill: Sonnet skeptic verifies content against spec/research → Opus fixes where broken; loop until rubric mean ≥9.5.
3. Cross-skill consistency reviewer (terminal-state tokens, link integrity, no duplicated verification engine).
4. `claude plugin marketplace add /mnt/c/Dev/projects/loop-engineer` → `claude plugin install loop-engineer@loop-engineer-local`; verify discovery.
5. Final commit + `git push -u origin main`.

---

## Self-Review (plan vs spec)

- **Spec coverage:** §1 contract→Tasks 5/11; §4 decision core→Tasks 3/11; §5 reuse→Global Constraints + Tasks 9/13/15; §6 contract→Tasks 5/10; §7 safety→Task 8/13/14; §8 evals+self-eval→Tasks 7/18; §9 spokes→Tasks 11–17; §10 packaging→Tasks 1/20; §11 acceptance→Tasks 2/18/19 + Phase 7; §12 build→Phases 3/7. All sections mapped.
- **Placeholder scan:** template `{{...}}` tokens are intentional (noted); no TBD/TODO in tasks.
- **Type consistency:** `validate_skill`/`extract_frontmatter` (Task 2) imported by `self_eval` (Task 18); `run_checks` schema fixed; terminal-state token set identical across Tasks 8/10/13/19.
