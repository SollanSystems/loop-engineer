# Loop Engineer — Master Roadmap: v0.3.4 → v1.0

*Plan/docs deliverable. Authored 2026-06-30. Source of truth: `review/REVIEW.md`,
`review/IMPROVEMENT-BACKLOG.md`, `review/POSITIONING.md`, `review/COMPETITIVE-ANALYSIS.md`.
Nothing here is invented; every task cites a finding ID (G/M/T/O), a backlog item ID
(QW/HI/ST), or is marked `[NEW — beyond review]` with a one-line justification.*

This roadmap is itself dogfooded: `roadmap/v1.0/` is a **validated loop-engineer
contract** (`python3 -m loop doctor roadmap/v1.0` → `ok: true`, 0 issues) that models
this planning milestone as an honest `Succeeded` — see §7. The four strategic design
specs it references (§5) carry the detailed mechanism; this file is the arc, the
sequencing law, and the finding→milestone ledger.

---

## 1. Definition of best — what v1.0 means

The wedge (verified in `COMPETITIVE-ANALYSIS.md` §Whitespace) is that Loop Engineer
owns an essentially empty quadrant: a **portable, typed-termination operating contract
with evidence-before-completion and first-class false-completion defense**, sitting
*above* the execution runtimes. v1.0 is reached when that wedge is not merely narrated
but **true under a skeptic's own tooling**. Four north-star exit criteria:

**N1 — The differentiator is ENFORCED, not self-asserted.**
The single theme of the three HIGH findings (G1, M1, M2) is that false-completion
defense is taken on trust in load-bearing paths. v1.0 requires that:
- No `Succeeded` terminal validates while `false_completion:true` or `criteria_met`
  is empty (closes **G1/QW2**).
- Inspector false-completion-defense credit is granted only on evidence a held-out /
  anti-cheat gate actually ran (closes **M1/HI4**).
- The shipped flagship example actually runs the held-out gate end-to-end (closes
  **M2/HI1**).
- The anti-cheat scanner cannot be silently defanged by rewriting its own gate
  functions (closes **G3/HI6**); an empty visible set cannot certify (closes
  **G2/QW6**).
- **Verify (whole-suite gate):** `uv run --with pytest --with pyyaml python3 -B -m pytest tests scripts -q`
  green with the new regression tests, and `python3 -m loop doctor .loop` → `ok:true`
  on the repo's own live contract.

**N2 — The adoption surface is complete.**
A stranger gets it in 10 seconds and reaches a visible score in 30 with zero install.
Requires the README hero (**QW1**), a weak→strong demo asset (**O2/HI2**), the
three-tier stack + comparison table (**HI3**), a runnable flagship example (**O1/HI1**),
the diagnostic spokes exposed at the router (**T1/QW3**), and the trigger-phrase and
onboarding-friction fixes (**T2-T4/QW9, O3/QW7, O4/QW8, QW4, QW5**).
- **Verify:** `python3 scripts/validate_frontmatter.py` and `python3 scripts/self_eval.py`
  green; `test -f docs/demo.gif`; `python3 -m loop inspect examples/coverage-repair`
  runs clean with no install on a fresh clone.

**N3 — The metrics are real.**
False-completion-rate (FCR) and repair-productivity (RP) are the primitives
`COMPETITIVE-ANALYSIS.md` names as having no competitor; their provenance must be
airtight. Requires one canonical repair record (**M4/QW11**), a recomputed-not-trusted
`productive` flag (**M3/HI5**), and a published baseline derived from a *gate-backed*
run, never a self-asserted one (**ST1**).
- **Verify:** `python3 scripts/self_eval.py` green; the `metrics` command's determinism
  covered by a pytest case; README numbers traceable to a computation over real
  `.loop/` receipts, not prose.

