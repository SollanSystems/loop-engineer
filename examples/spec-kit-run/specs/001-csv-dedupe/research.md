# Research: CSV Contact Dedupe

**Phase 0 output for** `specs/001-csv-dedupe/plan.md`. Records the decisions taken
before design and the reasons the conditional Phase 1 documents are omitted.

## Decision: dedupe key strategy

**Chosen**: a tuple of the lowercased, whitespace-trimmed email and phone.

**Rationale**: The observed duplicates differ only by casing and stray spaces, so
normalizing both fields collapses them while leaving genuinely different people
apart. Using the pair rather than email alone avoids merging two people who share a
shared inbox but differ by phone.

**Alternatives considered**: A hash of the whole row was rejected because it would
treat a re-typed display name as a different person and defeat the dedupe. Fuzzy
matching was rejected as over-scoped for a dataset whose only variance is casing.

## Decision: first-seen wins

**Chosen**: keep the first row that resolves to a key; discard and log later ones.

**Rationale**: First-seen-wins is order-stable given a fixed input order and makes
the re-run trivially idempotent, satisfying Constitution Principle I.

## Omitted Phase 1 documents

`data-model.md` and `contracts/` are not produced for this feature. There are no
persisted entities beyond flat CSV rows and no API surface to contract — the
deliverable is a single CLI pass. Per the tasks prerequisites, only the documents
that exist are listed as available design inputs, so their absence is faithful to a
pure-CLI feature rather than a gap.
