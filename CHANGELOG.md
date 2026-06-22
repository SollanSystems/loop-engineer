# Changelog

All notable changes to `loop-engineer` are documented here.

---

## 0.2.0 — 2026-06-21

Release-readiness pass: a real LICENSE file, owned terminology, a documented
differentiation story, and — most substantively — the false-completion defense
turned from prose into **runnable tooling** the loop can call.

### Added

**Licensing & docs**
- `LICENSE` — MIT, Sollan Systems 2026, at repo root. (Through 0.1.0, MIT was
  declared only in `plugin.json` / `README.md`; the license file itself was
  missing — a real public-release blocker.)
- `GLOSSARY.md` — owns the suite's vocabulary: loop engineering, the operating
  contract, deterministic gate vs advisory rubric, held-out verifier split,
  anti-cheat trajectory scan, false completion, the two first-class metrics, the
  repair record, the failure-mode taxonomy, and the 7 terminal states.
- `README.md` — a **"How it compares"** section positioning the suite against the
  adjacent clusters (native execution primitives, SDLC workflow harnesses,
  swarm/orchestration engines) and separating what is genuinely differentiated
  from what is table-stakes.

**Runnable false-completion defense (design-only in 0.1.0 → tooling in 0.2.0)**
- `scripts/holdout_gate.py` — the held-out verifier split as composable tooling:
  a loop may declare `Succeeded` only if a withheld **holdout** check set passes,
  not just the **visible** set it optimized against. Emits a measurable
  `false_completion` event so false-completion-rate is *measured*, not
  self-reported. Pure `decide()` core + a `run_manifest()` executor.
- `scripts/anticheat_scan.py` — the anti-cheat trajectory scan as composable
  tooling: after a `Succeeded` claim, sweeps the diff + trajectory for shortcut
  signatures (gate tampering, skip/xfail injection, assert-true, hidden-answer
  reads, test-file mutation). HIGH/CRITICAL findings auto-downgrade the verdict
  (`FailedUnverifiable` / `FailedSafety`); MEDIUM is a review flag so honest TDD
  is not punished.
- `scripts/test_holdout_gate.py`, `scripts/test_anticheat_scan.py` — TDD suites
  for both tools.
- `reference/eval-suite.md` + `skills/loop-evals/SKILL.md` — wire the two scripts
  in as the runnable realization of the Layer-4 false-completion-rate and
  Layer-5 anti-cheat surfaces (previously described only as design guidance).

**Stricter self-eval (10 → 12 deterministic checks)**
- `scripts/self_eval.py` — added `license-present` (a real MIT LICENSE with
  correct title / holder / year / body marker, so a stub cannot pass) and
  `readme-differentiation` (a "How it compares" heading plus both first-class
  metrics named). The gate was *strengthened*; no existing check was weakened.
- `evals/cases/structural.json` — `license` and `readme_differentiation` expected
  facts backing the two new checks.
- `scripts/test_self_eval.py` — coverage for both new checks
  (missing-then-present, wrong-holder, heading-required, markers-required) and
  the updated 12-check count.

### Changed
- `.gitignore` — ignore `.loop/` (per-run operating-contract telemetry from the
  self-improvement run; not plugin content).

### Notes
- The repo remains private. Flipping it to public MIT is a separate, human-only
  act outside the scope of the release run that produced this version.

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
