# ST1 — Published FCR / Repair-Productivity Baseline + Metrics CLI

*Design spec. Report-only planning artifact — no code in this document. Compiled 2026-06-30.*

**Backlog item:** ST1 (rank 15, Impact H / Effort H, Strategic) — *"Publish a real FCR / repair-productivity baseline + metrics CLI."*
**Grounded in:** metric-honesty findings **M3** (`productive` flag unenforced), **M4** (two disjoint 7-field repair-record shapes), **M5** (validator covers only 4 of 5 schemas; never checks repair records / receipts); backlog **QW11** (canonicalize the repair record), **HI5** (enforce `productive` — recompute + reject), **ST1**.
**Sources of truth:** `reference/eval-suite.md` §2 (FCR/RP definitions, "derived not self-reported"), `scripts/rollout_ledger.py`, `evals/cases/structural.json` (`repair_record_fields`), `skills/loop-repair/SKILL.md` (§ "The structured repair record"), `schemas/receipt.schema.json`, `examples/coverage-repair/repair-record.json`, `templates/RUNLOG.md.tmpl`, `templates/terminal_state.json.tmpl`.

---

## 1. Problem statement

false-completion-rate (FCR) and repair-productivity (RP) are the two first-class metrics the competitive analysis names as having no rival — they *are* the wedge. Today they are **claimed but not derivable from a tool the repo ships**, and their inputs are **self-asserted, not enforced**:

- **No metrics command exists.** `reference/eval-suite.md` §2 defines FCR and RP as formulas and asserts both are "derived, not self-reported," but nothing in `scripts/` or `loop/` computes them from a real `.loop/` run. The numbers live only in prose.
- **The `productive` input to RP is trusted verbatim.** `scripts/rollout_ledger.py` `summarize()` sums whatever `productive` boolean the caller supplies (M3); `skills/loop-repair/SKILL.md` prescribes `productive = verification_after.score > verification_before.score` but nothing recomputes or validates it.
- **"The repair record" is two different shapes** (M4 / QW11): `rollout_ledger.py RECORD_FIELDS` (`id`/`parent`/`verdict`/`score`/`score_delta`/`coherent_with_prior_winner`/`productive`) vs `evals/cases/structural.json repair_record_fields` (`failure_mode`/`hypothesis`/`repair_action`/`verification_before`/`verification_after`/`remaining_delta`/`productive`). They share only the count "7" and the field `productive`. RP's provenance is ambiguous.
- **The contract validator never checks the FCR/RP evidentiary trail** (M5): `validate_contract()` covers manifest/state/tasks/terminal only; `schemas/receipt.schema.json` is never referenced and no repair-record schema exists.

A metric with no published, tool-derived baseline reads as a claim. Worse: a baseline computed over the repo's *current* flagship example would be a baseline over a **self-asserted** run (the coverage-repair example asserts `false_completion:false` with no held-out gate ever invoked — findings M1/M2). Publishing that number would itself be a false completion of ST1.

## 2. Goal

Ship a repo-native **`metrics` command** that derives FCR + RP (plus supporting cost/efficiency figures) from a loop's *real* `.loop/` receipts / RUNLOG / repair records / verify bundles, with the `productive` input **recomputed and cross-checked** (never trusted); and publish a **checked-in baseline** computed by that command over a **genuinely gate-backed** example, with README numbers sourced from the computation rather than prose.

## 3. Non-goals

- Not building a new verification engine. Deterministic evidence is read from the contract's own `scripts/verify-*` bundles (eval-suite.md §5 "reuse, do not reimplement").
- Not implementing the gate-enforcement fixes ST1 depends on (QW2 / HI1 / HI4 / G1 / G2 / M1 / M2). Those live in the companion **v0.4 credibility / gate-enforcement spec** (see §7). This spec *consumes* their output; it does not duplicate it.
- Not shipping a comparative A/B win/loss number. `scripts/benchmark_harness.py` + eval-suite.md §7 already own the A/B protocol and deliberately bake in no product claim; ST1 scores *one* loop, not a harness-vs-harness swing.
- Not a live-telemetry or dashboard product. Output is a machine-readable JSON scorecard from committed files, offline, no network.

---

## 4. Design

### 4.1 Resolve the repair-record divergence (QW11 / M4) — one canonical repair record

There are two genuinely different artifacts today, both mislabelled "7-field repair record." They are **not** the same thing and unifying their *fields* would be wrong. The resolution is to canonicalize the **name** and the **derivation rule**, not to merge the shapes:

