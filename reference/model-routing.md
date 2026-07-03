# Model-routing doctrine — the canonical table + rationale

The one place the `read → haiku / reason → sonnet / write → opus` rule is defined. Every
spoke states the one-line rule inline (so it can act) and points here for the table, the
rationale, and the optional enforcement. This file is the single source of truth; if a skill
and this file ever disagree, this file wins.

> **Base directory.** This file ships at the **plugin root** `reference/` (a sibling of
> `skills/`), i.e. `${CLAUDE_PLUGIN_ROOT}/reference/model-routing.md`. Skills reach it as
> `reference/model-routing.md` resolved against the plugin root, not their own folder.

## The one rule

**Every agent dispatch names an explicit `model:`.** This holds for the `Agent` tool and for
every Workflow `agent()` call. There is no default-by-omission: an omitted `model:` inherits
the costly main-loop model, which is the single biggest cost leak in an agent loop.

## The tier table

| Tier | `model:` | Use it for |
|---|---|---|
| **read** | `haiku` | Read-only lookups feeding the loop — status/coverage scans, trace/RUNLOG fact extraction, a monitor poll, "where is X", list-and-report. The default: anything that only *reports* what it found. |
| **reason** | `sonnet` | Judgment without production writes — plan critique / pre-execution reflection, rubric judging, failure triage, multi-source synthesis, an ADR review. |
| **write** | `opus` | Production writes and load-bearing decisions — the per-task worker, a bounded repair (repairs edit code), committing regression cases. |
| **orchestrate** | main loop | The operator itself — advancing the state machine, choosing the next transition, adjudicating verification. Not a dispatched sub-agent tier. |

Rule of thumb: **read → haiku, reason → sonnet, write → opus, orchestrate → main loop.** If you
cannot justify sonnet or opus for a dispatch, it is a haiku dispatch.

## Why it is load-bearing

- **Cost is bounded.** Routing read-only work to haiku instead of the main-loop model is the
  difference between a loop that is cheap to run overnight and one that is not.
- **Dispatches are auditable.** An explicit tier per dispatch is a receipt line — append one
  receipt per dispatch to `.loop/receipts/*.jsonl` (schema: `schemas/receipt.schema.json`), so
  cost and routing are reconstructable after the run.
- **Omission is a broken call.** Treat a missing `model:` like a missing `prompt:` — fix it
  before dispatching. On the Workflow tool the leak is the same: a model-less `agent()` inherits
  the main-loop model just as an `Agent` call does.

## Optional enforcement (the author's stack — not required)

The rule holds as policy text in `WORKFLOW.md` on any platform, even one that cannot enforce it
at runtime. Where you already run them, these harden it — none are required to run a loop:

- **PreToolUse hooks** (`model_routing.py` for the `Agent` tool, `workflow_routing.py` for
  Workflow `agent()` calls) block a model-less or over-tier dispatch before it fires.
- **`/routing` modes** (`normal` / `conserve` / `burn`) modulate the ceilings; explicitness is
  never waived in any mode.
- **The `[escalation]` valve** — after a *verified* dispatch failure, re-dispatch the same prompt
  at +1 tier once, with the literal `[escalation]` marker in the prompt. Never on a first attempt.

Without any of this, keep the rule as a line in the loop's `WORKFLOW.md` and name `model:` by
hand on every dispatch. That is enough — the enforcement tooling only automates the same rule.
