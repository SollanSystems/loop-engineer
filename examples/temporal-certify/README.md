# Temporal recipe — durable execution below, proof-of-done above

A runnable [Temporal](https://github.com/temporalio/sdk-python) workflow whose
only path to a returned result is a **certify activity**. Temporal keeps its own
durable runtime (the workflow survives crashes, retries activities, resumes
where it left off); Loop Engineer adds the contract/proof tier above it —
evidence-backed state the `loop` CLI can independently validate and score.

## What it shows

`workflow_example.py` runs two activities under one workflow:

- `do_work_activity` writes `artifact.txt`.
- `certify_activity` — whose return value is the workflow's **only** result —
  runs the same **visible + withheld holdout** split the loop optimized against
  through the real `holdout_gate.decide` and `anticheat_scan.scan`, projects the
  verdict through `to_terminal_state`, and records it via `loop.emit`. It writes
  the verbatim gate verdict (`holdout-verdict.json`) as evidence.

Activities do the I/O; the `@workflow.defn` class stays deterministic. On a real
pass the terminal is `Succeeded` with evidence.

### The `--sabotage-holdout` false-completion demo

```bash
python workflow_example.py sabotaged-run/ --sabotage-holdout
```

`do_work_activity` now writes output that passes the **visible** check (the file
exists) but fails the **holdout** (the content is wrong). That is the measurable
false-completion event: the terminal becomes `FailedUnverifiable` with
`false_completion: true` — **never** `Succeeded`. The dishonest completion is
recorded, not laundered.

### Host-side failure mapping

Failures that never reach the certify activity are mapped off the
`WorkflowFailureError.cause` (`map_workflow_failure`): a workflow
`CancelledError` → `AbortedByHuman`, activity `RetryPolicy` exhaustion →
`FailedBlocked`, workflow timeout → `FailedBudget`. So a crash, cancel, or
budget cap still lands an honest terminal instead of an unwritten contract.

## Run it

```bash
pip install loop-engineer temporalio
python workflow_example.py demo-run/     # first run downloads a local Temporal dev server
loop doctor demo-run/                    # -> {"ok": true, ...}
loop metrics demo-run/                   # -> clean scorecard
```

Standalone mode starts a local Temporal dev server via
`temporalio.testing.WorkflowEnvironment.start_local()` — the **first** run
downloads the dev-server binary (network required); later runs reuse it.

The gate tools (`holdout_gate`, `anticheat_scan`) resolve from `loop._resources`
— the wheel bundles them, so a plain `pip install` is enough; running from a
repo checkout picks them up from `scripts/` too.

## The general pattern

The complement framing, the signal→terminal-state mapping table, and the
copy-paste (zero-install) projection live in
[`docs/integrations/temporal.md`](../../docs/integrations/temporal.md).
