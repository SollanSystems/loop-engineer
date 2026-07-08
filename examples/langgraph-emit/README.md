# LangGraph recipe — gate the graph, then emit proof-of-done

A runnable [LangGraph](https://github.com/langchain-ai/langgraph) graph whose
`END` is reachable **only through a `certify` node**. LangGraph keeps its own
runtime; Loop Engineer adds the contract/proof tier above it — evidence-backed
state the `loop` CLI can independently validate and score.

## What it shows

`graph_example.py` runs two plain-function nodes:

- `do_work` writes `artifact.txt`.
- `certify` — the only edge into `END` — runs the same **visible + withheld
  holdout** split the loop optimized against through the real `holdout_gate.decide`
  and `anticheat_scan.scan`, projects the verdict through `to_terminal_state`,
  and records it via `loop.emit`. It writes two evidence artifacts a scorecard
  can join: the verbatim gate verdict (`holdout-verdict.json`) and a verify
  bundle (`verify-T1.json`).

On a real pass the terminal is `Succeeded` with evidence, and `loop metrics`
scores the run clean: `false_completion_rate 0.0`, `evidence_backed: true`, the
two FCR methods agree.

### The `--sabotage-holdout` false-completion demo

```bash
python graph_example.py sabotaged-run/ --sabotage-holdout
```

`do_work` now writes output that passes the **visible** check (the file exists)
but fails the **holdout** (the content is wrong). That is the measurable
false-completion event: the terminal becomes `FailedUnverifiable` with
`false_completion: true` — **never** `Succeeded`. The dishonest completion is
recorded, not laundered.

## Run it

```bash
pip install loop-engineer langgraph
python graph_example.py demo-run/
loop doctor demo-run/            # -> {"ok": true, ...}
loop metrics demo-run/           # -> clean scorecard
```

The gate tools (`holdout_gate`, `anticheat_scan`) resolve from `loop._resources`
— the wheel bundles them, so a plain `pip install` is enough; running from a
repo checkout picks them up from `scripts/` too.

## The general pattern

The complement framing and the copy-paste (zero-install) projection live in
[`docs/integrations/langgraph.md`](../../docs/integrations/langgraph.md).