**N4 — The contract is a portable standard.**
A versioned, tool-agnostic spec + published schemas that other harnesses can emit and
consume, closing the last integrity gap (receipts/repair records unvalidated — **M5/ST2**)
and turning every Q3/Q2 engine into a complement via integration recipes (**ST3**).
- **Verify:** `python3 -m loop doctor roadmap/v1.0` → `ok:true` in CI; the schema
  conformance checklist passes; ≥2 integration recipes each produce a valid on-disk
  contract that `validate_contract` accepts.

v1.0 ships only when N1–N4 all hold **and** the launch front door (ST5) is built on top
of a finished N1–N3.

---

## 2. Release arc v0.4.0 → v1.0.0

Each release is a milestone with a theme, the finding/backlog IDs it closes, entry/exit
criteria, and the **one honest sequencing rule** it respects (drawn from
`IMPROVEMENT-BACKLOG.md` §Notes on sequencing). The suggested arc from the review was
followed; refinements are flagged `[refined]` with justification.

### v0.4.0 — "Enforce the wedge"
*The differentiator must survive a skeptic running `doctor`/`inspect`/reading the scanner.*

- **Closes:** G1/QW2, G2/QW6, G3/HI6, G4/QW10, M1/HI4, M2/HI1 (+ onboarding half O1).
  `[refined]` The review's v0.4 seed listed G1,M1,M2,HI4,HI6,HI1; **G2/QW6 and G4/QW10
  are pulled forward into this milestone** because they are gate-integrity/honesty-of-gate
  fixes and this milestone's whole theme is gate integrity — a skeptic reading
  `holdout_gate.py`/`self_eval.py` finds them in the same pass they find G1/G3.
- **Entry:** v0.3.4 baseline green (105 passed / self_eval 13/13 per MEMORY.md).
- **Tasks & Verify:**
  1. **QW2 (G1)** — `_validate_terminal` cross-checks: `Succeeded` requires
     `false_completion is False` **and** ≥1 true `criteria_met` entry.
     *Verify:* `uv run --with pytest --with pyyaml python3 -B -m pytest scripts -q -k terminal_cross` — the contradictory-terminal JSON from REVIEW.md G1 now fails; `doctor` flags it.
  2. **HI4 (M1)** — inspector scores `false_completion_defense` only when
     `holdout_gate.py`/`anticheat_scan.py` invocation is detectable in verify scripts/RUNLOG.
     *Verify:* pytest case "flag set but gate never run → no credit" passes.
  3. **HI1 (M2/O1)** — flagship `examples/coverage-repair` actually runs the held-out
     gate to a real 1-of-7 terminal state; example-local `verify-*` paths resolve from
     the example dir. *Verify:* `python3 -m loop inspect examples/coverage-repair` shows
     gate output as the evidence behind `false_completion:false`; example TASKS verify
     paths resolve (`cd examples/coverage-repair && ls scripts/verify-fast` or relabeled).
  4. **HI6 (G3)** — AST/hash structural invariant over the anticheat gate-decision
     functions; the `return False`-first-line repro now produces a finding.
     *Verify:* pytest case pins the REVIEW.md G3 repro → finding emitted.
  5. **QW6 (G2)** — `holdout_gate.decide`: `if not visible: return NotReady`.
     *Verify:* pytest `decide([], [...passed...])` → NotReady, not Succeeded.
  6. **QW10 (G4)** — rename/comment `self_eval` substring checks as
     documentation-completeness, not behavioral enforcement, wherever `self_eval` is
     described as "the gate." *Verify:* `python3 scripts/self_eval.py` green; grep confirms
     the label change.
  7. **`[NEW — beyond review]` live-contract exit gate** — `python3 -m loop doctor .loop`
     must return `ok:true`. Justification: dogfood gap #4 (§6) found the repo's own
     flagship on-disk contract fails the product's own validator; N1 is not met while
     that is true. *Verify:* `python3 -m loop doctor .loop` → `ok:true`.
