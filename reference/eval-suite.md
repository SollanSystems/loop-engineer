# Eval Suite — measuring a loop you can trust

Reference for [[loop-evals]] (designs the suite) and [[loop-flywheel]] (feeds failures back into it). A loop without measurement is a loop that *claims* success; this file defines how `loop-engineer` proves it. The suite is the proof layer of the repo-OS contract in `reference/repo-os-contract.md` — it lands as `scripts/verify-*` + `EVALS/{dataset,rubrics,regressions,traces}/` inside the loop's workspace, never in a vendor eval UI.

Design rule of the whole suite: **a model score may only ever ADD a failure, never clear a deterministic one.** Every layer below is ordered so the cheap, binary, ungameable checks gate the expensive, judgment-laden ones.

---

## 1. The seven layers

Each layer answers a different question, runs at a different cost, and emits one or more key metrics. `loop-evals` selects which layers a given loop needs from its `SPEC.md` (a read-only refactor needs layers 1/4/6/7; a money-moving agent adds 3/5 as blocking). Layers 1–2 run every iteration; 3–7 run on a schedule (see §6).

| # | Layer | Mechanism | Key metric(s) | Blocking? |
|---|---|---|---|---|
| 1 | Deterministic correctness | tests, lint, typecheck, schema/contract validation — `scripts/verify-fast` then `scripts/verify-full` | pass rate, constraint-violation count | **Yes** (hard gate) |
| 2 | Artifact quality | rubric-based model judge against a **fixed schema** (`EVALS/rubrics/`) | rubric mean, per-dimension score | No (advisory) |
| 3 | Human calibration | adjudicated sample review of judge verdicts | judge↔human agreement, false-accept / false-reject rate | Gate on the *judge*, not the run |
| 4 | Loop behavior | trace analysis over runs (`EVALS/traces/`, `RUNLOG.md`, `.gsd/audit/receipts/*.jsonl`) | plan compliance, repair depth, **premature-stop / false-completion rate** | No (advisory + alarm) |
| 5 | Security / governance | red-team scenarios, approval tests, prompt-injection probes | escape rate, approval-bypass rate, verifier-gaming detections | **Yes** for high-risk loops |
| 6 | Regression resistance | repo-native regression dataset + trace-derived cases (`EVALS/regressions/`) | regression failure count (must be 0) | **Yes** once a scorecard is frozen |
| 7 | Cost / efficiency | token / latency / tool logs from receipts | cost-per-success, wall-clock-to-success | No (budget alarm) |

Layer 1 is the spine: it is exactly the `/verify-slice` / `/verify-milestone` gate (see Reuse below), not a new engine. Layers 2–3 are the judge stack. Layer 4 is where the two first-class metrics in §2 live. Layer 5 is the anti-cheat surface detailed in `reference/safety-and-approvals.md`. Layers 6–7 are the durability and budget guards.

**Why this layering.** Long-horizon agentic-coding work fails first at *self-verification*, not at code generation — SWE-Marathon reports sub-30% success on ultra-long-horizon tasks, dominated by agents declaring victory their own verifier would reject. Deterministic layers 1/6 are the only ones an agent cannot talk its way past, so they gate everything; the judge layers 2/3 add nuance on top but are never permitted to overturn a layer-1 failure.

---

## 2. The two first-class metrics

Most eval harnesses track pass-rate and stop. The two metrics below are the ones that actually predict whether a *loop* (not a single attempt) is healthy, and they are promoted to first-class status — every loop reports them in its scorecard, and [[loop-flywheel]] watches their trend.

### 2.1 false-completion-rate (FCR)

**Definition.** The fraction of iterations (or runs) where the agent **declared the task complete while the deterministic verification layer disagrees** — i.e. it reached a self-asserted "done" but layer-1/layer-6 evidence shows ≥1 unmet `success_criteria` or a constraint violation.

```
FCR = (iterations claiming success AND failing deterministic verify)
      ----------------------------------------------------------------
                  (iterations claiming success)
```

- Computed from `RUNLOG.md` self-reports cross-joined with the layer-1 verification bundle for the same `iteration_id`. A claim of "Succeeded" that is not backed by a green `scripts/verify-full` run is a false completion, full stop.
- **Target: 0.** Any non-zero FCR is a defect in the loop's *stopping rule*, not in the task — it means the terminal-state machine is trusting narration over evidence.
- This is the direct, numeric guard against the prime-directive failure mode: a loop that cannot verify must terminate `FailedUnverifiable`, never silent-"completed". A rising FCR is the earliest signal that a loop is drifting toward verifier-blindness; a detected *deliberate* false completion (e.g. the agent edited a test to pass) is escalated by Layer 5 to a verifier-gaming hard-terminate, not just counted here.

### 2.2 repair-productivity (RP)

