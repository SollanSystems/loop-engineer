<!-- title: Foreign-harness gap reports — the inspect scoreboard pipeline -->
<!-- labels: help wanted -->

# Foreign-harness gap reports — the inspect scoreboard pipeline

Contribute a read-only `loop inspect` gap report for another public harness layout —
the second entry in an "inspect N public harnesses" scoreboard.

## Problem / opportunity

`docs/gap-reports/superpowers.md` is the template and the first entry. **Composes,
doesn't compete:** a gap report reads a foreign layout read-only and names the gaps a
loop-contract would *close* at the finish line — it is not a criticism of the foreign
harness or of the (fictional) work in the fixture. `inspect` labels a foreign layout
`advisory: true`; a foreign layout is read for gaps, never graded as a failing
contract.

The template's provenance rules are load-bearing:

- every claim is checkable against **one vendored, sanitized fixture** checked into
  `examples/` — no version-general claims about the foreign harness itself;
- the report carries the §14 A1–E1 conformance table (condensed from
  `reference/repo-os-contract.md` §14), read against that fixture;
- complement framing throughout ("composes, doesn't compete").

## Proposal

For another public harness layout: vendor a fictional, sanitized fixture under
`examples/<harness>-run/`, then author `docs/gap-reports/<harness>.md` following
`docs/gap-reports/superpowers.md` — the provenance blockquote, the §14 A1–E1 table,
the `inspect` reading, and "what emitting the contract would add," with every factual
claim restricted to the fixture.

## The gate that proves the fix

```bash
python3 -m loop inspect examples/<harness>-run   # produces a scored report
```

The exit criteria follow the `scripts/test_foreign_inspect.py` patterns (scored,
`foreign_layout` labeled, `advisory: true`), and the report follows the template's
provenance rules.
