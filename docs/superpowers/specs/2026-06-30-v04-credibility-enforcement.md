# v0.4 — Enforce the Wedge: Credibility-Enforcement Spec

**Status:** SPEC (design + tests-to-write). Not an implementation.
**Date:** 2026-06-30
**Sources of truth:** `review/REVIEW.md`, `review/IMPROVEMENT-BACKLOG.md`,
`review/POSITIONING.md`, `review/COMPETITIVE-ANALYSIS.md`.
**Scope of this spec:** the four fixes that convert Loop Engineer's headline
differentiator — *"they execute the loop; Loop Engineer proves when it's done"* —
from **self-asserted** to **enforced**. Covers findings **G1**, **M1 + HI4**,
**M2 + HI1**, **HI6**.

---

## 0. Why these four, and why together

The review's central finding (REVIEW §1, §3.5 note, IMPROVEMENT-BACKLOG "Honesty
note on the wedge") is that **false-completion defense is, in load-bearing paths,
narrated rather than enforced**: a loop can self-assert `false_completion:false`
and receive full credit — from the contract validator, from the inspector score,
and in the flagship example — without any held-out or anti-cheat gate ever
running. And the one script whose job is to catch a gamed gate cannot detect
being gamed itself.

Each fix closes one leak in the same pipe:

| Fix | Finding(s) | Severity | The leak it plugs |
|---|---|---|---|
| G1 | REVIEW G1 / QW2 | HIGH | Contract validator accepts a self-contradictory `Succeeded` terminal. |
| M1 + HI4 | REVIEW M1 / HI4 | HIGH | Inspector awards anti-cheat credit for a bare terminal flag. |
| M2 + HI1 | REVIEW M2, O1 / HI1 | HIGH | Flagship example's `false_completion:false` is gate-less. |
| HI6 | REVIEW G3 / HI6 | MEDIUM | Anti-cheat scanner cannot detect a logic rewrite of its own gate functions. |

