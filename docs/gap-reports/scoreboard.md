# The harness scoreboard — one task, eleven layouts

> **Provenance.** Every foreign row below is evaluated **only** against a
> vendored fixture under [`examples/`](../../examples/) — fictional, sanitized
> content, checked in, instantiating the *same* small task (a CSV
> deduplication) as a **completed run** in that harness's documented layout,
> pinned to the harness commit named in its row. No version-general claims
> about any project are made or implied: every statement is checkable against
> one directory and one SHA.
> **Date:** 2026-07-09.
> **Reproduce any row:** `python3 -m loop inspect examples/<fixture>`

## What this measures — and what it does not

`loop inspect` is the **advisory** scorecard (the hard gate is `loop doctor`,
which only applies to native contracts). It scores one narrow thing: **the
proof-of-done machinery visible on disk** — can a third party, reading only
the files a finished run leaves behind, verify how the run ended?

- verifiable success criteria, independently checkable
- an executable verification surface (`verify-*` / task verify commands)
- approval gates declared for side-effects
- a false-completion defense (a holdout / anti-cheat gate that actually ran)
- the 7 canonical terminal states, so a run cannot end in a silent "completed"

It does **not** measure project quality, adoption, design, or whether the
harness makes agents more effective. Every harness here is popular because it
works for what it optimizes. These systems drive *how an agent works*; the
loop contract proves *how the work ended*. They **compose** — any of these
harnesses can emit the contract at its finish line (four `loop.emit` calls;
worked end-to-end in [`docs/integrations/langgraph.md`](../integrations/langgraph.md)).

**The signals are deliberately conservative, so a low score is not an absence
claim.** Where a harness has real verification machinery the signals cannot
see — different vocabulary, console-only gates, state in SQLite or on GitHub —
the row's *notes* say so explicitly. Those notes were produced by an
adversarial fairness pass over each harness's actual pinned source, hunting
for exactly the machinery our signals miss.

## Methodology

1. One fictional task (`csv-dedupe`, the same fiction as
   [`examples/superpowers-run/`](../../examples/superpowers-run/)) is
   instantiated as a **completed, success-claiming run** under each harness's
   documented on-disk layout, from its pinned source. Structure, filenames,
   and headings follow each harness's own conventions; every sentence of
   content is original and fictional.
2. `loop/foreign.py` maps each layout's own files (its spec, plan, ledger,
   journal) onto the same signal surface — **a mapper, never a scorer**:
   scoring stays layout-blind and identical for native and foreign targets.
   Without the mapping, a low score would be a parsing artifact; with it, the
   remaining gaps are structural.
3. Each row was independently re-derived from the pinned clone by an
   adversarial verifier before publication (fixture fidelity, licensing,
   fairness notes).

Harnesses whose run state lives fundamentally off-repo (OpenHands and
SWE-agent trajectories, platform-hosted runs) are out of scope: there is no
on-disk run record for a repo-native inspector to read — which is its own
answer to the question this scoreboard asks.

## The scoreboard

