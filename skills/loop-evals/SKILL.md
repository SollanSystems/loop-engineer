---
name: loop-evals
description: "Design the evaluation harness for an agent loop — the proof layer that makes a loop trustworthy instead of merely confident. Use when asked to evaluate a loop, build an eval/verification harness or suite, measure how well a loop or agent system works, decide what to test, catch false completions, or grade a long-running agentic run. Lays out the 7-layer eval suite, makes false-completion-rate and repair-productivity first-class metrics, enforces deterministic-first-then-rubric, calibrates the judge, and keeps the regression harness repo-native. Delegates the deterministic gate to the contract's own verify scripts (with /verify-slice as an optional upgrade) — it designs the criteria, it does not build a new verification engine."
---

# loop-evals — design the harness that proves the loop

A loop without measurement is a loop that *claims* success. This skill designs the evaluation harness for a loop — what to check, in what order, with which metric — so a "Succeeded" terminal state is backed by evidence, not narration. It is the **designer** of the suite; `[[loop-run]]` is the caller that runs the gate each iteration, and `[[loop-flywheel]]` feeds real failures back into it.

**In → out.** In: the loop's `SPEC.md` (success criteria, constraints, evidence rules) + its artifacts. Out: `scripts/verify-*` skeletons, an `EVALS/{dataset,rubrics,regressions,traces}/` tree, and the metric definitions — all committed inside the loop's own repo. This skill is read-only/advisory toward the loop it grades; it authors the harness, it does not run the task.

Full depth, formulas, the calibration cadence, and the Workflow grading example live in `reference/eval-suite.md` — read it before authoring a real suite.

## When to reach for this

- "Build the eval harness / verification suite for this loop."
- "How do I measure this loop?" / "Is this agent actually working?"
- "It keeps saying it's done but the result is wrong" → you need false-completion-rate.
- "The repair loop is thrashing" → you need repair-productivity.
- Right after `[[loop-contract]]` scaffolds the contract (populate `scripts/verify-*` + `EVALS/`), and continuously via `[[loop-flywheel]]`.

## The 7-layer suite

`loop-evals` selects which layers a given loop needs from its `SPEC.md` — a read-only refactor needs 1/4/6/7; a money-moving agent adds 3/5 as blocking. Layers 1–2 run every iteration; 3–7 run on the schedule below. Every layer is ordered so cheap, binary, ungameable checks gate the expensive, judgment-laden ones.

| # | Layer | Mechanism | Key metric(s) | Blocking? |
|---|---|---|---|---|
| 1 | Deterministic correctness | tests, lint, typecheck, schema/contract validation (`verify-fast` → `verify-full`) | pass rate, constraint-violation count | **Yes** (hard gate) |
| 2 | Artifact quality | rubric model judge, fixed schema (`EVALS/rubrics/`) | rubric mean, per-dimension score | No (advisory) |
| 3 | Human calibration | adjudicated sample review of judge verdicts | judge↔human agreement, false-accept/reject | Gates the *judge* |
| 4 | Loop behavior | trace analysis (`EVALS/traces/`, `RUNLOG.md`, `.loop/receipts/*.jsonl`) | plan compliance, repair depth, **false-completion rate** | No (alarm) |
| 5 | Security / governance | red-team, approval tests, injection probes | escape rate, approval-bypass, verifier-gaming detections | **Yes** for high-risk |
| 6 | Regression resistance | repo-native dataset + trace-derived cases (`EVALS/regressions/`) | regression failure count (must be 0) | **Yes** once frozen |
| 7 | Cost / efficiency | token/latency/tool logs from receipts | cost-per-success, wall-clock-to-success | No (budget alarm) |

Layer 1 *is* the contract's deterministic verify gate (`scripts/verify-fast`→`verify-full`; optionally `/verify-slice`) — not a new engine. Layers 2–3 are the judge stack. Layer 4 carries the two first-class metrics. Layer 5 is the anti-cheat surface in `reference/safety-and-approvals.md`. Layers 6–7 are the durability and budget guards.

## The two first-class metrics

Most harnesses track pass-rate and stop. These two predict whether a *loop* (not a single attempt) is healthy, so every loop reports them in its scorecard and `[[loop-flywheel]]` watches their trend. Both are **derived, not self-reported** — the agent cannot inflate them by narrating confidence.

**false-completion-rate (FCR)** — fraction of iterations claiming success while the deterministic layer disagrees.

```
FCR = (iterations claiming success AND failing deterministic verify) / (iterations claiming success)
```
Computed by joining `RUNLOG.md` self-reports to the layer-1 verification bundle for the same `iteration_id`. **Target: 0.** A non-zero FCR is a defect in the loop's *stopping rule* — it is trusting narration over evidence, the prime-directive failure mode. A loop that cannot verify must go `FailedUnverifiable`, never silent-"completed". A *deliberate* false completion (e.g. an edited test) is escalated by Layer 5 to a verifier-gaming hard-terminate, not merely counted. `loop-engineer` ships this as runnable tooling — `scripts/holdout_gate.py` (the visible/holdout split that makes FCR a measured event) and `scripts/anticheat_scan.py` (the post-`Succeeded` trajectory sweep for shortcut signatures) — so the metric is computed at the gate, not narrated.

