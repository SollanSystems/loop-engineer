# CSV Dedupe — Plan

> Fictional sample content for the vendored fixture. Not a real project.
>
> Tasks are plain headers. Agent OS v3 tracks progress in the tool's ephemeral
> todo list, not on disk, so this file is never marked up as tasks complete —
> it reads the same after the run as before it.

## Task 1: Save Spec Documentation

Create `agent-os/specs/2026-07-09-1030-csv-dedupe/` holding this plan plus
`shape.md`, `standards.md`, and `references.md`. This runs first so the shaping
work is captured before any code changes begin.

## Task 2: Normalization key

Add `normalize_key(email, phone)` returning `(email.strip().lower(),
phone.strip().lower())`. Cover it with mixed-case and surrounding-whitespace
fixtures so equal contacts collapse to one key regardless of how they were typed.

## Task 3: Idempotent import

Track seen keys during the load and skip the insert when a key already exists,
counting each skip. Result: the two sample files produce 41 unique contacts from
57 rows read, and a second import of the same files inserts 0 new rows.

## Task 4: Dedupe log

Append every dropped duplicate to `dedupe.log` as `<source>:<lineno> dropped
(kept <first_lineno>)`. Result: each discarded row is traceable back to the
source line it came from, and kept-plus-dropped equals rows read.
