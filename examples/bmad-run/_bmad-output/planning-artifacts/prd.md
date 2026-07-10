---
title: Idempotent contact import — PRD
status: final
created: 2026-07-09
updated: 2026-07-09
---

# Idempotent contact import

## Overview

The `contact-sync-cli` tool merges contacts from two upstream exports into a
single roster. Operators noticed that a person listed in both exports lands in
the roster twice whenever the two sources spell the same email or phone with
different letter casing. This PRD scopes a small, contained fix: make the import
recognize a contact by a case-insensitive key so a re-run never grows the roster.

## Problem

`import_contacts.py` inserts one row per input line without comparing against
rows already imported. Because equality is exact-string, `Ada@Example.com` and
`ada@example.com` are treated as two people. The current sample pair of exports
holds fifty-seven rows describing forty-one distinct contacts.

## Goals

- Collapse case-variant duplicates so the roster reflects distinct people.
- Guarantee that importing the same sources twice adds nothing on the second run.
- Leave a readable audit trail of which input lines were dropped and why.

## Functional Requirements

- FR1: Derive a match key from the lowercased email and lowercased phone; two rows
  sharing that key are the same contact.
- FR2: Keep the first occurrence of a key and discard later ones (first-seen wins).
- FR3: Append every dropped row to `dedupe.log` with its source file and line number.
- FR4: Re-importing already-imported sources yields zero new roster rows.

## Non-Goals

- Fuzzy or phonetic name matching, merging of conflicting field values, and any
  change to the upstream export format are out of scope for this task.

## Success Measures

- Importing the two sample exports produces forty-one roster entries.
- A second import over the same files reports zero additions.
- Each of the sixteen dropped rows is traceable to its origin line in the log.
