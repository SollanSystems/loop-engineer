---
baseline_commit: 3af19c2
---

# Story 1.1: Deduplicate CSV rows

Status: done

## Story

As an operator running the nightly merge,
I want the import to treat case-variant rows as one contact and log the rows it drops,
so that the roster reflects real people and re-running the merge changes nothing.

## Acceptance Criteria

1. Given the two sample exports (fifty-seven rows), when the import runs once, then the roster holds forty-one distinct contacts and each dropped row is logged with its source file and line number.
2. Given a roster already built from those exports, when the same exports are imported again, then zero new rows are added and the skip count is reported.
3. Given two rows whose email or phone differ only in casing, when the match key is computed, then both resolve to one key and the earlier input line is retained.

## Tasks / Subtasks

- [x] Task 1: Compute a case-insensitive match key (AC: 3)
  - [x] Add `normalize_key(email, phone)` lowercasing and stripping both fields
  - [x] Unit-test mixed-case and whitespace-padded inputs
- [x] Task 2: First-seen retention and dropped-row logging (AC: 1)
  - [x] Skip a row when its key was already seen; keep the earliest line
  - [x] Append each skipped row to `dedupe.log` with source file and line number
- [x] Task 3: Idempotent re-import (AC: 2)
  - [x] Return an import summary carrying kept and skipped counts
  - [x] Assert a second import over the same sources adds zero rows

### Review Findings

- [x] [Review][Patch] Guard against a blank email and blank phone collapsing every empty-field row into one key [src/import_contacts.py:14] — resolved: empty keys are passed through, never deduped.

## Dev Notes

The dedupe boundary lives entirely in `import_contacts.py`; the CSV reader and the
roster writer were left untouched. The match key is the tuple of the lowercased,
stripped email and phone — names are intentionally excluded because upstream spells
them inconsistently and name collisions are not duplicates.

### Project Structure Notes

- Code deliverable: `src/import_contacts.py` (project source tree, not under `_bmad-output`).
- Test: `tests/test_import_contacts.py`, run with `pytest`.
- Audit output `dedupe.log` is written beside the roster at run time and is not committed.

### References

- [Source: _bmad-output/planning-artifacts/prd.md#Functional Requirements]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.1: Deduplicate CSV rows]

## Dev Agent Record

### Agent Model Used

Fictional dev agent (Amelia), running the bmad-dev-story skill.

### Debug Log References

- First `test_second_import_adds_nothing` failed as expected before the seen-set was persisted across calls; passed once the summary carried the running key set.

### Completion Notes List

- Red-green-refactor followed: failing tests written first, then minimal code.
- Full suite green (5 passed); no regressions in the existing import tests.
- Enhanced Definition of Done checklist: PASS. Story Ready for Review: 1-1-deduplicate-csv-rows.
- code-review run in fresh context raised one low patch (empty-key guard), applied above; no high/medium findings.

### File List

- src/import_contacts.py (modified)
- tests/test_import_contacts.py (added)

## Change Log

| Date | Version | Description |
|------|---------|-------------|
| 2026-07-09 | 0.1 | Story drafted from Epic 1 and moved to ready-for-dev |
| 2026-07-09 | 0.2 | Implementation complete; DoD PASS; moved to review |
| 2026-07-09 | 1.0 | code-review clean after one applied patch; Status set to done |
