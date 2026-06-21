# SPEC.md — pricing-coverage-and-validation

> Intent layer. Describes WHAT success looks like, not HOW to achieve it.
> Scaffolded by `loop-contract` from the ADR. Written once; amended only if the goal changes.

## Goal

Bring `pricing.py` up to at least 80% line coverage and add typed input validation to
`parse_request`, so the pricing module rejects malformed input with a clear error instead of
crashing or returning a wrong price downstream.

## Success criteria

Each criterion is independently verifiable; a criterion with no evidence rule is itself a spec gap.

1. `pricing.py` line coverage is `>= 80%`.
2. `pricing.parse_request` rejects malformed input (missing keys, non-numeric quantity, negative
   price) by raising a typed `PricingError` — never returning a price or raising a bare
   `KeyError`/`TypeError`.

## Constraints

Things the loop must NOT do, regardless of outcome:

- Do not modify existing public function signatures (`parse_request`, `apply_discount`, `quote`).
- No new third-party dependencies.
- Do not edit tests, fixtures, golden files, or the verify scripts to manufacture a passing gate.

## Non-goals

Explicitly out of scope for this loop:

- Refactoring the discount algorithm or its rounding behavior.
- Performance tuning of `quote`.
- Touching any module other than `pricing.py` and its tests.

## Evidence rules

What counts as proof that each success criterion is met:

| Criterion | Evidence | Verification command |
|---|---|---|
| 1 — coverage `>= 80%` | coverage report line-rate for `pricing.py` | `scripts/verify-full` |
| 2 — typed validation | parametrized rejection tests pass; bad input raises `PricingError` | `scripts/verify-fast` |

## Underspecified-criteria rule

If any success criterion cannot be reduced to a concrete, checkable evidence rule, treat the loop
as `FailedSpecGap` rather than proceeding. Both criteria above map to a runnable `scripts/verify-*`
gate, so this loop is well-specified.

## Risk profile

`low` — workspace-write only, no external services, fully reversible (tests + one module).

## Inputs

- `goal`: bring `pricing.py` to `>=80%` coverage + typed `parse_request` validation
- `workspace_path`: `./`
- `allowed_tools`: [`read`, `workspace-write`]  (NOT network, NOT external-side-effects)
- `time_budget`: `30m`
- `cost_budget`: `1.00usd`
- `approval_policy`: `on_side_effects`
