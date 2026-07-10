# ccpm-run — a vendored foreign-harness fixture

A minimal, sanitized project directory in the layout the
[CCPM](https://github.com/automazeio/ccpm) agent skill (v2) leaves behind —
a PRD under `.claude/prds/`, a technical epic under `.claude/epics/<name>/`,
and the per-issue journal CCPM writes while parallel agents run. It is pinned
to commit `7d7e4623bc6d4c0c9ba66ca6bfecd7e5261dc697`; every field name, path,
and heading follows CCPM's documented conventions, but all prose is fictional
and no template body text is copied.

To stay small, the tree materializes one representative issue (#1235) in full —
its task file, parallel-stream analysis, and `updates/1235/` progress and
stream journals — while the two sibling tasks (#1236, #1237) appear only at the
epic roll-up level, in `epic.md`'s Tasks-Created list, `github-mapping.md`, and
`execution-status.md`. A real run would carry a `1236.md` and `1237.md` beside
`1235.md`. The epic is also left at the live `.claude/epics/csv-dedupe/` path
rather than moved to `.claude/epics/archived/`, which is where CCPM's merge step
relocates an epic once its archival is run.

The run modeled here is a **completed** pass over the shared csv-dedupe task
(the same fiction as `examples/superpowers-run`): `import_contacts.py` emitted
duplicate rows when one contact appeared in two source files with different
casing, and the fix normalizes on a lowercased email/phone key. Only the
project-management and traceability metadata lives here — the actual code
deliverable was built in a sibling git worktree, merged to `main`, and its
worktree removed, so no application source is part of this tree. CCPM treats
GitHub Issues as its source of truth, so the closing comments and issue-state
audit trail live off-disk; `github-mapping.md` is the sole on-disk link back to
them.

CCPM is a **complement**, not a competitor: it organizes long-running feature
work into epics, tasks, and parallel agent streams. Loop Engineer is the
contract layer that proves how a run *ended*. This fixture exists so
`python3 -m loop inspect examples/ccpm-run` can score that layout read-only.
The honest score is not a criticism of CCPM — it measures what an epic/task
metadata layout structurally proves about completion. CCPM ships a structural
metadata validator (`validate.sh`) and a self-attested Definition-of-Done
checklist, but no held-out evidence gate and no persisted test result, so the
on-disk proof of "done" is ticked checkboxes and a progress note.

## Reproduce

```bash
uv run --with pyyaml python3 -B -m loop inspect examples/ccpm-run
```
