# Dedupe CSV Rows

## Why

Operators export contacts from two systems whose lists overlap, and
`import_contacts.py` stores every raw row. When the same person appears in both
files with different letter casing, the importer writes them twice, so the
contact table carries visible duplicates and the second import inflates it
again.

## What Changes

- Rows are matched on a case-folded, whitespace-trimmed `(email, phone)` key.
- On a collision the first row read wins; later rows are dropped, not stored.
- Every dropped row is appended to `dedupe.log` with its source file and line.
- Re-importing the same files becomes a no-op instead of adding rows.

## Capabilities

### New Capabilities
- `csv-dedupe`: collapse duplicate contact rows on a case-insensitive identity
  key, keep the earliest occurrence, and log what was dropped.

### Modified Capabilities
<!-- None: this is the first behavior added for contact import dedupe. -->

## Impact

- `import_contacts.py`: add the normalization key and the skip-on-collision path.
- `dedupe.log`: new append-only artifact recording each skipped duplicate.
- Import runs are now idempotent, so scheduled re-imports are safe to repeat.
