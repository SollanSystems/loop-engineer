<!-- title: emit.open_contract seeds a metrics-dirty RUNLOG placeholder -->
<!-- labels: help wanted -->

# emit.open_contract seeds a metrics-dirty RUNLOG placeholder

A fresh scaffold is born "metrics-dirty," which forces every integration recipe to
work around it. Fix the root so the workaround can be retired.

## Problem

`loop.emit.open_contract` scaffolds a `RUNLOG.md` from `templates/RUNLOG.md.tmpl`,
whose outcome block (`templates/RUNLOG.md.tmpl:27`) is
`` `{{ITERATION_OUTCOME}}` — one of: `task_passed`, … ``. `loop/scaffold.py`
`_substitutions` has no `ITERATION_OUTCOME` key, so `_fill` renders the unknown token
as the literal `REPLACE` (`loop/scaffold.py:95`). `scripts/metrics.py` then parses
`REPLACE` as an unrecognized outcome token, so a just-scaffolded loop is
metrics-dirty until real iterations land.

Checkable at this commit:

```python
import sys, tempfile, os
from loop import emit
sys.path.insert(0, "scripts"); import metrics
ws = os.path.join(tempfile.mkdtemp(), "scaffold_check")
emit.open_contract(ws)
print(metrics.compute_metrics(ws)["provenance"]["unrecognized_outcomes"])
# -> ['replace']
```

Because of this, both engine recipes reset `<ws>/RUNLOG.md` to emit's fresh header
right after `open_contract`: `examples/langgraph-emit/graph_example.py:105` and
`examples/temporal-certify/workflow_example.py:159`. That inline reset is a
documented carve-out in the plan's Global Constraints
(`docs/superpowers/plans/2026-07-08-v0.8.0-composes-the-field.md`, "Adjudicated
carve-out").

## Proposal

Make the scaffold not seed a metrics-flagged placeholder. Options, pick one:

- a first-class affordance — `emit.open_contract(seed_runlog=False)` or
  `emit.reset_runlog(ws)` — so a caller that scores from iteration 0 opts out of the
  placeholder; or
- render the placeholder outcome as a value `metrics` recognizes (or omit the seeded
  iteration block entirely) so a fresh scaffold is metrics-clean by construction.

The reset only ever strips a placeholder — it never fabricates state — so the
affordance must preserve that (no synthetic completed iteration).

## The gate that proves the fix / acceptance

- A freshly-scaffolded loop reports `provenance.unrecognized_outcomes == []` (the
  snippet above returns `[]`).
- Both recipes drop their inline `RUNLOG.md` resets and still pass their gates.
- The plan's Global-Constraints carve-out text can be retired.

```bash
python3 -m pytest scripts/test_metrics.py scripts/test_emit.py   # green
python3 -m loop doctor <recipe-workspace>   # recipe still clean after the inline reset is removed
```
