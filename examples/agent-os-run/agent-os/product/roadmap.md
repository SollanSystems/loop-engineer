# Product Roadmap

> Fictional sample content for the vendored fixture. Not a real project.

## Phase 1: MVP

- CSV import from common spreadsheet exports
- **De-duplication on import** — collapse overlapping rows into unique contacts
- A drop log that records every discarded duplicate with its source line
- Manual review of the imported list before it is committed

## Phase 2: Post-Launch

- Fuzzy matching on names to catch typo-level duplicates the key misses
- Scheduled re-imports that stay idempotent across runs
- Per-source merge rules so newer fields can override older ones