| Artifact | Canonical shape | Schema tag | On-disk location | Role | Feeds |
|---|---|---|---|---|---|
| **Repair record** *(the canonical "repair record")* | `evals/cases/structural.json repair_record_fields`: `failure_mode`, `hypothesis`, `repair_action`, `verification_before`, `verification_after`, `remaining_delta`, `productive` (+ envelope `schema`/`iteration_id`/`attempt` per `examples/coverage-repair/repair-record.json`) | `loop-engineer/repair@1` | `.loop/repair/<iteration_id>.json` | one bounded repair pass, emitted by `loop-repair` | **RP** (canonical input) |
| **Rollout / candidate ledger record** | `rollout_ledger.py RECORD_FIELDS`: `id`, `parent`, `verdict`, `score`, `score_delta`, `coherent_with_prior_winner`, `productive` | `loop-engineer/rollout@1` (new) | `.loop/*.jsonl` (append-only) | one *candidate adjudication* in a rollout / genetic-hardening loop | rollout-productivity (a flywheel view), **not** the RP baseline |

**Decisions:**
1. The **repair record** (structural.json shape, `loop-engineer/repair@1`) is the single artifact that may be called "the repair record." It is RP's canonical input — consistent with `eval-suite.md` §2.2, which already anchors RP on the repair record's `verification_before`/`verification_after` fields.
2. The `rollout_ledger.py` record is **renamed in documentation** to the "rollout ledger / candidate record" (`loop-engineer/rollout@1`). It is a distinct artifact for candidate adjudication; it must stop being branded "the repair record." Its `productive` field is the *rollout*-productivity signal, not the RP baseline.
3. **Both derive `productive` by the same underlying rule** — *did this pass measurably improve the score?* — expressed against each shape's own evidence:
   - repair record → `productive == (verification_after.score > verification_before.score)`
   - rollout record → `productive == (score_delta > 0)` (equivalently `score > parent-winner score`)
4. `reference/eval-suite.md` gains one sentence naming the repair record as canonical for RP and pointing at the rollout ledger as the separate candidate artifact. `evals/cases/structural.json` remains the structural source of the 7 repair fields (no field change).

*This closes M4 (two schemas branded "the" repair record) and satisfies QW11 (one canonical 7-field repair schema). QW11 is a hard predecessor of ST1: the baseline cannot be derived until it is unambiguous which record RP reads.*

### 4.2 Canonical schemas (closes M5 for the RP/FCR trail)

Publish two JSON Schema files under `schemas/` (companion to the existing `schemas/receipt.schema.json`):

- **`schemas/repair-record.schema.json`** (`$id: loop-engineer/repair@1`): the 7 canonical fields as `required`, plus envelope `schema`/`iteration_id`/`attempt`; `verification_before`/`verification_after` each require a numeric `score`; `productive` is `boolean`. `additionalProperties: true` (repair records carry loop-specific evidence keys like `metric`/`failing`, per the coverage-repair example).
- **`schemas/rollout-record.schema.json`** (`$id: loop-engineer/rollout@1`): the 7 `rollout_ledger.py` fields as `required`; `score`/`score_delta` numeric-or-null; `productive` boolean.

