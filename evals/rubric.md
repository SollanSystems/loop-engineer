# loop-engineer Self-Eval Rubric

**Purpose:** Scored by an LLM judge (`scripts/self_eval.py`) against the built suite.
The deterministic structural gate (100% pass rate) is the hard pass/fail;
this rubric is advisory toward the **target mean ≥ 9.5 / 10**.

**Scoring rule:** each dimension is rated 1–10 against its anchor descriptions.
The weighted mean is `sum(score_i * weight_i) / sum(weight_i)`.
A failing dimension drags the mean below threshold; all 10 must be reviewed.

---

## Dimensions

### 1. Research-Fidelity — weight 1.5

The skill suite accurately reflects the source research (PreFlect, SWE-Marathon,
plan-then-execute, plan-compliance, Code-as-Agent-Harness) and does not invent
mechanisms not present in the spec or research.

| Score | Anchor |
|-------|--------|
| 1 | Claims from the research are misrepresented or fabricated; key findings (e.g., sub-30% SWE-Marathon success rate, PreFlect A/B trigger policy) absent or contradicted. |
| 5 | Research findings are cited but imprecisely; one or two mechanisms named but not operationalized in the suite. |
| 10 | Every mechanism in the spec traceable to a research finding; nothing invented; quantitative claims (e.g., sub-30% LH failure rate) correctly attributed and operationalized (e.g., `FailedSpecGap` directly defends it). |

---

### 2. Scenario-Routing-Correctness — weight 1.5

`loop-architect` correctly maps the 5 scenario signals to the right architecture
and the right realization primitive, and the decision table is complete and internally
consistent.

| Score | Anchor |
|-------|--------|
| 1 | Architecture selection criteria missing or mixed up (e.g., single-session fan-out routed to Python-FSM-spine instead of Workflow tool). |
| 5 | Three of five scenarios correctly mapped; one realization primitive confused with another. |
| 10 | All 5 scenarios correctly classified with rationale; the maximize-single-agent-first rule stated; each realization (Workflow tool / markdown-supervisor / Harmony spine / /verify-slice delegation) named precisely and tied to the correct scenario. |

---

### 3. Contract-Completeness — weight 1.5

`loop-contract` scaffolds every repo-OS artifact (AGENTS.md, SPEC.md,
WORKFLOW.md, TASKS.json, RUNLOG.md, EVALS/, scripts/, .loop/state.json) and
the `loop-run` skill exposes the full state-machine with a traceable
`state.json`-externalization rule.

| Score | Anchor |
|-------|--------|
| 1 | Multiple repo-OS artifacts missing from scaffolding; state machine omits key transitions (e.g., no repair branch, no approval-wait). |
| 5 | Six of eight artifacts scaffolded; state machine present but approval-wait / replan not distinct nodes. |
| 10 | All repo-OS artifacts scaffolded with per-field schema; state machine includes all nine nodes (intake→plan→critique→queue→execute→verify→repair/replan/approval-wait→terminal); resume-from-`state.json` rule unambiguous. |

---

### 4. Reuse-Not-Duplication — weight 1.0

The suite delegates verification to `/verify-slice` / `/verify-milestone`,
grader design to `launch-local-agent` patterns, resume-state to Harmony `engine/cli.py`,
and routing to `model_routing.py` / `workflow_routing.py` — without reimplementing
any of them.

| Score | Anchor |
|-------|--------|
| 1 | One or more capabilities reimplemented inline (e.g., a new verify loop written in `loop-run`, a new FSM in `loop-repair`). |
| 5 | References are mentioned but not positioned as delegation targets; a partial reimplementation exists for one capability. |
| 10 | Every reused asset named explicitly as a call target (not just "see also"); no duplicate verification engine; the reuse contract table in the spec is reflected in the skills. |

---

### 5. Safety and Terminal-State Rigor — weight 1.5

All 7 terminal states are present, distinct, non-overlapping, and each state's
trigger condition is unambiguous. The escalation ladder, approval-lifecycle, and
verifier-gaming hard-terminate are all encoded.

| Score | Anchor |
|-------|--------|
| 1 | Fewer than 7 terminal states; "completed" used as a silent default; approval bypass possible; verifier-gaming not mentioned. |
| 5 | All 7 states present but trigger conditions for two or more overlap or are ambiguous; escalation ladder partially described. |
| 10 | All 7 states present with distinct, checkable trigger conditions; escalation ladder rung-by-rung (deterministic-fail→patch; rubric-fail→critique; repeat-fail→replan; side-effect→approval-wait; policy-risk→FailedSafety; verifier-gaming→hard-terminate+log); approval pause/resume rule unambiguous. |

---

### 6. Eval-Suite Depth — weight 1.0

