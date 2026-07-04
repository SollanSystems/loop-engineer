# LangGraph — proof-of-done in 10 lines

`loop.emit` is a pure-stdlib writer: your graph keeps its own runtime, and the
terminal node records evidence-backed state the `loop` CLI can independently
validate. `pip install loop-engineer` (LangGraph itself stays your dependency).

```python
from loop import emit

emit.open_contract("run/")                                   # once, before the graph runs

def conclude(state):                                          # your graph's terminal node
    emit.append_iteration("run/", iteration_id=1, outcome="task_passed",
                          task_id="T1", verify_cmd="pytest -q", verify_outcome="pass")
    emit.terminate("run/", state="Succeeded",
                   criteria_met={"tests": True}, evidence=["reports/pytest.txt"])
    return {}
```

`emit.terminate` **refuses an evidence-free `Succeeded`** (raises `EmitError`) —
the same cross-check `loop doctor` enforces, applied before the file exists.

Gate it in CI:

```yaml
- run: pip install loop-engineer
- run: loop doctor run/
```

Full runnable example: [`examples/langgraph-emit/`](../../examples/langgraph-emit/).