`validate_contract()` is extended (in the companion enforcement spec's scope, but specified here because it is the M5 fix) to **optionally** validate `.loop/repair/*.json` and `.loop/*.jsonl` receipt/rollout files against these schemas *when present*, so a loop can no longer "pass validation" while its metric inputs are missing or malformed.

### 4.3 Recompute-and-reject `productive` (HI5 / M3)

A shared validator function — call it `recheck_productive(record)` — is the single point of truth used by **both** the metrics command and (in the enforcement spec) `rollout_ledger.summarize()`:

- **Repair record:** recompute `expected = verification_after.score > verification_before.score`. If the stored `productive` disagrees with `expected`, the record is **rejected** (not silently coerced) — the metrics command excludes it from the RP numerator/denominator and reports it under a `rejected_records` provenance list with the reason. A record missing `verification_before`/`verification_after.score` is likewise rejected (it "cannot demonstrate productivity" — loop-repair SKILL.md already states such a record is invalid).
- **Rollout record:** recompute `expected = (score_delta is not None and score_delta > 0)`; same reject-on-disagreement rule.
- **No caller-supplied boolean is ever summed verbatim.** RP is computed only over records whose `productive` was *recomputed and agreed*. This converts RP from a self-report into a derivation — exactly the property `eval-suite.md` §2.2 claims and M3 shows is currently false.

Rejection is a first-class output, not a crash: the command exits non-zero **only** when asked to emit a *baseline* (see §4.5) over a run containing rejected records; in plain `metrics` mode it reports them and continues, so an operator can see *which* records are dishonest.

### 4.4 The `metrics` command

A new `scripts/metrics.py`, wired as a `python3 -m loop metrics <loop-dir>` subcommand alongside `doctor` / `inspect` (same editable-install, repo-relative `scripts/` resolution constraint noted in `pyproject.toml`; see QW8). Pure stdlib, offline, deterministic.

**Inputs (all read from the target loop dir — never the agent's narration):**

| Input | File(s) | Used for |
|---|---|---|
| Success claims + per-iteration outcome | `RUNLOG.md` (`### Outcome` = `task_passed`/`terminal`/…), `terminal_state.json` (`state`, `succeeded`) | FCR numerator/denominator (claims of "done") |
| Deterministic evidence per iteration | `.loop/` verify bundles (`verify-*.json`: `verify_fast`/`verify_full` outcome, `score`, `failing`), the layer-1 gate output | FCR cross-join (did deterministic verify agree?) |
| Held-out gate output | `scripts/holdout_gate.py` result / `anticheat_scan.py` sweep recorded in the verify trail or RUNLOG | `evidence_backed` flag (§4.5); FCR via aggregated `false_completion` flag |
| Repair records | `.loop/repair/<iteration_id>.json` (`loop-engineer/repair@1`) | RP (after recompute-and-reject) |
| Receipts | `.loop/receipts/*.jsonl` (`loop-engineer/receipt@1`) | cost-per-success, iteration/dispatch counts (layer 7) |

**Computation (exactly the eval-suite.md §2 formulas):**

```
FCR = (iterations claiming success AND failing deterministic verify)
      / (iterations claiming success)                                     # target 0

RP  = (repair passes where verification_after.score > verification_before.score, recomputed)
      / (total repair passes attempted)                                   # target high, trending up
```

- FCR is anchored to the **deterministic layer**, per eval-suite.md §3 — a "Succeeded"/`task_passed` claim not backed by a green `verify-full` for the same `iteration_id` is a false completion. The command computes FCR **two ways** and asserts they agree: (a) the RUNLOG-claim × verify-bundle cross-join, and (b) the aggregated `holdout_gate` `false_completion` flag. Disagreement is surfaced (it means the loop's own gate output and its logged claims are inconsistent) rather than silently picking one.
- RP is computed only over validated (recomputed-and-agreed) repair records (§4.3).

**Output:** a JSON scorecard to stdout, e.g.

```json
{
  "schema": "loop-engineer/metrics@1",
  "loop": "<loop-dir>",
  "false_completion_rate": 0.0,
  "repair_productivity": 0.5,
  "iterations_claiming_success": 3,
  "false_completions": 0,
  "repair_passes": 2,
  "productive_repairs": 1,
  "cost_per_success_usd": null,
  "evidence_backed": true,
  "provenance": {
    "fcr_source": ["RUNLOG.md", ".loop/<verify bundles>"],
    "rp_source": [".loop/repair/iter-002.json"],
    "rejected_records": []
  }
}
```

- `evidence_backed` is **true only when a held-out / anti-cheat gate invocation is detectable** in the verify trail or RUNLOG for the success-claiming iterations — the same honesty rule HI4 puts on the inspector. A run that self-asserts `false_completion:false` with no gate ever invoked reports `evidence_backed:false` and an `FCR` derived purely from the deterministic cross-join (never from the untrusted flag).
- Every headline number ships with a `provenance` block naming the files it came from, so a skeptic can re-derive it by hand.

### 4.5 The published baseline — and why it is gated

A `--baseline` mode writes a checked-in scorecard (e.g. `docs/metrics-baseline.json`) that the README's FCR/RP numbers cite by reference (not prose). This mode enforces the honesty preconditions ST1 exists to protect:

1. It **refuses** (exits non-zero, writes nothing) if `evidence_backed` is false for the run — a baseline may only be computed over a **genuinely gate-backed** run. *Do not baseline over a self-asserted run — that would itself be a false completion of ST1.*
2. It **refuses** if any repair/rollout record was rejected by §4.3 (a baseline must not contain a record whose `productive` disagrees with its own evidence).
3. It stamps the source example, the commit, and the exact input file list so the number is reproducible and diffable in PRs.

The baseline is computed over the **HI1-fixed** `examples/coverage-repair` — the version that actually runs `holdout_gate.py` end-to-end and records the gate's output as the evidence behind `false_completion:false`. Until HI1 lands, the example is not eligible and `--baseline` will (correctly) refuse.

---

## 5. Acceptance criteria

- **AC1 (QW11/M4):** `schemas/repair-record.schema.json` (`loop-engineer/repair@1`) and `schemas/rollout-record.schema.json` (`loop-engineer/rollout@1`) exist; `reference/eval-suite.md` names the repair record as RP's canonical input and the rollout ledger as the separate candidate artifact; `evals/cases/structural.json repair_record_fields` remains the structural source and validates against the repair schema. `self_eval.py` structural checks stay green.
- **AC2 (HI5/M3):** a `recheck_productive` validator recomputes `productive` from `verification_before`/`verification_after.score` (repair) and `score_delta` (rollout) and **rejects** disagreements; the metrics command aggregates RP only over validated records; a regression test pins a disagreeing repair record → rejected + excluded from RP.
- **AC3 (metrics CLI):** `python3 -m loop metrics <loop-dir>` derives FCR + RP from real `.loop/` receipts / RUNLOG / repair records / verify bundles — never from agent narration — and emits a JSON scorecard with a `provenance` block; a pytest case pins determinism on a fixture loop dir.
- **AC4 (FCR honesty):** FCR is computed from the deterministic cross-join and cross-checked against the aggregated `holdout_gate` `false_completion` flag; `evidence_backed` is true only when a gate invocation is detectable; a test covers "claim set but gate never run" → `evidence_backed:false`.
- **AC5 (baseline gating):** `--baseline` refuses to emit over a run that is not `evidence_backed` or that contains rejected records; on the HI1-fixed example it writes `docs/metrics-baseline.json`; README FCR/RP numbers are sourced from that file, not prose.
- **AC6 (M5, optional-when-present):** `validate_contract()` validates `.loop/repair/*.json` and `.loop/*.jsonl` against their schemas when present (may land with the companion enforcement spec; noted here for traceability).

## 6. Test plan

- Unit: `recheck_productive` over agree / disagree / missing-score cases (repair + rollout shapes).
- Unit: FCR cross-join over a fixture with a "claimed done + verify red" iteration (FCR = 1) and an all-green fixture (FCR = 0).
- Unit: RP over a fixture with one productive + one churn repair record (RP = 0.5), and a fixture whose stored `productive` lies (rejected → excluded).
- Determinism: same fixture dir → byte-identical scorecard across runs.
- Guard: `--baseline` over a non-`evidence_backed` fixture exits non-zero and writes nothing.
- Schema: `schemas/repair-record.schema.json` / `rollout-record.schema.json` validate the shipped `examples/coverage-repair/repair-record.json` and a rollout-ledger fixture.

## 7. Dependency ordering (READ BEFORE SCHEDULING)

ST1 is Effort-H precisely because it has hard predecessors. Two classes of dependency:

**A. Schema predecessor (can land now, independent of the gate work):**
- **QW11 (§4.1)** — canonicalize the repair record. *Must* land before RP is derived; otherwise it is ambiguous which record RP reads. This is pure documentation + schema work and is the natural first slice of ST1 itself.

**B. Credibility predecessor — the v0.4 gate-enforcement spec (companion; do NOT baseline before it lands):**
The *metrics CLI (the tool)* can be built and tested against fixtures independently. The **published baseline number** must wait for the enforcement work that makes a run genuinely gate-backed, because a baseline over a self-asserted run is a false completion of ST1:
- **HI1** — make the flagship example actually run the held-out gate end-to-end. Gates the baseline's *input* (§4.5). Also gates HI2 (demo GIF) and this baseline per the backlog's own sequencing note.
- **HI4** — score false-completion-defense only on real gate invocation. Same honesty rule this spec's `evidence_backed` flag depends on.
- **QW2 / G1** — cross-check terminal state vs `false_completion`/`criteria_met`; **G2 / QW6** — empty-visible → NotReady; **M1 / M2** — inspector/example self-assertion holes. These are the enforcement fixes that make the gate output the metrics command reads trustworthy.

**Sequencing:** `QW11 (schema)` → `metrics.py + recheck_productive + tests (this spec, against fixtures)` → *(companion v0.4 enforcement: QW2, G1, G2, M1, M2, HI1, HI4)* → `python3 -m loop metrics --baseline` over the HI1-fixed example → commit `docs/metrics-baseline.json` → wire README numbers. Do **not** run the final baseline step until the companion enforcement spec has landed.

## 8. Risks

- **Baselining too early.** The single biggest risk is publishing a number over a self-asserted run. Mitigated structurally by §4.5's `--baseline` refusal — the tool itself will not let you.
- **RUNLOG ↔ verify-bundle join fragility.** The FCR cross-join keys on `iteration_id`; if a loop's RUNLOG and verify bundles disagree on iteration ids the join is lossy. Mitigation: the command reports unmatched iterations under provenance and treats an unmatched success-claim as a false completion (fail-closed, per eval-suite.md §2.1 "not backed by a green verify … is a false completion, full stop").
- **Two-way FCR disagreement.** If the deterministic cross-join and the aggregated `holdout_gate` flag disagree, that is itself a defect signal; the command surfaces it rather than picking a winner, so it can't launder an inconsistent run into a clean number.
