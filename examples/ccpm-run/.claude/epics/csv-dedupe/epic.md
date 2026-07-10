---
name: csv-dedupe
status: completed
created: 2026-07-09T13:20:07Z
updated: 2026-07-09T18:41:55Z
progress: 100%
prd: .claude/prds/csv-dedupe.md
github: https://github.com/acme-contacts/pipeline/issues/1234
---

# Epic: csv-dedupe

## Overview

Teach `import_contacts.py` to treat case- and whitespace-variant rows as one
contact, keep the first occurrence, and journal every discard. The change is
contained to the importer module and a new log file; no schema change is
needed.

## Architecture Decisions

- Match on a derived key rather than mutating stored values, so the raw rows
  remain available for auditing.
- Build the key from `lower(strip(email))` joined with `lower(strip(phone))`,
  because those two fields were confirmed to identify a contact.
- Retain the earliest row on collision — first-seen wins — to keep imports
  deterministic regardless of file ordering within a run.

## Technical Approach

### Frontend Components

None. This is a batch importer with no user-facing surface.

### Backend Services

A `normalize_key(email, phone)` helper and an in-memory seen-key set guard the
insert path. A companion writer appends discarded rows to `dedupe.log`.

### Infrastructure

No new services. The log is a plain file written alongside existing importer
output.

## Implementation Strategy

Land the key helper and its tests first so the guard has a stable contract,
then wire the idempotent insert path, then attach the discard log. Each slice
is independently verifiable against the two sample exports.

## Task Breakdown Preview

- The normalization key and its unit coverage.
- The idempotent insert guard that consults the seen-key set.
- The discard log with source filenames and line numbers.

## Dependencies

- The current CSV reader and insert path in `import_contacts.py`.

## Success Criteria (Technical)

- 41 unique contacts result from the 57-row sample pair.
- A repeat import inserts zero rows.
- `dedupe.log` names every dropped row's source file and line.

## Estimated Effort

Roughly one focused day across three small tasks.

## Tasks Created
- [x] 1235.md - Normalization key (parallel: true)
- [x] 1236.md - Idempotent import guard (parallel: false)
- [x] 1237.md - Dedupe log (parallel: true)

Total tasks: 3
Parallel tasks: 2
Sequential tasks: 1
Estimated total effort: 8 hours
