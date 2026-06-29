# WORKFLOW.md — pricing-coverage-and-validation Loop Policy

> Stable loop policy. Governs HOW the loop runs, not WHAT it builds.
> Scaffolded by `loop-contract`. Do NOT change during a run without re-entering the `plan` state.

## Loop

```
intake → plan → critique-plan → queue-tasks
  → execute-task → verify
    → [pass] → next-task or terminal(Succeeded)
    → [fail] → repair (cap N=2) → [fixed] → verify
                                 → [cap exceeded] → replan | revert | approve | terminate
    → [approval needed] → approval-wait → resume
    → [budget exceeded] → terminal(FailedBudget)
    → [safety violation] → terminal(FailedSafety)
    → [spec gap] → terminal(FailedSpecGap)
    → [human abort] → terminal(AbortedByHuman)
```

State is externalized to `.loop/state.json` after every transition.
Resume rule: if `.loop/state.json` exists with `terminal_state: null`, skip intake and continue
from `state`. `[[loop-run]]` operates this machine one transition per turn.

## Approval gates

Side-effect boundaries that pause for approval: destructive commands, secret access, production
changes, money movement, policy-sensitive output. `approval_policy`: `on_side_effects`.

This loop is `risk_profile: low` (workspace-write only), so no gate fired during the run —
adding tests and validation code are not side effects. Approval gates pause-and-resume from the
same `.loop/state.json` checkpoint; they never spawn a fresh untracked attempt.

## Budgets

- **Time budget:** `30m`
- **Cost budget:** `1.00usd`
- Tracked in `.loop/state.json` as `budget_remaining`. On exhaustion → `FailedBudget` immediately.

## Repair cap

- **Max repair attempts per task:** `2` (default).
- After exceeding the cap: replan / revert / approve / terminate — never silently retry.
- Each repair attempt produces a structured repair record (see `[[loop-repair]]` and
  `repair-record.json` in this example).
- A repair that does not measurably improve the score is churn → replan.
- Detected verifier-gaming → hard-terminate `FailedSafety` immediately.

## Terminal states

Exactly 7. No other string is a valid terminal state. No silent "completed."

| State | Fires when |
|---|---|
| `Succeeded` | All success criteria verified with evidence |
| `FailedUnverifiable` | Cannot produce or run verification; evidence missing or contradicting |
| `FailedBlocked` | External dependency, permission, or tool boundary prevents progress |
| `FailedBudget` | `time_budget` or `cost_budget` exhausted before `Succeeded` |
| `FailedSafety` | Safety violation, approval bypass, or verifier-gaming detected |
| `FailedSpecGap` | Success criteria undefined, contradictory, or unverifiable by design |
| `AbortedByHuman` | A human explicitly stopped the run |

When a terminal state is reached, write `.loop/terminal_state.json` and stop. Never claim
`Succeeded` without verification evidence; unverified completion → `FailedUnverifiable`.

## Dispatch (model-routing HARD CONTRACT)

Every dispatched agent / Workflow `agent()` names an explicit `model:` — read→`haiku`,
reason→`sonnet`, write→`opus`, orchestrate→main loop. Receipts land in
`.loop/receipts/*.jsonl`; `/routing` modes are honored. In this run the coverage status
read used `haiku` and the test-writing repair used `opus` (see `RUNLOG.md`).

## Verification

- `scripts/verify-fast` — deterministic gate (validation tests + lint), run after every task.
- `scripts/verify-full` — full deterministic gate incl. coverage, run before claiming `Succeeded`.
- Acceptance verification delegates to `/verify-slice` (claude-code-orchestration); this loop
  builds **no new verifier**. The deterministic gate is binary and BLOCKING; any rubric judge is
  advisory only.
- Do not modify tests or verification scripts to make them pass.

## Anti-cheat

High-value regression tasks carry hidden canary checks and adversarial probes. Passing
verification by editing the verifier is `FailedSafety` + logged as a security failure.
