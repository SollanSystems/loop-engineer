# Adoption Slices — pre-launch design

*2026-07-03. Follows the v1.0 roadmap (`docs/ROADMAP-v1.0.md`); executes its ST3
lane and extends it with a packaging substrate and two enforcing adapters. All
work lands before `M5-LAUNCH` fires.*

## Problem

v0.6.0 is credibility-complete but adoption-thin. Every shipped artifact proves
the tool is honest about *itself* (gate-backed example, derived FCR/RP baseline,
red-teamed metrics). Nothing makes it trivial to attach to *someone else's*
repo, runtime, or pipeline — the only on-ramp is `git clone` plus a full repo-OS
scaffold. Launch traffic that cannot answer "how do I use this with MY stack"
bounces.

## Goal

One thin, enforcing slice per adopter persona, on a shared packaging substrate:

| Persona | Slice | Adoption artifact |
|---|---|---|
| any (substrate) | S0 self-contained wheel + PyPI | `uvx loop-engineer inspect .` |
| framework devs | B1 `loop/emit.py` + LangGraph recipe | 10-line integration |
| Claude Code users | A1 Stop-hook firewall | plugin hook, zero config |
| CI engineers | C1 `action.yml` + pre-commit | one workflow step |

"Enforcing" is the selection filter (roadmap principle: enforce, don't
narrate). Docs-only recipes were considered and rejected.

## Scope — five PRs, each independently shippable

```
PR1  S0  self-contained wheel + PyPI publish            (do first)
PR2  B1  loop/emit.py writer API + LangGraph recipe
PR3  A1  Stop-hook false-completion firewall            (parallel with PR4)
PR4  C1  action.yml + .pre-commit-hooks.yaml            (parallel with PR3)
PR5  docs: README "Adopt in your stack" + show-hn.md leads with uvx
```

Launch (`M5-LAUNCH`) is minimally gated on **PR1 + PR5**; PR2–PR4 are
strongly-want-before but individually droppable if one stalls.

## PR1 — S0: PyPI substrate

The pyproject currently documents the wheel as editable-install-only:
`inspect`/`metrics` resolve `scripts/` relative to the repo, and a built wheel
ships neither `scripts/` nor `schemas/` nor `templates/`.

- Package `schemas/`, `templates/`, and the CLI-needed tool scripts
  (`inspect_loop`, `metrics`, and the holdout/anticheat entry points the CLI
  invokes) as package data. Resolution order: `importlib.resources` first,
  existing repo-relative path as the editable-install fallback.
- Publish `loop-engineer` to PyPI (name verified free, 404 on 2026-07-03) via a
  tag-triggered GitHub Actions workflow using a trusted publisher — no token in
  the repo. Claim the name with the next patch release immediately after merge.
- Console script stays `loop`; `python3 -m loop` from a clone keeps working.
- Funnel this enables: `uvx loop-engineer inspect .` on a stranger's repo scores
  `0/weak` → `uvx loop-engineer scaffold` starts the fix. Before/after on
  *their own repo* is the adoption moment and the HN post's first command.

**Acceptance:** a test builds the wheel and runs `doctor`, `inspect`, and
`scaffold` from a temp dir with the repo checkout absent; publish workflow
green on a tag; editable install still passes the full suite.

## PR2 — B1: emit API + one recipe

- `loop/emit.py`, pure stdlib, ~5 functions: open a contract (delegates to the
  existing scaffold renderer), append an iteration/receipt, write
  `terminal_state.json`. The writer **refuses an evidence-free `Succeeded`** —
  the G1 cross-check enforced at write time, not only at validate time. Output
  is schema-valid by construction.
- One recipe done well: `docs/integrations/langgraph.md` + a small runnable
  example — a LangGraph graph whose terminal node calls `emit.terminate(...)`,
  with a CI snippet running `loop doctor`. LangGraph is a dev dependency of the
  example only; the package stays zero-dependency. Verify the current LangGraph
  API surface via Context7 before authoring.

**Acceptance:** `test_emit.py` proves schema-valid outputs and the evidence-free
`Succeeded` refusal; the recipe example runs end-to-end and its emitted contract
passes `doctor`.

## PR3 — A1: Stop-hook false-completion firewall

- Plugin ships a Stop hook (registered in `.claude-plugin/plugin.json`): on
  session stop, if the CWD has a `.loop/` directory, run `python3 -m loop
  doctor` plus the terminal cross-check. If the contract claims `Succeeded` and
  doctor says `ok:false`, the hook returns blocking feedback carrying the doctor
  issues, so the agent cannot end the turn on a false "done."
- Strict no-op when no `.loop/` exists — zero cost for every other repo.
- Fail-open on any hook error: a broken firewall must never lock a session.
- CLI resolution order: installed `loop` if present, else `python3 -m loop`
  via `CLAUDE_PLUGIN_ROOT` — marketplace installs work without pip.

**Acceptance:** hook exercised offline against fixture `.loop/` dirs — honest
(passes silently), lying (blocks with issues), absent (no-op) — plus a
forced-error fixture proving fail-open.

## PR4 — C1: GitHub Action + pre-commit

- In-repo composite `action.yml`: setup-python → `pip install
  loop-engineer==<pinned>` → `doctor` + `inspect` → scorecard as job summary,
  optional PR comment. `doctor` failure fails the job; `inspect` verdict is
  warn-only by default with a configurable fail threshold.
- `.pre-commit-hooks.yaml` exposing `loop doctor` as a hook id.
- Dogfood: this repo's own CI runs the action against its own `.loop/` — the
  "passes its own gate" story extended to CI.

**Acceptance:** action smoke-run green in this repo's CI on its own contract;
pre-commit hook runs from a consumer-side `.pre-commit-config.yaml` fixture.

## PR5 — docs + launch tie-in

- README gains one "Adopt in your stack" section: three short paths (Claude
  Code hook / any Python runtime via `emit` / CI via action + pre-commit).
- `roadmap/launch/.loop/artifacts/M5-LAUNCH/show-hn.md` first command becomes
  `uvx loop-engineer inspect .`.
- `self_eval` / docs-claims tests updated so every new README claim is
  gate-backed.

## Testing bar

Repo bar as-is: pytest per module; wheel self-containment test; hook fixtures
both honest and lying; docs-claims tests extended; action smoke in CI. Canonical
invocation: `uv run --with pytest --with pyyaml python -B -m pytest -q -p
no:cacheprovider scripts`.

## Risks

- **Scope creep delaying launch** — each PR independently shippable; launch
  gates only on PR1 + PR5.
- **Hook annoyance** — no-op without `.loop/`, fail-open, and the block message
  names the exact doctor issues so it is actionable, never mysterious.
- **PyPI name squat** — publish immediately after PR1 merges.
- **Emit API drifting into a runtime** — it stays a writer: no orchestration,
  no execution. The v1.0 non-goal ("never an execution engine") carries over
  verbatim.

## Non-goals

- No new runtimes, orchestrators, or execution engines.
- No additional recipes beyond LangGraph in this pass (OpenHands/ruflo/Temporal
  remain the ST3 backlog).
- No hosted service, telemetry, or badge endpoint (badge idea deferred).