| Harness | Stars· | Pinned | Fixture | Score | Verdict | Terminals |
|---|---:|---|---|---:|---|---:|
| *(calibration)* loop-engineer contract | — | this repo | [`flaky-test-triage`](../../examples/flaky-test-triage/) | **90** | strong | 7/7 |
| Superpowers ([obra/superpowers](https://github.com/obra/superpowers)) | 251k | fixture× | [`superpowers-run`](../../examples/superpowers-run/) | **12** | weak | 0/7 |
| Spec Kit ([github/spec-kit](https://github.com/github/spec-kit)) | 119k | `3f7392a` | [`spec-kit-run`](../../examples/spec-kit-run/) | **12** | weak | 0/7 |
| CCPM ([automazeio/ccpm](https://github.com/automazeio/ccpm)) | 8.3k | `7d7e462` | [`ccpm-run`](../../examples/ccpm-run/) | **12** | weak | 0/7 |
| BMAD-METHOD ([bmad-code-org/BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD)) | 50k | `49069b8` | [`bmad-run`](../../examples/bmad-run/) | **0** | weak | 0/7 |
| Task Master ([eyaltoledano/claude-task-master](https://github.com/eyaltoledano/claude-task-master)) | 28k | `c0c98d3` | [`task-master-run`](../../examples/task-master-run/) | **0** | weak | 0/7 |
| OpenSpec ([Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec)) | 60k | `93e27a7` | [`openspec-run`](../../examples/openspec-run/) | **0** | weak | 0/7 |
| ruflo ([ruvnet/ruflo](https://github.com/ruvnet/ruflo), né claude-flow) | 64k | `7ef4d4e` | [`ruflo-run`](../../examples/ruflo-run/) | **0** | weak | 0/7 |
| Agent OS ([buildermethods/agent-os](https://github.com/buildermethods/agent-os)) | 5.0k | `cae8e66` | [`agent-os-run`](../../examples/agent-os-run/) | **0** | weak | 0/7 |
| PRPs ([Wirasm/PRPs-agentic-eng](https://github.com/Wirasm/PRPs-agentic-eng)) | 2.2k | `ada2f5b` | [`prp-run`](../../examples/prp-run/) | **0** | weak | 0/7 |
| *(calibration)* an unstructured agent loop | — | this repo | [`naive-loop`](../../examples/naive-loop/) | **0** | weak | 0/7 |

·Stars as reported by the GitHub API on 2026-07-09, for scale only.
×The Superpowers row predates this scoreboard's SHA-pinning: its fixture was
built from the layout documented in [`superpowers.md`](superpowers.md)
(evaluated 2026-07-08) and carries no pinned commit.

## Read the zeros correctly

Three things the table does *not* say:

1. **0 vs 12 is a vocabulary match, not a discipline ranking.** The 12-point
   rows earn exactly one check — a success-criteria heading the signal
   recognizes. BMAD-METHOD carries *more* done-checking machinery than several
   12-point rows (an adversarial review gate, a definition-of-done checklist,
   a mandated red-green-refactor test cycle) yet scores 0, because its
   vocabulary is "Success Measures" and "Acceptance Criteria" and its gates
   are natural-language instructions. The score measures conservative signal
   match; the notes carry the truth.
2. **0/7 terminals across every foreign row is the headline finding.** Not one
   of the nine harnesses ships a typed failure taxonomy. Every one of them
   records "done" — a checkbox, a `status:` string, a dated archive dir, a
   prose "complete" — and none of them can record *"this run failed, here is
   the typed reason"* in a way a machine can refuse to confuse with success.
   A loop that cannot express `FailedUnverifiable` will eventually claim it
   succeeded when it didn't. That is the false-completion surface.
3. **Much of the field's real verification is not portable proof.** The
   pattern repeats across rows: genuine gates exist, but they run
   console-only, live off-disk, or end as self-asserted checkmarks. The
   verification happened; a third party cannot prove it from the repo.

## Per-harness readings

Each reading is what the fixture proves / cannot prove — with the fairness
notes from the adversarial pass over the pinned source.

### Superpowers — 12 / weak

The seed row; the full item-by-item reading is
[`superpowers.md`](superpowers.md). A spec/plan/journal layout that proves
disciplined design-first work and structurally cannot prove how the run ended:
completion is the prose "Marking the work complete." — no typed terminal, no
gate, no evidence trail.

### Spec Kit — 12 / weak

Spec-driven discipline: a numbered `specs/NNN-slug/` folder with a
constitution, requirements checklist, and phased tasks. It proves the front of
the loop well — verifiable Success Criteria, a Constitution Check, a
requirements-quality checklist — the surface the contract layer composes with.
What it structurally cannot prove is how the work ended: no typed terminal, no
held-out gate, no machine-readable done flag.

Fairness notes: `/speckit.implement` runs a real checkbox PASS/FAIL gate and
halts on FAIL — but it is a natural-language instruction that writes no file.
`/speckit.analyze` emits a severity/coverage cross-artifact report —
console-only by design. The Constitution Check is an on-disk PASS gate in
`plan.md`, just under vocabulary no conservative signal matches. Its strongest
verification (a test pinning the exact survivor count, mandated by the
constitution) lives in the code tree, outside any run record.
*Reproduce:* `python3 -m loop inspect examples/spec-kit-run`

### CCPM — 12 / weak

A requirement-to-merge traceability spine: PRD → technical epic → per-task
Definition-of-Done and acceptance checkboxes → parallel-stream analysis →
per-issue journals, rolled up to `status: closed / progress: 100%`. What the
on-disk tree cannot prove is how the run ended: no typed terminal, no
persisted test result, no held-out gate.

Fairness notes: CCPM's real merge-time test run (`sync.md` runs the project's
own suite in the worktree before merge) persists no artifact — its journal
honestly reports counts "from stdout." Its issue-lifecycle audit trail lives
on GitHub, invisible to a repo-only reader. It ships `validate.sh`, a
structural metadata validator — real, but advisory (always exits 0) and aimed
at PM metadata, not code outcome. And it has success rollups but no failure
taxonomy at all.
*Reproduce:* `python3 -m loop inspect examples/ccpm-run`

### BMAD-METHOD — 0 / weak

A disciplined, reviewed story lifecycle: PRD and epics decompose into a story
with quantitative acceptance criteria, a red-green-refactor task ledger, an
adversarial code-review pass, a retrospective, and `sprint-status.yaml`
mirroring every state to `done`. What it cannot prove to an external checker
is machine-checkable completion: `done` is a status string; the
definition-of-done and explicit "no lying or cheating" gates are
natural-language; there is no typed failure terminal or evidence bundle.

Fairness notes: the 0 is a pure vocabulary artifact — success criteria exist
as "## Success Measures" / "## Acceptance Criteria" (with Given/When/Then
thresholds); a real pytest gate is mandated but reports in prose; the
`sprint-status.yaml` ledger has a typed *success* lifecycle
(`ready-for-dev → … → done`) with no failure states. This row carries more
completion discipline than its score can show.
*Reproduce:* `python3 -m loop inspect examples/bmad-run`

### Task Master — 0 / weak

A disciplined, resumable run record: a parsed PRD, a complexity analysis, and
a `.taskmaster/tasks/tasks.json` ledger where every task carries a
`testStrategy` and a timestamped journal of verification evidence. What it
structurally cannot prove is that completion was independently gated: the
default status write is unenforced, and there is no typed terminal record.

Fairness notes: per-task acceptance criteria are real (`testStrategy`), just
not under a recognized heading. Its strongest gate is code-enforced but
off-tree: the autopilot TDD workflow (RED/GREEN/COMMIT, commit blocked until
tests pass) persists its state under the *user home* directory, not the
project — so an in-project read sees status fields, not the gate. Editor
hooks (test-success task completion, PR-readiness) gate completion externally
too.
*Reproduce:* `python3 -m loop inspect examples/task-master-run`

### OpenSpec — 0 / weak

An archived-change layout that proves a change was proposed, specified with
WHEN/THEN acceptance scenarios, designed, worked to a fully-checked task
ledger, and reconciled into a living capability spec. What it cannot
structurally prove is that code ran: completion is a dated `archive/` dir plus
an updated spec — a path convention, not a typed terminal — and the checked
`## Verification` boxes are self-asserted.

Fairness notes: `openspec validate --strict` is a real deterministic gate (it
refuses any requirement without a scenario) — but it checks document
structure, not test runs, and isn't a `verify-*` surface the signals credit.
`/opsx:verify` emits a completeness/correctness/coherence verdict —
console-only, persists nothing. The done-idiom (a checked Verification task
block) is de-facto success criteria under vocabulary the scan misses.
*Reproduce:* `python3 -m loop inspect examples/openspec-run`

### ruflo — 0 / weak

The most verification-rich layout on this board, and the least portable: a
multi-phase SPARC run with five recorded quality gates (criteria like
"coverage ≥ 80%, all ACs have tests"), an AC→test→code traceability matrix, a
truth score, and a CVE-clean security badge — held in SQLite memory
(`.swarm/memory.db`, `.hive-mind/hive.db`) and JSON exports rather than a
portable contract. What it cannot give an outside reader is a typed terminal
or a held-out gate they can independently replay: its criteria and verdicts
are self-asserted inside the swarm's own memory.

Fairness notes: the gate ledger, structured acceptance criteria, coverage and
security gates are all *real and recorded* — no conservative text signal can
point at a binary DB, and self-computed verdicts (truth score 0.97) earn no
credit by the same rule that a self-asserted `false_completion: false` earns
none. The honest weak score measures the portability gap, not ruflo's rigor.
*Reproduce:* `python3 -m loop inspect examples/ruflo-run`

### Agent OS — 0 / weak

Agent OS v3.0 is a deliberate refocus onto standards and spec-shaping: a run
leaves a standards tree and a shaped spec (`shape.md`, `plan.md`) in a
timestamped spec dir. It proves careful, standards-anchored specification.
By design, v3.0 retired the implementation/verification phases earlier
versions shipped — so a completed run's on-disk record is a spec, and
questions of how execution *ended* are outside what the layout can express:
no ledger, no journal, no terminal record.

Fairness notes: v3.0's genuine gates are procedural (plan-mode entry
enforcement on `/shape-spec`) and human (confirm-before-create) — they gate
how work *starts*, not how it ended. Its definition-of-done lives in
`shape.md`'s scope prose, vocabulary no conservative signal matches; git
history and the ephemeral todo are its completion signals, both outside the
spec dir. This row should be read against v3.0's chosen scope, not v1/v2's.
*Reproduce:* `python3 -m loop inspect examples/agent-os-run`

### PRPs — 0 / weak

A disciplined prd → plan → implement → review pipeline under `.claude/PRPs/`:
the plan carries a six-level *executable* validation gate ("every command must
exit 0"), a per-change validate-until-green loop, and a machine
`{clean, blocking}` review verdict the loop blocks completion on — all
recorded on disk (run log, `green@2` state history, `verdict.json`). The
layout proves work was planned, validated to green, and reviewed clean. What a
single-repo convention structurally cannot carry is exactly what the contract
scores for: an *independent held-out* gate — the review is the same agent
family reviewing its own PR — and a typed terminal (done is a plan archived
into `plans/completed/`).

Fairness notes: PRPs comes closest on this board to portable verification
evidence; the 0 measures the delta between "recorded and reviewed done" and
"proven un-fakeable done" — signal-shape (markdown-embedded commands, a
review verdict rather than a named holdout gate), not intent. Verifiable
success criteria exist in the plan and PRD, outside the role the
success-criteria signal reads.
*Reproduce:* `python3 -m loop inspect examples/prp-run`

## What the whole field is missing

Across nine popular harnesses — ~590k stars of them — the same three
structural gaps repeat, independent of methodology, maturity, or how much
verification machinery each ships:

1. **No typed terminal taxonomy (0/7, every row).** "Done" is always
   expressible; *"failed, and here is the machine-readable reason"* never is.
2. **No held-out gate.** Every verification surface that exists is run by the
   same agent that claims success, and most persist nothing. Nothing prevents
   the claim from being wrong — and nothing measures how often it is (no row
   has anything a false-completion-rate could be computed from).
3. **Proof is not portable.** The field's real gates end as stdout, GitHub
   state, home-dir session files, or SQLite — all invisible to the next tool,
   the reviewer, or CI reading the repo.

None of this is an argument against any harness. It is an argument that the
*contract* — typed terminals, an evidence trail, a held-out gate, derivable
FCR/RP — is a missing **layer**, one every harness on this board could emit
at its finish line. The port is small: four `loop.emit` calls
(`open_contract`, `append_iteration`, `append_receipt`, `terminate`), worked
end-to-end for a real engine in
[`docs/integrations/langgraph.md`](../integrations/langgraph.md) and
[`docs/integrations/temporal.md`](../integrations/temporal.md).

## Contribute a row

The method is repeatable and every step is checkable: pin a SHA, vendor a
faithful fictional fixture, map the layout in `loop/foreign.py` (a mapper,
never a scorer), let the inspector read it, and write the fairness notes from
the pinned source. Gap-report contributions are welcome — see
[`docs/contributing/issues/06-help-wanted-gap-reports.md`](../contributing/issues/06-help-wanted-gap-reports.md)
and use [`superpowers.md`](superpowers.md) as the deep-dive template.
