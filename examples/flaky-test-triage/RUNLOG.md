# RUNLOG.md — flaky-test-triage

> Human-readable iteration history. Machine state lives in `.loop/state.json`.

---

## Iteration 1 — 2026-07-08T10:08:00Z

- **active_task:** `T1` — Make next_jobs tie-order deterministic
- **action:** Reproduced the flake: `target/measure_stability.py` runs the visible
  test under 5 fixed PYTHONHASHSEED values; the buggy priority-only sort key
  passed 3/5.
- **verify:** `scripts/verify-full` → FAIL — stability score 0.6 < 1.0
- **outcome:** repair_triggered
- **evidence:** `.loop/artifacts/verify-T1-iter1.json`

## Iteration 2 — 2026-07-08T10:24:00Z

- **active_task:** `T1`
- **action:** Applied the repair from `.loop/repair/iter-002.json`: sort key
  (priority, name) so tie order is a function of the data.
- **verify:** `scripts/verify-full` → PASS — stability score 1.0; held-out order
  property green (holdout_gate verdict: Succeeded)
- **outcome:** task_passed
- **evidence:** `.loop/artifacts/verify-T1.json`, `.loop/artifacts/holdout-verdict.json`