`loop-evals` covers all 7 eval layers, defines false-completion-rate and
repair-productivity as first-class metrics, and encodes the deterministic-first
rule and judge-calibration cadence.

| Score | Anchor |
|-------|--------|
| 1 | Fewer than 5 eval layers; neither missed metric defined; judge calibration absent. |
| 5 | All 7 layers named but mechanisms for 2–3 are vague; one missed metric defined but the other omitted. |
| 10 | All 7 layers present with mechanism + key metric; both false-completion-rate and repair-productivity defined with precise formulas; deterministic-gate-first rule stated; judge-calibration cadence (human-labeled set, monthly + post-model-change review) explicit. |

---

### 7. Flywheel and Memory Clarity — weight 1.0

`loop-flywheel` clearly distinguishes short-term compaction (continue-this-run)
from long-term lessons (improve-future-runs), explains trace→eval→harness-change
loop, and states the freeze-scorecard condition.

| Score | Anchor |
|-------|--------|
| 1 | No distinction between short-term and long-term memory; trace mining not described; improvement schedule absent. |
| 5 | Short/long distinction present but conflated in the procedure; trace→eval→harness path described at high level only. |
| 10 | Short-term (compaction summary written to `.loop/memory/session-summary.md`) and long-term (lessons written to `.loop/memory/lessons.md` and surfaced to flywheel) distinguished by destination and cadence; trace→eval→new-regression-case pipeline step-by-step; freeze condition (stable metric + ≥2 iterations without regression) stated. |

---

### 8. Frontmatter and Trigger Quality — weight 0.5

Every SKILL.md has a quoted `description:`, `name:` matching its directory,
and a trigger set that is specific enough to route correctly without ambiguity
(no triggers broad enough to catch all intents or narrow enough to miss the
obvious phrasings).

| Score | Anchor |
|-------|--------|
| 1 | Two or more SKILL.md files have unquoted descriptions or name mismatches; trigger sets empty or duplicated across spokes. |
| 5 | All frontmatter parses; triggers present but two or more spokes share an overlapping trigger phrase that would route ambiguously. |
| 10 | All 7 frontmatter blocks parse via `yaml.safe_load` to a dict; `name:` == directory in every case; trigger set per spoke covers natural phrasings without overlap; validate_frontmatter.py passes 7/7. |

---

### 9. Brevity and Altitude — weight 0.5

SKILL.md bodies stay tight (~80–200 lines); depth lives in `reference/`;
skills operate at the right altitude (instruction, not prose narration).

| Score | Anchor |
|-------|--------|
| 1 | One or more SKILL.md files exceed 300 lines; content that belongs in `reference/` is inlined; narrative prose replaces imperative instructions. |
| 5 | Bodies within range but two or more skills contain inline lookup tables that duplicate `reference/` content. |
| 10 | All SKILL.md bodies within 80–200 lines; all deep tables/schemas/matrices live in `reference/` with a pointer; instructions are imperative and scannable; no narration. |

---

### 10. Worked-Example Quality — weight 0.5

The `examples/coverage-repair/` scenario is self-consistent, end-to-end,
and demonstrates the full arc: ADR → scaffolded contract → ≥2 RUNLOG iterations →
one repair record → terminal state `Succeeded`.

| Score | Anchor |
|-------|--------|
| 1 | Example missing key artifacts (no ADR, or RUNLOG has only 1 iteration, or no repair record); terminal state absent or inconsistent. |
| 5 | All files present; RUNLOG has ≥2 iterations but the repair record does not connect to the failing verification in iteration 1; terminal state present but not traced to evidence. |
| 10 | ADR names architecture=single-supervisor + realization=markdown-supervisor with rationale; RUNLOG iteration 1 shows a verify-fail linked to the repair record; iteration 2 shows the repair outcome (verify-pass); terminal_state.json is `Succeeded` with cited verification evidence; README ties each artifact to the producing spoke. |

---

## Scoring Summary

| # | Dimension | Weight |
|---|-----------|--------|
| 1 | Research-Fidelity | 1.5 |
| 2 | Scenario-Routing-Correctness | 1.5 |
| 3 | Contract-Completeness | 1.5 |
| 4 | Reuse-Not-Duplication | 1.0 |
| 5 | Safety and Terminal-State Rigor | 1.5 |
| 6 | Eval-Suite Depth | 1.0 |
| 7 | Flywheel and Memory Clarity | 1.0 |
| 8 | Frontmatter and Trigger Quality | 0.5 |
| 9 | Brevity and Altitude | 0.5 |
| 10 | Worked-Example Quality | 0.5 |
| | **Total weight** | **10.0** |

**Target: weighted mean ≥ 9.5 / 10.**

A suite that scores below 9.5 is sent to the Opus fix pass
(`loop-flywheel` → re-author the failing dimension → re-score).
The structural gate (100% pass) is independent and must clear first.
