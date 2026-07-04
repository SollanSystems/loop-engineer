# Changelog

All notable changes to `loop-engineer` are documented here.

---

## Errata

- **2026-06-30 — receipts claim corrected (M1 credibility slice).** The 0.3.4
  *Documentation* note below overstated `examples/coverage-repair`: it implied the
  frozen example ships a receipts trail. In reality a live run appends receipts to
  `.loop/receipts/*.jsonl`, but this example ships the contract artifacts only —
  `find examples/coverage-repair -iname '*receipt*'` returns nothing. The example's
  `WORKFLOW.md` and `README.md` are reworded to describe the mechanism; the 0.3.4
  history is left intact.

## Unreleased

**B1 — the writer API.** `loop.emit` lets a foreign runtime (LangGraph, a plain
script, any orchestrator) record an evidence-backed loop contract without
adopting the loop-engineer runtime. It is a writer, never a runtime: it renders
the contract artifacts and refuses a dishonest `Succeeded` at write time — the
same evidence cross-check `loop doctor` enforces, applied before the file exists.

### Added
- **`loop/emit.py` writer API** — `open_contract`, `append_iteration`,
  `append_receipt`, and `terminate`, plus the `EmitError` raised when a write
  would produce a dishonest or schema-invalid artifact. `terminate` refuses an
  evidence-free `Succeeded` (also no-met-criterion or false-completion-flagged),
  so the honesty gate runs at write time rather than only at validate time;
  every artifact it writes passes `doctor` by construction.
- **LangGraph recipe** (`examples/langgraph-emit/`) — a runnable three-node
  graph whose terminal node ships proof-of-done through `loop.emit`; the emitted
  contract passes `loop doctor` independently of the graph that wrote it. Paired
  with the 10-line integration guide `docs/integrations/langgraph.md`.
- **Recipe acceptance test** (`scripts/test_langgraph_recipe.py`) — runs the
  example end-to-end and asserts the emitted contract passes `doctor` and ends
  `Succeeded` with evidence. Env-guarded on `langgraph` (skips when absent), so
  the package stays zero-dependency; a dedicated `recipe (langgraph)` CI job
  installs LangGraph and runs it.

**A1 — the Stop-hook firewall.** The false-completion wedge, enforced at the
session boundary instead of only on demand. When a `.loop/` contract claims
`Succeeded` while `loop doctor` still reports `ok:false`, the Stop hook blocks the
turn from ending and hands the agent the named doctor issues, so a run cannot exit
on a false "done". It is fail-open by construction — a broken or unresolvable
firewall never locks a session — and a strict no-op for every repo without a
`.loop/` contract.

### Added
- **`hooks/stop_firewall.py`** — a stdlib-only Stop hook that blocks a
  `Succeeded`-claiming contract whose `loop doctor` report is `ok:false`, carrying
  the issues into the block reason. Fails open on any error (malformed stdin,
  unresolvable `loop` CLI, doctor failure), stays silent when no `.loop/` exists,
  respects `stop_hook_active` to avoid livelock, and blocks at most once per
  session per issue-set (a tempdir sentinel keyed on the issue digest). Covered by
  `scripts/test_stop_firewall.py` (subprocess acceptance tests for the honest,
  lying, in-flight, absent, once-per-session, and fail-open paths).
- **Plugin-manifest registration** — the hook is wired into
  `.claude-plugin/plugin.json` under the top-level `hooks.Stop` key
  (`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/stop_firewall.py`), so a marketplace
  install gets the firewall with zero configuration.

## 0.6.1 — 2026-07-04

**PyPI substrate.** `loop-engineer` becomes a self-contained wheel that runs from
any directory — the CLI no longer depends on being executed from a source
checkout — and ships to PyPI on a version tag through trusted publishing, with no
token or secret stored in the repo.

