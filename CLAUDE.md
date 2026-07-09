# CLAUDE.md — loop-engineer

Read this first. It replaces the "continue where we left off" cold-start that has been
booting this repo for 9+ days. Nested git repo (`SollanSystems/loop-engineer`, MIT) —
do NOT commit CLAUDE.md or treat it as plugin content.

## What this is

A Claude-Code plugin that designs, launches, verifies, repairs, and improves **agent
loops**. It is an **architect + operator**, not a task-doer: it stands up the operating
contract for a long-running agentic-coding run, gates it against false completion, and
mines its own history for compounding improvement.

Two shipping surfaces from one repo:
- **Plugin** — hub-and-spoke skill suite (router + 8 spokes) invoked inside Claude Code.
- **Portable Loop Contract Core** — a pure-stdlib Python package `loop` + CLI
  (`loop` / `loop-engineer`, also `uvx loop-engineer`) that validates and inspects
  repo-native operating contracts on any stack. `pip install -e .` pulls **zero** runtime
  deps; two optional extras enrich validation: `yaml` (PyYAML) and `schemas` (jsonschema).

## Skill architecture (9 skills = router + 8 spokes)

| Skill | Role |
|---|---|
| `loop-engineer` | Router — dispatches broad agent-loop intent to the right spoke. |
| `loop-architect` | The brain — classify the task, choose architecture + Claude-Code realization, emit a structured ADR (architecture, loop patterns, risk profile, terminal-state plan, next spokes). |
| `loop-contract` | Scaffold the repo-OS contract (SPEC / WORKFLOW / TASKS.json / RUNLOG / `.loop/state.json` + `verify-*` skeletons) from an ADR, then run the pre-execution reflection. |
| `loop-run` | The operator — run/resume the state machine one bounded transition at a time; every run ends in exactly one of the 7 terminal states. |
| `loop-repair` | Patch-and-repair loop — classify the failure mode, make the smallest bounded repair, write a 7-field repair record, enforce a max-attempt cap; refuses to widen scope or edit tests to fake a pass. |
| `loop-evals` | Design the eval harness — the 7-layer suite, FCR + repair-productivity as first-class metrics, deterministic-first-then-rubric, judge calibration. Delegates the deterministic gate to the contract's own `verify-*` scripts. |
| `loop-flywheel` | Turn run history (RUNLOG / traces / receipts) into new eval cases; drive baseline→harden→regression→freeze; compact memory. |
| `loop-inspector` | Read-only score of a **foreign** loop against the prime-directive checklist + 7 terminal states → a scored gap report (advisory heuristic, not a gate). |
| `loop-runtime-monitor` | Watch a running loop from outside — detect stall / repair-churn / budget-overrun and surface one intervention. |

## Version + state

- **Current release: v0.7.0** (`.claude-plugin/plugin.json` + `pyproject.toml`), main at `4647820`.
- **Active branch: `feat/v0.8.0-composes-the-field`** (v0.8.0 NOT yet released — release cut
  is the last commit of PR-B). Working tree has in-progress Temporal recipe files (Task 3).
