<!-- title: Reconcile emit's iteration-outcome vocabulary with metrics' recognized tokens -->
<!-- labels: good first issue -->

# Reconcile emit's iteration-outcome vocabulary with metrics' recognized tokens

The writer and the metrics reader disagree on the outcome vocabulary, so a RUNLOG
written entirely through the sanctioned writer can still look "dirty" to `loop
metrics`.

## Problem

`loop/emit.py` `_ITERATION_OUTCOMES` (`loop/emit.py:26`) accepts `approval_requested`
and `replanned`, but `scripts/metrics.py` `_KNOWN_OUTCOME_TOKENS`
(`scripts/metrics.py:101`, built from `_SUCCESS_OUTCOME_TOKENS` +
`_HONEST_RED_OUTCOME_TOKENS`) recognizes neither. So an iteration appended via
`emit.append_iteration(..., outcome="approval_requested")` — a fully valid write —
surfaces under `provenance.unrecognized_outcomes`.

Checkable at this commit:

```python
import sys; sys.path.insert(0, "scripts"); import metrics
from loop.emit import _ITERATION_OUTCOMES
print([o for o in _ITERATION_OUTCOMES if o not in metrics._KNOWN_OUTCOME_TOKENS])
# -> ['approval_requested', 'replanned']
```

## Proposal

Decide the canonical vocabulary and align the two ends:

- either add `approval_requested` and `replanned` to metrics' honest-red set
  (`scripts/metrics.py` `_HONEST_RED_OUTCOME_TOKENS`) — they are known, non-success
  outcomes, so they belong there and should not read as "unrecognized synonyms";
- or narrow `emit`'s accepted set to the tokens metrics already knows.

Add a round-trip regression test: `emit.append_iteration` writing every allowed
outcome, then `compute_metrics(...)` reports `provenance.unrecognized_outcomes == []`.

## The gate that proves the fix

```bash
python3 -m pytest scripts/test_metrics.py scripts/test_emit.py   # green
```