### Added
- **Self-contained wheel** — the schemas, contract templates, and CLI-needed tool
  scripts the loop reads at runtime are bundled into the wheel under
  `loop/_bundle/` (via `[tool.hatch.build.targets.wheel.force-include]`) and
  resolved through an `importlib.resources`-first resolver (`loop/_resources.py`)
  that falls back to the repo-relative layout for editable installs / source
  checkouts. `loop` invocations no longer break when run outside the repo tree.
- **`loop-engineer` console script** — a second `[project.scripts]` entry point
  alongside `loop` (both map to `loop.__main__:main`), so `uvx loop-engineer`
  funnels straight to the CLI under the PyPI project name.
- **Wheel self-containment acceptance test**
  (`scripts/test_wheel_selfcontained.py`) — builds the wheel and asserts its zip
  manifest carries the bundled `schemas/`, `templates/`, and `tools/` resources,
  so a regression that drops a runtime resource from the wheel fails the suite
  (env-guarded: skips when `pip`/`build` are unavailable locally, hard-fails the
  build under CI).
- **Tag-triggered PyPI publish workflow** (`.github/workflows/publish.yml`) — on a
  `v*` tag push it guards that the tag matches the `pyproject` version, builds the
  sdist + wheel, smoke-tests the wheel from a throwaway venv (`loop-engineer
  --version`, then `loop scaffold`/`doctor`/`inspect`), and publishes via PyPI
  **trusted publishing** (`id-token: write`, the `pypi` environment,
  `pypa/gh-action-pypi-publish`) — no API token or secret anywhere in the repo.

## 0.6.0 — 2026-07-03

