<!-- title: Integration recipe: ruflo swarm → acceptance gate -->
<!-- labels: help wanted -->

# Integration recipe: ruflo swarm → acceptance gate

An integration recipe that layers a single acceptance gate over a ruflo swarm.
**Composes, doesn't compete:** ruflo is the ORCHESTRATE tier — a multi-agent swarm
whose terminal is "the coordinator decided the objective is met," a self-report
across N agents. Loop Engineer adds one acceptance gate the swarm must pass *as a
whole*. This adds a layer, it does not replace the swarm.

## Problem / opportunity

The design is written — `docs/superpowers/specs/2026-06-30-st3-integration-adapters.md`
§5.4 — but no runnable recipe ships yet. Same shape as the OpenHands recipe (issue
04): follow the shipped LangGraph/Temporal recipes as the template (`loop/integrations.py`
adapter, an env-guarded end-to-end example, a CI job).

The seam is the swarm's terminal hook: **no individual agent may declare the swarm
done** — the acceptance gate does. Register the gate as the swarm's terminal hook
(ruflo exposes hooks / an MCP coordination server), read the merged diff and agent
trails as the anti-cheat inputs, run the holdout split, and project through
`to_terminal_state`.

## Proposal

Follow the `docs/integrations/langgraph.md` recipe end-to-end for a ruflo swarm,
wiring the gate as the terminal hook so the swarm's collective "done" is decided by
the held-out gate, not by any agent's self-report.

## The gate that proves the fix

```bash
python3 -m loop doctor <recipe-out>   # doctor round-trip is clean
```

Plus a pinned false-completion invariant test: visible-green / holdout-red must
project to `FailedUnverifiable` with `false_completion: true`, and **never**
`Succeeded`.