- **Exit:** N1 holds. Full suite + self_eval green; the three HIGH findings each have a
  pinned regression; live `.loop` passes doctor.
- **Sequencing rule:** *Wedge-credibility before launch* — close the holes a skeptic
  finds by running `doctor`/`inspect` before any traffic (ST5) is invited.

### v0.5.0 — "First screen"
*The entire first impression: a stranger gets it in 10s, scores a loop in 30s.*

- **Closes:** T1/QW3, T2-T4/QW9, O2/HI2, O3/QW7, O4/QW8, plus positioning-sourced
  QW1, HI3, QW4, QW5 (no finding ID — sourced from POSITIONING.md).
- **Entry:** v0.4.0 shipped (HI1 done — required to film an honest demo).
- **Tasks & Verify:**
  1. **QW1** — README hero: tagline line 1, 3 concrete failure modes, zero-install
     first command. *Verify:* README line 1–3 = tagline + 2-line pain; first fenced cmd
     is a no-install `inspect`; `python3 scripts/self_eval.py` README checks green.
  2. **HI2 (O2)** — `docs/demo.gif` (+ `docs/demo.cast`) of the weak→strong `inspect`
     arc (score ~36 `weak` → ~90 `strong`), embedded at README top + set as social card.
     *Verify:* `test -f docs/demo.gif && test -f docs/demo.cast`; grep README for the embed.
  3. **HI3** — CONTRACT/ORCHESTRATE/EXECUTE stack diagram + verified comparison table
     (7 competitors + LE; columns per POSITIONING §5), honest table-stakes caveat kept.
     *Verify:* grep README for the three tiers + the table header; competitor rows match
     `COMPETITIVE-ANALYSIS.md`.
  4. **QW3 (T1)** — router `SKILL.md:3` + `marketplace.json:5` name the 2 diagnostic
     spokes (loop-inspector, loop-runtime-monitor) + a diagnostic verb.
     *Verify:* `python3 scripts/validate_frontmatter.py` + `python3 scripts/self_eval.py`
     green; grep frontmatter for `inspect`/`audit`/`watch`.
  5. **QW9 (T2/T3/T4)** — trigger-phrase batch (shared "grade" disambiguated,
     `loop-evals` description trimmed into peer length band, `loop-run` first example
     qualified). Ride QW3's frontmatter edit. *Verify:* `validate_frontmatter.py` green;
     `loop-evals` description back in the ~400–510-char band.
  6. **QW7 (O3)** — CONTRIBUTING gains the local-marketplace staleness-trap note.
     *Verify:* grep CONTRIBUTING.md for `marketplace`/`refresh`/`stale`.
  7. **QW8 (O4)** — `[project.scripts] loop = "loop.__main__:main"`, preserving relative
     `scripts/` resolution. *Verify:* pytest confirms relative resolution when invoked
     as `loop`; `python3 -m loop` still works.
  8. **QW4** — GitHub About + topics (add 8 discovery/category terms), own
     "false completion" + "loop engineering". *Verify:* metadata-only; checklist in PR.
  9. **QW5** — PRs to ≥2 community discovery lists (awesome-claude-code /
     -plugins). *Verify:* PR links tracked in the release notes.
- **Exit:** N2 holds. The QW1+HI2+HI3 batch (POSITIONING §8 "the one thing") ships
  together; frontmatter/self_eval green.
- **Sequencing rule:** *HI1 gates HI2* — you cannot honestly film the money-shot demo
  over an example that self-asserts completion; the runnable, gate-backed example (v0.4)
  is the prerequisite for the GIF.

### v0.6.0 — "Metrics real"
*Turn FCR and repair-productivity from claims into derivations with a published baseline.*

