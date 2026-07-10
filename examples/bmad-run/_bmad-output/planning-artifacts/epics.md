---
title: Epic breakdown — idempotent contact import
status: final
created: 2026-07-09
updated: 2026-07-09
---

# Epics — contact-sync-cli

## FR Coverage Map

- FR1, FR2 → Story 1.1 (match key + first-seen retention)
- FR3 → Story 1.1 (dropped-row logging)
- FR4 → Story 1.1 (idempotent re-run)

## Epic List

- Epic 1: Idempotent contact import — one story delivers the whole fix.

## Epic 1: Idempotent contact import

Make the contact import recognize the same person across case-variant spellings so
the merged roster holds distinct contacts and stays stable across repeated runs.

### Story 1.1: Deduplicate CSV rows

As an operator running the nightly merge,
I want the import to treat case-variant rows as one contact and log the rows it
drops,
So that the roster reflects real people and re-running the merge changes nothing.

**Acceptance Criteria:**

**Given** the two sample exports totalling fifty-seven rows
**When** the import runs once
**Then** the roster holds forty-one distinct contacts
**And** the sixteen dropped rows are each written to `dedupe.log` with their source
file and line number.

**Given** a roster already built from those exports
**When** the same exports are imported a second time
**Then** zero new rows are added
**And** the run reports the skip count.

**Given** two rows whose email or phone differ only in letter casing
**When** the match key is computed
**Then** both rows resolve to the same key
**And** the earlier input line is the one retained.
