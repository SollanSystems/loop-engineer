# Requirements Quality Checklist: CSV Contact Dedupe

**Purpose**: Validate that the requirements themselves are complete, clear, consistent, and measurable — these are quality gates on the writing, not tests of the code.
**Created**: 2026-07-09
**Feature**: [spec.md](../spec.md)

## Completeness

- [x] CHK001 [Completeness] Every user-facing outcome in the story has a matching functional requirement (FR-001..FR-005).
- [x] CHK002 [Completeness] The audit-log behavior is specified, including that the source line number is captured (FR-003, SC-003).
- [x] CHK003 [Completeness] The idempotent re-run behavior is stated as its own requirement, not left implicit (FR-004, SC-002).

## Clarity

- [x] CHK004 [Clarity] The dedupe key is defined without ambiguity — lowercased, trimmed email and phone (FR-001).
- [x] CHK005 [Clarity] "First-seen wins" is stated explicitly so the survivor among duplicates is never in doubt (FR-002).
- [x] CHK006 [Clarity] No requirement carries an unresolved NEEDS CLARIFICATION marker.

## Consistency

- [x] CHK007 [Consistency] The 41-from-57 count is identical across the story, FR/SC sections, and tasks — no drift.
- [x] CHK008 [Consistency] The blank-field edge case does not contradict the key definition (empty field, not wildcard).

## Coverage

- [x] CHK009 [Coverage] Each success criterion (SC-001..SC-003) is measurable and traces to at least one acceptance scenario.
- [x] CHK010 [Coverage] Both edge cases in the spec are reflected either in a requirement or an acceptance scenario.

## Notes

- All items are checked, so the implement-time PASS/FAIL gate reads PASS and no unchecked item blocks the run.
- This checklist grades the requirements document; the code's behavior is proven separately by the tests in `tasks.md`.
