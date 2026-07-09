# CSV dedupe — design

> Fictional sample content for the vendored fixture. Not a real project.

## Problem

`import_contacts.py` writes duplicate rows when the same contact appears in
two source files with different casing.

## Approach

Normalize on a `(lower(email), lower(phone))` key before insert; keep the
first-seen row; log dropped duplicates to `dedupe.log`.

## Success Criteria

- Importing the two sample files yields 41 unique contacts (was 57 rows).
- Re-running the import is idempotent (0 new rows on the second run).
- Dropped duplicates are logged with their source line numbers.
