---
issue: 1235
stream: normalization-key
started: 2026-07-09T13:45:12Z
status: completed
---

## Scope

Implement the `normalize_key(email, phone)` helper in `import_contacts.py` and
expose it for the guard and the test suite to import.

## Progress

- Wrote `normalize_key` to lowercase and strip both fields and return them as a
  tuple, so a case- or whitespace-variant row maps onto an earlier row's key.
- Confirmed against a mixed-case fixture pair that the two rows share one key.
- Handed the finished signature to Stream B and marked this stream completed.
