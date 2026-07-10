<!-- title: Integration recipe: OpenHands run → FCR gate -->
<!-- labels: help wanted -->

# Integration recipe: OpenHands run → FCR gate

An integration recipe that layers the loop-contract's false-completion gate over an
OpenHands run. **Composes, doesn't compete:** OpenHands is the EXECUTE tier — it
writes, runs, and tests code in a sandbox; "done" is still the agent stopping. Loop
Engineer wraps that exit in a typed terminal + held-out gate. This adds a layer, it
does not replace the runtime.

## Problem / opportunity

The design is already written — `docs/superpowers/specs/2026-06-30-st3-integration-adapters.md`
§5.3 — but no runnable recipe ships yet. The shipped LangGraph and Temporal recipes
are the template to follow:

- the adapter seam: `loop/integrations.py` (`EngineOutcome` → `to_terminal_state`);
- an env-guarded end-to-end example under `examples/` (skips cleanly when the engine
  isn't installed, like `examples/langgraph-emit/` and `examples/temporal-certify/`);
- a CI job that exercises it.

The specialization from §5.3: OpenHands' `AgentStuckError` / max-iteration stop maps
to `FailedBudget`; a sandbox that touched a holdout/answer-key path (HIGH anti-cheat
finding) maps to `FailedUnverifiable` — the exact "the runtime ran tests but the
agent peeked" case OpenHands can't itself catch.

## Proposal

Follow the `docs/integrations/langgraph.md` recipe end-to-end for OpenHands: read the
run's trajectory as the anti-cheat trajectory input, run the holdout split, and
project the engine outcome through `to_terminal_state` into a typed terminal.

## The gate that proves the fix

```bash
python3 -m loop doctor <recipe-out>   # doctor round-trip is clean
```

Plus a pinned false-completion invariant test: visible-green / holdout-red must
project to `FailedUnverifiable` with `false_completion: true`, and **never**
`Succeeded`.
