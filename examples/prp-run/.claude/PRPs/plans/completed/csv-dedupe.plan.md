# Feature: Contact Import Deduplication

## Summary

Route every imported row through a normalized `(lower(email), lower(phone))` key,
keep the first row seen for each key, and append the rows we drop to `dedupe.log`.
The importer becomes idempotent with no schema change; full problem and hypothesis
live in the source PRD (back ref below).

## Metadata

| Field | Value |
| ----- | ----- |
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | contacts import CLI |
| Dependencies | Python 3.12 standard library only |
| Estimated Tasks | 3 |

## Lifecycle (append-only)

- **Created:** 2026-07-09T14:05:03Z
- **Modified:** 2026-07-09T14:48:19Z
- **Commits:** a1b2c3d4
- **Agent / Session:** claude-opus (prp-loop-2026-07-09T14:01:55Z)
- **Back refs:** `.claude/PRPs/prds/csv-dedupe.prd.md` — source PRD, Phase 1
- **Forward refs:** -

## Files to Change

| File | Action | Justification |
| ---- | ------ | ------------- |
| `contacts/dedupe.py` | CREATE | Merge key + drop-log helper |
| `contacts/import_contacts.py` | UPDATE | Route rows through the key before insert |
| `tests/test_dedupe.py` | CREATE | Cover the key, idempotency, and the log |

## NOT Building (Scope Limits)

- No fuzzy or name-based matching — exact normalized email/phone only.
- No database migration — dedupe stays in application code.

## Step-by-Step Tasks

Task markers: `[ ]` not started · `[wip]` underway · `[x]` done · `[f]` could not pass.

### `[x]` Task 1: CREATE `contacts/dedupe.py`
- **ACTION**: Add `normalize_key(email, phone)` (lowercase + strip) and a `DropLog` appender. **VALIDATE**: `mypy contacts`.

### `[x]` Task 2: UPDATE `contacts/import_contacts.py`
- **ACTION**: Track seen keys; skip repeats and log them with the source line. **GOTCHA**: log before `continue` or the trail loses the row. **VALIDATE**: `ruff check . && mypy contacts`.

### `[x]` Task 3: CREATE `tests/test_dedupe.py`
- **ACTION**: Cover key normalization, the 57→41 count, and second-run 0 inserts. **VALIDATE**: `pytest tests/test_dedupe.py`.

## Validation Commands

Every command below must exit 0 before this plan counts as done.

- **Level 1: STATIC_ANALYSIS** — `ruff check . && mypy contacts` (no errors).
- **Level 2: UNIT_TESTS** — `pytest tests/test_dedupe.py` (all green).
- **Level 3: FULL_SUITE** — `pytest` (full suite passes).
- **Level 4: DATABASE_VALIDATION** — N/A, flat-file importer, no database.
- **Level 5: BROWSER_VALIDATION** — N/A, command-line tool, no UI.
- **Level 6: MANUAL_VALIDATION** — import both exports → 41, re-run → 0 inserts.

## Acceptance Criteria

- [x] First import of both exports yields 41 unique contacts.
- [x] A second identical import inserts 0 rows.
- [x] All 16 dropped rows are logged with their source line numbers.
- [x] Level 1–3 validation commands exit 0.

## Completion Checklist

- [x] All tasks complete in order, each validated on completion.
- [x] Level 1 static analysis passes.
- [x] Level 2 unit tests pass.
- [x] Level 3 full suite passes.
- [x] Acceptance criteria met.

## Success Criteria

- **CONTEXT_COMPLETE**: Patterns and the one gotcha are captured from the file.
- **IMPLEMENTATION_READY**: Tasks run top to bottom without clarification.
- **PATTERN_FAITHFUL**: The guard mirrors the existing import loop.
- **VALIDATION_DEFINED**: Every task carries an executable check.
- **ONE_PASS_TARGET**: Confidence 8+ signals a likely first-attempt success.

**Confidence Score**: 9/10 that this lands on the first attempt — the change is
local, stdlib-only, and covered by a deterministic row-count test.

## Amendments

<details>
<summary>2026-07-09T14:48:19Z — built, validated, and archived</summary>
Implemented all three tasks; Level 1–3 passed after one lint fix on iteration 1.
Moved into `plans/completed/` on the green implement pass.
</details>
