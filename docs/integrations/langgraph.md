# LangGraph — gate the graph, then emit proof-of-done

LangGraph owns the ORCHESTRATE tier: it stays your runtime — the state machine
that routes nodes, holds state, and decides what runs next. Loop Engineer adds
the tier *above* it — a contract-and-proof layer that turns "the graph reached
`END`" into evidence-backed, independently-checkable proof-of-done. It never
replaces LangGraph; it certifies what LangGraph produced.

## The pattern

Make a `certify` node the **only** edge into `END`. It runs the same visible +
withheld-holdout split the loop optimized against through the real gate
(`holdout_gate.decide`) and the trajectory sweep (`anticheat_scan.scan`),
projects the result through `to_terminal_state`, and records it via `loop.emit`
— which refuses a dishonest `Succeeded` before anything hits disk.

```python
from loop import emit
from loop.integrations import EngineOutcome, to_terminal_state

def certify(state):                          # the ONLY node wired to END
    gate = holdout_gate.decide(visible, holdout)      # visible green + holdout green?
    ac = anticheat_scan.scan(diff_text="", trajectory=[...])
    terminal = to_terminal_state(
        outcome=EngineOutcome(reached_end=True, artifacts=[...]),
        gate_verdict=gate, anticheat=ac,
        criteria_met={"1": gate["verdict"] == "Succeeded"},
    )
    emit.terminate(ws, state=terminal["state"], criteria_met=terminal["criteria_met"],
                   evidence=terminal["evidence"], false_completion=terminal["false_completion"],
                   reason=terminal["reason"], iteration_id=1)
    return {"terminal_state": terminal["state"]}
```

Wire it so nothing else reaches `END`:

```python
graph.add_edge("do_work", "certify").add_edge("certify", END)
```

## LangGraph signal → typed terminal state

| LangGraph signal | Typed terminal state |
|---|---|
| graph reached `END`, holdout green + anticheat clean | `Succeeded` |
| graph reached `END`, visible green / holdout red | `FailedUnverifiable` (`false_completion: true`) |
| `GraphRecursionError` (LangGraph's own step cap) | `FailedBudget` |
| caught tool/credential exception | `FailedBlocked` |
| operator interrupt | `AbortedByHuman` |

## Zero-install mode

The `loop.integrations` module is convenience, not a requirement — the whole
projection is ~15 lines you can paste into any graph with no dependency:

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

`loop metrics` scores the run from its on-disk evidence (RUNLOG success claims,
the verify bundle, the held-out verdict) — not from the graph's narration.

Verified against `langgraph` 1.2.8 (2026-07-08).

Full runnable example (happy path + `--sabotage-holdout` false-completion demo):
[`examples/langgraph-emit/`](../../examples/langgraph-emit/).
