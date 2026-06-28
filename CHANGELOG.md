# Changelog

All notable changes to `loop-engineer` are documented here.

---

## 0.3.1 — 2026-06-22

Adversarial-fix milestone. The v0.3.0 release closed two false-POSITIVE classes
in the anti-cheat scanner; a GPT-5.5/xhigh `codex challenge` over the v0.3.0 diff
then found the blind side — evasion paths the scanner failed to flag, plus
boundary-validation gaps in three harness scripts. This patch closes them.

### Fixed

**Anti-cheat scanner false-negatives (P1.1–P1.5)** — `scripts/anticheat_scan.py`
- **Scoped self-exclusion (P1.1).** A scanner self-edit that empties or shrinks
  `DEFAULT_GATE_PATHS` / `_ADDED_LINE_SIGNATURES` is now graded critical
  (`FailedSafety`); additive and comment-only self-edits stay clean. Removed
  entries are compared semantically, so a reorder or reformat does not flag.
- **Delete + rename evidence (P1.2).** `parse_changed_files` now also captures
  gate files that are deleted (`+++ /dev/null`) or renamed
  (`rename from`/`rename to`); both of Codex's exact exploit diffs now return
  `clean:false`.
- **verify-\* gate coverage (P1.3).** Gate-path matching now covers
  `verify-fast` / `verify-full` / `verify-safety`; tampering one to bypass it is
  flagged.
- **Broader tautology detection (P1.4).** Identical-operand assertions (a literal
  or an identifier compared against itself) and always-true unittest calls now
  downgrade to `FailedUnverifiable`; honest asserts with distinct operands stay clean.
- **Path-shaped hidden-answer names (P1.5).** Trajectory reads of held-out /
  hold_out / answer-key / golden / expected-output paths are flagged, while a
  plain `assert result == expected` stays clean.

**Boundary validation (P1.6, P2.1–P2.4)**
- `scripts/benchmark_harness.py` — `compare()` raises on a mismatched A/B
  task-set instead of reporting a silent delta; non-bool `claimed_done` /
  `verification_passed` and out-of-range repair / criteria counts are rejected.
- `scripts/runtime_monitor.py` — robust score parsing for `1e-3`, negatives, and
  malformed input (no crash); tests pin the exact intervention per scenario.
- `scripts/inspect_loop.py` — bounded shallow walk with a per-file read cap
  replaces the unbounded full-tree traversal.

### Changed (P2.5)
- `README.md` — present-tense install note corrected to "all 9 skills".
- `.claude-plugin/plugin.json` — version `0.3.0` → `0.3.1`.

### Credits
- The false-negative and boundary findings came from the GPT-5.5/xhigh
  `codex` adversarial review over the v0.3.0 release diff.

---

## 0.3.0 — 2026-06-21

The v0.2-roadmap (`G5`–`G8`) plus the two anti-cheat scanner fixes carried over
from the 0.2.0 run, built to the same deterministic release bar. Two net-new
spokes take the suite from 7 to 9 skills; the new capability ships as runnable,
composable tooling, not a new runtime. No publish — that remains a human-only act.

### Added

**Two new spokes (7 → 9 skills)**
- `skills/loop-runtime-monitor/` (**G6**) — the *observer*. Watches an in-flight
  run from outside via `.loop/state.json` + `RUNLOG.md`, detects **stall**
  (same `active_task` across N iterations with no measured progress),
  **repair-churn** (repair attempts without score improvement), and
  **budget-overrun**, and surfaces one intervention recommendation
  (replan / revert / approval / terminate). Backed by runnable
  `scripts/runtime_monitor.py`. Read-only over the run — it recommends, never
  mutates.
- `skills/loop-inspector/` (**G7**) — the *quality layer above the ecosystem*.
  Reads an existing loop directory (a `.loop/` contract, a superpowers or ruflo
  harness — read-only, plan-then-execute) and emits a **scored gap report**
  against the prime-directive checklist (defines success? verification? terminal
  states? approval gates? false-completion defense?) plus the 7-state taxonomy.
  Backed by runnable `scripts/inspect_loop.py`.

**Rollout ledger (G8)**
- `scripts/rollout_ledger.py` — an append-only JSONL **rollout ledger**: one
  record per loop candidate with EXACTLY the 7 fields `id`, `parent`, `verdict`,
  `score`, `score_delta`, `coherent_with_prior_winner`, `productive`, plus a
  read/summarize path. The lineage survives compaction; `productive` is the
  per-candidate signal behind repair-productivity. `scripts/test_rollout_ledger.py`
  is the TDD suite (round-trips ≥2 records, asserts all 7 fields).

**Comparative benchmark (G5)**
- `scripts/benchmark_harness.py` — a **comparative benchmark** that computes
  false-completion-rate, repair-productivity, and criteria-met for TWO result
  inputs (reference-harness vs loop-engineer) and the delta between them. Ships
  the measurement tool only — live numbers are the operator's to run, not a baked
  claim. `scripts/test_benchmark_harness.py` asserts the deltas across two
  distinct inputs.
- `reference/eval-suite.md` — adds a documented **Comparative A/B Protocol**
  section pairing the harness with the existing metric definitions.

### Fixed

**Anti-cheat scanner (two false-positive classes pinned as regression tests)**
- `scripts/anticheat_scan.py` — gate-path matching is now **basename /
  word-boundary**, not substring: a test file editing test-mutation is graded
  `test-file-mutation` (medium), never upgraded to critical `gate-tampering` by a
  substring collision with a gate script's path.
- `scripts/anticheat_scan.py` — **self-exclusion**: a diff that introduces or
  modifies the scanner's own file set (`anticheat_scan.py` + its test) is no
  longer graded as gate-tampering against its own correction.
- `scripts/test_anticheat_scan.py` — both fixes pinned as regression tests; the
  pre-existing `gate-tampering-is-critical` failsafe stays green.

**Stricter structural facts**
- `evals/cases/structural.json` — `skill_names` updated 7 → 9 to match real
  on-disk state (the two new spokes); `self_eval.py` now asserts all 9 skills.
- `skills/loop-engineer/SKILL.md` — router decision-map gains
  `[[loop-runtime-monitor]]` and `[[loop-inspector]]` rows.

### Changed
- `.claude-plugin/plugin.json` — version `0.2.0` → `0.3.0`.
- `README.md` / `GLOSSARY.md` — document the two new spokes, the rollout ledger,
  and the comparative benchmark; the *How it compares* positioning is unchanged.

### Notes
- The repo remains private. Flipping it to public MIT is a separate, human-only
  act outside the scope of the run that produced this version.

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
