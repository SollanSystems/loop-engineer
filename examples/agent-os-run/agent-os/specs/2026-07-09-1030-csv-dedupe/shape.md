# CSV Dedupe — Shaping Notes

> Fictional sample content for the vendored fixture. Not a real project.

## Scope

Make `import_contacts.py` de-duplicate as it loads. Today it writes one row per
parsed line, so two overlapping source files produce doubles. After this change,
importing the two sample files yields 41 unique contacts where 57 rows were
read, a second import of the same files inserts 0 new rows, and every dropped
duplicate is written to `dedupe.log` with the line number it came from. Those
three outcomes are the definition of done for this work; Agent OS keeps them
here as scope prose rather than under a separate acceptance heading.

## Decisions

- Key each contact on `(lower(email), lower(phone))` after trimming whitespace.
- Keep the first row seen for a key; discard every later collision.
- Log drops to `dedupe.log`; do not fail the import when duplicates appear.
- Guard the existing insert with a key-membership check so re-runs are no-ops.

## Context

- **Visuals:** None — this is a backend import path with no UI surface.
- **References:** the current `import_contacts.py` insert loop (see references.md).
- **Product alignment:** the "De-duplication on import" line in Phase 1 of the
  product roadmap; imports must be safe to run more than once.

## Standards Applied

- backend/data-imports — this is an importer, so its idempotency, normalized-key,
  and drop-logging rules govern the whole change.
