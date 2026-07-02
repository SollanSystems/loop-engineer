# Loop Engineer — v1.0 Roadmap (master doc)

*Authored 2026-06-30. Source of truth for what v1.0 must deliver. Derived entirely
from the 2026-06-30 technical review of v0.3.4:*
`review/REVIEW.md`, `review/IMPROVEMENT-BACKLOG.md`, `review/POSITIONING.md`,
`review/COMPETITIVE-ANALYSIS.md`.

*(Provenance note: `review/` and `roadmap/` are maintainer workbenches, kept
untracked by design — the raw review and the self-hosted planning contract are
not shipped in this repository. Pointers to them are for maintainers.)*

> This roadmap is itself governed by a self-hosted loop-engineer contract at
> `roadmap/v1.0/` (untracked, see above) that passes `python3 -m loop doctor
> roadmap/v1.0` on the maintainer machine. That contract
> wraps only the **planning** milestone (authoring this doc), which is complete.
> **v1.0 the release is not done** and is executed by separate, human-gated runs —
> claiming otherwise would be the exact false completion this roadmap fixes
> (findings G1/M2).

---

## 1. Why v1.0 exists (the one-paragraph thesis)

Loop Engineer's defensible whitespace — verified in `COMPETITIVE-ANALYSIS.md` — is
Q1: a portable, typed-termination **operating contract** with
**evidence-before-completion** and **first-class false-completion defense**, sitting
*above* the execution runtimes. The review's central finding is that this headline
differentiator is **under-enforced by the repo's own code**: three of the four
highest-severity findings all say the same thing — *a loop can self-assert it did
not falsely complete and receive full credit without any held-out or anti-cheat
check ever running*, and the flagship example does exactly that. **v1.0's job is to
make the differentiator true in code, then make it legible and distributable.**
Everything below serves that, in that order.

## 2. The v1.0 release definition (exit criteria)

v1.0 ships when **all** of these hold. Each is release-blocking unless marked
*(stretch)*. Every item traces to a milestone in §4 and a finding/backlog ID in §5.

1. **The differentiator is enforced, not narrated.** `loop doctor`/`validate_contract`
   rejects a `Succeeded` terminal whose `false_completion` is `true` or whose
   `criteria_met` has no true entry (G1/QW2). The inspector awards
   false-completion-defense credit only when a held-out/anti-cheat gate was actually
   invoked (M1/HI4). The held-out gate cannot certify on an empty visible set
   (G2/QW6). The anti-cheat scanner detects logic rewrites of its own gate functions
   (G3/HI6).
2. **The flagship example actually runs a held-out gate, end to end** — or is
   explicitly relabeled inspect-only with the skip documented (M2/HI1). Its
   `verify-*` paths resolve from the example dir.
3. **The loop-health metrics are real numbers with airtight provenance.**
   `repair-productivity` is recomputed from before/after scores and mismatches are
   rejected (M3/HI5). "The repair record" is one canonical 7-field schema (M4/QW11).
   A published FCR / repair-productivity baseline is derived from a genuinely
   gate-backed run (ST1) *(stretch — gated on items 1-2)*.
4. **First-screen comprehension.** README leads with the pain-then-proof hero + a
   zero-install first command (QW1); a weak→strong `inspect` demo GIF sits near the
   top and is the social card (HI2); a three-tier stack diagram + verified comparison
   table frames every competitor as a complement (HI3).
5. **Onboarding friction removed.** The marketplace-staleness trap is documented in
   CONTRIBUTING (O3/QW7); a `loop` console script exists alongside `python3 -m loop`
   (O4/QW8); the `self_eval` doc-completeness checks are honestly labeled (G4/QW10).
6. **Trigger discoverability.** The router description + `marketplace.json` name all
   8 spokes incl. the 2 diagnostic ones and a diagnostic verb (T1/QW3); the three
   low-severity trigger-phrase ambiguities are disambiguated (T2-T4/QW9).
7. **The contract is a versioned, portable standard.** A versioned spec + published
   JSON schemas for `state.json`/`TASKS.json`/receipt/repair-record; `validate_contract`
   optionally checks receipts/repair records when present (M5/ST2).
8. **Distribution surfaces exist.** Listed on ≥2 community discovery lists (QW5);
   GitHub About/topics tuned to own "false completion" + "loop engineering" (QW4);
   ≥2 integration recipes layering the contract above an existing engine (ST3)
   *(stretch)*; a contributor funnel of good-first-issues + a 2nd example (ST4)
   *(stretch)*.
9. **Dogfood exit gate.** The repo's own live `.loop/` contract passes
   `python3 -m loop doctor .loop` (today it does **not** — see §6), and a contract
   scaffolded from `templates/` passes `doctor` unedited (the template drift is
   fixed). *A product whose pitch is "prove it's done" must pass its own gate.*
10. **Launch.** *(stretch, gated on 1-4)* Show HN / r/ClaudeAI / a "false completion"
    post, leading with the HI2 GIF and HI3 diagram (ST5).

