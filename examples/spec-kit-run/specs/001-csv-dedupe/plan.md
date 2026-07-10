# Implementation Plan: CSV Contact Dedupe

**Branch**: `001-csv-dedupe` | **Date**: 2026-07-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-csv-dedupe/spec.md`

## Summary

Fold case-varying duplicate contacts into a single first-seen row on import, and
log every discarded row with its source line. The approach is a stdlib CSV read
that builds a normalized `(lower(email), lower(phone))` key per row, keeps the
first occurrence of each key, and appends the rest to `dedupe.log`.

## Technical Context

**Language/Version**: Python 3.11

**Primary Dependencies**: standard library only (`csv`, `argparse`) — no third-party packages

**Storage**: flat CSV files on disk; no database

**Testing**: pytest

**Target Platform**: Linux/macOS command line

**Project Type**: single-project CLI

**Performance Goals**: comfortably handles the sample exports (tens of thousands of rows) in one pass

**Constraints**: deterministic output regardless of input file order; idempotent on re-run

**Scale/Scope**: one command, one dedupe pass, one log file

## Constitution Check

*This gate is evaluated before Phase 0 research begins and evaluated again once the Phase 1 design settles.*

- Principle I (Deterministic Output): PASS — first-seen-wins over a normalized key is
  order-stable, the re-run adds nothing, and each drop is logged with its source line.
- Principle II (Test-Backed Change): PASS — the plan pins a test that asserts the exact
  41-row survivor count for the sample fixture before the logic is written.

Initial gate: PASS. Re-checked after Phase 1 design: PASS (no new violations introduced).

## Project Structure

### Source Code (repository root)

```text
src/
├── cli/
│   └── import_contacts.py     # command entry point
└── lib/
    └── dedupe.py              # normalize_key + first-seen dedupe pass

tests/
├── unit/
│   └── test_dedupe.py         # key normalization + survivor count
└── integration/
    └── test_import.py         # end-to-end import + idempotent re-run
```

**Structure Decision**: Single-project CLI layout. There is no web or mobile tier
and no service boundary, so the default `src/` + `tests/` split is used directly.

## Complexity Tracking

> Populate this section only when the Constitution Check surfaces a violation that needs a written justification.

No violations. The design stays within stdlib and a single dedupe pass, so this
table is intentionally empty.
