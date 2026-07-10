# bmad-run — a vendored foreign-harness fixture

A minimal, sanitized run directory in the layout that
[BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) V6 (the BMM module)
leaves behind after `npx bmad-method install`: a `_bmad/` install tree plus the
twin `_bmad-output/planning-artifacts/` and `_bmad-output/implementation-artifacts/`
output folders. Layout follows
`bmad-code-org/BMAD-METHOD@49069b8b5276afd21402bc3b978b69ad78a7d2ef`. BMAD is not
MIT-licensed, so only directory structure, YAML key names, and section headings
follow its documented conventions — **every sentence of prose here is original and
fictional, and no template body text was copied**.

The run modeled here is a **completed** pass over the shared csv-dedupe task (the
same fiction as `examples/superpowers-run`): `import_contacts.py` emitted duplicate
rows when one contact appeared in two source files with different casing, and the
fix normalizes on a lowercased `(email, phone)` key, keeps the first-seen row, and
logs each dropped duplicate. The fixture walks the flagship sprint-story flow —
`create-story` distills the PRD and epics into one story file, `dev-story`
implements it red-green-refactor, `code-review` gates it in fresh context, and a
`retrospective` closes the epic — so every artifact class appears once.

BMAD is a **complement**, not a competitor: it is a full-lifecycle agile method
that shapes *how* an agent plans, builds, and reviews a story. Loop Engineer is the
contract layer that proves *how the run ended*. The honest score here is not a
criticism — it measures what a story-file-plus-status-ledger layout structurally
proves about completion. BMAD's done-gate is genuinely strong in intent: a
"NO LYING OR CHEATING" rule, an Enhanced Definition of Done checklist, and an
adversarial `code-review` pass that only flips `Status: done` when no unresolved
high or medium findings remain. But those are natural-language instructions an
agent is asked to follow, and "done" is ultimately a `Status:` string mirrored
across the story file and `sprint-status.yaml`. There is no held-out machine gate,
no typed terminal record, and no persisted evidence bundle — which is exactly what
emitting the contract adds.

## Reproduce

```bash
uv run --with pyyaml python3 -B -m loop inspect examples/bmad-run
```
