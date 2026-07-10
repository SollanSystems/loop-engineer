# openspec-run — a vendored foreign-harness fixture

A minimal, sanitized run tree in the layout the
[OpenSpec](https://github.com/Fission-AI/OpenSpec) CLI leaves behind for a
`spec-driven` change (proposal → specs → design → tasks, then archive), pinned
at `Fission-AI/OpenSpec@93e27a755ce5386c66be7f3274a35f70018002bc`. All content
is fictional and original — no OpenSpec template text is copied. It exists so
`python3 -m loop inspect examples/openspec-run` can score a foreign layout
read-only, and so a gap report has a stable target to check against.

OpenSpec is a **complement**, not a competitor: it drives *how* a spec-authoring
agent proposes, refines, and applies a change, then keeps a living capability
spec current. Loop Engineer is the contract layer that proves *how the work
ended*. The score here measures what a proposal/spec/tasks tree
structurally can and cannot prove. OpenSpec has a genuine deterministic gate on
spec-document structure (`openspec validate --strict` requires every Requirement
to carry at least one Scenario), but ships no harness-provided gate that
executes code or tests, and persists no iteration journal — the dated archive
directory plus the updated living spec is the sole durable "it finished" signal.

This fixture models the **archived (completed)** state of the shared fictional
csv-dedupe task, dated 2026-07-09 — the same task as `examples/superpowers-run`,
rendered in OpenSpec's own completion idiom so the scoreboard compares one task
across nine layouts.

## File map

| Path | Role |
|---|---|
| `openspec/config.yaml` | Workspace anchor — declares `schema: spec-driven`, project `context`, per-artifact `rules`. |
| `openspec/specs/csv-dedupe/spec.md` | Living capability spec — the post-sync source of truth an archived run produces. |
| `openspec/changes/archive/2026-07-09-dedupe-csv-rows/proposal.md` | Intent — Why / What Changes / Capabilities / Impact. |
| `.../design.md` | Technical design — Context / Goals · Non-Goals / Decisions. |
| `.../tasks.md` | Task ledger, every box checked, closing with a `## Verification` section. |
| `.../specs/csv-dedupe/spec.md` | Delta spec — `## ADDED Requirements`, the acceptance criteria `openspec validate` gates. |
| `.../.openspec.yaml` | Per-change metadata — `schema` + `created` only; no status field (status is derived on demand). |

## Reproduce

```bash
uv run --with pyyaml python3 -B -m loop inspect examples/openspec-run
```

A weak verdict (exit 1) is the honest, expected result: the layout has no
held-out gate, no typed terminal state, and no evidence trail — exactly the
proof surface that emitting a Loop Engineer contract adds on top.
