# loop-runtime-monitor — detection heuristics, thresholds, and the intervention ladder

> **Base directory.** The bundled `scripts/runtime_monitor.py` named below is **plugin-root-relative** (`${CLAUDE_PLUGIN_ROOT}/scripts/…`, i.e. `../../../scripts/…` from this `skills/loop-runtime-monitor/reference/` folder). The `.loop/` state and `RUNLOG.md` it reads belong to the *watched loop*, not this plugin.

The detail behind `SKILL.md`. This file is the spec the runnable check (`scripts/runtime_monitor.py`) implements: the exact signals, their thresholds, the evidence each one emits, and the rung each maps to. Tune the thresholds here; keep them conservative — a monitor that cries wolf trains the operator to ignore it.

## Inputs

The monitor reads two files from a `.loop/` directory, both written by the loop itself:

- **`state.json`** — the current truth. Fields read: `active_task`, `best_score`, `iteration_id`, `budget_remaining` (a mapping of named budget axes to remaining amounts).
- **`RUNLOG.md`** — the append-only iteration ledger. Each iteration line is parsed for `active_task=<id>` and `best_score=<float>`; repair turns additionally carry `attempt=<n>` and `productive=<true|false>` (the [[loop-repair]] record fields). Lines without an `active_task`/`best_score` pair are ignored — the parser extracts facts, it does not interpret prose.

Both reads are non-destructive. The monitor never opens the diff, the tasks, or any third-party content — it observes the loop's own externalized state and nothing else.

## Signal 1 — stall

**Definition.** The loop is re-attempting the same unit of work without moving the score.

**Heuristic.** Over the last `STALL_MIN_ITERS` iterations (default **3**):

- `active_task` is identical across all of them, AND
- the span of `best_score` (max − min) is `<= SCORE_EPSILON` (default `1e-9`, i.e. no measured progress).

**Why these thresholds.** One repeated iteration is normal — a task often takes more than one turn. Two is still plausible. Three identical-task, flat-score iterations is a *pattern*: the work isn't converging and the execution graph, not the patch, is probably wrong. `SCORE_EPSILON` is float-noise tolerance; any real score movement (even a partial-criteria gain) clears the stall, because a moving score means the loop *is* making progress even on the same task.

**Evidence emitted.** `active_task '<id>' unchanged across N iterations with best_score flat at <score>`.

**Maps to** → `replan`. The fix for a stall is a different plan, not a louder repeat of the same step.

## Signal 2 — repair-churn

**Definition.** The repair lane is burning attempts without improving the verification score — the in-flight view of the repair-productivity metric.

**Heuristic.** Consider only iterations that carry an `attempt=` marker (repair turns). Over the last `CHURN_MIN_ATTEMPTS` of them (default **3**):

- every record has `productive=false`, AND
- the span of `best_score` across them is `<= SCORE_EPSILON`.

**Why these thresholds.** `productive` is already the derived churn flag in the [[loop-repair]] record (`verification_after.score > verification_before.score`); the monitor just watches it accumulate. The [[loop-repair]] cap is N=2 *per failure mode within a task*; this signal looks across the recent repair history so a loop that keeps re-classifying the same failure to dodge the cap still trips here. Three non-productive repairs with a flat score is thrashing — the repair loop should have escalated to `replan`/`revert` already.

**Evidence emitted.** `N consecutive repair attempts on '<task>' with productive=false and best_score flat at <score>`.

**Maps to** → `revert`. Stop stacking patches; restore the best-known-good `.loop/state.json` and let the next strategy start from clean ground (loop-repair's "prefer revert over a worse patch" rule).

## Signal 3 — budget-overrun

**Definition.** A hard wall — a budget axis the loop tracks numerically has reached zero or below.

**Heuristic.** In `state.json.budget_remaining`, any value that is a real number (`int`/`float`, excluding `bool`) and is `<= 0` fires the flag. Non-numeric axes (e.g. `"multi-session (resumable)"`) are skipped — they are descriptive, not gated. This is intentionally string-tolerant: the kernel state.json carries human-readable budget strings, and a strict numeric parse would either crash or false-fire on them.

**Why this is the hardest stop.** Stall and churn are *strategy* problems the operator can fix by re-planning. An exhausted budget is not a strategy problem — the only honest moves are extend-the-budget (a human act) or terminate `FailedBudget`. The monitor cannot grant budget, so it routes to a human.

**Evidence emitted.** `budget_remaining exhausted: <axis>[, <axis>...] <= 0`.

**Maps to** → `approval`. Only a human can extend the budget; the operator pauses and surfaces the request rather than iterating into the wall.

## The intervention ladder

The monitor reports all three booleans, but emits exactly **one** recommendation — the rung for the *worst* active signal, in this precedence:

| Precedence | Active signal | Recommendation | Who acts |
|---|---|---|---|
| 1 (worst) | budget-overrun | `approval` | human extends budget or operator terminates `FailedBudget` |
| 2 | repair-churn | `revert` | operator restores best-known-good, picks a new strategy |
| 3 | stall | `replan` | operator revises the execution graph |
| — (none) | none | `continue` | leave the run alone — it is making measured progress |

`terminate` is the reserved worst-case rung — not auto-emitted by these three signals, but the right escalation when a stall *survives a replan* (the replan reproduced the same flat-score pattern) or a safety signal appears. The monitor names the rung; [[loop-run]] is what transitions, through its approval gates. The recommendation is advisory: a single number off a ledger never moves money, edits the diff, or ends a run — it tells the operator where on the ladder to look.

## Tuning notes

- **Raise, don't lower, the iteration thresholds** for noisy loops (long tasks, exploratory phases) — a higher `STALL_MIN_ITERS` trades earlier detection for fewer false alarms. Lowering below 3 is rarely right: it fires on normal multi-turn tasks.
- **`SCORE_EPSILON`** exists only to absorb float noise. Do not widen it to "tolerate small regressions" — a falling score is itself a signal worth catching, not smoothing away.
- **Budget axes** are whatever the loop chooses to track numerically. A loop that wants budget-overrun detection must write at least one numeric axis into `budget_remaining`; a purely descriptive budget is invisible to this signal by design.
