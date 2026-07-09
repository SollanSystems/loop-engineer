# Temporal — durable execution below, proof-of-done above

Temporal owns the EXECUTE tier: your durable runtime — the workflow *survives
crashes*, retries activities, resumes where it left off. What it says nothing
about is whether the work is *correct*. Loop Engineer adds the tier *above* it —
a contract-and-proof layer that turns "the workflow returned" into evidence-backed
proof-of-done. It never replaces Temporal; it certifies what Temporal ran.

## The pattern

A `certify` **activity** is the workflow's only path to a returned result:
activities do the I/O (write files, run the gate), the workflow stays
deterministic and just orchestrates. The certify activity runs the same visible
+ withheld-holdout split the loop optimized against through the real gate
(`holdout_gate.decide`) and trajectory sweep (`anticheat_scan.scan`), projects it
through `to_terminal_state`, and records it via `loop.emit` — which refuses a
dishonest `Succeeded` before anything hits disk.

```python
@activity.defn
async def certify_activity(args: WorkArgs) -> dict:
    gate = holdout_gate.decide(visible, holdout)          # visible green + holdout green?
    ac = anticheat_scan.scan(diff_text="", trajectory=[...])
    terminal = to_terminal_state(
        outcome=EngineOutcome(reached_end=True, artifacts=[...]),
        gate_verdict=gate, anticheat=ac,
        criteria_met={"1": gate["verdict"] == "Succeeded"},
    )
    emit.terminate(ws, state=terminal["state"], criteria_met=terminal["criteria_met"],
                   evidence=terminal["evidence"], false_completion=terminal["false_completion"],
                   reason=terminal["reason"], iteration_id=1)
    return {"state": terminal["state"]}

@workflow.defn
class CertifiedGoalWorkflow:
    @workflow.run
    async def run(self, args: WorkArgs) -> dict:
        await workflow.execute_activity(do_work_activity, args, ...)
        return await workflow.execute_activity(certify_activity, args, ...)  # the ONLY return path
```

Failures short of the certify activity are mapped host-side off `WorkflowFailureError.cause`, so a crash/cancel/timeout still lands an honest terminal.

## Temporal signal → typed terminal state

| Temporal signal | Typed terminal state |
|---|---|
| workflow returned via certify activity, holdout green + anticheat clean | `Succeeded` |
| workflow returned, visible green / holdout red | `FailedUnverifiable` (`false_completion: true`) |
| workflow `CancelledError` | `AbortedByHuman` |
| activity `RetryPolicy` exhaustion on an external dependency | `FailedBlocked` |
| workflow timeout (`run_timeout`) | `FailedBudget` |

## Zero-install mode

The `loop.integrations` module is convenience, not a requirement — the whole
projection is the SAME ~15 lines you can paste into any engine (the adapter is
engine-neutral; byte-identical to the LangGraph recipe's):

```python
def to_terminal(gate, anticheat, criteria_met, evidence,
                *, human_abort=False, blocked=None, over_budget=False):
    fc = gate.get("false_completion") is True
    if anticheat.get("downgrade_to") == "FailedSafety": state = "FailedSafety"
    elif human_abort: state = "AbortedByHuman"
    elif blocked: state = "FailedBlocked"
    elif over_budget: state = "FailedBudget"
    elif any(v is None for v in criteria_met.values()): state = "FailedSpecGap"
    elif (not gate or not anticheat or anticheat.get("downgrade_to")
          or gate.get("verdict") != "Succeeded" or fc
          or not any(criteria_met.values()) or not evidence): state = "FailedUnverifiable"
    else: state = "Succeeded"
    return {"schema": "loop-engineer/terminal@1", "state": state,
            "criteria_met": {k: v is True for k, v in criteria_met.items()},
            "evidence": list(evidence), "false_completion": fc}
```

## Gate it in CI

```yaml
- run: pip install loop-engineer
- run: loop doctor run/          # -> {"ok": true}: the contract is structurally honest
- run: loop metrics run/         # -> false_completion_rate + evidence-backed scorecard
```

`loop metrics` scores the run from its on-disk evidence — not the workflow's narration.

Verified against `temporalio` 1.30.0 (2026-07-08).

Full runnable example (happy path + `--sabotage-holdout` demo + cancellation → `AbortedByHuman`): [`examples/temporal-certify/`](../../examples/temporal-certify/).
