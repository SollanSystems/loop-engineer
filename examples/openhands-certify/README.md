# OpenHands recipe — certify the run after it ends

A runnable post-run certifier for [OpenHands](https://github.com/OpenHands/software-agent-sdk).
OpenHands keeps its own runtime; Loop Engineer adds the contract/proof tier above
it — evidence-backed state the `loop` CLI can independently validate and score.

## Why post-run

LangGraph has an `END` edge and Temporal has a certify activity. OpenHands has
neither: a run ends when the agent itself sets `execution_status = FINISHED`.
The seam that needs **zero engine changes** is therefore the record the SDK
already wrote when you pass `persistence_dir=`:

```
<persistence_dir>/<conversation-id-hex>/base_state.json
<persistence_dir>/<conversation-id-hex>/events/event-00000-<uuid>.json
```

`certify_run.py` reads that with nothing but `json` — it imports no `openhands`
package, so it runs on Python 3.10 while the SDK requires 3.12, and it needs no
LLM key.

## What it shows

```bash
python certify_run.py demo-run/ \
  --conversation fixtures/conversations/finished \
  --agent-workspace fixtures/workspaces/green
loop doctor demo-run/            # -> {"ok": true, ...}
loop metrics demo-run/           # -> clean scorecard
```

The certifier runs the same **visible + withheld** split the loop optimized
against through the real `holdout_gate.decide`, sweeps the event log through
`anticheat_scan.scan`, projects the OpenHands terminal through
`to_terminal_state`, and records it via `loop.emit`. It writes two evidence
artifacts a scorecard can join: the verbatim gate verdict
(`holdout-verdict.json`) and a verify bundle (`verify-T1.json`).

On a real pass the terminal is `Succeeded` with evidence, and `loop metrics`
scores the run clean: `false_completion_rate 0.0`, `evidence_backed: true`, the
two FCR methods agree.

### The false-completion demo

```bash
python certify_run.py sabotaged-run/ \
  --conversation fixtures/conversations/finished \
  --agent-workspace fixtures/workspaces/stale
```

Same conversation record — OpenHands still reports `finished` — but the work
product passes the **visible** check (the file exists) and fails the **withheld**
one (the content is wrong). That is the measurable false-completion event: the
terminal becomes `FailedUnverifiable` with `false_completion: true`, **never**
`Succeeded`. The dishonest completion is recorded, not laundered.

## Fixtures

`fixtures/conversations/` holds six conversation dirs captured from
`openhands-sdk` 1.37.1 (trimmed: the agent/LLM block is reduced, the system-prompt
event dropped; every field the certifier reads is verbatim).

| Fixture | `execution_status` | Terminal (with a green workspace) |
|---|---|---|
| `finished` | `finished` | `Succeeded` — or `FailedUnverifiable` with the `stale` workspace |
| `max-iterations` | `error` + `MaxIterationsReached` | `FailedBudget` |
| `stuck` | `stuck` | `FailedBudget` |
| `blocked` | `error` + `LLMAuthenticationError` | `FailedBlocked` |
| `paused` | `paused` | `AbortedByHuman` |
| `running` | `running` | `FailedUnverifiable` |

Every non-happy row is certified against a **green** workspace on purpose: a
passing check never overrides the engine's own terminal signal.

Because the fixtures are committed, `scripts/test_openhands_recipe.py` is
deterministic and credential-free and runs in the default gates matrix.
`scripts/test_openhands_sdk_drift.py` pins those fixtures against the *installed*
SDK and is the live schema-drift alarm (its own CI job, python 3.12).

## The general pattern

The complement framing, the full signal table, the precedence trap, and the
copy-paste (zero-install) projection live in
[`docs/integrations/openhands.md`](../../docs/integrations/openhands.md).