**Definition.** The fraction of repair passes that **measurably improve the score** versus passes that churn (no measurable improvement, or regression) — the health metric for [[loop-repair]].

```
RP = (repair passes where verification_after > verification_before)
     -------------------------------------------------------------
                  (total repair passes attempted)
```

- "Improvement" is read straight off the structured repair-record schema [[loop-repair]] emits: `verification_before` vs `verification_after` on the same metric (a layer-1 pass count, a layer-2 rubric dimension, or a closed `remaining_delta`). A pass that leaves `remaining_delta` unchanged is churn.
- **Target: high and trending up.** Low RP means the repair loop is thrashing — it is hitting its max-N cap (default N=2, per `WORKFLOW.md`) and burning budget without converging. Low RP is the data-driven trigger for the escalation ladder's "same failure mode repeats without measurable improvement → re-plan" rung (see `reference/safety-and-approvals.md`).
- RP and the repair max-N cap are complementary: the cap bounds *how many* repairs run; RP measures whether those repairs were *worth* running. A loop with a healthy cap but RP≈0 is still broken.

Both metrics are derived, not self-reported: FCR comes from joining claims to deterministic evidence, RP from the before/after fields in repair records. Neither can be inflated by the agent narrating confidence.

---

## 3. Deterministic-first, then rubric

The non-negotiable ordering inside every evaluation cycle:

1. **Run the deterministic gate first** (Layer 1: `verify-fast` → `verify-full` → schema/contract checks → Layer 6 regression set). It is binary, reproducible, and ungameable.
2. **If — and only if — the deterministic gate is green, run the rubric judge** (Layer 2). The judge scores *quality and nuance* (clarity, completeness, design fidelity) that a test cannot capture.
3. **The judge is advisory; the gate is authoritative.** A high rubric score can never clear a red deterministic check. A model verdict may only ADD a finding (lower the quality score, surface a missed edge case), never subtract a deterministic failure. This mirrors the `launch-local-agent` grader split — an objective gate (binary, blocking) in front of a judged rubric (advisory) — and the Hermes no-leak grader stance that a model score is never sufficient alone.

This is why FCR (§2.1) is anchored to the deterministic layer, not to the judge: if a quality rubric could mark a run "done," a confident-but-wrong agent would game it. By construction, the only thing that closes `success_criteria` is layer-1/layer-6 evidence.

Order of operations per iteration: `verify-fast` (seconds, every change) → on green, the rest of `verify-full` + regression set → on green, the rubric judge → write the verification bundle → update FCR/RP → decide terminal vs repair vs continue.

---

## 4. Judge calibration

A rubric judge (Layer 2) is itself a model under test. An uncalibrated judge silently rots the whole suite, so it is governed by Layer 3:

- **Maintain a human-labeled adjudication set** in `EVALS/dataset/` — a fixed sample of artifacts with ground-truth human verdicts (accept / reject + the correct per-dimension scores). This set is the judge's "test suite."
- **Track judge↔human agreement** on that set, plus **false-accept** (judge passed what a human rejects — the dangerous direction) and **false-reject** rates. These are the key metrics of Layer 3.
- **Re-measure on a cadence and on every trigger:** monthly at minimum, AND immediately after any change that could shift judge behavior — a base-model upgrade (Opus/Sonnet version bump), a rubric edit, or a prompt-template change. Model and rubric changes both invalidate prior calibration; treat an un-recalibrated judge after a model bump as unverified.
- **The judge gates itself, not the run.** If agreement drops below threshold or false-accept rises, the judge is the thing that fails — `loop-flywheel` opens a harness-change proposal to fix the rubric or re-anchor the judge before its verdicts are trusted again. A drifted judge does not get to fail-or-pass live runs.
- **Calibration is the false-accept guard.** False-accept is the judge-level analogue of false-completion: a judge that waves through bad artifacts is a judge manufacturing false completions one level up. Weight the calibration threshold toward catching false-accepts.

The dispatched judge always names an explicit model (`reason → sonnet`); see the regression-harness example in §5.

---

## 5. The regression harness is repo-native

The regression layer (Layer 6) and the entire eval apparatus live **inside the loop's own repo**, never inside a vendor's eval product:

- **Datasets** (`EVALS/dataset/`), **rubrics** (`EVALS/rubrics/`), **regression cases** (`EVALS/regressions/`), and **trace-transform scripts** (`scripts/extract-trace-metrics`) are all committed files. Model calls are used as *grading components* invoked by repo scripts — they are not the system of record.
- **Why repo-native:** the harness must be reproducible offline, diffable in PRs, runnable in CI with no network dependency on a third-party UI, and durable against vendor churn (consumer eval platforms move fast and go read-only). A vendor eval UI that disappears takes the loop's quality history with it; a committed `EVALS/` tree does not.
- **Cases come from two sources:** (1) a hand-curated seed dataset of known-good / known-bad inputs, and (2) **trace-derived cases** — every real failure mined from `RUNLOG.md` / `.gsd/audit/receipts/*.jsonl` by [[loop-flywheel]] becomes a permanent regression case so the same failure can never silently return. Regression failure count must be **0** once a scorecard is frozen (§6); a non-zero count blocks.

