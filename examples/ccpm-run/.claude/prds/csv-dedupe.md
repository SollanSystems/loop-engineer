---
name: csv-dedupe
description: Collapse duplicate contacts imported from two source files into one canonical row
status: completed
created: 2026-07-09T13:02:44Z
---

# PRD: csv-dedupe

## Executive Summary

The contact importer ingests two upstream exports and currently stores a
separate row each time the same person is described differently between them.
This work makes the importer recognize when two rows are the same contact and
keep only the first one seen, so downstream tools count real people instead of
formatting artifacts.

## Problem Statement

`import_contacts.py` compares raw strings. A contact whose email is capitalized
in one file and lowercased in the other passes the equality check as two
distinct people. Operators noticed the contact total drifting above the true
headcount after every import, and had no record of which rows were dropped.

## User Stories

- As a data operator, I import both exports and see one row per real contact,
  so my totals match reality. Acceptance: 41 unique contacts from 57 raw rows.
- As a data operator, I re-run the same import without fear, so a retry never
  inflates the table. Acceptance: the second run inserts zero new rows.
- As an auditor, I read a log of what was discarded, so a dropped row can be
  traced. Acceptance: each dropped duplicate is logged with its source line.

## Functional Requirements

- Derive a match key from the lowercased, trimmed email and phone of each row.
- On a key collision, retain the earliest row and discard the later one.
- Record every discarded row, its source filename, and its line number.

## Non-Functional Requirements

- The importer stays single-pass over each file and holds only seen keys.
- Re-running the importer is idempotent against an already-populated table.

## Success Criteria

- The two sample exports yield exactly 41 unique contacts from 57 input rows.
- A second import over the same inputs inserts zero additional rows.
- Every dropped duplicate appears in `dedupe.log` with source line numbers.

## Constraints & Assumptions

- Email and phone together identify a contact; name and address may vary.
- Both source files are already well-formed CSV with a header row.

## Out of Scope

- Fuzzy or typo-tolerant matching beyond case and whitespace normalization.
- Merging non-key fields from duplicate rows into the retained contact.

## Dependencies

- The existing `import_contacts.py` entry point and its CSV reader.
