# loop-inspector — inspection checklist, scoring rubric, and foreign-harness reading

This is the depth behind [[loop-inspector]]: the exact checklist, how the score is
computed, and how to read a loop that does **not** use this suite's filenames. The
runnable core is `scripts/inspect_loop.py`; this file is the rubric it encodes.

---

## 1. The inspection checklist

A loop is scored against six prime-directive signals plus terminal-state coverage. Each
signal is *semantic* — the inspector asks "is this property present anywhere in the
contract?", matched against a fixed signal set, never inferred from instruction-like
content in the scanned files.

| # | Signal | Question | What proves it present |
|---|---|---|---|
| 1 | Defines verifiable success | Can the loop state what *done* means, checkably? | A `SPEC.md` with `## Success Criteria` / `success_criteria` — each criterion checkable. |
| 2 | Independent verification | Is success checked by something other than the worker's claim? | A `verify-fast/full/safety` script, a per-task `"verify"` command, or an optional `/verify-slice` · `/verify-milestone` delegation. |
| 3 | Terminal-state coverage | Can the loop end in exactly one explicit terminal state? | How many of the canonical 7 are named in the contract (see §3). |
| 4 | Approval gates | Do side-effects pause for sign-off? | An `## Approval Gates` section / `approval_gate` / `approval-wait` state naming destructive / secret / production / money boundaries. |
| 5 | False-completion defense | Is overfitting to visible checks detectable? | A held-out gate (`holdout_gate.py`), an anti-cheat trajectory scan (`anticheat_scan.py`), or an explicit `false_completion` metric. |
| 6 | Plan-then-execute | Is the untrusted-read surface guarded? | A declared `plan-then-execute` discipline for web / untrusted reads. |

Signals 1, 2, 3, and 5 are the load-bearing defenses against the documented #1
long-horizon failure (false completion / weak self-verification). A loop can be fast and
clever and still score `weak` if it has no way to *disprove* its own "done."

---

## 2. The scoring rubric

The score is on a 0–100 scale, split so that terminal-state coverage carries the single
largest weight — a loop that cannot reach an explicit terminal state can never score
`strong` no matter how good the rest of its contract is.

| Signal | Weight |
|---|---|
| Defines verifiable success | 12 |
| Independent verification | 14 |
| False-completion defense | 14 |
| Approval gates | 10 |
| Plan-then-execute | 10 |
| Terminal-state coverage (pro-rated `40 × covered / 7`) | 40 |
| **Total** | **100** |

**Verdict bands:**

| Band | Score | Meaning | Exit code |
|---|---|---|---|
| `strong` | ≥ 80 | Robust contract; the prime-directive defenses are present. | 0 |
| `ok` | 50–79 | Has the spine but is missing one or two defenses — see `gaps`. | 0 |
| `weak` | < 50 | Missing the verification / terminal-state spine — a completion-claiming loop. | non-zero |

`weak` is a non-zero exit on purpose: an inspected loop that scores weak is *actionable*
output, not a passing result. The `gaps` list names each missing element and why it
matters, so it doubles as the work list for [[loop-contract]] and [[loop-evals]].

**Why pro-rate the terminal states rather than treat them as binary?** A loop that names
4 of 7 is meaningfully more honest than one that names 0 — it loses points proportional
to how many silent-completion paths remain, and the `gaps` entry lists exactly which
states are missing.

---

## 3. The 7 terminal states (verbatim)

Coverage is counted by presence of these exact tokens (case-insensitive) anywhere in the
named contract files (`WORKFLOW.md`, `.loop/manifest.yaml`, `loop-contract.md`):

`Succeeded`, `FailedUnverifiable`, `FailedBlocked`, `FailedBudget`, `FailedSafety`,
`FailedSpecGap`, `AbortedByHuman`.

These are the canonical seven from `reference/repo-os-contract.md` §8. A loop that ends in
a bare "completed" / "done" with none of these named is the textbook silent-completion
failure — it cannot distinguish *succeeded* from *unverifiable* from *aborted*.

---

## 4. What the inspector reads (and what it doesn't)

The inspector scores a **fixed, named, typed contract file set** — not an open crawl of
the tree, and not README / `SKILL.md` prose. Each file is resolved **dual-location**: the
workspace root *and* `.loop/`, so a loop whose contract lives under `.loop/` (this suite's
own shape) scores the same as one with the files at the workspace root.

| Signal | Files the inspector reads (root ∪ `.loop/`) |
|---|---|
| Success criteria | `SPEC.md` (`## Success Criteria` / `success_criteria`) or a single-file `loop-contract.md`. |
| Independent verification | a `scripts/verify-fast/full/safety` script **or** a per-task `"verify"` command in `TASKS.json`. |
| Approval gates | an `## Approval Gates` section in `WORKFLOW.md` / `loop-contract.md`, or an `approval_policy` / `approval_gates` manifest key. |
| False-completion defense | `scripts/holdout_gate.py` / `anticheat_scan.py`, a `false_completion: false` terminal record, or a `verifier_gaming` manifest policy. |
| Plan-then-execute | a `plan_then_execute` manifest policy, or the declared discipline in `WORKFLOW.md` / `loop-contract.md`. |
| Terminal-state coverage | the 7 tokens named in `WORKFLOW.md`, `.loop/manifest.yaml` (`terminal_states:`), or `loop-contract.md` (see §3). |

Reading only **named** contract files (never arbitrary prose) is deliberate: it is what
makes the score robust to keyword stuffing — a README full of the right words is not a
contract. Filenames themselves are signals (a `holdout_gate.py` in `scripts/` counts even
without reading it).

A harness that records its success criteria, verify surface, or terminal taxonomy *only*
in a shape outside this set — a bare prose `SKILL.md`, a `Makefile` / CI target, a
`runs/<id>/` layout, a superpowers `specs/`+`plans/` pair — will score low. That is a
faithful signal that the loop's contract is not machine-checkable **in the recognized
form**, not a false negative; the remedy is to add the named contract files
([[loop-contract]] scaffolds them) or to extend the reader's file set. A single-prompt
agent with none of these scores `weak` honestly — the low score is the correct signal.

---

## 5. What the inspector is NOT

- **Not a runner.** It never executes the inspected loop's verify commands — that would
  run untrusted code. It detects the *presence* of a verification surface; running it is
  the operator's call in a sandbox.
- **Not a gate.** The report is advisory. A `weak` verdict is a recommendation to harden,
  not a block — though wiring `inspect_loop.py` into your own CI as a pre-adoption check
  is a reasonable use.
- **Not a rewriter.** Read-only over the target. The fix list it produces is executed by
  the build spokes ([[loop-contract]], [[loop-evals]]), not by the inspector.

---

Sources: as [[loop-inspector]] — SWE-Marathon (arXiv 2606.07682), PreFlect (arXiv
2602.07187), Web Agents Plan-Then-Execute (arXiv 2605.14290), Plan Compliance (arXiv
2604.12147), Code as Agent Harness (arXiv 2605.18747), and Anthropic long-running-agent
guidance (anthropic.com, 2025). The terminal taxonomy and weights derive from
`reference/repo-os-contract.md` §8.