- **Shipped through v0.7.0:**
  - ST2 "Portable standard" — `reference/repo-os-contract.md` promoted to the normative,
    versioned, tool-agnostic spec (PR #31).
  - External-review credibility patch set **PRs #27–#30** (10 findings): empty-evidence
    terminal now fails doctor; terminal write-once + atomic writes; strict UTF-8 + declared
    ledger discovery; strict-by-install on the Action + pre-commit hook; verify-script
    existence checks; **inspector honesty** (#30) — keyword-stuffed fakes no longer score
    100/strong, `loop inspect` documented as advisory while `loop doctor` is the hard gate.
  - Adoption slices (PRs #19–#23): PyPI wheel substrate, `loop/emit.py` writer API +
    LangGraph recipe, `hooks/stop_firewall.py` Stop-hook false-completion firewall,
    composite `action.yml` + `.pre-commit-hooks.yaml`.
- **v0.8.0 "composes-the-field" (in progress):** ST3 integration adapters
  (`loop/integrations.py` EngineOutcome→terminal projection, LangGraph recipe upgraded to
  gate+adapter+metrics-clean, Temporal recipe) + ST4 contributor funnel (foreign-harness
  inspect adapter `loop/foreign.py`, gap report, `flaky-test-triage` example, contributor
  issue drafts + CONTRIBUTING). Resume ledger: `.superpowers/sdd/` (progress.md + briefs).
- **Test baseline: 395 tests** collected on the v0.8.0 branch (372/10 at v0.7.0; ~10 skip
  in structural-fallback mode without jsonschema).
- **Dogfood:** the suite has been run on its own v1.0 launch (self-hosted contract at
  `roadmap/launch/`) and on `examples/coverage-repair` (doctor-clean, inspect 90/strong).

## Load-bearing invariants (enforced by `scripts/self_eval.py` vs `evals/cases/structural.json`)

- **7 canonical terminal states:** `Succeeded`, `FailedUnverifiable`, `FailedBlocked`,
  `FailedBudget`, `FailedSafety`, `FailedSpecGap`, `AbortedByHuman`.
- **7-field repair record:** `failure_mode`, `hypothesis`, `repair_action`,
  `verification_before`, `verification_after`, `remaining_delta`, `productive`.
- **7-layer eval suite:** deterministic-correctness, artifact-quality, human-calibration,
  loop-behavior, security/governance, regression-resistance, cost/efficiency.
- **2 first-class metrics:** `false-completion-rate` (FCR), `repair-productivity` (RP).
- Also pinned: 6-item `failure_mode_taxonomy`, `repair_cap_default` 2, `rubric_target_mean`
  9.5 (advisory), 9 skill names, 8 reference filenames, 14 template filenames, MIT license.
- **When the suite changes** (new skill/template/reference/terminal state), update
  `evals/cases/structural.json` — the self-eval checks compare live repo state against it.

## Verify commands (run from the repo root; this env has no system pytest — use `uv run`)

```bash
uv run --with pyyaml python3 -B scripts/validate_frontmatter.py            # 9 SKILL.md frontmatter blocks
uv run --with pyyaml python3 -B scripts/self_eval.py                       # structural invariants (self-locates root)
uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts   # full suite
```

CLI subcommands (`python3 -m loop <cmd>` — commands: `scaffold doctor validate verify
inspect metrics`): `loop doctor` is the **hard gate**, `loop inspect .` is the **advisory
scorecard**. CI (`.github/workflows/ci.yml`) installs `pyyaml pytest jsonschema` and runs
`python -B -m pytest -q -p no:cacheprovider scripts`; without jsonschema the core falls back
to structural hand-checks (a deliberate design, not a bug).

## Install / refresh

Installed **user-scope** from the local marketplace `loop-engineer-local`. The plugin-cache
copy is a **static COPY** (nested under `cache/<mkt>/loop-engineer/<ver>/`), NOT a symlink —
it goes **stale after any post-install commit**. Refresh with:

```bash
git -C /mnt/c/Dev/projects/loop-engineer archive HEAD | tar -x -C <cache-dir>
diff -rq /mnt/c/Dev/projects/loop-engineer <cache-dir>   # verify
```

Then **restart Claude Code** to reload the skills.

## Roadmap / open work

- **Human gates (blocking PyPI):** register the PyPI pending trusted publisher
  (project `loop-engineer`, owner `SollanSystems`, workflow `publish.yml`, environment
  `pypi`), then `git tag v0.7.0 4647820 && git push origin v0.7.0`; verify the funnel
  `uvx loop-engineer@0.7.0 inspect .` from a scratch dir.
- **Finish v0.8.0:** Temporal recipe (Task 3) → ship PR-A → PR-B (foreign adapter, gap
  report, flaky example, contributor funnel, 0.8.0 release cut) → file the 6 contributor
  issues at merge.
- **Then:** "inspect N public harnesses" scoreboard post; Show HN launch (human-gated).
- **Positioning (verified):** never claim to coin "loop engineering" — cobusgreyling's
  `loop-engineering` (~4.6k stars) owns the term. Own **"false completion"** /
  **"proof-of-done contract"** instead.

## Repo conventions

- Specs → `docs/superpowers/specs/` (dated); plans → `docs/superpowers/plans/` (dated).
- Session narratives → `memory/session-summaries/YYYY-MM-DD-*.md` (memory/ is gitignored).
- **Gitignored workbench/telemetry** (not plugin content): `.loop/`, `review/`, `roadmap/`,
  `.claude/`, `.gsd/`, `memory/`, `.tmp/`. CI runs on a fresh checkout where these are
  absent — never point a CI/dogfood job at the live gitignored `.loop/`; target a tracked
  `examples/*` contract instead.
- Env quirks: the Bash deny-list blocks `rm`, bare `cd`, `VAR=` assignments, `timeout`,
  `printf`, `source` — use `git -C <path>`, literal absolute paths, and `bash -c`.
