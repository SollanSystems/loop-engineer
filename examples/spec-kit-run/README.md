# spec-kit-run — a vendored foreign-harness fixture

A minimal, sanitized run directory in the layout that
[Spec Kit](https://github.com/github/spec-kit) leaves behind
(`.specify/` scaffold + a numbered `specs/NNN-slug/` feature folder). Layout
follows `github/spec-kit@3f7392ae32131c9cfe6a1f97c5c213311183263a` (MIT); every
sentence of content here is original and fictional — no template body text was
copied. It exists so `python3 -m loop inspect examples/spec-kit-run` can score a
foreign layout read-only against the same fictional CSV-dedupe task the other
example runs use.

Spec Kit is a **complement**, not a competitor: it is a spec-driven workflow that
shapes *how* an agent plans and builds a feature; Loop Engineer is the contract
layer that proves *how the work ended*. The honest low score here is not a
criticism — it measures what a spec/plan/tasks/checklist layout *structurally
cannot prove*. Spec Kit's quality gates (the checklist PASS/FAIL table, the
`analyze` severity pass, the Constitution Check, the "Done When" list) are
natural-language instructions the agent is asked to follow; the only tool-enforced
check it ships is prerequisite-file existence. There is no held-out gate, no typed
terminal record, and no machine-readable done flag — "done" is the checkbox state
of `tasks.md`. That gap is exactly what emitting the contract adds.

Reproduce the score:

```bash
uv run --with pyyaml python3 -B -m loop inspect examples/spec-kit-run
```