> **Not in v1.0 / explicit non-goals:** becoming an execution engine or
> orchestrator (forfeits the wedge — see POSITIONING §7); any feature that competes
> head-on with LangGraph/ruflo/OpenHands rather than layering above them.

## 3. Guiding principles (from the review)

- **Wedge-credibility before launch.** The skeptics who decide whether the "layer
  above" claim is real are exactly the ones who will run `doctor`/`inspect` and read
  the scanner. Close the enforcement holes *before* inviting scrutiny (M1 → … → M4).
- **Enforce, don't narrate.** Every metric the pitch rests on must be *derived and
  checkable*, never self-reported. This is both the top correctness priority and the
  top adoption priority (they are the same work).
- **Compose, don't compete.** Positioning is always "the contract layer above your
  runtime." Never a replacement.
- **Honesty is adoption fuel.** Keep the table-stakes-vs-novel caveats; they build
  trust with the P2/P3 evaluators. This roadmap's own honest `Succeeded` (planning
  done, release not claimed) is the pattern the product sells.

## 4. Milestones (execution order)

Each milestone is executed by its **own** loop-engineer contract (its own SPEC/
WORKFLOW/TASKS/verify gates + a one-of-7 terminal state), gated by human approval.
M1 is release-blocking and leads because the review's three HIGH findings live there.

### M1 — Enforce the differentiator *(release-blocking; do first)*
Close the false-completion self-assertion holes so the headline promise is true in
code. **Strategic spec:** `roadmap/v1.0/specs/spec-1-enforce-the-differentiator.md`.
Covers G1/QW2, G2/QW6, G3/HI6, M1/HI4, M2/HI1, plus the dogfood exit gate (live
`.loop/` + template drift). **Exit:** a skeptic running `doctor`/`inspect`/reading
the scanner finds the promise enforced; the flagship example runs the gate; the
repo passes its own `doctor`.

### M2 — Make the loop-health metrics real
Give FCR and repair-productivity airtight provenance and turn the contract into a
versioned standard. **Strategic spec:** `roadmap/v1.0/specs/spec-2-real-loop-health-metrics.md`.
Covers M3/HI5, M4/QW11, M5, ST1, ST2. **Depends on M1** (a baseline over
self-asserted runs would itself be a false completion). **Exit:** RP is a derivation
not a claim; one canonical repair record; a published baseline sourced from a
gate-backed run; versioned schemas that `validate_contract` can check.

### M3 — First-screen comprehension + onboarding-DX
Make a stranger "get it" in 10 seconds and reach a visible score in 30. **Strategic
spec:** `roadmap/v1.0/specs/spec-3-onboarding-and-discoverability.md`. Covers QW1,
HI2, HI3, O1-O4 (QW7/QW8), T1-T4 (QW3/QW9), G4/QW10, QW4. **HI2 depends on M1** (the
filmed run must be honestly gate-backed, not the current self-asserting example).
**Exit:** the README hero + demo GIF + three-tier table are the first screen; the
router fires on real phrasing; onboarding traps are documented.

### M4 — Distribution + the portable standard
Meet the adjacent communities where they are and turn the contract into a standard
others emit/consume. **Strategic spec:** `roadmap/v1.0/specs/spec-4-distribution-and-standard.md`.
Covers QW5, ST3, ST4, ST5, and the ST2 spec's distribution face. **Gated on
M1+M3** (never launch behind an un-enforced promise or an empty first screen).
**Exit:** listed on ≥2 discovery lists; ≥2 integration recipes; a seeded contributor
funnel; a launch post owning "false completion."

## 5. Traceability — every finding and backlog item → a milestone

**Review findings** (`review/REVIEW.md`):

| Finding | Sev | Dimension | Milestone |
|---|---|---|---|
| G1 terminal vs false_completion/criteria_met uncross-checked | HIGH | gate-integrity | M1 |
| G2 empty visible set vacuously passes holdout gate | MED | gate-integrity | M1 |
| G3 anticheat misses logic rewrites of its own gate fns | MED | gate-integrity | M1 |
| G4 self_eval checks are substring, not behavioral | LOW | gate-integrity | M3 |
| M1 inspector credits bare self-asserted false_completion flag | HIGH | metric-honesty | M1 |
| M2 shipped example never runs a holdout gate | HIGH | metric-honesty | M1 |
| M3 repair record `productive` flag unenforced | MED | metric-honesty | M2 |
| M4 two disjoint "7-field" repair records both branded canonical | MED | metric-honesty | M2 |
| M5 validator ignores repair records / receipts (4 of 5 schemas) | LOW | metric-honesty | M2 |
| T1 router omits 2 of 8 spokes + all diagnostic verbs | MED | trigger-quality | M3 |
| T2 shared "grade" trigger | LOW | trigger-quality | M3 |
| T3 loop-evals description verbosity outlier | LOW | trigger-quality | M3 |
| T4 loop-run weak first trigger example | LOW | trigger-quality | M3 |
| O1 bundled example not runnable, only inspectable | MED | onboarding-dx | M1 (runnable) + M3 (relabel/demo) |
| O2 no visual demo asset | MED | onboarding-dx | M3 |
| O3 marketplace-staleness trap undocumented | MED | onboarding-dx | M3 |
| O4 no console-script entry point | LOW | onboarding-dx | M3 |
| docs-honesty | — | (0 findings) | n/a |

