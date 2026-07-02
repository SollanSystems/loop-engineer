---
name: loop-repair
description: "Patch-and-repair loop for a failing agent run — use when a loop is failing, verification failed, a check is red, or you need to fix-and-rerun. Classifies the failure mode, makes the smallest bounded repair, writes a structured repair record, and enforces a max-attempt cap before it replans, reverts, requests approval, or terminates. Refuses to widen scope or edit the tests to manufacture a pass."
---

# loop-repair

The repair lane. When verification disagrees with the work, **this skill is what reacts — bounded, recorded, and capped.** It does not own running the loop ([[loop-run]] does) or defining the checks ([[loop-evals]] does); it owns the disciplined response to a *failing* check so the loop converges instead of thrashing. Every rule here is downstream of the escalation ladder, the repair cap, and the verifier-gaming guard in `reference/safety-and-approvals.md` — read that for the full safety model; this is the operating procedure.

**When this fires:** a deterministic check (test / lint / typecheck / schema) failed, the rubric judge fell below threshold, or [[loop-run]] reached the `repair` state. Inputs: the failing `verification_bundle`, the best prior `.loop/state.json`, and the diff since that best state. Output: a structured **repair record** (below) + an updated state, then control back to [[loop-run]] to re-verify.

## The REPAIR-LOOP procedure

One pass = one hypothesis = one bounded change = one re-verify. Never batch fixes; never guess twice in one pass.

1. **Read the actual failure.** Open the failing output — the assertion, the stack trace, the lint rule, the judge's named dimension. Do not infer the cause from the goal; infer it from the evidence. (Mirrors the workspace self-annealing rule: analyze the error, don't guess.)
2. **Classify the failure mode** (next section). The class decides the rung and the kind of fix.
3. **Form one hypothesis** — the single most-likely cause, stated as a falsifiable sentence.
4. **Make the smallest bounded repair** that would fix *that* hypothesis and nothing else (see "Smallest bounded repair").
5. **Re-verify** by re-running the exact failing check via [[loop-run]] → `scripts/verify-fast` (then `verify-full` if fast passes). Capture `verification_before` and `verification_after`.
6. **Score the repair.** Did the verification score move toward passing? If yes, the repair was *productive* (this is the **repair-productivity** metric in `reference/eval-suite.md`). If no, it was churn — do **not** keep poking; increment the attempt counter and escalate.
7. **Write the repair record** and update `.loop/state.json`. If passing → return to [[loop-run]] for the next task. If still failing and under the cap → loop to step 1 with a *new* hypothesis. If the cap is hit → escalate (below).

## Failure-mode classification

| `failure_mode` | Signal | Rung / fix shape |
|---|---|---|
| `deterministic-fail` | test / lint / typecheck / schema red | Rung 1 — patch the smallest thing, rerun `verify-fast` |
| `rubric-fail` | judge below threshold on a named dimension | Rung 2 — one targeted repair on *that* dimension only |
| `flaky` | check passes/fails non-deterministically | Stabilize the check or the fixture — never paper over it; an unstable signal is `FailedUnverifiable`, not a pass |
| `regression` | a previously-green check (or a canary) goes red | Rung 1, but treat as high-priority; a tripped canary may escalate to the gaming path |
| `spec-gap` | the failure reveals the criterion itself is undefined/contradictory | Stop repairing → route [[loop-run]] to `FailedSpecGap`; tighten `SPEC.md` first |
| `environmental` | missing dep / credential / external service down | Not a code repair → `FailedBlocked` (or approval gate if a tier-3+ action would fix it) |

Classifying correctly is the whole game: repairing a `spec-gap` or `environmental` failure with code is how loops burn budget on the wrong problem and drift toward verifier-gaming.

## Smallest bounded repair

- **One hypothesis, one change.** The diff should be the minimum that tests the hypothesis. A large speculative refactor is not a repair — it destroys the signal about what actually fixed the failure.
- **Stay inside the failure's blast radius.** Touch the code the failing check exercises; do not refactor adjacent code "while you're in there."
- **No scope-widening.** Do not add features, change the goal, or expand `TASKS.json` to dodge a red check. Widening scope to make a failure "go away" is a gaming precursor (`reference/safety-and-approvals.md` §5).
- **Do not modify existing test assertions, remove test cases, relax fixtures, or alter golden files / the rubric / `SPEC.md` to manufacture a green signal.** Fix the code, not the goalposts. Adding *new* test cases that exercise genuinely uncovered code paths is **not** a violation of this rule — that is legitimate repair. The gaming signal is softening or removing a verification constraint, not extending coverage. The verifier is a protected, *independent* set; weakening it during a run is itself a verifier-gaming signal → hard-terminate `FailedSafety` + logged as a security failure. This is the single hardest rule in the skill.
- **Prefer revert over a worse patch.** If a repair makes the score worse, revert to the best prior `.loop/state.json` before trying the next hypothesis — never stack a bad patch on a bad patch.

