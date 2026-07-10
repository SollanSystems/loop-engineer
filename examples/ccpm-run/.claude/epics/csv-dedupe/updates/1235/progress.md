---
issue: 1235
started: 2026-07-09T13:45:00Z
last_sync: 2026-07-09T17:58:03Z
completion: 100%
---
<!-- SYNCED: 2026-07-09T17:58:03Z -->

# Progress: Issue #1235 — Normalization key

## Summary

The key helper landed and the guard built on it collapsed the sample pair to
41 unique contacts from 57 raw rows, matching the target. Both streams closed
and the issue was marked complete.

## Work Log

- Implemented `normalize_key` with lowercasing and whitespace trimming on both
  email and phone, returned as a tuple so it seeds the seen-key set directly.
- Added unit cases for mixed casing, padded whitespace, and an empty phone;
  all pass locally.
- Ran the importer over both sample exports: 41 rows inserted, 16 discarded.

## Verification Notes

I re-ran the importer a second time over the same inputs and it inserted zero
new rows, which is the idempotency behavior the task asked for. The counts were
read from the run's own stdout; no separate proof artifact is attached to this
journal.