**repair-productivity (RP)** — fraction of repair passes that measurably improve the score vs churn; the health metric for `[[loop-repair]]`.

```
RP = (repair passes where verification_after > verification_before) / (total repair passes attempted)
```
Read straight off the repair-record schema `[[loop-repair]]` emits (`verification_before` vs `verification_after`; a pass that leaves `remaining_delta` unchanged is churn). **Target: high, trending up.** Low RP means the repair loop is thrashing against its max-N cap (default N=2, per `WORKFLOW.md`) — the data-driven trigger for the escalation ladder's "same failure mode, no improvement → re-plan" rung.

## Deterministic-first, then rubric

The non-negotiable ordering inside every evaluation cycle:

1. **Run the deterministic gate first** (Layer 1: `verify-fast` → `verify-full` → schema/contract → Layer 6 regression set). Binary, reproducible, ungameable.
2. **Only if the gate is green, run the rubric judge** (Layer 2) for quality/nuance a test cannot capture.
3. **The judge is advisory; the gate is authoritative.** A high rubric score never clears a red deterministic check — a model verdict may only ADD a finding, never subtract a deterministic failure.

This mirrors the `launch-local-agent` grader split (objective binary gate in front of a judged advisory rubric) and the no-leak grader principle that a model score is never sufficient alone. It is also *why* FCR is anchored to the deterministic layer, not the judge: if a quality rubric could mark a run "done," a confident-but-wrong agent would game it.

## Judge calibration

A rubric judge is itself a model under test; an uncalibrated judge silently rots the suite (Layer 3 governs it):

- Maintain a **human-labeled adjudication set** in `EVALS/dataset/` — the judge's own test suite.
- Track **judge↔human agreement**, **false-accept** (the dangerous direction — a judge waving through bad artifacts manufactures false completions one level up), and false-reject.
- **Re-measure monthly AND after every trigger** that shifts judge behavior: a base-model bump, a rubric edit, or a prompt-template change. Treat an un-recalibrated judge after a model change as unverified.
- The judge **gates itself, not the run**: if agreement drops, `[[loop-flywheel]]` opens a harness-change proposal before its verdicts are trusted again.

## The regression harness is repo-native

Datasets, rubrics, regression cases, and trace-transform scripts are **committed files inside the loop's repo** — model calls are grading *components* invoked by repo scripts, never the system of record. This keeps the harness reproducible offline, diffable in PRs, CI-runnable with no third-party network dependency, and durable against vendor churn (consumer eval UIs move fast and go read-only; a committed `EVALS/` tree does not lose your quality history). Cases come from a hand-curated seed set **plus** trace-derived cases — every real failure `[[loop-flywheel]]` mines becomes a permanent regression case so the same failure can never silently return.

**Reuse, do not reimplement.** The deterministic layer *is* the contract's own `scripts/verify-fast`→`verify-full` gate. `loop-evals` **designs** the criteria + the `EVALS/` tree; `loop-run` **calls** the gate; neither builds a new engine. *Optional integration:* with `claude-code-orchestration` installed, `/verify-slice` (2-iteration fix loop + cross-review) and `/verify-milestone` (batch) run that gate with auto-repair. A regression batch is the canonical Workflow fan-out — every dispatched grader names an explicit `model:` per the routing rule:

```js
// Workflow: grade the regression set — deterministic gate per case, then an advisory judge.
for (const c of regressionCases) {
  const det = await agent({ model: "haiku",        // read/run: deterministic verify only
    prompt: `Run scripts/verify-full against case ${c.id}; report pass/fail + constraint violations.` });
  if (det.passed) {
    await agent({ model: "sonnet",                 // reason: rubric judgment, cannot override the gate
      prompt: `Score case ${c.id} against EVALS/rubrics/quality.md (fixed schema).` });
  }
}
```
(`read → haiku`, `reason → sonnet`, `write → opus` per the model-routing rule — tier table + rationale in `reference/model-routing.md`; receipts append to `.loop/receipts/`.)

## Standing the suite up

Do not freeze a scorecard on day one — `[[loop-flywheel]]` drives the staged rollout; the full four-phase sequence (with which layers come online when) is in `reference/eval-suite.md` §6. Two load-bearing facts hold here: Baseline (Layer 1 + Layer 7) is the minimum before `[[loop-run]]` may execute the loop, and the schedule is a ratchet — only add gates, only freeze once the cheap layers are clean.

## Hands off to / from

- `[[loop-contract]]` — scaffolds the `scripts/verify-*` + `EVALS/` skeletons this skill fills in.
- `[[loop-run]]` — calls the Layer-1 gate each iteration; honors the terminal states FCR protects.
- `[[loop-repair]]` — emits the repair-record fields RP is computed from.
- `[[loop-flywheel]]` — runs the schedule above, mines traces into regression cases, watches FCR/RP, proposes harness changes.

See `reference/eval-suite.md` for the formulas, the calibration cadence, and the full grading example.
