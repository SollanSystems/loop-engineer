---
description: "Task list for CSV Contact Dedupe"
---

# Tasks: CSV Contact Dedupe

**Input**: Design documents from `specs/001-csv-dedupe/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md

**Tests**: Included — Constitution Principle II requires a test that pins the survivor count.

**Organization**: Tasks are grouped by user story so the single P1 story is independently verifiable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: The user story a task serves (US1)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Lay down the project skeleton the dedupe pass lives in.

- [X] T001 Create the `src/cli`, `src/lib`, and `tests` tree per the plan
- [X] T002 Add a `pytest` dev dependency and a minimal project config
- [X] T003 [P] Vendor the two fictional sample exports under `tests/fixtures/`

**Checkpoint**: Skeleton and fixtures in place — dedupe work can begin.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The row-reading and logging primitives every later task depends on.

- [X] T004 Read CSV rows into dicts and carry each row's source file + line number
- [X] T005 Open `dedupe.log` for append and write one line per dropped row

**Checkpoint**: Rows can be read with provenance and drops can be recorded.

---

## Phase 3: User Story 1 - Merge two contact exports without duplicates (Priority: P1) 🎯 MVP

**Goal**: One clean list from the two overlapping exports, plus an audit log.

**Independent Test**: Import the two sample exports; assert 41 surviving rows and a log naming each drop.

### Tests for User Story 1

> Written FIRST and confirmed failing before the implementation below.

- [X] T006 [P] [US1] Unit test in `tests/unit/test_dedupe.py` pinning `normalize_key` on mixed-case input
- [X] T007 [P] [US1] Integration test in `tests/integration/test_import.py` asserting 41 rows and idempotent re-run

### Implementation for User Story 1

- [X] T008 [US1] Implement `normalize_key(email, phone)` in `src/lib/dedupe.py`
- [X] T009 [US1] Implement the first-seen dedupe pass over normalized keys
- [X] T010 [US1] Log every discarded row with its source line to `dedupe.log`
- [X] T011 [US1] Wire the `import_contacts.py` CLI entry point and report the survivor count

**Checkpoint**: User Story 1 fully functional — 41/57 rows, 0 new on re-run, all drops logged.

---

## Phase 4: Polish & Cross-Cutting Concerns

**Purpose**: Final validation of the completed run.

- [X] T012 [P] Note the run command and expected counts in `quickstart.md`
- [X] T013 Run `quickstart.md` validation against the sample exports

**Checkpoint**: All phases complete — every task above is marked `[X]`.