"Metrics real": false-completion-rate (FCR) and repair-productivity (RP) graduate
from claims to derivations (the ST1 spec), and the derivation itself survived two
rounds of adversarial red-teaming before merge — every exploit found is now a
pinned regression test. (PR #16.)

### Added
- **`loop metrics <loop-dir>`** — derives FCR and RP from a loop's real on-disk
  evidence (RUNLOG, verify bundles, held-out verdict, repair records, receipts),
  never from agent narration. FCR is computed two ways — the deterministic
  claim×verify cross-join and the aggregated held-out `false_completion` flag —
  and disagreement is surfaced, not resolved. An unmatched success claim counts
  as a false completion (fail-closed). Output is a `loop-engineer/metrics@1`
  scorecard whose `provenance` block names every input file, so a skeptic can
  re-derive each number by hand.
- **`loop metrics --baseline`** — writes `docs/metrics-baseline.json` and
  **refuses** (non-zero exit, writes nothing) unless the run is genuinely
  gate-backed: a structurally valid held-out verdict artifact must exist (a gate
  line in a verify script never qualifies); no rejected or unanchored repair
  record; the two FCR methods must agree; a vacuous zero-claim run cannot
  baseline.
- **Published baseline** over the gate-backed `examples/coverage-repair`:
  **FCR 0.0, RP 1.0** — the README numbers cite the committed file (a test binds
  the README literals to the JSON), reproducible with
  `python3 -m loop metrics examples/coverage-repair`.
- **Canonical record schemas** — `schemas/repair-record.schema.json`
  (`loop-engineer/repair@1`, RP's only input) and
  `schemas/rollout-record.schema.json` (`loop-engineer/rollout@1`, the separate
  candidate-adjudication artifact). Ends the two-shapes-both-called-"the repair
  record" ambiguity; `validate_contract` checks record files when present and
  `doctor` reports which record schemas it validated.
- **`loop` console script** (`[project.scripts]`) — the CLI runs from any
  directory under the supported editable install.

### Changed
- **`productive` is recomputed, never trusted.** `recheck_productive` recomputes
  it from each record's own evidence and rejects disagreements;
  `rollout_ledger.summarize()` (whose productivity key is now honestly named
  `rollout_productivity`) and the metrics command aggregate only validated
  records. Repair records additionally **anchor** to the deterministic verify
  bundles: `verification_before/after` scores must match a same-task red→green
  bundle pair (order-enforced when known), or the record is rejected/unanchored.
- **Claim semantics are outcome-class aware.** A completion-class claim
  (`task_passed`/`succeeded`/`terminal`) is clean only if every verify bundle in
  its iteration is green — no exceptions; a progress-class claim (`advanced`)
  may carry a red intermediate only if the same task reaches green in a strictly
  later iteration. Unrecognized outcome tokens are surfaced in provenance
  instead of silently escaping the denominator.

### Honesty hardening (adversarial pre-merge review)
Two red-team rounds (four, then two, adversarial reviewers) attacked the metrics
implementation before merge and confirmed 17 issues — including a `--baseline`
that would have published a clean headline FCR over a run its own held-out gate
had flagged, and an `evidence_backed` satisfiable by a prose mention of the
gate. All are fixed and pinned as regression tests; the honest residual is
documented in the README: a committed verdict artifact is *evidence, not proof* —
tamper detection belongs to the anti-cheat layer.

## 0.5.0 — 2026-07-03

The two pre-launch milestones of the v1.0 roadmap landed together: **"enforce the
wedge"** (false-completion defense is now enforced by validators, not asserted by
docs) and **"first screen"** (the README/demo surface rebuilt for a stranger's
first 30 seconds). PRs #7–#13. The version jumps 0.3.4 → 0.5.0 to match the
roadmap's milestone numbering (`docs/superpowers/plans/2026-06-30-loop-engineer-v1.0-roadmap.md`);
there is no 0.4.x tag.

### Added
- **Gate-backed flagship example.** `examples/coverage-repair` now runs
  end-to-end through the real held-out gate; its `false_completion: false` is
  backed by a committed gate verdict (`.loop/artifacts/holdout-verdict.json`),
  not a hand-set flag (#9).
- **Weak→strong demo, filmed live.** `docs/demo.gif` + `docs/demo.cast`: the
  inspector scores a self-asserted DIY loop (committed as `examples/naive-loop`)
  0/weak, then the gate-backed example 90/strong — 100% live tool output.
  Social card at `docs/social-card.png` (#13).
- **`loop scaffold`** command + JSON Schemas for the contract artifacts
  (`schemas/*.schema.json`), with templates reconciled to what the validator
  actually checks (#8).
- **Promised templates shipped:** `templates/verify-safety.sh`,
  `templates/extract-trace-metrics.sh`, `templates/judge-rubric.sh`; central
  model-routing doctrine at `reference/model-routing.md` (#11).
- **v1.0 master roadmap + four strategic specs** committed under
  `docs/superpowers/` — credibility enforcement, ST1 metrics baseline, ST2
  portable contract spec, ST3 integration adapters (this release).

### Changed
- **Validator cross-checks.** A `Succeeded` terminal no longer validates with
  `false_completion: true` or an empty/false `criteria_met`; the inspector
  grades false-completion defense on *invocation evidence* (the gate/scan
  actually ran), never on a self-asserted flag (#8).
- **Held-out gate + scanner hardening.** An empty visible set can no longer
  certify (`test_empty_visible_set_returns_not_ready`); the anti-cheat scanner
  detects edits that neuter its own gate-decision functions
  (`test_self_neuter_of_gate_matcher_is_detected`) and reports gate tampering
  with a distinct exit code (#8).
- **README first screen** rebuilt for launch conversion: tagline, concrete
  failure modes, zero-install first command, stack diagram, comparison table,
  demo embed (#7, #12).
- **Skill trigger surface:** diagnostic spokes (loop-inspector,
  loop-runtime-monitor) named at the router and marketplace, trigger-phrase
  batch, path anchoring and neutral framing across all 9 skills (#11).

### Fixed
- **CLI:** `--help`/`--version`/usage text, distinct operational-error messages,
  explicit exit codes, ledger tolerance for foreign receipt lines (#10).
- **The repo's own live contract passes its own gate:** `python3 -m loop doctor
  .loop` → `ok: true` — the release-blocking exit criterion of the
  wedge-enforcement milestone (#8).

## 0.3.4 — 2026-06-29

Dogfood-driven hardening: ran `loop-inspector` + `loop-runtime-monitor` against 9 real
on-disk loops (foreign and in-house). The tools had been built and tested only against
this suite's own well-formed loops, so first contact with foreign/edge-case inputs exposed
six defects — all fixed here under TDD, each pinned by a regression test.

### Fixed
- **(P1) `inspect_loop` no longer crashes on a malformed `manifest.yaml`.** `read_manifest`
  (`loop/contract.py`) ran `yaml.safe_load` without a guard — the one read path missing the
  `json.JSONDecodeError` guard every JSON read already had — so a malformed manifest in an
  untrusted/foreign loop dir killed the inspector with a traceback instead of returning a
  report. It now fails safe to `{}`, fixing the crash for `inspect_loop`, `validate_contract`,
  and `doctor_report` at once.
- **`inspect_loop` now scores `SPEC.md` / `WORKFLOW.md` / `TASKS.json` dual-location** (`.loop/`
  ∪ workspace root), like `manifest`/`state` already resolved. Previously SPEC/WORKFLOW were
  hard-coded to the workspace root, so a loop whose contract lives under `.loop/` (including
  loop-engineer's own repo) was falsely scored as having "no success criteria" / "no
  independent verification." Scores on substance, not on where the file sits.
- **`inspect_loop` recognizes a single-file `loop-contract.md`** as a contract-owned source
  for success criteria, approval gates, plan-then-execute, and terminal-state coverage — a
  committed minimal-contract loop that names all 7 terminal states is no longer scored 0/7.
- **`runtime_monitor` is terminal-state-aware.** It now reads `terminal_state` / `state ==
  "terminal"` and reports `recommendation: "done"` (surfacing the terminal state) instead of
  advising `continue` on a loop that has already finished.
- **`runtime_monitor` no longer reports an unparseable RUNLOG as healthy.** A non-empty
  RUNLOG that yields zero parseable iteration records now returns `status: "degraded"` /
  `recommendation: "replan"` (with evidence) instead of the benign `ok`/`continue`/`[]` that
  was byte-identical to a healthy loop — making the silent inertness of stall/repair-churn
  detection on prose RUNLOGs visible.

### Changed
- Removed the unreferenced broad-substring corpus scoring path from `scripts/inspect_loop.py`
  (`_gather_corpus`, `_walk_bounded`, `_evaluate_checks`, `_terminal_states_covered`) — dead
  code since the keyword-stuffing fix replaced it with the typed-contract path. Corrected
  `loop-inspector/SKILL.md` and `reference/patterns.md` §4 to describe the actual named,
  typed, dual-located contract file set the inspector reads, rather than a "reads any foreign
  harness shape semantically" claim the implementation never honored.

### Added
- **`pyproject.toml`** — the portable core is now installable with `pip install -e .`
  (optional `pip install -e ".[yaml]"` for faster manifest parsing), so
  `python3 -m loop doctor|inspect <workspace>` runs from any directory rather than only the
  repo root. The core stays pure-stdlib; PyYAML remains an optional extra. A new
  `test_docs_version` check pins the `pyproject.toml` version to `.claude-plugin/plugin.json`.

### Documentation
- README: the *Portable validator / inspector* section documents the editable install for
  running outside the repo root; the 30-second `inspect` demo now shows the full
  `target` / `present` / `gaps` report; the `doctor` block notes the omitted `paths` object;
  `validate` / `verify` are documented as `doctor` aliases; `terminal_state.json` is noted as
  resolving in either `.loop/` or the workspace root.
- `examples/coverage-repair` records receipts at the canonical `.loop/receipts/*.jsonl` (was the
  stale pre-decoupling `.gsd/audit/receipts/` path, inconsistent with the example's own `.loop/`
  layout).
- `loop-runtime-monitor/SKILL.md` frames its position generically ("vs a loop-driving operator")
  instead of naming a private plugin agent.

## 0.3.3 — 2026-06-29

### Changed
- Citation accuracy: corrected three over-reaching attributions to real sources
  (no citations removed, no IDs changed). The "A/B trigger policy / cost-benefit
  knob" and "cuts wasted edits" are reframed as this suite's own design choices
  rather than PreFlect (arXiv 2602.07187) findings — PreFlect reflects on every
  plan unconditionally and reports no edit-efficiency metric. The "repo-native
  run-ledger over a vendor eval UI" is attributed to this suite as its answer to
  the open challenge posed by Code as Agent Harness (arXiv 2605.18747), not as
  that paper's claim.

### Fixed
- Standalone scripts now resolve the `loop` package when run by path. The
  documented invocations `python3 scripts/runtime_monitor.py <loop>` and
  `python3 scripts/inspect_loop.py <loop>` put `scripts/` on `sys.path` (not the
  repo root), so the sibling `loop` package was unimportable and the scripts
  silently used their degraded fallbacks — `runtime_monitor` reported
  `missing RUNLOG.md` on the canonical `.loop/RUNLOG.md` layout, and
  `inspect_loop` could not read `plan_then_execute` from `.loop/manifest.yaml`.
  Both scripts now self-bootstrap the repo root onto `sys.path` before importing
  `loop.*`, matching `python -m loop` behaviour. The bug was invisible to CI
  because `python -m pytest` already places the repo root on `sys.path`; added
  by-path subprocess regression tests that reproduce the real standalone call.

## 0.3.2 — 2026-06-28

Loop Contract Core plus a public open-source readiness pass: every skill now runs
on the bundled portable core with no private tooling, and the repo ships CI and
standard community files.

### Added
- **Loop Contract Core.** The portable `loop/` package with
  `python3 -m loop doctor|validate|verify|inspect`, shared workspace/`.loop`
  path resolution, and JSON schemas for `manifest@1`, `state@1`, `tasks@1`, and
  `terminal@1`.
- **Generic receipt schema** (`schemas/receipt.schema.json`, `receipt@1`) — an
  engine-neutral dispatch/cost record at `.loop/receipts/*.jsonl` so the flywheel,
  evals, and runtime-monitor compute routing + cost metrics without any private
  telemetry.
- **`byo-default` structural check** (the 13th self-eval check) — fails if any
  skill depends on an unbundled tool without also naming the bundled default path.
- **Continuous integration** (`.github/workflows/ci.yml`) — runs the frontmatter,
  self-eval, pytest, compile, JSON-validity, and quickstart-smoke gates on Python
  3.10 / 3.11 / 3.12.
- **Community files** — CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, and issue/PR
  templates.
- **Discoverability metadata** in `plugin.json` (homepage, repository, keywords).

### Changed
- **Bring-your-own-verifier decoupling.** Skills and reference docs now default to
  the bundled gate (`scripts/verify-fast` → `verify-full`, `python3 -m loop verify`)
  and `.loop/receipts/*.jsonl`. `/verify-slice`, `/verify-milestone`, `.gsd/`
  receipts, `model_routing.py` / `workflow_routing.py`, Harmony, and Hermes are now
  documented as optional integrations / example realizations, never requirements.
- **Install** is now `claude plugin marketplace add SollanSystems/loop-engineer`;
  the marketplace is renamed from `loop-engineer-local` to `loop-engineer`.
- `.claude-plugin/plugin.json` version `0.3.1` → `0.3.2`.

### Fixed
- `scripts/inspect_loop.py` now scores contract-owned artifacts instead of broad
  README/prose keyword matches; `plan_then_execute: false` no longer receives
  credit by substring.
- `scripts/runtime_monitor.py` now resolves canonical root `RUNLOG.md`, returns
  structured reports for partial loop state, and avoids cross-task repair-churn
  false positives.
- `scripts/benchmark_harness.py` rejects duplicate task ids before computing A/B
  metrics.
- `scripts/anticheat_scan.py` flags semantic self-weakening of safety ranking or
  downgrade mapping as `FailedSafety`.

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