- **Closes:** M4/QW11, M3/HI5, ST1.
- **Entry:** v0.4.0 (HI1 + HI4) shipped — a real gated run and honest credit exist.
- **Tasks & Verify:**
  1. **QW11 (M4)** — canonicalize "the repair record": one 7-field schema (or
     `eval-suite.md` states which is canonical for RP and how the two relate).
     *Verify:* `python3 scripts/self_eval.py` structural checks green; schema referenced
     from both `rollout_ledger.py` and `evals/cases/structural.json`.
  2. **HI5 (M3)** — repair-record validator recomputes `productive` from
     `verification_before/after` and rejects mismatches; `summarize()` aggregates only
     validated records. *Verify:* pytest — a disagreeing record is rejected.
  3. **ST1** — `metrics` command derives FCR + RP from real `.loop/` receipts/RUNLOG;
     a checked-in baseline computed over the gate-backed HI1 example; README numbers
     sourced from that computation. *Verify:* pytest determinism case;
     `python3 -m loop metrics examples/coverage-repair` reproduces the checked-in baseline.
- **Exit:** N3 holds. Baseline is reproducible and traceable to a gated run.
- **Sequencing rule:** *No FCR baseline over a self-asserted example, and QW11 gates ST1*
  — the canonical repair schema must exist before RP is derived, and the baseline must
  post-date HI1/HI4 or it would itself be a false completion.

### v0.7.0 — "Portable standard"
*The contract becomes a documented, versioned, tool-agnostic format — and the repo's own
templates/contract stop lying to it.*

