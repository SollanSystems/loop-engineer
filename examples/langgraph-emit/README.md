# LangGraph recipe — proof-of-done through `loop.emit`

A runnable [LangGraph](https://github.com/langchain-ai/langgraph) graph whose
**terminal node writes the loop contract** — evidence-backed state the `loop`
CLI can independently validate. LangGraph keeps its own runtime; `loop.emit` is
a pure-stdlib writer that refuses to record a dishonest result.

## What it shows

`graph_example.py` runs three plain-function nodes — `do_work` writes
`artifact.txt`, `verify` re-reads it from disk, and `conclude` records the
outcome:

- On a real pass, `conclude` calls `emit.terminate(..., state="Succeeded",
  evidence=["artifact.txt"])`.
- A lying `Succeeded` — no evidence, or no met criterion — raises `EmitError`
  **before anything hits disk**. That is the same cross-check `loop doctor`
  enforces, applied at write time.

## Run it

```bash
pip install loop-engineer langgraph
python graph_example.py demo-run/
loop doctor demo-run/          # -> {"ok": true, ...}
```

`demo-run/.loop/terminal_state.json` ends `Succeeded` with `evidence`; `loop
doctor` validates it independently of the graph that wrote it.

## The 10-line integration

The general pattern (any graph, any terminal node) lives in
[`docs/integrations/langgraph.md`](../../docs/integrations/langgraph.md).
