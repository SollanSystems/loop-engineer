<!-- title: Label self_eval terminal/repair/eval checks honestly as doc-completeness -->
<!-- labels: good first issue -->

# Label self_eval terminal/repair/eval checks honestly as doc-completeness

A naming/comment clarification (no behavioral change required) that keeps the gate
honest about its own scope.

## Problem

Three `scripts/self_eval.py` checks are substring-presence scans over a single
`SKILL.md` each, not behavioral enforcement:

- `check_terminal_states` (`scripts/self_eval.py:185`) — `missing = [s for s in
  facts["terminal_states"] if s not in text]` over `skills/loop-run/SKILL.md`.
- `check_repair_fields` (`scripts/self_eval.py:193`) — same shape over
  `skills/loop-repair/SKILL.md`.
- `check_eval_layers_and_metrics` (`scripts/self_eval.py:206`) — normalized
  substring presence over `skills/loop-evals/SKILL.md`.

Each passes as long as the canonical words *appear in the prose*. Presenting them as
"the hard pass/fail gate" risks a reader mistaking documentation-completeness for
runtime-correctness enforcement — gaming requires only listing the canonical words.

## Proposal

Rename and/or comment the three checks as **documentation-completeness** checks (not
behavioral enforcement), and say so where `self_eval` is described as a gate — in
`CONTRIBUTING.md` (the "Ground rule" / self_eval mention) and in the README's
structural-check list. No behavioral change is required if the checks are
intentional; this is a scope-honesty clarification consistent with the suite's own
posture.

## The gate that proves the fix

```bash
python3 scripts/self_eval.py   # green (13 structural invariants)
python3 -m pytest -q scripts/test_docs_claims.py   # README accuracy assertions green
```