- **Closes:** M5/ST2, plus the dogfood template/validator drift (§6 gaps #1,#2,#3,#5).
- **Entry:** v0.6.0 (QW11) shipped — a canonical repair record exists to schematize.
- **Tasks & Verify:**
  1. **ST2 (M5)** — versioned spec doc + published JSON schemas for
     `state.json`/`TASKS.json`/receipt/repair-record + stability/version note +
     conformance checklist; `validate_contract` optionally checks `.loop/receipts/*.jsonl`
     and repair-record files when present. *Verify:* `python3 -m loop doctor roadmap/v1.0`
     → `ok:true` in CI; pytest over the conformance checklist.
  2. **`[NEW — beyond review]` template↔validator reconciliation** (dogfood gaps #1,#3) —
     templates emit `schema` (not `schema_version`); manifest + JSON companions use one
     consistent schema key. Justification: dogfood found a contract scaffolded straight
     from `templates/` fails `doctor` with `schema_mismatch`. *Verify:* `python3 -m loop
     doctor` on a freshly-scaffolded-from-template contract → `ok:true`.
  3. **`[NEW — beyond review]` terminal-template completeness** (dogfood gap #2) —
     `templates/terminal_state.json.tmpl` carries top-level `criteria_met`,
     `false_completion`, and a top-level `evidence` list. Justification: template
     scaffolding currently yields 3 `invalid_terminal` issues. *Verify:* scaffold →
     `doctor` → 0 terminal issues.
  4. **`[NEW — beyond review]` `Planned`/`NotStarted`/`Deferred` state design** (dogfood
     gap #5) — spec the first-class "planned but not yet started" representation into
     ST2's versioned contract. Justification: a roadmap-as-contract had to express this
     indirectly via a `Succeeded` planning milestone + `pending_approval`. *Verify:*
     design section present in the ST2 spec; no runtime change required this milestone.
- **Exit:** N4's standard-half holds. The spec is published; templates, the live
  contract, and doctor agree.
- **Sequencing rule:** *You cannot publish a portable standard while your own reference
  contract and templates fail your own validator* — reconcile the dogfood drift before
  inviting other harnesses to emit the format.

### v0.8.0 — "Composes the field"
*Every 50K-star engine becomes a complement that needs you.*

- **Closes:** ST3, ST4.
- **Entry:** v0.7.0 (ST2) shipped — a stable format exists for adapters to target.
- **Tasks & Verify:**
  1. **ST3** — integration recipes for ≥2 of {LangGraph terminal-node → typed terminal
     state, Temporal workflow → repo-OS contract, OpenHands run → FCR gate, ruflo swarm →
     acceptance gate}, each a runnable snippet + resulting terminal-state/evidence
     mapping. *Verify:* each recipe produces an on-disk contract that
     `python3 -m loop doctor <recipe-out>` accepts.
  2. **ST4** — contributor funnel: ≥4 `good first issue`/`help wanted` (the QW3/QW9
     trigger fixes as labeled issues once shipped are examples of the *class*), a 2nd
     runnable example, and a read-only foreign-harness `inspect` adapter + checked-in
     gap report. *Verify:* `python3 -m loop inspect <foreign-harness-dir>` produces a
     scored report; the 2nd example passes `doctor`.
- **Exit:** N4 fully holds — the standard is not just published but demonstrably ridden
  by external engines.
- **Sequencing rule:** *Compose, don't compete* — never claim to replace an execution
  engine; every recipe wraps, never swaps, the underlying runtime (POSITIONING §7 DON'T).

### v1.0.0 — "Launch"
*The front door is finished; open it.*

- **Closes:** ST5.
- **Entry:** N1–N3 hold and the launch prerequisites (HI1 v0.4, HI2 + HI3 v0.5, ST1 v0.6)
  are all shipped.
- **Tasks & Verify:**
  1. **ST5** — Show HN / r/ClaudeAI / r/LocalLLaMA post led by the HI2 GIF; a
     `false completion` blog/dev.to post embedding the HI3 diagram; two-way cross-link
     with `claude-code-orchestration`'s `/verify-slice`. *Verify:* the demo (HI2), hero
     (QW1), table (HI3), and baseline (ST1) all present on `main` before posting —
     a checklist gate, not a code test.
- **Exit:** v1.0 tagged; N1–N4 all hold; launch surfaces live.
- **Sequencing rule:** *Launch last* — a launch without the weak→strong GIF and the
  honest, gate-backed example is a wasted first impression at 0★
  (`IMPROVEMENT-BACKLOG.md` §Notes: ST5 gated on HI1+HI2+HI3).

---

## 3. Dependency graph

The four EXACT invariants from `IMPROVEMENT-BACKLOG.md` §Notes on sequencing are
preserved and shown as hard edges:

```
 v0.4 ENFORCE THE WEDGE                     v0.5 FIRST SCREEN
 ┌─────────────────────────────┐           ┌───────────────────────────┐
 │ QW2(G1) QW6(G2) HI6(G3)      │           │ QW1  QW3(T1) QW4 QW5       │
 │ QW10(G4) HI4(M1) HI1(M2/O1)  │           │ QW7(O3) QW8(O4) QW9(T2-4)  │
 │  ── wedge-credibility ──     │           │ HI2(O2)  HI3               │
 │     {QW2,HI1,HI4,HI6} ───────┼───┐       └───────────────────────────┘
 └──────────┬───────────┬───────┘   │            ▲          │        │
      HI1 ──┤           └── HI4 ──┐  │            │ HI1      │ HI2    │ HI3
            │                     │  │  (gates)   │ gates    │        │
            ▼ (gates HI2)         ▼  │            │ HI2      ▼        ▼
     ┌──────────────┐        v0.6 METRICS REAL    │      v1.0 LAUNCH (ST5)
     │  HI2 (v0.5)  │        ┌──────────────────┐ │      gated on HI1+HI2+HI3
     └──────────────┘        │ QW11(M4) ─gates─▶ │ │      (+ ST1 baseline)
                             │ HI5(M3)   ST1    │◀┘
                             │ ST1  ◀─ needs HI1+HI4 (no baseline over
                             └────────┬─────────┘  a self-asserted example)
                                      │ ST1 needs QW11 + HI1
                                      ▼
                             v0.7 PORTABLE STANDARD
                             ┌──────────────────────────┐
                             │ ST2(M5) + template/       │  needs QW11 (canonical
                             │ validator drift + states  │  repair record) to schematize
                             └───────────┬──────────────┘
                                         │ ST2 = the format adapters target
                                         ▼
                             v0.8 COMPOSES THE FIELD
                             ┌──────────────────────────┐
                             │ ST3 recipes · ST4 funnel  │
                             └───────────┬──────────────┘
                                         ▼  (all N1–N3 + launch assets in place)
                             v1.0 LAUNCH · ST5
```

**The four preserved invariants, called out explicitly:**
1. **Wedge-credibility (QW2/HI1/HI4/HI6) before launch/GIF.** All four land in v0.4,
   strictly before HI2 (v0.5 GIF) and ST5 (v1.0 launch).
2. **HI1 gates HI2 and ST1.** HI1 is in v0.4; HI2 (v0.5) and ST1 (v0.6) both come after.
3. **QW11 gates ST1.** Both are in v0.6; QW11 is sequenced first within the milestone.
4. **No FCR baseline over a self-asserted example.** ST1 (v0.6) depends on HI1 **and**
   HI4 (both v0.4) so the baseline is computed only over a gate-backed run.

---

## 4. Mapping table — every finding & every backlog item

Nothing is dropped. Milestone column is the release that closes it.

### 4a. Review findings (§3 of REVIEW.md)

| ID | Dimension / severity | Backlog item | Milestone |
|---|---|---|---|
| G1 | gate-integrity HIGH | QW2 | v0.4 |
| G2 | gate-integrity MEDIUM | QW6 | v0.4 |
| G3 | gate-integrity MEDIUM | HI6 | v0.4 |
| G4 | gate-integrity LOW | QW10 | v0.4 |
| M1 | metric-honesty HIGH | HI4 | v0.4 |
| M2 | metric-honesty HIGH | HI1 | v0.4 |
| M3 | metric-honesty MEDIUM | HI5 | v0.6 |
| M4 | metric-honesty MEDIUM | QW11 | v0.6 |
| M5 | metric-honesty LOW | ST2 | v0.7 |
| T1 | trigger-quality MEDIUM | QW3 | v0.5 |
| T2 | trigger-quality LOW | QW9 (batch) | v0.5 |
| T3 | trigger-quality LOW | QW9 (batch) | v0.5 |
| T4 | trigger-quality LOW | QW9 (batch) | v0.5 |
| O1 | onboarding-dx MEDIUM | HI1 | v0.4 |
| O2 | onboarding-dx MEDIUM | HI2 | v0.5 |
| O3 | onboarding-dx MEDIUM | QW7 | v0.5 |
| O4 | onboarding-dx LOW | QW8 | v0.5 |
| docs-honesty | **none surfaced** | — | — (nothing to close; audited clean) |

### 4b. Backlog items (IMPROVEMENT-BACKLOG.md)

| ID | Title (abbrev) | Finding(s) | Milestone |
|---|---|---|---|
| QW1 | README hero | (positioning) | v0.5 |
| QW2 | terminal cross-check | G1 | v0.4 |
| QW3 | diagnostic spokes to router/marketplace | T1 | v0.5 |
| QW4 | GitHub metadata/SEO | (positioning) | v0.5 |
| QW5 | awesome-list PRs | (positioning) | v0.5 |
| QW6 | empty visible → NotReady | G2 | v0.4 |
| QW7 | staleness-trap doc | O3 | v0.5 |
| QW8 | console-script `loop` | O4 | v0.5 |
| QW9 | trigger-phrase batch | T2, T3, T4 | v0.5 |
| QW10 | honest self_eval labels | G4 | v0.4 |
| QW11 | canonical repair schema | M4 | v0.6 |
| HI1 | runnable flagship example | M2, O1 | v0.4 |
| HI2 | weak→strong demo GIF | O2 | v0.5 |
| HI3 | three-tier stack + table | (positioning) | v0.5 |
| HI4 | honest inspector credit | M1 | v0.4 |
| HI5 | enforce `productive` | M3 | v0.6 |
| HI6 | anticheat structural invariant | G3 | v0.4 |
| ST1 | published FCR/RP baseline + metrics CLI | (metric-honesty + competitive) | v0.6 |
| ST2 | versioned portable contract spec + schemas | M5 | v0.7 |
| ST3 | integration recipes | (positioning + competitive) | v0.8 |
| ST4 | contributor funnel | (positioning) | v0.8 |
| ST5 | launch surfaces | (positioning) | v1.0 |

**Nothing is deferred past v1.0.** All 17 enumerable findings and all 22 backlog items
route to a milestone in the v0.4→v1.0 arc.

### 4c. Note on REVIEW.md's internal count inconsistency

REVIEW.md is internally inconsistent about its own finding count and this roadmap sides
with the enumerable/backlog-consistent number:
- REVIEW.md §1 and §4 (the count table) both claim **18 total** and **6 metric-honesty**
  findings (2 HIGH / 2 MEDIUM / 2 LOW).
- But REVIEW.md §3.2 only **enumerates 5 metric-honesty findings** (M1–M5 = 2 HIGH /
  2 MEDIUM / **1 LOW**), giving **17 enumerable findings**.
- `IMPROVEMENT-BACKLOG.md` §"Dimension coverage this pass" agrees with the *enumerated*
  count: metric-honesty = **5** (2 HIGH + 2 MEDIUM + 1 LOW).

There is no M6 anywhere in the text, so the "6 / 18" figures appear to be a
tally error; the mapping above covers the 17 findings that actually exist (M1–M5) plus
docs-honesty=none. If a sixth metric-honesty finding is ever recovered, it would route to
v0.6 with the other metric work.

---

## 5. Strategic design specs (mechanism lives here)

The four strategic specs authored 2026-06-30 carry the detailed enforcement/format
design; each milestone above delegates its mechanism to one of them:

| Spec | Drives milestone | Closes |
|---|---|---|
| [`docs/superpowers/specs/2026-06-30-v04-credibility-enforcement.md`](../specs/2026-06-30-v04-credibility-enforcement.md) | v0.4 | G1/QW2, G2/QW6, G3/HI6, M1/HI4, M2/HI1 + the dogfood live-contract gate |
| [`docs/superpowers/specs/2026-06-30-st1-metrics-baseline.md`](../specs/2026-06-30-st1-metrics-baseline.md) | v0.6 | ST1, M3/HI5, M4/QW11 |
| [`docs/superpowers/specs/2026-06-30-st2-portable-contract-spec.md`](../specs/2026-06-30-st2-portable-contract-spec.md) | v0.7 | ST2/M5 + template/validator drift + the `Planned` state design |
| [`docs/superpowers/specs/2026-06-30-st3-integration-adapters.md`](../specs/2026-06-30-st3-integration-adapters.md) | v0.8 | ST3, ST4 |

*(The contract in `roadmap/v1.0/specs/spec-1..4-*.md` mirrors these four as the
contract's own internal spec set; the canonical, dependency-free copies are the
`docs/superpowers/specs/` files listed above.)*

---

## 6. Dogfood — gaps found by self-hosting

These are **real defects surfaced by authoring this roadmap as a loop-engineer contract
against the live validator (`loop/contract.py`)**, logged in `roadmap/v1.0/RUNLOG.md`.
They are not in the original review; each is routed to a milestone (mostly v0.7, the
template/validator-drift milestone). Marked `[NEW — beyond review]` throughout.

| # | Dogfood gap | Route | How it's closed / Verify |
|---|---|---|---|
| 1 | **Template `schema_version` vs validator `schema` drift** — `templates/state.json.tmpl` & `terminal_state.json.tmpl` emit `"schema_version":"1.0"` but the validator checks key `schema` (`loop-engineer/state@1`, `…/terminal@1`); a from-template scaffold fails `doctor` with `schema_mismatch (got None)`. | v0.7 (task 2) | Templates emit `schema`. *Verify:* scaffold-from-template → `python3 -m loop doctor <dir>` → `ok:true`. |
| 2 | **Terminal template missing required fields** — no `criteria_met`, no `false_completion`; `evidence` nested under `verification_evidence` instead of a top-level list. `_validate_terminal` requires all three at top level → 3 `invalid_terminal` issues. | v0.7 (task 3) | Template carries the three top-level fields. *Verify:* scaffold → `doctor` → 0 terminal issues. |
| 3 | **Manifest template uses `schema:` while its JSON companions use `schema_version:`** — the shipped template set is internally inconsistent on the very field that names the schema. | v0.7 (task 2) | One consistent schema key across manifest + companions. *Verify:* grep templates for a single `schema` key convention. |
| 4 | **The repo's OWN live contract fails doctor** — `python3 -m loop doctor .loop` → `ok:false` (state/TASKS/terminal carry `schema_version`; terminal lacks `criteria_met`/`false_completion`). The flagship on-disk contract does not pass the product's own gate. | **v0.4** (task 7, release-blocking exit gate) | Migrate the live `.loop` to the validated shape. *Verify:* `python3 -m loop doctor .loop` → `ok:true`. |
| 5 | **No `Planned`/`NotStarted`/`Deferred` state exists** — the 7 states are all terminal and the FSM starts at `intake`; there is no first-class way to mark a milestone "planned but not started" (a roadmap-as-contract needs exactly this). Had to express it via a `Succeeded` planning milestone + a `pending_approval` block. | v0.7 (task 4) | Design the planned/deferred representation into the ST2 versioned spec. *Verify:* design section present in the ST2 spec. |
| 6 | **`doctor` has no `--strict` cross-field mode** — because G1 is an un-enforced hole, dogfooding cannot ask doctor to enforce the honesty this contract practices voluntarily. | **v0.4** (folds into QW2/G1) | The QW2 cross-field rule makes the honesty mandatory (a `--strict` surface is optional once the rule is unconditional). *Verify:* the G1 regression test (§2 v0.4 task 1). |

Routing summary: gaps #4 and #6 are pulled into **v0.4** (they are wedge-enforcement /
live-contract-integrity, and #4 is an explicit N1 exit blocker); gaps #1, #2, #3, #5 land
in **v0.7** where the template/validator drift is reconciled as part of publishing the
portable standard.

---

## 7. `roadmap/v1.0/` is a validated contract — the positive contrast to G1/M2

`roadmap/v1.0/` is not just documentation; it is a **loop-engineer contract that passes
the product's own gate**:

- `python3 -m loop doctor roadmap/v1.0` → **`ok: true`, 0 issues** (passed on the first
  run and again with the full file set).
- Its terminal is an **honest `Succeeded`** for the *planning* milestone only:
  `false_completion:false`, all-true `criteria_met` — every criterion is a real artifact
  (this roadmap, the four specs, the mapping table) that exists on disk.
- The v1.0 **release** is deliberately **withheld as human-gated**
  (`state.json.pending_approval`), not silently marked done.

This is the deliberate inverse of findings **G1** (a `Succeeded` terminal with
`false_completion:true` validating clean) and **M2** (a flagship example asserting
`false_completion:false` with no gate ever run): here the success terminal is
internally consistent *and* evidence-backed, and the un-earned part of the goal (shipping
v1.0) is honestly parked in `pending_approval` instead of claimed. The roadmap practices
the enforcement that v0.4 will make mandatory for everyone.
*Verify:* `python3 -m loop doctor roadmap/v1.0` → `ok:true`.

---

*End of roadmap. Every milestone task above carries a concrete `Verify:` command
(pytest / self_eval / doctor / inspect / file check). Canonical test invocation per
project memory: `uv run --with pytest --with pyyaml python3 -B -m pytest tests scripts -q`.*
