# Gap report — Superpowers (foreign-harness inspect)

> **Provenance.** Evaluated **only** against the vendored fixture
> [`examples/superpowers-run/`](../../examples/superpowers-run/) — fictional,
> sanitized content, checked in. No version-general claims about Superpowers
> itself are made or implied: every statement below is checkable against that
> one directory.
> **Date:** 2026-07-08.
> **Reproduce:** `python3 -m loop inspect examples/superpowers-run`

## Composes, doesn't compete

Superpowers is a skills library — it drives *how* an agent works. The fixture
vendors exactly the layout such a run leaves behind: a design spec under
`docs/superpowers/specs/`, a plan of `- [x]` checkboxes under
`docs/superpowers/plans/`, and a prose `progress.md` journal. Loop Engineer is
the contract layer — it proves *how the work ended*. The two **compose**: a
Superpowers-driven run can emit a Loop-Engineer contract at the finish line.
This report is not a criticism of Superpowers or of the (fictional) work in the
fixture; the low score below measures only what a spec/plan/journal layout
*structurally cannot prove*.

## §14 conformance — read against the fixture

The "What the standard requires" column is condensed from
[`reference/repo-os-contract.md`](../../reference/repo-os-contract.md) §14.

| Item | What the standard requires | Fixture status |
|---|---|---|
| A1 | `.loop/manifest.yaml` valid against `manifest@1` incl. the canonical 7 `terminal_states` | **unmet** — no `.loop/` exists |
| A2 | `.loop/state.json` valid against `state@1` | **unmet** |
| A3 | `TASKS.json` valid against `tasks@1` (no dup ids; no evidence-free `done`) | **unmet** — plan checkboxes carry no evidence field at all |
| A4 | `RUNLOG.md` present | **unmet** — the journal (`progress.md`) narrates but is not an iteration log |
| B1 | exactly-one-of: no terminal vs valid terminal pair | **structurally unprovable** — the layout has no terminal record; "marking the work complete" lives in prose |
| B2 | `terminal@1` with `criteria_met`/`evidence`/`false_completion`; honest `Succeeded` rules | **structurally unprovable** |
| C1–C3 | receipts / repair / rollout validate when present | **absent** (nothing to check — and nothing to mine for FCR/RP) |
| D1–D2 | versioned `schema` keys; additive tolerance | **unmet** — no artifact carries a schema id |
| E1 | `doctor` lifecycle report consistent with B1 | **unmet** — `doctor` (correctly) refuses: no contract |

Each row is checkable against the fixture: `examples/superpowers-run/` contains
only `README.md`, `docs/superpowers/specs/2026-07-08-csv-dedupe-design.md`,
`docs/superpowers/plans/2026-07-08-csv-dedupe.md`, and
`.superpowers/sdd/progress.md`. There is no `.loop/`, no `schema:` key in any
file, and `progress.md`'s closing line is the prose "Marking the work
complete." — the exact false-completion surface B1/B2 exist to make typed.
Running `python3 -m loop doctor examples/superpowers-run` returns `ok: false`
with `lifecycle: unknown` and `missing_file` issues for every contract
artifact (E1).

## `inspect` reading

```json
{
  "target": "examples/superpowers-run",
  "score": 12,
  "terminal_states_covered": 0,
  "present": [
    "defines verifiable success criteria"
  ],
  "gaps": [
    "no independent verification (verify-* script / TASKS verify command) — success is self-asserted",
    "no approval gates declared for side-effects (destructive / secret / production / money)",
    "no false-completion defense: no recorded holdout/anti-cheat invocation (a self-asserted false_completion flag or prose mention earns no credit)",
    "no plan-then-execute discipline for untrusted/web reads (prompt-injection surface)",
    "0/7 terminal states present — missing Succeeded, FailedUnverifiable, FailedBlocked, FailedBudget, FailedSafety, FailedSpecGap, AbortedByHuman (loop can end in a silent 'completed')"
  ],
  "verdict": "weak",
  "foreign_layout": "superpowers",
  "advisory": true
}
```

The fixture scores **weak** (`score: 12`, `terminal_states_covered: 0`),
labeled `foreign_layout: superpowers` and `advisory: true`. Read this plainly:
the low score measures what the layout *cannot prove*, not the quality of the
work, nor of Superpowers. `advisory: true` is the whole point — a foreign
layout is read for gaps, never graded as a failing contract.

## What emitting the contract would add

- **A typed terminal instead of prose "complete."** The `Succeeded`/`Failed*`
  record replaces `progress.md`'s free-text "Marking the work complete." with
  one of the canonical 7 states plus a `false_completion` boolean.
- **A held-out gate that makes false completion *measurable*.** An
  anti-cheat/holdout invocation is what turns "tests pass locally" into a
  third-party-checkable verdict — the missing `false-completion defense` gap.
- **An evidence trail.** `criteria_met` maps each success criterion to a check;
  verify bundles under `.loop/artifacts/` back the terminal instead of a
  self-assertion.
- **FCR / RP derivable by `loop metrics`.** With receipts and repair records on
  disk, false-completion-rate and repair-productivity are *computed*, not
  claimed (the C1–C3 "nothing to mine for FCR/RP" gap).

The *how* is small: four `loop.emit` calls — `open_contract`,
`append_iteration`, `append_receipt`, `terminate` — at the run's finish line.
That path is worked end-to-end for a real engine in
[`docs/integrations/langgraph.md`](../integrations/langgraph.md).

## This is a seed

This is the first entry in an "inspect N public harnesses" scoreboard: read a
foreign layout read-only, name the gaps a contract would close, keep every
claim checkable against a vendored fixture. Contributions of further gap
reports are welcome — this file is the template. See the drafted contributor
issue
[`docs/contributing/issues/06-help-wanted-gap-reports.md`](../contributing/issues/06-help-wanted-gap-reports.md)
(`help wanted: gap reports`, filed on GitHub at release).
