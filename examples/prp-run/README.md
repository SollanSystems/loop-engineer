# prp-run — a vendored foreign-harness fixture

A minimal, sanitized run directory in the layout the
[PRPs-agentic-eng](https://github.com/Wirasm/PRPs-agentic-eng) skill suite
(`prp-prd` → `prp-plan` → `prp-implement` → `prp-review`, driven headlessly by
`prp-loop`) leaves behind: a problem-first PRD, a context-rich plan that carries
its own task ledger, an implementation report, a PR review, and the loop's own
state and verdict files under `.claude/PRPs/`. Directory names and section
headings follow the harness's documented conventions
(Wirasm/PRPs-agentic-eng@ada2f5b867c196b68f17628d4870356e4e8164a4); every
sentence of prose is original and fictional — no template body text is copied.
It instantiates the shared fictional **csv-dedupe** task dated 2026-07-09, the
same task every sibling `examples/*-run` fixture models, so the scoreboard can
compare one job across nine layouts.

PRPs is a **complement**, not a competitor: it is a spec-plan-implement-review
pipeline that drives how an agent does the work, with a genuine six-level
validation gate, a machine `{clean, blocking}` verdict, and a completion idiom
(the plan is physically moved into `plans/completed/`). Loop Engineer is the
contract layer that names how the work must end — a typed terminal record and an
independent held-out gate that no single-repo convention is obliged to carry.
The honest inspect score below is not a criticism; it measures the small delta
between "recorded done six ways" and "proven un-fakeable done once."

`.claude/prp-loop.state.json`, `.claude/prp-loop.run.log`, and the
`.claude/PRPs/reviews/*.verdict.json` files are runtime state that a real PRPs
project gitignores; they are vendored here anyway so every artifact class — spec,
plan, task ledger, run journal, verification, machine verdict, loop state — is
represented on disk.

The loop captures the plan's path at plan time, so `prp-loop.state.json`, the
implementation report, and the PRD's phase row all reference
`.claude/PRPs/plans/csv-dedupe.plan.md`, while `prp-implement` archives the file
itself into `plans/completed/` at the end — which is where the later PR review
resolves it. The fixture keeps that pre-archive/post-archive path split rather
than smoothing it into one location, because the split is exactly what a real
run leaves on disk.

Reproduce the read-only score:

```bash
uv run --with pyyaml python3 -B -m loop inspect examples/prp-run
```
