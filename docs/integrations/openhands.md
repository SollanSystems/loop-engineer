# OpenHands — certify the run after it ends

OpenHands owns the EXECUTE tier: the autonomous coding runtime that plans, edits,
runs commands, and decides for itself when it is done. What it cannot do is
independently check *its own* completion claim — the agent both does the work and
declares `FINISHED`. Loop Engineer adds the tier *above* it: a contract-and-proof
layer that turns "the conversation finished" into evidence-backed proof-of-done.
It never replaces OpenHands; it certifies what OpenHands ran.

## The pattern

Unlike LangGraph (`END` edge) or Temporal (certify activity), OpenHands has **no
seam to insert a certify node into** — the run ends when the agent sets its own
execution status. So the recipe is a **post-run certifier** over the record the SDK
already persisted:

```
<persistence_dir>/<conversation-id-hex>/base_state.json     # execution_status, max_iterations, stats
<persistence_dir>/<conversation-id-hex>/events/event-00000-<uuid>.json   ← the trajectory
                                        events/event-00001-<uuid>.json
```

The conversation id segment is the UUID **hex** (32 chars, no hyphens); a
conversation only persists when you pass `persistence_dir=`. The certifier takes a
conversation dir directly, so that composition rule is documentation, not code.

```python
from loop import emit
from loop.integrations import EngineOutcome, to_terminal_state

state = json.loads((conv_dir / "base_state.json").read_text(encoding="utf-8"))
events = sorted((conv_dir / "events").glob("event-*.json"), key=event_index)

gate = holdout_gate.decide(visible, withheld)          # visible green + withheld green?
ac = anticheat_scan.scan(diff_text=git_diff, trajectory=[str(p) for p in events])
terminal = to_terminal_state(
    outcome=to_engine_outcome(state, events, artifacts=[...]),
    gate_verdict=gate, anticheat=ac,
    criteria_met={"1": gate["verdict"] == "Succeeded"},
)
emit.terminate(ws, state=terminal["state"], criteria_met=terminal["criteria_met"],
               evidence=terminal["evidence"], false_completion=terminal["false_completion"],
               reason=terminal["reason"], iteration_id=1)
```

The certifier **imports no `openhands` package** — the record is plain JSON, so it
runs on Python 3.10 even though the SDK requires 3.12, and the gate needs no LLM
key. The event log doubles as the trajectory fed to `anticheat_scan.scan`: the
"the runtime ran the tests but the agent read the answer key" case OpenHands
cannot catch about itself, because the answer key is not part of its contract.

## OpenHands signal → typed terminal state

| `base_state.json` signal | `EngineOutcome` field | Typed terminal state |
|---|---|---|
| `execution_status: "finished"`, gate green + anticheat clean | `reached_end=True` | `Succeeded` |
| `execution_status: "finished"`, visible green / withheld red | `reached_end=True` | `FailedUnverifiable` (`false_completion: true`) |
| `execution_status: "stuck"` (stuck detector) | `budget_exhausted=True` | `FailedBudget` |
| `execution_status: "error"` + `ConversationErrorEvent.code == "MaxIterationsReached"` | `budget_exhausted=True` | `FailedBudget` |
| `execution_status: "error"`, any other code | `external_error="<code>: <detail>"` | `FailedBlocked` |
| `execution_status: "paused"` (`conversation.pause()`) | `human_abort=True` | `AbortedByHuman` |
| `idle` / `running` / `waiting_for_confirmation` (read mid-flight or abandoned) | `reached_end=False` | `FailedUnverifiable` |
| trajectory touched an answer-key path (anticheat HIGH) | — | `FailedUnverifiable` |
| the diff edits a gate script (anticheat CRITICAL) | — | `FailedSafety` |

**The precedence trap.** A max-iteration stop arrives *as*
`execution_status == "error"` with a `ConversationErrorEvent` whose `code` is
`MaxIterationsReached`. Since `to_terminal_state` ranks blocked above budget,
setting **both** `external_error` and `budget_exhausted` reports `FailedBlocked`
and silently loses the budget signal. Inspect the error code first and set
**exactly one**. `code` is a free-form `str`, so anything unrecognized falls
through to `FailedBlocked` — which fails safe: an unclassified error can never
become `Succeeded`.

## Zero-install mode

The `loop.integrations` module is convenience, not a requirement — the whole
projection is the SAME ~15 lines the LangGraph and Temporal recipes paste
(the adapter is engine-neutral):

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
- run: python certify_run.py run/ --conversation "$CONV_DIR" --agent-workspace "$WS"
- run: loop doctor run/          # -> {"ok": true}: the contract is structurally honest
- run: loop metrics run/         # -> false_completion_rate + evidence-backed scorecard
```

`loop metrics` scores the run from its on-disk evidence — not the agent's narration.

Verified against `openhands-sdk` 1.37.1 (2026-07-25), MIT
([`OpenHands/software-agent-sdk`](https://github.com/OpenHands/software-agent-sdk),
"Copyright (c) 2026 OpenHands contributors" — PyPI carries no license metadata).
The persistence layout, the `ConversationExecutionStatus` members, and the
`MaxIterationsReached` literal are pinned live by
[`scripts/test_openhands_sdk_drift.py`](../../scripts/test_openhands_sdk_drift.py).

Full runnable example (six committed fixture conversations + the false-completion
demo): [`examples/openhands-certify/`](../../examples/openhands-certify/).