## The structured repair record

Every pass appends one record to `.loop/repair/<iteration_id>.json` (and a one-line `RUNLOG.md` entry). All seven fields are required — a record missing `verification_before`/`after` cannot demonstrate productivity and is rejected:

```json
{
  "iteration_id": "iter-007",
  "attempt": 1,
  "failure_mode": "deterministic-fail",
  "hypothesis": "pricing.apply_discount divides by zero when qty == 0",
  "repair_action": "guard qty == 0 -> return base_price; add the zero-qty branch only",
  "verification_before": { "verify_fast": "FAIL", "failing": ["test_zero_qty"], "score": 0.82 },
  "verification_after":  { "verify_fast": "PASS", "failing": [], "score": 1.0 },
  "remaining_delta": "none — all SPEC criteria green",
  "productive": true
}
```

- **`failure_mode`** — the class from the table (decides the rung).
- **`hypothesis`** — the single falsifiable cause this pass tested.
- **`repair_action`** — the minimal change actually made (not a plan; what was done).
- **`verification_before`** — the failing check state *before* the repair.
- **`verification_after`** — the check state *after* re-running (proves the effect).
- **`remaining_delta`** — what is still unmet (drives the next pass or the terminal state). `"none"` means the criterion is met.
- **`productive`** — the derived churn flag (`verification_after.score > verification_before.score`); the field [[loop-evals]] reads to compute the repair-productivity metric.

`productive = verification_after.score > verification_before.score`. A run of non-productive records is the churn signal that trips the cap.

## Max-attempt cap → escalation

The cap is `repair.max_attempts`, **default N=2**, configurable in `WORKFLOW.md`. It bounds rungs 1–2 (the in-run code repairs). When attempts on the *same failure mode* reach N without becoming productive, **stop repairing** and escalate in this order (the operator [[loop-run]] picks per `risk_profile`):

1. **Replan (once).** Hand back to [[loop-run]]'s `replan` state — revise the execution graph, not the same patch. Rung 3. A re-plan that reproduces the same failure mode N more times is exhausted.
2. **Revert.** Restore the best prior `.loop/state.json`; discard the failed diff so the next strategy starts from clean known-good.
3. **Request approval.** If the only fix crosses a side-effect boundary (tier 3/4), pause-and-resume through the approval gate (`reference/safety-and-approvals.md` §2) — never auto-execute it.
4. **Terminate** with the honest terminal state: `FailedUnverifiable` (can't prove the fix), `FailedBlocked` (environmental / approval denied), `FailedBudget` (cap + budget exhausted), or `FailedSpecGap` (the failure exposed an undefined criterion). **Never relabel an unfixed failure as `Succeeded`.**

**Unbounded retrying is itself a failure mode.** It burns budget toward `FailedBudget` and, under retry pressure, is the most common precursor to a stuck agent editing the goalposts. The cap exists to force a *strategy* change (replan/revert/escalate) instead of a louder repeat of the same change.

## Dispatching a repair to a subagent

For a bounded, isolated fix, [[loop-run]] may dispatch the repair to a write-tier agent. Per the model-routing rule (tier table: `reference/model-routing.md`), the dispatch **must** name an explicit `model:` — repairs write production code, so they route to `opus`:

```
Agent(
  subagent_type: "general-purpose",
  model: "opus",            # write tier — repairs edit code
  prompt: "Repair record iter-007: hypothesis='div-by-zero at qty==0'. "
          "Make the SMALLEST bounded fix in pricing.py. Do NOT edit tests, "
          "fixtures, or SPEC.md. Re-run scripts/verify-fast. Return the "
          "verification_before/after and the diff. Stop after one change."
)
```

A read-only triage step (classify the failure, locate the line) routes to `model: "haiku"`; the actual code change routes to `opus`. The acceptance re-verification runs the contract's gate — `scripts/verify-fast`→`verify-full` (optionally `/verify-slice`) — this skill never builds its own verifier; it consumes the one [[loop-evals]] designed. The repair record and the receipt append to `.loop/receipts/*.jsonl` alongside the run.

## Boundaries

- **No secrets** in the hypothesis, the repair record, the diff, or any log.
- **Independent verifier, always.** The agent making the repair is never the agent that grades it — that separation is what keeps the pass signal meaningful.
- **One change per pass; cap the passes; escalate honestly.** That is the entire discipline.

Reference: `reference/safety-and-approvals.md` (escalation ladder §1, approval lifecycle §2, terminal states §3, verifier-gaming §5, anti-cheat canaries §6). Siblings: [[loop-run]] (operator that invokes this), [[loop-evals]] (designs the checks this consumes), [[loop-flywheel]] (promotes every real failure into a permanent regression case).
