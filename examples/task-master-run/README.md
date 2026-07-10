# task-master-run — a vendored foreign-harness fixture

A minimal, sanitized project directory in the layout that
[Task Master](https://github.com/eyaltoledano/claude-task-master) leaves behind —
a `.taskmaster/` scaffold holding `config.json`, `state.json`, a parsed PRD under
`docs/`, the `tasks/tasks.json` ledger with its per-task `task_NNN.txt` mirrors,
and an `analyze-complexity` report under `reports/`. It is pinned to commit
`c0c98d367c55296bfe69e65680625b6db437af02`; every field name, path, and heading
follows Task Master's documented conventions, but all prose is fictional and no
template body text is copied. Task Master is licensed MIT with the Commons Clause,
so this fixture mirrors structure and naming only — never verbatim template text.

The run modeled here is a **completed** pass over the shared csv-dedupe task
(the same fiction as `examples/superpowers-run`): `import_contacts.py` emitted
duplicate rows when one contact appeared in two source files with different
casing, and the fix normalizes on a lowercased email/phone key. All three tasks
carry `status: "done"` in `tasks.json`, each with a `testStrategy` field and an
appended `<info added on 2026-07-09T…Z>` journal block recording the verification
evidence (15/15 unit tests, 41 unique contacts from 57 rows, a second import that
inserted 0 rows).

Task Master is a **complement**, not a competitor: it parses a PRD into a task
ledger and drives the daily implement-and-log loop. Loop Engineer is the contract
layer that proves how a run *ended*. This fixture exists so
`python3 -m loop inspect examples/task-master-run` can score that layout read-only.
The honest score is not a criticism of Task Master — it measures what a task-ledger
layout structurally proves about completion. The default `set-status --status=done`
path is an unenforced status write with no test-pass check, and marking a parent
cascades its subtasks to done. Task Master's only code-enforced test gate is the
opt-in autopilot TDD workflow, whose RED/GREEN/COMMIT run-state persists off-tree
in `~/.taskmaster/<project-id>/sessions/` and is therefore intentionally absent
here; the durable in-project proof of "done" is the status fields plus the journal.

## Reproduce

```bash
uv run --with pyyaml python3 -B -m loop inspect examples/task-master-run
```
