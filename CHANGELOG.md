# Changelog

All notable changes to `loop-engineer` are documented here.

---

## 0.1.0 — 2026-06-20

Initial release of the loop-engineer local plugin.

### Added

**Plugin packaging**
- `.claude-plugin/plugin.json` — plugin manifest (name `loop-engineer`, version `0.1.0`, MIT)
- `.claude-plugin/marketplace.json` — local marketplace registration (`loop-engineer-local`)

**Skills — 1 router + 6 spokes**
- `skills/loop-engineer/` — router; maps broad intent to the right spoke; decision quickstart
- `skills/loop-architect/` — scenario classification → architecture decision record (chosen architecture + realization + loop patterns + risk profile); encodes the full scenario→architecture→realization matrix
- `skills/loop-contract/` — scaffolds the repo-OS operating contract (SPEC / WORKFLOW / TASKS.json / RUNLOG / .loop/state.json) with pre-execution reflection
- `skills/loop-run/` — operator; runs the state machine iteration by iteration; 7 explicit terminal states; approval pause/resume; delegates to `/verify-slice`; model-routing-compliant dispatch examples
- `skills/loop-repair/` — patch-and-repair loop; structured repair record (failure\_mode / hypothesis / repair\_action / verification\_before / verification\_after / remaining\_delta); max-N attempt cap (default 2) with replan/revert/terminate escalation
- `skills/loop-evals/` — 7-layer eval suite designer; makes false-completion-rate and repair-productivity first-class metrics; deterministic-gate-first then rubric-judge; repo-native regression harness; delegates to `/verify-slice` + `/verify-milestone`
- `skills/loop-flywheel/` — improvement flywheel; mines traces and RUNLOG to generate new eval cases; memory compaction (short-term continue-run summary vs long-term lessons); improvement schedule and scorecard freeze policy

**Reference depth (7 files)**
- `reference/architecture-matrix.md` — 5-candidate architecture comparison table (complexity / reliability / verifiability / parallelism / cost / ease-of-adoption) + scenario→realization decision table; maximize-single-agent-first rule
- `reference/loop-patterns.md` — 6 loop patterns with when-to-use and 3-line skeletons: pre-execution reflection (PreFlect), milestone loop, patch-and-repair, improvement flywheel, manager-orchestrator delegation, plan-then-execute
- `reference/repo-os-contract.md` — full repo-OS tree layout; per-artifact schemas for SPEC / WORKFLOW / TASKS.json / RUNLOG / .loop/state.json / terminal\_state.json; separation-of-concerns rationale; YAML skill-manifest example
- `reference/prompt-templates.md` — 4 templates adapted for Claude Code: BOOTSTRAP, GOAL-LAUNCH, REPAIR-LOOP, SHORT-OUTCOME-FIRST; portability note for Codex
- `reference/eval-suite.md` — 7-layer suite table (layer / mechanism / key metric); false-completion-rate and repair-productivity definitions; deterministic-first-then-rubric rule; judge calibration; flywheel schedule
- `reference/safety-and-approvals.md` — escalation ladder; approval lifecycle (pause + resume from run state, never a fresh attempt); 7 terminal states with firing conditions; plan-then-execute policy; verifier-gaming → hard-terminate; anti-cheat (hidden canaries + adversarial probes); permission tiers
- `reference/platform-map.md` — portable-core mapping: Claude (Workflow tool / Agent routing / /verify-slice / GSD / Harmony spine), Codex/ChatGPT-Pro (AGENTS.md / Goal mode / structured outputs), Hermes (persistent memory / isolated subagents), Google Conductor

**Contract templates (10 files)**
- `templates/AGENTS.md.tmpl` — table-of-contents of stable rules
- `templates/SPEC.md.tmpl` — success criteria, constraints, non-goals, evidence rules
- `templates/WORKFLOW.md.tmpl` — loop policy, approval gates, budgets, 7 terminal states, repair cap (N=2)
- `templates/TASKS.json.tmpl` — machine-readable task ledger scaffold
- `templates/RUNLOG.md.tmpl` — human-readable iteration history scaffold
- `templates/state.json.tmpl` — all state fields from the interface contract; terminal\_state: null
- `templates/terminal_state.json.tmpl` — terminal state record scaffold
- `templates/EVALS-rubric.md.tmpl` — eval rubric scaffold (7-layer)
- `templates/verify-fast.sh` — runnable stub with comment markers for fast deterministic checks
- `templates/verify-full.sh` — runnable stub with comment markers for full verification suite

**Scripts / quality gates**
- `scripts/validate_frontmatter.py` — deterministic frontmatter gate: `yaml.safe_load` parse, dict check, `name:` == directory name, `description:` non-empty; exits `1` on any error
- `scripts/test_validate_frontmatter.py` — pytest suite for the frontmatter validator (TDD; 4 cases)
- `scripts/self_eval.py` — 10 structural checks (skills present, frontmatter valid, reference cross-links, `[[link]]` resolution, terminal-state tokens, repair-record fields, eval-layer + metric coverage, templates present, no secret patterns, model-routing compliance); reports `structural_pass_rate`
- `scripts/test_self_eval.py` — pytest suite for the self-eval runner (TDD; 2 cases)

**Evals harness**
- `evals/rubric.md` — 10 weighted dimensions (research-fidelity, scenario-routing-correctness, contract-completeness, reuse-not-duplication, safety/terminal-state rigor, eval-suite depth, flywheel/memory clarity, frontmatter/trigger quality, brevity/altitude, worked-example quality); target mean ≥9.5/10
- `evals/cases/structural.json` — expected structural facts for `self_eval.py` check inputs

**Worked example**
- `examples/coverage-repair/` — end-to-end scenario: bring `pricing.py` to 80% coverage + input validation via a repair loop; includes ADR (architecture=single-supervisor, realization=markdown-supervisor), SPEC, WORKFLOW, TASKS.json, RUNLOG (2 iterations: verify-fail → repair → verify-pass), repair-record.json, terminal\_state.json (Succeeded), and README tying each artifact to its spoke

**Docs**
- `README.md` — what it is; 7-skill table; install commands; decision quickstart; terminal state reference; reuse table; gate commands
- `CHANGELOG.md` — this file

### Design decisions

- The loop is the design object, not the prompt. Skills architect loops, not domain solutions.
- 7 explicit terminal states; no silent "completed."
- Reuse over reimplementation: `/verify-slice`, `/verify-milestone`, Harmony `engine/cli.py` spine, `launch-local-agent` grader split, model-routing HARD CONTRACT, `.gsd/audit/receipts/*.jsonl`.
- Portable core: repo-OS contract is engine-neutral; v1 ships contract-level mapping across Claude / Codex / Hermes / Google — live cross-engine runners are deferred.
- Deterministic structural gate (100% pass required) is separate from the advisory LLM rubric judge (target ≥9.5/10).
- `description:` frontmatter MUST be double-quoted to avoid the colon-space YAML-discovery break (enforced by `validate_frontmatter.py`).
- No new verification engine — delegates to existing infrastructure.
