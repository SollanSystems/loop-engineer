# Worked example — coverage-repair

A self-contained, end-to-end walk through the **loop-engineer** lifecycle on one concrete
fictional target:

> **Scenario:** *Bring `pricing.py` to `>=80%` line coverage and add typed input validation to
> `parse_request`, via a patch-and-repair loop.*

This is the canonical demonstration that the suite **designs → scaffolds → runs → repairs →
verifies → ends in an explicit terminal state** — reusing existing verification (`/verify-slice`),
the model-routing contract, and the repo-OS contract, with **no new verification engine**. Every
artifact below is exactly what the named spoke would emit; read them in order.

## The arc in one line

`[[loop-architect]]` → ADR (single supervisor / markdown supervisor) → `[[loop-contract]]`
scaffolds SPEC/WORKFLOW/TASKS/RUNLOG/state → `[[loop-run]]` runs the FSM → **iter 1 verify FAIL**
→ `[[loop-repair]]` one bounded productive pass → **iter 2 verify PASS** → `terminal_state.json:
Succeeded`.

## Each artifact, and the spoke that produced it

| File | Produced by | What it shows |
|---|---|---|
| `ADR.md` | `[[loop-architect]]` | The architecture decision: **architecture = supervisor-skill (single supervisor)**, **realization = markdown-supervisor + repo-OS contract**, the loop patterns, the prime-directive check, the risk profile, and why cheaper/costlier shapes were rejected. |
| `SPEC.md` | `[[loop-contract]]` | The **intent** — goal, two independently-verifiable success criteria, constraints, non-goals, and the evidence rule (which `scripts/verify-*` proves each criterion). |
| `WORKFLOW.md` | `[[loop-contract]]` | The **stable loop policy** — state machine, the 7 terminal states, repair cap N=2, approval policy, budgets, and the model-routing dispatch rule. |
| `.loop/manifest.yaml` | `[[loop-contract]]` | The machine-readable operating contract (inputs/outputs/permissions/terminal_states). |
| `TASKS.json` | `[[loop-contract]]` → updated by `[[loop-run]]` | The **machine-readable queue** — `T1` (validation) and `T2` (coverage), each with its `verify` command, `criterion_ref`, `attempts`, and `evidence`. Both end `done`. |
| `RUNLOG.md` | `[[loop-run]]` (+ repair blocks from `[[loop-repair]]`) | The **append-only history** — two dated iterations: iteration 1 verify **FAIL** → repair → iteration 2 verify **PASS** → terminal. |
| `.loop/state.json` | `[[loop-run]]` | The **live FSM cursor** — serialized after every transition; here at the terminal snapshot (`state: terminal`, `best_score: 0.83`, `terminal_state: "Succeeded"`). This is what makes the loop resumable across sessions. |
| `repair-record.json` | `[[loop-repair]]` | One **structured repair record** — `failure_mode`, `hypothesis`, `repair_action`, `verification_before`, `verification_after`, `remaining_delta` (+ `productive: true`). The verification delta proves the repair moved the score (`repair-productivity`). |
| `terminal_state.json` | `[[loop-run]]` | The **single end record** — `state == "Succeeded"`, `criteria_met` both true, `evidence` paths, and `false_completion: false`. No silent "completed." |

> The `scripts/verify-*` gates and `EVALS/` rubrics referenced here are designed by `[[loop-evals]]`
> and *called* by `[[loop-run]]` (delegating acceptance to `/verify-slice`); after the run,
> `[[loop-flywheel]]` mines `RUNLOG.md` + traces to promote the zero-qty / negative-price cases
> into the permanent regression set. This example ships the loop artifacts, not the target repo.

## What to notice (the design points this example proves)

1. **Verification is the source of "done," not prose.** `terminal_state.json` is `Succeeded` only
   because `scripts/verify-full` reported coverage `0.83 >= 0.80` *and* `scripts/verify-fast` showed
   typed rejection — both evidence paths are attached. A claim with no passing gate would have been
   `FailedUnverifiable`, never `Succeeded`.
2. **Bounded, recorded, capped repair.** The single red gate (iteration 1) produced exactly one
   repair record — one hypothesis, one change, one re-verify — and it was **productive**
   (`0.74 → 0.83`), so the cap (N=2) was never reached. No scope-widening, no editing the verifier.
3. **Externalized state = resumable.** Machine truth lives in `.loop/state.json` and `TASKS.json`,
   not in chat context, so a fresh session (or another engine) reconstitutes the loop from disk —
   the repo-OS realization of the Harmony spine pattern.
4. **Reuse, not reinvention.** Acceptance verification delegates to `/verify-slice`; every dispatch
   in `RUNLOG.md`/`WORKFLOW.md` names an explicit `model:` (read→`haiku`, write→`opus`) per the
   model-routing HARD CONTRACT; receipts land in `.loop/receipts/*.jsonl`. The suite added no
   verifier of its own.
5. **An explicit terminal state, always.** The run ends in exactly one of the canonical seven
   (`Succeeded`), written once to `terminal_state.json`.

## Validate the artifacts

```bash
# All JSON in this example parses:
for f in TASKS.json .loop/state.json repair-record.json terminal_state.json; do
  uv run --with pyyaml python3 -c "import json,sys; json.load(open('$f')); print('ok:', '$f')"
done

# The terminal state is Succeeded:
uv run --with pyyaml python3 -c "import json; assert json.load(open('terminal_state.json'))['state']=='Succeeded'; print('terminal: Succeeded')"
```

## Where to go next

- New loop of your own → start at `[[loop-architect]]` (it emits an ADR like `ADR.md`).
- The schema behind every file here → `reference/repo-os-contract.md`.
- The 7-layer eval suite + `false-completion-rate` / `repair-productivity` → `[[loop-evals]]` and
  `reference/eval-suite.md`.
- The full safety / approval / verifier-gaming model → `reference/safety-and-approvals.md`.
