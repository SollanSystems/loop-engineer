# SPEC.md — flaky-test-triage

> Intent layer. Describes WHAT success looks like, not HOW to achieve it.
> Scaffolded by `loop-contract` from the ADR. Written once; amended only if the goal changes.

## Goal

Make the toy scheduler's job-order test deterministic across interpreter runs. `next_jobs`
orders jobs by priority; equal-priority jobs currently keep set-iteration order, which is stable
within one process but changes across `PYTHONHASHSEED` values — a genuinely flaky test. Make the
tie order a function of the data so the same input always yields the same order.

## Success Criteria

Each criterion is independently verifiable; a criterion with no evidence rule is itself a spec gap.

1. The visible suite passes under all 5 probe `PYTHONHASHSEED` values — stability `score == 1.0`
   (`target/measure_stability.py`).
2. Job order is a function of the data, independent of input order — the held-out order-property
   probe is green (`target/test_holdout.py`), and the held-out gate certifies `Succeeded`.

## Constraints

Things the loop must NOT do, regardless of outcome:

- Do not modify the public `next_jobs` / `load_jobs` signatures.
- No new third-party dependencies.
- Do not edit tests, fixtures, golden files, or the verify scripts to manufacture a passing gate.

## Non-goals

Explicitly out of scope for this loop:

- Changing the priority ordering itself (higher priority still runs first).
- Adding new job types or scheduling policy.
- Touching any module other than `target/jobs.py` and its tests.

## Evidence rules

What counts as proof that each success criterion is met:

| Criterion | Evidence | Verification command |
|---|---|---|
| 1 — stability `score == 1.0` | passing fraction over 5 fixed probe seeds | `scripts/verify-full` |
| 2 — order-independence | held-out probe passes; held-out gate verdict `Succeeded` | `scripts/verify-full` |

## Underspecified-criteria rule

If any success criterion cannot be reduced to a concrete, checkable evidence rule, treat the loop
as `FailedSpecGap` rather than proceeding. Both criteria map to a runnable `scripts/verify-*` gate,
so this loop is well-specified.

## Risk profile

`low` — workspace-write only, no external services, fully reversible (one sort key + its tests).
