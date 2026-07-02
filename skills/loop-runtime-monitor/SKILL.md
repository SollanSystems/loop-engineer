---
name: loop-runtime-monitor
description: "Watch a RUNNING agent loop from outside and call the intervention before it burns the budget — read .loop/state.json + RUNLOG.md, detect stall (same active_task across N iterations with no measured progress), repair-churn (repair attempts without score improvement), and budget-overrun, then surface one recommendation (replan / revert / approval / terminate). Use when someone says watch the loop, is the loop stuck, the run isn't making progress, monitor the long-running agent, why is this loop spinning, or should I intervene in the run."
---

# loop-runtime-monitor — watch the run, call the intervention

The **observer**. While [[loop-run]] advances the state machine and [[loop-repair]] reacts to a red gate, this skill stands *outside* an in-flight run and answers one question: **is the loop still making progress, or is it spinning?** It reads the loop's externalized state — `.loop/state.json` + `RUNLOG.md` — recomputes progress from evidence (never from the agent's prose), and when a run has gone bad it surfaces a single intervention recommendation. It is read-only over the run; it recommends, it never mutates.

This is the in-flight complement to the post-hoc [[loop-flywheel]] (which mines a *finished* run's history) and the gap-scoring loop-inspector (which audits a loop's *contract*). loop-runtime-monitor watches the run *as it happens*, so a stuck run gets caught at iteration 4 instead of at the budget wall.

## Position vs a loop-driving operator

A loop **operator** — [[loop-run]], or any continuous-agent-loop driver — *drives* a loop: it dispatches the next step and keeps the thing running. loop-runtime-monitor does the opposite job: it is the **circuit-breaker that watches the driver.** An operator optimizes for "keep going"; left alone, that bias is exactly how a loop spins on the same task or churns repairs until the budget is gone. This skill is the independent progress signal that says *stop going, intervene* — separation of "run it" from "is it still worth running" is the whole point, the same way a verifier must not be the agent it grades.

## What it reads (evidence, not claims)

- **`.loop/state.json`** — `active_task`, `best_score`, `iteration_id`, `budget_remaining`. The current truth of the run.
- **`RUNLOG.md`** — the per-iteration ledger [[loop-run]] appends: `active_task`, the verify outcome, `best_score`, and (on repair turns) `attempt` + `productive`. The history of the run.

Both are written to disk by the loop itself, so the monitor's read survives compaction and works across a session boundary — it can be pointed at a run another session is driving.

## The three signals

| Signal | Detection | Why it matters |
|---|---|---|
| **stall** | same `active_task` across the last N iterations (default 3) with `best_score` flat (no measured progress) | the loop is re-attempting the same unit without moving the needle — the earliest sign the execution graph is wrong, not the patch |
| **repair-churn** | the last N repair attempts (default 3) all carry `productive=false` with `best_score` flat | the repair lane is thrashing against its cap, burning budget without converging — a [[loop-repair]] record schema read straight off `productive` |
| **budget-overrun** | a numeric field in `state.json.budget_remaining` has reached `<= 0` | a hard wall — the only honest next move is human, not another iteration |

Thresholds and the exact heuristics live in `reference/patterns.md`. The defaults are deliberately conservative: a single non-productive iteration is normal, three in a row on the same task is a pattern.

## The intervention ladder (recommendation, not action)

The monitor emits **exactly one** recommendation, mapped to the worst active signal — it is advisory; the operator [[loop-run]] is what actually transitions:

- **`continue`** — no signal active; the run is making measured progress, leave it alone.
- **`replan`** — stall: revise the execution graph, not the same patch (loop-run's `replan` state).
- **`revert`** — repair-churn: stop stacking bad patches; restore the best-known-good `.loop/state.json` before the next strategy.
- **`approval`** — budget-overrun: only a human can extend the budget; pause and surface the request.
- **`terminate`** — reserved for the worst case (a safety signal, or a stall that survived a replan); end honestly in the right one of the 7 terminal states rather than spinning toward `FailedBudget`.

The monitor recommends the rung; it never *takes* the side-effecting action itself. Acting on `revert`/`approval`/`terminate` is [[loop-run]]'s job, through its normal approval gates.

## The runnable check

`scripts/runtime_monitor.py` is the deterministic core — importable and a CLI:

```bash
python3 scripts/runtime_monitor.py path/to/.loop
```

It emits the JSON health report `{active_task, iterations_observed, stalled, repair_churn, budget_overrun, recommendation, evidence}`. `evidence` is the concrete reason for each fired flag (the spinning task, the flat score, the exhausted budget key) — never a prose claim, always the read-off fact. Import `health_report(loop_dir)` to fold the same report into a Workflow or a watch poll. A read-only monitor poll routes to `model: "haiku"` per the model-routing rule (tier table: `reference/model-routing.md`); the report is data, the intervention decision is the operator's.

## Boundaries

- **Read-only over the run.** The monitor never edits `state.json`, `TASKS.json`, or the diff — observing a loop must not perturb it.
- **Evidence over claim.** A flag fires only on a fact computed from the ledger; "the agent said it's stuck" is not a signal, a flat `best_score` across N iterations is.
- **Recommend, don't act.** Every recommendation past `continue` crosses back to [[loop-run]] and its approval gates; the monitor is the alarm, not the hand on the switch.

## Cross-links

- [[loop-run]] — the operator that acts on these recommendations and owns the 7 terminal states.
- [[loop-repair]] — emits the `productive` repair records the churn signal reads.
- [[loop-evals]] — designs the false-completion-rate / repair-productivity metrics this skill watches in-flight.

---

Sources: "Designing a Loop Engineer Skill for Frontier Agent Workflows" (2026), synthesizing SWE-Marathon (arXiv 2606.07682 — the stall / no-progress failure mode), the repair-productivity churn signal from the loop-repair record schema, Code as Agent Harness (arXiv 2605.18747 — the code-as-harness framing; the repo-native run ledger is this suite's own), and Anthropic guidance on monitoring long-running agent harnesses (anthropic.com, 2025).
