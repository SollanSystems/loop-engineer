# naive-loop — the deliberately weak fixture

This is the "before" subject of the demo GIF: a typical DIY agent loop whose
entire completion story is a self-asserted flag in `.loop/state.json`. No
success criteria, no independent verification, no approval gates, no typed
terminal states — just `"status": "completed"`.

Score it yourself:

```bash
python3 -m loop inspect examples/naive-loop
```

The inspector gives it **score 0, verdict `weak`** (exit code 1) and lists every
missing proof mechanism. Contrast with the gate-backed example:

```bash
python3 -m loop inspect examples/coverage-repair   # score 90, verdict strong
```

Nothing here is a strawman: this shape — a status field somewhere that the
agent itself sets — is how most ad-hoc agent loops record "done" today.