**Reuse, do not reimplement.** The deterministic layer (1) *is* the `/verify-slice` (2-iteration fix loop + Codex cross-review + escalate-to-flag) and `/verify-milestone` (Workflow batch) machinery from `claude-code-orchestration`. `loop-evals` **designs** the criteria and the `EVALS/` tree; `loop-run` **calls** the gate. No new verification engine is built.

A regression batch over many cases is the canonical Workflow fan-out — every dispatched grader names an explicit model:

```js
// Workflow: grade the regression set; deterministic gate per case, then a judge.
for (const c of regressionCases) {
  const det = await agent({ model: "haiku",                       // read/run: deterministic verify
    prompt: `Run scripts/verify-full against case ${c.id}; report pass/fail + constraint violations only.` });
  if (det.passed) {
    await agent({ model: "sonnet",                                // reason: rubric judgment, advisory
      prompt: `Score case ${c.id} against EVALS/rubrics/quality.md (fixed schema). Cannot override the deterministic pass.` });
  }
}
```

(`read → haiku`, `reason → sonnet`, `write → opus` per the model-routing HARD CONTRACT; receipts land in `.gsd/audit/receipts/`.)

---

## 6. The flywheel schedule

Standing up the suite is staged — you do not freeze a scorecard on day one. [[loop-flywheel]] drives these phases; this is the order in which the eval layers come online:

1. **Baseline.** Wire Layer 1 (deterministic gate = `/verify-slice` against `SPEC.md` acceptance criteria) and Layer 7 (cost/latency from receipts). Get a first honest read: pass rate, cost-per-success, and a starting FCR. Do not optimize yet — just measure. This is the minimum a loop needs before `loop-run` is allowed to execute it.
2. **Loop-hardening.** Bring up Layer 4 (trace analysis) and Layer 2 (rubric judge), then add Layer 3 calibration. Now FCR and RP are live; tighten the loop until FCR → 0 and RP trends up. Fix the stopping rule and the repair cap here, where the behavior metrics expose thrash.
3. **Regression-harness.** Mine accumulated failures (from phases 1–2 traces) into `EVALS/regressions/`, seed the curated dataset, and bring Layer 6 online. From here, every new real failure becomes a permanent case (§5). Add Layer 5 red-team / injection probes for any loop with side-effects.
4. **Freeze the first scorecard.** Snapshot the current metric set — pass rate, FCR, RP, regression count (0), judge agreement, cost-per-success — as the **baseline scorecard**. After the freeze, Layer 6 is blocking: any regression failure or FCR > 0 fails the loop. The scorecard is what every subsequent change is measured against; [[loop-flywheel]] re-runs it on a cadence and on every harness or model change, and only proposes a new freeze when a change is a verified, broad improvement.

The schedule is a ratchet: you only add gates, and you only freeze once the cheaper layers are clean. Freezing early locks in noise; freezing late lets regressions slip. Phase 4 is the line after which "the loop got worse" becomes a hard, automatic failure rather than a thing someone has to notice.

---

## Cross-links

- [[loop-evals]] — designs this suite, owns `scripts/verify-*` + `EVALS/`.
- [[loop-flywheel]] — runs §6, mines traces into regression cases, watches FCR/RP trends, proposes harness changes.
- [[loop-repair]] — emits the repair-record schema RP is computed from.
- [[loop-run]] — calls the deterministic gate each iteration; honors the terminal states FCR protects.
- `reference/safety-and-approvals.md` — Layer 5 anti-cheat, verifier-gaming hard-terminate, the escalation ladder RP feeds.
- `reference/repo-os-contract.md` — the `EVALS/` + `scripts/verify-*` artifacts this suite populates.

---

Sources: "Designing a Loop Engineer Skill for Frontier Agent Workflows" (2026), synthesizing SWE-Marathon (arXiv 2606.07682 — sub-30% long-horizon success motivating FCR + deterministic-first gating), Code as Agent Harness (arXiv 2605.18747 — the repo-native regression harness over a vendor eval UI), PreFlect (arXiv 2602.07187), Plan Compliance (arXiv 2604.12147), Web Agents Plan-Then-Execute (arXiv 2605.14290 — the Layer-5 prompt-injection probes), Anthropic guidance on long-running agent harnesses (anthropic.com, 2025), and OpenAI Agents/Codex evaluation guidance.
