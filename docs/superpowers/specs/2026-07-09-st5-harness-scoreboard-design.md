# ST5 — "Inspect N public harnesses" scoreboard (design)

**Date:** 2026-07-09 · **Slice:** ST5 (follows ST4's contributor funnel; the
Superpowers gap report declared itself "the first entry in an 'inspect N public
harnesses' scoreboard" — this slice builds the scoreboard.)

## Problem

`docs/gap-reports/superpowers.md` proved the pattern: read a foreign harness
layout read-only, score what it *structurally cannot prove*, keep every claim
checkable against a vendored fixture. One row is a seed, not a scoreboard. The
launch plan (Show HN, human-gated) needs the N-harness post.

Scoring foreign repos **without layout mappers would be dishonest**: the
inspector reads contract-owned files (SPEC/WORKFLOW/TASKS/verify-*/RUNLOG), so
a harness whose run leaves `specs/001-x/spec.md` on disk would score near-zero
simply because our tool didn't read its files — a parsing artifact presented
as a finding. `loop/foreign.py`'s own docstring states the principle: **a
mapper, never a scorer.**

## The 8 new harnesses (pinned 2026-07-09)

| Harness | Repo | Stars | Pinned SHA |
|---|---|---|---|
| Spec Kit | github/spec-kit | 119k | `3f7392a` |
| Agent OS | buildermethods/agent-os | 5.0k | `cae8e66` |
| BMAD-METHOD | bmad-code-org/BMAD-METHOD | 50k | `49069b8` |
| Task Master | eyaltoledano/claude-task-master | 28k | `c0c98d3` |
| CCPM | automazeio/ccpm | 8.3k | `7d7e462` |
| PRPs | Wirasm/PRPs-agentic-eng | 2.2k | `ada2f5b` |
| OpenSpec | Fission-AI/OpenSpec | 60k | `93e27a7` |
| ruflo (né claude-flow) | ruvnet/ruflo | 64k | `7ef4d4e` |

Plus the existing Superpowers row (fixture, score 12) and calibration rows
from this repo's own examples (`naive-loop` 0, `flaky-test-triage` 90).

**Selection criteria:** public, active, substantial adoption, and the harness
prescribes an on-disk layout for a run (specs/plans/tasks/state). Platforms
whose run state lives off-repo (OpenHands, SWE-agent trajectories) are a
methodology note, not scored rows.

## Deliverables

1. **`examples/<name>-run/` × 8** — vendored fixtures, each instantiating the
   harness's *documented* run layout for the **same fictional CSV-dedupe task**
   as `superpowers-run` (comparability: one task, nine layouts). Each fixture
   carries a README with provenance (layout per `<repo>@<sha>`; all content
   fictional). **Zero verbatim template prose** — BMAD / Task Master / PRPs are
   not MIT-licensed; structure and headings follow their docs, every sentence
   is ours.
2. **`loop/foreign.py` → layout registry** — data-driven table of foreign
   layouts (signature paths → LoopPaths mapping), superpowers + 8 new. Native
   `.loop/state.json` always wins; detection precedence is deterministic;
   `doctor` stays unmapped. **Scoring stays layout-blind** — the registry only
   points existing signals at foreign files; no scoring changes in this slice.
   Includes the roadmap follow-up: tighten the superpowers signature so this
   repo's own root (specs/plans but no journal) no longer false-positives.
3. **Tests** — per-fixture detect + advisory + deterministic-score tests in
   `scripts/test_foreign_inspect.py`; a repo-root-negative regression.
4. **`docs/gap-reports/scoreboard.md`** — the scoreboard post: table (stars,
   SHA, target, score, verdict, terminal coverage), methodology, fairness
   rules, per-harness sections with verbatim inspect JSON + a **notes** field
   for verification machinery the harness has that our conservative signals
   don't credit.
5. **`.gitignore` root-anchoring** — `.loop/`→`/.loop/` etc., so fixture
   dot-dirs (`.claude/epics/`, `.taskmaster/`) are trackable; resolves the
   `!examples/*/.loop/**` follow-up.
6. **HN post draft** → `roadmap/launch/` (gitignored; publication human-gated).

## Fairness invariants (the post lives or dies on these)

- **Advisory, always.** Every foreign row carries `advisory: true`. The score
  measures *proof-of-done machinery visible on disk*, never project quality.
- **Composes, doesn't compete.** Same framing as the Superpowers report: each
  harness drives *how the agent works*; the contract proves *how the work
  ended*. Any harness can emit the contract at its finish line.
- **Version-specific claims only.** Every row is pinned to a SHA and a vendored
  fixture; reproduce = `python3 -m loop inspect examples/<name>-run`.
- **Conservative signals must not read as absences.** Where a harness defines
  success under a different heading, or has verification machinery our gate
  tokens can't see, the row's notes say so explicitly. Verifier agents hunt
  for exactly this failure mode before any row ships.
- **Fixtures are faithful.** A fixture must not omit an artifact a real run of
  that harness would leave (especially verification artifacts), and must not
  add anything the harness doesn't prescribe.

## Non-goals

- No scoring/weight changes to `inspect_loop.py`.
- No claims about harness quality, community, or roadmap.
- No mapper for off-disk-state platforms (methodology note instead).
- Publication (HN/blog) is out of scope — human gate.

## Risks

- **Reputational:** naming popular projects with "weak" verdicts. Mitigation:
  fairness invariants above + per-row adversarial verification + the same
  respectful framing that shipped for Superpowers.
- **Fixture infidelity:** a wrong fixture poisons a row. Mitigation: analyst →
  builder → independent adversarial verifier per harness, all reading the
  pinned clone.
- **Registry false positives:** generic signatures (`docs/prd.md`) colliding.
  Mitigation: require distinctive multi-path signatures; explicit precedence;
  negative tests.
