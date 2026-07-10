# ST5 — harness scoreboard (plan)

Spec: `../specs/2026-07-09-st5-harness-scoreboard-design.md`. Branch:
`feat/st5-scoreboard`. Clones pinned in the session scratchpad; SHAs recorded
in the spec table.

## Stages

1. **Prep (main loop).** Root-anchor `.gitignore` workbench patterns; create
   the branch.
2. **Per-harness pipeline (workflow, 8×).**
   - *Analyst (opus, read-only):* read the pinned clone; return structured
     layout facts — run-artifact paths, detect signature, success-criteria
     vocabulary, any verification/terminal machinery (with file evidence),
     fixture file plan, caveats.
   - *Builder (opus):* write `examples/<name>-run/` — the shared fictional
     CSV-dedupe task in the harness's documented layout + provenance README.
     Zero verbatim template prose. ≤ 9 files.
3. **Registry (workflow, 1×, barrier).** One engineer rewrites
   `loop/foreign.py` as a layout registry (all 9 layouts; superpowers signal
   tightened), extends `scripts/test_foreign_inspect.py`, runs the suite.
4. **Score (main loop).** `loop inspect` + `loop doctor` on all fixtures;
   capture verbatim JSON.
5. **Adversarial verify (workflow, 8×).** Per row: fixture fidelity vs cloned
   docs; no verbatim prose; notes capture machinery our signals miss; row
   claims accurate. Fix-or-flag.
6. **Post (main loop).** `docs/gap-reports/scoreboard.md` + HN draft in
   `roadmap/launch/`.
7. **Gates + PR.** validate_frontmatter · self_eval · full pytest (≥400 pass,
   no new failures) · fixture inspect determinism. Atomic commits; PR without
   auto-merge (human review gate).

## Global constraints

- Fixtures: content fictional and ours; structure theirs; provenance README
  per fixture; no wikilinks needed (constraint currently scoped to skills/).
- No scoring changes in `scripts/inspect_loop.py`.
- Workflow `agent()` calls carry explicit `model:` (HARD CONTRACT); writes are
  disjoint per harness; `foreign.py`/tests single-writer.