They interlock: **M2/HI1 makes the example gate-backed**, which is a precondition
for **M1/HI4's tightened inspector rule** to still grant the example credit
(otherwise tightening M1 would make the repo's own demo fail its own check).
Ship them in one v0.4 batch. Every fix below ships with a regression test that is
**RED on today's code and GREEN after the fix**, pinning the exact repro quoted
in REVIEW.md.

**Test invocation (canonical for this repo):**
```
uv run --with pytest --with pyyaml python -B -m pytest -q scripts loop
```
Green baseline before this work: 105 passed / `self_eval` 13/13.

---

## 1. G1 — Contract validator must cross-check the terminal state

### 1.1 Problem (file:line + repro)

`loop/contract.py:169` `_validate_terminal()` validates only *field types* — that
`state` is one of the 7 canonical states, `criteria_met` is a dict, `evidence` is
a list, `false_completion` is a bool. It never checks that a **`Succeeded`**
terminal is internally consistent. (REVIEW **G1**, HIGH, CONFIRMED;
IMPROVEMENT-BACKLOG **QW2**.)

Verified repro (REVIEW G1, `loop/contract.py:169-180`):

```python
_validate_terminal(
    {'schema': 'loop-engineer/terminal@1', 'state': 'Succeeded',
     'criteria_met': {}, 'evidence': [], 'false_completion': True},
    path, issues,
)
# -> issues == []   (validates clean; doctor/validate_contract report ok)
```

A `terminal_state.json` can claim victory (`Succeeded`) while simultaneously
flagging itself a false completion (`false_completion:true`) and listing **zero**
met criteria — and `validate_contract()` (`loop/contract.py:219`) /
`doctor_report()` (`loop/contract.py:243`) pass it clean. For the P3 evaluator
who runs `doctor` to decide whether the proof layer is real, this single repro
refutes the entire wedge.

### 1.2 Enforcement design

Add a **cross-field consistency rule** to `_validate_terminal`, after the
existing type checks, gated on `state == "Succeeded"` so failure-state terminals
(which legitimately carry `false_completion:true` and/or empty `criteria_met`)
are never touched:

```python
# after the four existing type checks in _validate_terminal:
if data.get("state") == "Succeeded":
    if data.get("false_completion") is not False:
        issues.append(ContractIssue(
            "contradictory_terminal",
            "Succeeded terminal requires false_completion == false",
            path,
        ))
    criteria = data.get("criteria_met")
    if not (isinstance(criteria, dict) and any(v is True for v in criteria.values())):
        issues.append(ContractIssue(
            "contradictory_terminal",
            "Succeeded terminal requires >=1 true entry in criteria_met",
            path,
        ))
```

Rules, stated normatively:

- **R1** — `state == "Succeeded"` ⇒ `false_completion` **is** `False` (exactly
  `False`, not merely falsy — `None`/missing must fail, since the type check
  already requires bool but a self-contradictory file must not slip through on a
  missing key).
- **R2** — `state == "Succeeded"` ⇒ `criteria_met` is a dict with **≥1** entry
  whose value is exactly `True`.
- **R3** — Non-`Succeeded` terminals are **exempt** from R1/R2 (a `FailedBudget`
  run may honestly report `false_completion:true` and `criteria_met:{}`).

Both R1 and R2 emit the same issue code `contradictory_terminal` so
`doctor`/`validate_contract` surface it as one class. `SCHEMA_IDS` /
`schemas_checked` are unaffected (still the same 4 validators).

### 1.3 Tests — RED then GREEN

Add to `scripts/test_loop_contract_core.py`:

1. **`test_validate_terminal_rejects_succeeded_with_false_completion_true`**
   — pins the exact REVIEW G1 repro: `Succeeded` + `false_completion:True` +
   `criteria_met:{}`. Asserts `validate_contract`/`_validate_terminal` returns
   **≥1** issue whose code is `contradictory_terminal`.
   *RED today* (repro returns `[]`) → *GREEN after fix*.
2. **`test_validate_terminal_rejects_succeeded_with_empty_criteria_met`**
   — `Succeeded` + `false_completion:False` + `criteria_met:{}` (isolates R2).
   Asserts a `contradictory_terminal` issue. *RED → GREEN.*
3. **`test_validate_terminal_rejects_succeeded_with_all_false_criteria`**
   — `Succeeded` + `false_completion:False` + `criteria_met:{"1": false}`
   (no *true* entry). Asserts a `contradictory_terminal` issue. *RED → GREEN.*
4. **`test_validate_terminal_accepts_consistent_succeeded`** (guard, must be
   GREEN after)
   — `Succeeded` + `false_completion:False` + `criteria_met:{"1": true}` ⇒ no
   `contradictory_terminal` issue. Prevents over-blocking.
5. **`test_validate_terminal_allows_failure_state_with_false_completion_true`**
   (guard for R3, must be GREEN after)
   — `state:"FailedBudget"` + `false_completion:True` + `criteria_met:{}` ⇒ no
   `contradictory_terminal` issue. Proves failure terminals are exempt.
6. **`test_doctor_flags_contradictory_terminal_from_disk`**
   — write the repro `terminal_state.json` into a `tmp_path` contract fixture,
   run `doctor_report(tmp_path)`, assert `ok is False` and the issue surfaces
   end-to-end. *RED → GREEN.*

The existing `test_loop_doctor_accepts_valid_contract_*` tests
(`scripts/test_loop_contract_core.py:137,154`) must **stay green** — their
terminal fixtures already carry `false_completion:false` + a true criterion.

### 1.4 Acceptance

- The REVIEW G1 repro now yields ≥1 `contradictory_terminal` issue; `doctor` /
  `validate_contract` report `ok:false` for it.
- Consistent `Succeeded` terminals and all non-`Succeeded` terminals validate
  unchanged.
- Full suite green including the two pre-existing valid-contract doctor tests.

---

## 2. M1 + HI4 — Inspector grants false-completion-defense credit only on detectable gate invocation

### 2.1 Problem (file:line + repro)

`scripts/inspect_loop.py:187-193` computes the `false_completion_defense`
checklist item (worth 14 of 100 points, `_CHECKS` in `inspect_loop.py`):

```python
has_false_completion = (
    _script_exists(paths.workspace, "holdout_gate.py", "anticheat_scan.py", "anti_cheat.py")
    or terminal.get("false_completion") is False      # <-- the leak (line 189)
    or "verifier_gaming" in str(manifest).lower()
    or "false-completion" in workflow
    or "false_completion" in workflow
)
```

The `terminal.get("false_completion") is False` disjunct awards **full**
anti-cheat credit whenever a `terminal_state.json` merely *states* the flag — with
no check that a held-out / anti-cheat gate ever ran. That is exactly the
self-reported signal `reference/eval-suite.md:62` says the metric is meant to
*replace*. (REVIEW **M1**, HIGH, CONFIRMED; IMPROVEMENT-BACKLOG **HI4**.)

The mere-`_script_exists` disjunct is the same class of leak one step weaker:
credit for a gate file **existing** in `scripts/`, not for it being **invoked**.
Per the finding's own wording — *"only when … actually invoked … not merely
exists"* — both are tightened.

### 2.2 Enforcement design

Replace the bare-flag and mere-existence disjuncts with an **invocation-detection**
signal. Add a helper `_gate_invoked(paths) -> bool` that returns `True` iff a
reference to a held-out / anti-cheat gate (`holdout_gate`, `anticheat_scan`,
`anti_cheat`) is textually present in **any** of the loop's *execution-trail*
artifacts — the surfaces that only get a gate name written into them when the
gate was actually wired into a run:

- each existing verify-* script's text
  (`verify-fast[.sh]`, `verify-full[.sh]`, `verify-safety[.sh]`), and
- `RUNLOG.md` (the append-only iteration trail; the example writes the gate into
  its Terminal block), and
- any `TASKS.json` task `verify` command string.

```python
_GATE_TOKENS = ("holdout_gate", "anticheat_scan", "anti_cheat")

def _gate_invoked(paths) -> bool:
    haystacks = [_read_text(s) for s in _verify_script_paths(paths.workspace)]
    haystacks.append(_read_text(paths.runlog))
    haystacks.extend(
        str(row.get("verify", ""))
        for row in _read_json_object(paths.tasks).get("tasks", [])
        if isinstance(row, dict)
    )
    blob = "\n".join(haystacks).lower()
    return any(tok in blob for tok in _GATE_TOKENS)
```

New credit rule for `false_completion_defense`:

```python
has_false_completion = (
    _gate_invoked(paths)                              # invocation, not existence
    or "verifier_gaming" in str(manifest).lower()     # manifest declares the policy
    or "false-completion" in workflow                 # WORKFLOW documents the defense
    or "false_completion" in workflow
)
```

Normative rules:

- **R1** — A bare `terminal_state.json.false_completion == false` grants **no**
  credit on its own (the `terminal.get(...) is False` disjunct is **removed**).
- **R2** — Credit is granted when a gate token is detectable in a verify script,
  `RUNLOG.md`, or a `TASKS.json` verify command (evidence the gate was run).
- **R3** — The manifest `verifier_gaming` policy and `WORKFLOW.md`
  false-completion prose remain valid credit sources (they are contract-owned
  declarations of the defense, not per-run self-report), matching REVIEW M1/HI4
  which scope the fix to the *terminal flag*.

Design note: mere `_script_exists(... holdout_gate.py ...)` is intentionally
**dropped** as a standalone credit source per the finding's "actually invoked …
not merely exists" wording; a gate file that is never referenced by any verify
script / RUNLOG / task earns nothing.

### 2.3 Tests — RED then GREEN

Add to `scripts/test_inspect_loop.py` (build minimal loop dirs under `tmp_path`
exercising `_evaluate_contract_checks(loop_dir)["false_completion_defense"]`):

1. **`test_false_completion_defense_denied_for_bare_terminal_flag`** — pins the
   HI4 "flag set but gate never run → no credit" repro: dir has
   `terminal_state.json {"false_completion": false}` and **no** gate reference in
   any verify script / RUNLOG / TASKS / manifest / WORKFLOW. Assert credit is
   `False`. *RED today* (line 189 grants `True`) → *GREEN after fix*.
2. **`test_false_completion_defense_denied_when_gate_only_exists_never_invoked`**
   — `scripts/holdout_gate.py` file present but referenced nowhere. Assert credit
   `False`. *RED today* (`_script_exists` grants `True`) → *GREEN after fix*.
3. **`test_false_completion_defense_granted_when_gate_invoked_in_runlog`** —
   `RUNLOG.md` mentions `holdout_gate.py`; no terminal flag, no script file.
   Assert credit `True`. *RED today* (no current disjunct matches) →
   *GREEN after fix* (proves the RUNLOG invocation path is wired).
4. **`test_false_completion_defense_granted_when_gate_invoked_in_verify_script`**
   — `scripts/verify-full` text calls `anticheat_scan.py`. Assert credit `True`.
   *GREEN after fix.*
5. **`test_false_completion_defense_granted_from_manifest_policy`** (guard, R3)
   — manifest contains `verifier_gaming`, no terminal flag. Assert credit `True`
   (unchanged behavior preserved). *GREEN before and after.*

### 2.4 Acceptance

- A bare `false_completion:false` flag, and a merely-present-but-uninvoked gate
  file, both earn **no** `false_completion_defense` credit.
- Credit is earned when a gate token is detectable in a verify script, `RUNLOG.md`,
  or a task verify command (or via the manifest/WORKFLOW declaration).
- Only the `false_completion_defense` check changes; the other four checklist
  items and the terminal-coverage score are byte-for-byte unaffected (existing
  `scripts/test_inspect_loop.py` cases for those stay green).
- **Cross-dependency:** after §3 (M2/HI1) lands, the flagship example must earn
  this credit via real invocation — see §3.3 test 4.

---

## 3. M2 + HI1 — Flagship example must actually run the held-out gate

### 3.1 Problem (file:line + repro)

`examples/coverage-repair/terminal_state.json:10` asserts
`"false_completion": false`, but:

- the only cited evidence files (`.loop/artifacts/verify-T1.json`,
  `.loop/artifacts/verify-T2.json`) contain plain pass/score data with **no**
  `holdout_gate` / `anticheat` reference **anywhere** under
  `examples/coverage-repair/` (verified: `grep -rl 'holdout\|anticheat'
  examples/coverage-repair` → empty); and
- `examples/coverage-repair/TASKS.json:12,20` reference `scripts/verify-fast` /
  `scripts/verify-full`, which exist only at **repo root**, not under the example
  dir — so the paths are broken relative to the example itself
  (`examples/coverage-repair/README.md:44` admits it "ships the loop artifacts,
  not the target repo").

So the repo's own flagship demo never wires the held-out check the suite claims
makes FCR *measured, not narrated*, undermining `README.md:277` **by example**,
and a newcomer never watches the FSM iterate/repair/verify live. (REVIEW **M2**
HIGH + **O1** MEDIUM, CONFIRMED; IMPROVEMENT-BACKLOG **HI1**.)

> This spec prescribes the **adoption-max path** (make it genuinely run). The
> honest fallback (relabel "inspect a finished run" + document the skip) is
> recorded in §3.5, but the fallback voids §2.3 test 4 and the HI2 demo GIF, so
> the runnable path is preferred.

### 3.2 Enforcement design (changes to the example — implemented in v0.4, not here)

Make `false_completion:false` **gate-backed** and the example locally replayable:

1. **Ship a minimal real target under the example** so a gate can actually run:
   `examples/coverage-repair/pricing.py` (the under-test module), a `tests/`
   split into a **visible** set (what the loop optimizes against) and a
   **holdout** set (withheld), and example-local `scripts/verify-fast`,
   `scripts/verify-full`, `scripts/verify-safety` that resolve **relative to the
   example dir**.
2. **Add a held-out manifest** `examples/coverage-repair/.loop/holdout-manifest.json`
   with `visible` + `holdout` command splits (the schema in
   `scripts/holdout_gate.py`), runnable via
   `python3 scripts/holdout_gate.py examples/coverage-repair/.loop/holdout-manifest.json
   --cwd examples/coverage-repair`.
3. **Record the gate's verdict as the evidence** behind the flag: write
   `.loop/artifacts/holdout-verdict.json` = the `decide(...)` output
   (`{"verdict":"Succeeded","false_completion":false,"passed_visible":true,
   "passed_holdout":true, ...}`), add it to `terminal_state.json.evidence`, and
   set `terminal_state.json.false_completion` **from** that artifact — never
   hand-authored.
4. **Reference the gate in RUNLOG.md**: the Terminal block records that
   `scripts/holdout_gate.py` produced the `Succeeded` verdict (this is what makes
   the example earn §2's tightened inspector credit, and it is honest — the gate
   really ran).
5. **Fix TASKS.json verify-path resolution** so each `task.verify` resolves from
   the example dir (ship the example-local verify scripts from step 1).

### 3.3 Tests — RED then GREEN

Add a new test module `scripts/test_example_coverage_repair.py` (runs against the
checked-in example, so it is a durable regression that the demo stays honest):

1. **`test_flagship_holdout_manifest_runs_end_to_end`** — load
   `examples/coverage-repair/.loop/holdout-manifest.json`, run
   `holdout_gate.run_manifest(manifest, cwd=<example dir>)`; assert
   `verdict == "Succeeded"`, `false_completion is False`, `passed_holdout is True`.
   *RED today* (manifest does not exist) → *GREEN after fix*.
2. **`test_flagship_false_completion_is_gate_backed`** — assert
   `terminal_state.json.evidence` contains the holdout-verdict artifact **and**
   that artifact's `false_completion` equals `terminal_state.json.false_completion`.
   *RED today* (no artifact) → *GREEN after fix*.
3. **`test_flagship_task_verify_paths_resolve_from_example_dir`** — for every
   `task.verify` in the example `TASKS.json`, assert the referenced script exists
   **relative to `examples/coverage-repair/`**. *RED today* (they point at repo
   root) → *GREEN after fix*.
4. **`test_inspect_flagship_grants_false_completion_defense_via_invocation`**
   (ties M2/HI1 to M1/HI4) — run `_evaluate_contract_checks("examples/coverage-repair")`;
   assert `false_completion_defense is True` **and** that it is earned via
   `_gate_invoked` (assert `_gate_invoked(resolve_loop_paths(example)) is True`),
   not the bare terminal flag. *RED after §2 alone* (tightened rule would drop the
   example's credit) → *GREEN once §3 wires the gate into RUNLOG/verify*.
5. **`test_flagship_terminal_validates_clean`** (ties to §1) — `doctor_report`
   over the example is `ok:true` (consistent `Succeeded`: `false_completion:false`
   + a true `criteria_met` entry). Guards that §3 edits don't trip §1's new rule.

### 3.4 Acceptance

- The example reaches a real 1-of-7 terminal state with `holdout_gate.py`'s
  recorded output as the evidence behind `false_completion:false`.
- Example-local `verify-*` paths resolve from the example dir.
- `python3 -m loop inspect examples/coverage-repair` still grants
  `false_completion_defense` credit **under §2's tightened rule**, via real
  invocation.
- All five tests green; `doctor` over the example is `ok:true`.

### 3.5 Documented fallback (only if the runnable path is dropped)

Relabel the `README.md:38-44` "30-second demo" as "inspect a **finished** run,"
state in `examples/coverage-repair/README.md` that the example intentionally does
not execute the held-out gate and why, and **remove** §2.3 test 4 (the example
would no longer earn invocation-based credit). This fallback forfeits the HI2
weak→strong demo GIF's honest subject and is **not** the recommended path.

---

## 4. HI6 — Structural invariant on the anti-cheat gate-decision functions

### 4.1 Problem (file:line + repro)

`scripts/anticheat_scan.py:52` `_SELF_FILES` blanket-exempts `anticheat_scan.py`
from gate-tampering detection, and the only self-edit detection is
`_gate_evisceration_findings` (collection-literal net-shrink, lines 214-256) and
`_semantic_gate_weakening_findings` (two narrow `_RANK`/downgrade regexes, lines
259-293). None of these inspect the **bodies** of the functions that *decide*
whether a tamper finding is produced. (REVIEW **G3**, MEDIUM, CONFIRMED;
IMPROVEMENT-BACKLOG **HI6**.)

Verified repro (REVIEW G3 / HI6) — a diff inserting `return False` as the first
line of `_is_gate_path`'s body:

```python
scan(diff_text=<diff adding '+        return False' inside _is_gate_path>)
# -> {'findings': [], 'clean': True, 'downgrade_to': None}
```

A function-body rewrite of `_is_gate_path` / `_is_verify_gate` (an early
`return False`) silently disables gate-tampering detection **and** is invisible to
the scanner, because textual matching catches only three narrow tamper shapes, not
arbitrary logic edits. For a product whose differentiator is catching gamed gates,
a scanner that cannot detect being gamed is the suite's highest-irony credibility
risk.

### 4.2 Enforcement design

Add a **structural (AST-span) invariant** over the scanner's own gate-decision
functions, wired into the diff path (to pin the exact `scan(diff_text=...)`
repro) and backed by a runtime AST-signature check (defense-in-depth for the
running module).

**Registry.** Name the functions whose logic determines whether a tamper finding
is produced:

```python
_GATE_DECISION_FNS = ("_basename", "_is_verify_gate", "_is_gate_path", "scan")
```

**(a) Diff-based logic-edit detection — pins the repro.** Add
`_gate_logic_edit_findings(diff_text)`:

- Reuse the existing `in_self` hunk-tracking (as `_gate_evisceration_findings`
  does) to consider only `anticheat_scan.py` hunks. This check is **not**
  self-exempt.
- Parse each hunk's `@@ -a,b +c,d @@` header to assign line numbers to added
  (`+`, new-file numbering) and removed (`-`, old-file numbering) content lines.
- Skip blank-only, comment-only, and the collection-entry lines already handled
  by `_gate_evisceration_findings` (avoid double-flagging).
- Compute each `_GATE_DECISION_FNS` member's source line-span
  (`ast.FunctionDef.lineno .. end_lineno`) from the **current module source**
  (`inspect.getsource` / `ast.parse`).
- If any surviving added/removed line's number falls inside a gate function's
  span, emit `{"signature": "gate-logic-edit", "severity": "critical",
  "evidence": <line>[:120]}`. A `critical` finding downgrades to `FailedSafety`
  via the existing severity roll-up in `scan()` (lines 348-354).

Wire it in alongside the existing self-edit checks:

```python
findings.extend(_gate_evisceration_findings(diff_text))
findings.extend(_semantic_gate_weakening_findings(diff_text))
findings.extend(_gate_logic_edit_findings(diff_text))   # NEW
```

**(b) Runtime AST-signature invariant — defense-in-depth.** Add
`check_self_integrity() -> list[dict]` that recomputes a normalized-AST hash for
each `_GATE_DECISION_FNS` member from the live module source and compares it to a
pinned baseline constant `_GATE_DECISION_SIGNATURES: dict[str, str]`; a mismatch
yields a `critical` `gate-self-mutation` finding. A companion test (§4.3 test 4)
asserts the pinned baseline equals the live source, so a **legitimate** refactor
that forgets to re-pin fails CI, and a **malicious** logic edit that changes a
body without re-pinning is caught at runtime.

Normative rules:

- **R1** — Any added/removed non-trivial line inside the AST span of a
  `_GATE_DECISION_FNS` member within an `anticheat_scan.py` hunk ⇒ a `critical`
  `gate-logic-edit` finding ⇒ `downgrade_to == "FailedSafety"`.
- **R2** — Comment-only / blank-only / pure-reorder edits inside those functions
  ⇒ **no** finding (no false positives on cosmetic changes).
- **R3** — The pinned `_GATE_DECISION_SIGNATURES` must equal
  `check_self_integrity()` over the live source (baseline stays honest).

### 4.3 Tests — RED then GREEN

Add to `scripts/test_anticheat_scan.py`:

1. **`test_return_false_rewrite_of_is_gate_path_is_flagged`** — pins the exact
   REVIEW G3/HI6 repro: construct a unified diff adding `+        return False` as
   the first body line of `_is_gate_path` in `scripts/anticheat_scan.py`; assert
   `scan(diff_text=diff)["clean"] is False`, a finding with `signature ==
   "gate-logic-edit"` and `severity == "critical"`, and
   `downgrade_to == "FailedSafety"`. *RED today* (`{'findings': [], 'clean':
   True}`) → *GREEN after fix*.
2. **`test_body_rewrite_of_is_verify_gate_is_flagged`** — a diff editing a body
   line of `_is_verify_gate` ⇒ `gate-logic-edit` critical. *RED → GREEN.*
3. **`test_comment_or_reorder_in_gate_fn_stays_clean`** (guard, R2) — a diff
   adding only a `# comment` line (or reordering two existing lines) inside
   `_is_gate_path` ⇒ `clean is True`. *GREEN after fix* (must not false-positive).
4. **`test_gate_decision_signatures_match_live_source`** (guard, R3) — assert
   `check_self_integrity()` over the live module returns **no** finding, i.e. the
   pinned `_GATE_DECISION_SIGNATURES` equals the current source's normalized-AST
   hashes. *GREEN after the baseline is pinned; fails loudly on any un-re-pinned
   edit.*
5. **`test_existing_evisceration_and_semantic_checks_unchanged`** (regression) —
   the current `_gate_evisceration_findings` / `_semantic_gate_weakening_findings`
   fixtures in `scripts/test_anticheat_scan.py` still produce their existing
   verdicts; and the scanner's own regression FIXTURES (e.g. `+    assert 1 == 1`,
   exempt via `_SELF_FILES` in `scan()`'s added-line loop) are **not** newly
   flagged by `_gate_logic_edit_findings` because they live outside the gate-fn
   spans. *GREEN before and after.*

### 4.4 Acceptance

- The `return False` repro yields a `critical` `gate-logic-edit` finding →
  `downgrade_to == "FailedSafety"`.
- Body rewrites of any `_GATE_DECISION_FNS` member inside `anticheat_scan.py`
  hunks are flagged; comment/reorder-only edits stay clean.
- `check_self_integrity()` passes against the live source, and the pinned baseline
  test fails if a future edit changes a gate body without re-pinning.
- All pre-existing `scripts/test_anticheat_scan.py` cases stay green.

---

## 5. Landing order, gates, and out-of-scope

**Order (single v0.4 batch):**
1. **G1** (§1) — smallest, self-contained; unblocks a clean example terminal.
2. **HI6** (§4) — self-contained; no cross-file coupling.
3. **M2 / HI1** (§3) — wires the example gate (needed before M1 tightens).
4. **M1 / HI4** (§2) — tighten inspector credit **last**, after the example earns
   credit via real invocation (else §2.3-adjacent example credit would regress).

**Definition of done (all four):**
- Every "RED → GREEN" test above is added and passes after its fix; each was
  confirmed RED against pre-fix code first (TDD).
- `uv run --with pytest --with pyyaml python -B -m pytest -q scripts loop` green
  (≥ 105 prior + the new cases).
- `python3 -m loop doctor examples/coverage-repair` → `ok:true`;
  `python3 -m loop inspect examples/coverage-repair` → `false_completion_defense`
  present and gate-backed.
- `self_eval` structural checks stay green (no SKILL.md wording regressions).

**Explicitly out of scope for this spec** (tracked elsewhere in
IMPROVEMENT-BACKLOG, not part of the four wedge-enforcement fixes): QW6
(empty-visible `NotReady`, gate-integrity G2), HI5 (recompute `productive`, M3),
QW11 (canonical repair record, M4), ST1/ST2 (published FCR baseline + versioned
schema, M5), and all trigger-quality (T1-T4) / onboarding-DX (O2-O4) items. This
spec is strictly the **HIGH-severity + HI6 wedge-enforcement** cut.

---

## 6. Traceability

| Spec § | REVIEW finding | Backlog item | Repro pinned by test |
|---|---|---|---|
| §1 | G1 (HIGH) | QW2 | `test_validate_terminal_rejects_succeeded_with_false_completion_true` |
| §2 | M1 (HIGH) | HI4 | `test_false_completion_defense_denied_for_bare_terminal_flag` |
| §3 | M2 (HIGH) + O1 (MED) | HI1 | `test_flagship_holdout_manifest_runs_end_to_end` + `test_flagship_false_completion_is_gate_backed` |
| §4 | G3 (MED) | HI6 | `test_return_false_rewrite_of_is_gate_path_is_flagged` |
