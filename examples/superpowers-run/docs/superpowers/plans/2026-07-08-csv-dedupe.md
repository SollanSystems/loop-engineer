# CSV dedupe — implementation plan

> Fictional sample content for the vendored fixture. Not a real project.

## Task 1: normalization key

- [x] Write `normalize_key(email, phone)` with lowercase + strip
- [x] Unit test with mixed-case fixtures

## Task 2: idempotent import

- [x] Skip insert when the key exists; count skips
- [x] Re-run the import; assert 0 new rows

## Task 3: dedupe log

- [x] Append dropped rows to `dedupe.log` with source line numbers
