# agent-os-run — a vendored foreign-harness fixture

A minimal, sanitized run directory in the layout that
[Agent OS](https://github.com/buildermethods/agent-os) v3.0 leaves behind
(layout per `buildermethods/agent-os@cae8e664fb59a01869718c3151e0f45b7a06a2fb`,
MIT). All content is fictional and every sentence is original — none of the
harness's own template text is copied. It exists so `python3 -m loop inspect
examples/agent-os-run` can score this layout read-only, holding the *same*
fictional csv-dedupe task the other fixtures use, dated 2026-07-09.

## The shared task

Identical scenario to [`examples/superpowers-run`](../superpowers-run/): dedupe
`import_contacts.py` so the two sample files collapse from 57 rows to 41 unique
contacts, a second import inserts 0 new rows, and dropped duplicates are logged
with their source line numbers. The scoreboard compares one task across nine
harness layouts, so the story here matches — only the on-disk shape differs.

## What a completed run looks like on disk (the differentiating finding)

Agent OS v3 was refocused onto standards and spec-shaping; it retired the
implementation, orchestration, and verification phases earlier versions shipped,
along with the post-build recap. As a result **it records "done" nowhere on
disk.** The spec folder under `agent-os/specs/2026-07-09-1030-csv-dedupe/` is
authored up front — `plan.md` Task 1 is always "Save Spec Documentation" — and
is never mutated afterward, so a finished run and an abandoned plan are
byte-identical here. Completion for this run lived in two places the fixture
cannot show: the git history of the code changes (outside the `agent-os/` tree
entirely) and Claude Code's ephemeral in-tool todo list (never serialized).
`plan.md` therefore lists tasks as plain `## Task N` headers with no checkboxes
and no status field — faithful to the template, unlike the superpowers fixture's
`- [x]` marks.

## Composes, not competes

Agent OS is a **complement**: a standards catalog plus a plan-mode spec-shaping
workflow that governs how an agent starts work. Loop Engineer is the contract
layer that proves how work ended. The honest low score here is not a verdict on
Agent OS — it measures what a standards-and-shaping layout *structurally cannot
prove*: there is no held-out gate, no typed terminal record, and no evidence
trail, so nothing on disk distinguishes a verified finish from a claimed one.
Its only gates are procedural (`/shape-spec` refuses to run outside plan mode)
and human (AskUserQuestion confirm-before-create loops) — neither leaves an
artifact. Emitting the contract is exactly what closes that gap.

## Reproduce

```bash
uv run --with pyyaml python3 -B -m loop inspect examples/agent-os-run
```

A weak verdict (exit 1) is the expected, faithful result for this layout.
