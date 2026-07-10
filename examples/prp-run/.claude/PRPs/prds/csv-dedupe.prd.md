# Contact Import Deduplication

## Problem Statement

The nightly contact importer appends every row it reads, so when the same person
appears in two vendor exports with different letter casing the database ends up
holding several near-identical records. Sales reps then waste time reconciling
duplicates by hand, and merge mistakes leak into outbound campaigns.

## Evidence

- A single import of the two January exports produced 57 rows for 41 real people.
- Support logged three "why did this lead get two emails" tickets last month.
- `import_contacts.py` has no uniqueness check before its insert call.

## Proposed Solution

Compute a normalized merge key of `(lower(email), lower(phone))` for each row and
keep only the first occurrence, appending every dropped row to a `dedupe.log`
audit trail. This lives entirely inside the existing importer — no schema change,
no new service.

## Key Hypothesis

A case-insensitive email-and-phone merge key should collapse the duplicate
contacts the ops team keeps hitting down to one record apiece. The falsifiable
check: a fresh import of the two sample exports lands 41 unique contacts, and
running that same import a second time inserts nothing.

## What We're NOT Building

- Fuzzy name matching — out of scope; only exact normalized email/phone merges.
- A dedupe UI — the audit log is enough for this pass.

## Success Metrics

| Metric | Target | How Measured |
|--------|--------|--------------|
| Unique contacts after import | 41 (from 57 rows) | Row count after loading both exports |
| Second-run inserts | 0 | Re-run the same import, count new rows |
| Dropped rows logged | 16, with source line numbers | `wc -l dedupe.log` and spot-check entries |

## Open Questions

- [x] Should phone-only or email-only matches merge? Resolved: require both fields to agree.

## Implementation Phases

<!-- STATUS: pending | in-progress | complete -->

| # | Phase | Description | Status | Parallel | Depends | PRP Plan |
|---|-------|-------------|--------|----------|---------|----------|
| 1 | Dedupe key + idempotent import | Normalize the merge key, skip repeat keys, log drops | complete | - | - | `.claude/PRPs/plans/csv-dedupe.plan.md` |

### Phase Details

**Phase 1: Dedupe key + idempotent import**
- **Goal**: One import that is safe to re-run and leaves an auditable drop trail.
- **Scope**: `normalize_key`, the first-seen guard in the import loop, the log writer.
- **Success signal**: 41 unique contacts on the first run, 0 inserts on the second.

---

*Generated: 2026-07-09*
*Status: COMPLETE — Phase 1 shipped via PR #42*
