# Worked example — flaky-test-triage

A second self-contained walk through the **loop-engineer** lifecycle, built to showcase one pillar
the flagship (`examples/coverage-repair/`) only touches in passing: the **structured repair record**
and the **repair-productivity (RP)** metric it feeds.

> **Scenario:** *A genuinely flaky test — tie-order in a priority sort over an unordered set — is
> triaged and repaired. The order is deterministic within one interpreter but changes across
> `PYTHONHASHSEED` values, so the visible test passes on some seeds and fails on others.*

## The bug, and why it is really flaky

`target/jobs.py` orders jobs by priority, highest first. Equal-priority jobs used to be left in
**set-iteration order** — stable within one process, but Python randomizes string hashing per
`PYTHONHASHSEED`, so the tie order (and the test result) changes from run to run. The repair makes
the sort key `(-priority, name)`, so the order is a function of the data, not the interpreter state.

`target/measure_stability.py` turns that flake into a deterministic probe: it runs the visible test
under 5 fixed `PYTHONHASHSEED` values and reports the passing fraction. This is real, not narrated —
swap the key back to priority alone and the score drops below 1.0.

## The repair-record pillar

The single bounded repair pass is recorded at its canonical path,
`.loop/repair/iter-002.json` (`loop-engineer/repair@1`, the 7 canonical fields). Its
`verification_before`/`verification_after` scores are anchored to a same-task red→green pair of
deterministic verify bundles:

| Artifact | Outcome | score |
|---|---|---|
| `.loop/artifacts/verify-T1-iter1.json` (red) | FAIL | `0.6` — visible test passed under 3/5 probe seeds |
| `.loop/artifacts/verify-T1.json` (green) | PASS | `1.0` — 5/5 probe seeds after the `(priority, name)` key |

`loop metrics` recomputes `productive` from that `0.6 → 1.0` delta (never trusts the record's own
flag) and anchors it to the two bundles, so the scorecard reports a **non-null RP**:

```
repair_productivity   = 1.0      # one repair pass, measurably productive
repair_passes         = 1
productive_repairs    = 1
false_completion_rate = 0.0      # the terminal claim's iteration carries only a green bundle
evidence_backed       = true     # a real held-out gate verdict is on disk
provenance.fcr_methods_agree = true   # deterministic cross-join and held-out flag agree
```

Every number above is derived from the committed files, not asserted — run the command below to
re-derive it byte-for-byte.

## The three commands

```bash
# 1. The contract objects are valid (manifest/state/tasks/terminal/repair): ok == true
python3 -m loop doctor examples/flaky-test-triage

# 2. Prime-directive score (verify surface invokes the gate; all 7 terminal states in WORKFLOW):
#    verdict "strong", score 90
python3 -m loop inspect examples/flaky-test-triage

# 3. The FCR/RP scorecard derived from this loop's real .loop/ evidence:
#    repair_productivity 1.0, false_completion_rate 0.0, evidence_backed true
python3 -m loop metrics examples/flaky-test-triage
```

## Run it yourself

One entrypoint re-derives the committed held-out verdict from a **live** gate run and checks the
terminal claim against it — needs `pytest` importable by `python3` (no other installs), ~1–2s:

```bash
bash examples/flaky-test-triage/scripts/run-example
```

It runs the **real** repo held-out gate `scripts/holdout_gate.py` over the toy target's visible +
holdout checks, writes the verdict to `.loop/artifacts/holdout-verdict.json`, and asserts the
committed `terminal_state.json`'s `false_completion: false` is **backed** by an independent
`Succeeded` verdict — exiting nonzero on any mismatch. `scripts/verify-full` runs the same stability
score + held-out gate as the milestone check. Delete the toy target or the gate wiring and both the
run and `loop metrics` go red.

## What to notice

1. **A non-null RP needs anchored evidence, not a flag.** The repair record's `productive: true` is
   only counted because a same-task red→green verify-bundle pair (`0.6 → 1.0`) corroborates it — a
   fabricated or free-floating number is rejected, not summed.
2. **The flake is deterministic per seed.** `measure_stability.py` makes an intermittent failure
   reproducible, so the red bundle's `0.6` is a real measurement, not a story.
3. **Verification is the source of "done."** `terminal_state.json` is `Succeeded` only because the
   stability score reached `1.0` and the held-out order-property gate passed — both evidence paths
   attached, `false_completion: false`.

## Where to go next

- The flagship coverage-repair walkthrough → `examples/coverage-repair/README.md`.
- The schema behind every file here → `reference/repo-os-contract.md`.
- The two first-class metrics (`false-completion-rate` / `repair-productivity`) →
  `reference/eval-suite.md`.