**Backlog items** (`review/IMPROVEMENT-BACKLOG.md`):

| ID | Title | Milestone |
|---|---|---|
| QW1 | README hero: pain-then-proof + zero-install first command | M3 |
| QW2 | Cross-check terminal state vs false_completion/criteria_met | M1 |
| QW3 | Add the 2 diagnostic spokes to router + marketplace | M3 |
| QW4 | GitHub metadata/SEO: About, topics, own "false completion" | M3 |
| QW5 | List on awesome-claude-code(-plugins) | M4 |
| QW6 | Empty visible set → NotReady, not Succeeded | M1 |
| QW7 | Document the local-marketplace staleness trap | M3 |
| QW8 | Console-script entry point (`loop`) | M3 |
| QW9 | Trigger-phrase disambiguation batch (T2-T4) | M3 |
| QW10 | Label `self_eval` checks honestly (doc-completeness) | M3 |
| QW11 | Canonicalize "the repair record" — one 7-field schema | M2 |
| HI1 | Make the flagship example run the held-out gate | M1 |
| HI2 | weak→strong `inspect` demo GIF + social card | M3 |
| HI3 | Three-tier stack diagram + verified comparison table | M3 |
| HI4 | Score false-completion-defense only on real gate invocation | M1 |
| HI5 | Enforce the repair record's `productive` flag | M2 |
| HI6 | Structural (AST/hash) invariant on anticheat gate fns | M1 |
| ST1 | Publish a real FCR / repair-productivity baseline + metrics CLI | M2 |
| ST2 | Versioned portable contract spec + schemas | M2 |
| ST3 | Integration recipes above LangGraph/ruflo/OpenHands/Temporal | M4 |
| ST4 | Contributor funnel: good-first-issues + 2nd example + adapter | M4 |
| ST5 | Launch surfaces: Show HN / r/ClaudeAI / "false completion" post | M4 |

*All 18 findings and all 22 backlog items are accounted for. docs-honesty produced
no findings, so no item derives from it.*

## 6. The dogfood mandate (a v1.0 exit gate the review implies)

Authoring this roadmap by dogfooding the contract on itself surfaced that **the
product does not currently pass its own gate** (full list in
`roadmap/v1.0/RUNLOG.md` → DOGFOOD GAPS):

- `templates/state.json.tmpl` + `templates/terminal_state.json.tmpl` emit
  `schema_version`, but `loop/contract.py` checks `schema` — a template-scaffolded
  contract fails `doctor` immediately.
- The terminal template lacks the validator's required `criteria_met` /
  `false_completion` / top-level `evidence` fields.
- Running `python3 -m loop doctor .loop` on the repo's **own live contract** returns
  `ok:false` for exactly these reasons.
- There is no `Planned`/`NotStarted`/`Deferred` status — only the 7 *terminal*
  states — so a "planned but not executed" roadmap has to be expressed indirectly
  (this contract does it via a Succeeded planning milestone + a `pending_approval`
  block). A first-class deferred status belongs in the versioned spec (M2/ST2).

**v1.0 exit gate (§2 item 9):** the live `.loop/` contract passes `doctor`, and a
template-scaffolded contract passes `doctor` unedited. Fixing the templates +
migrating the live contract's field names lands in M1 (the enforcement milestone)
so the repo's flagship on-disk artifact is honest before launch.

## 7. Sequencing summary

```
M1 enforce differentiator  ──►  M2 real metrics ──┐
   (release-blocking)      └─►  M3 onboarding  ───┼─►  M4 distribution ──►  (stretch) ST5 launch
                                (HI2 needs M1)     │      (needs M1+M3)
                                                   └──►  ST1 baseline (needs M1+M2)
```

- **Do M1 first and fully** — it is the credibility floor and it fixes the dogfood
  gate.
- **M2 and M3 can run in parallel** after M1 (different files, different personas),
  except HI2's filmed demo and ST1's baseline, which both wait on M1.
- **M4 is last** — distribution behind an un-enforced promise wastes the first
  impression.

## 8. Pointers

- This roadmap's governing contract: `roadmap/v1.0/SPEC.md`, `WORKFLOW.md`,
  `TASKS.json`, `RUNLOG.md`, `.loop/{manifest.yaml,state.json,terminal_state.json}`.
- The four strategic specs (per-item acceptance criteria): `roadmap/v1.0/specs/`.
- Ground-truth review: `review/`.
