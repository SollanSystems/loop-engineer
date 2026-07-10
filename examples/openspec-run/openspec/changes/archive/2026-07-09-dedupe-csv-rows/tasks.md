# Tasks: dedupe-csv-rows

## 1. Normalization key

- [x] 1.1 Add `normalize_key(email, phone)` that lowercases and strips both fields
- [x] 1.2 Return the pair as a hashable identity key for collision lookups
- [x] 1.3 Unit-test the key with mixed-case and padded-whitespace fixtures

## 2. Idempotent import

- [x] 2.1 Track seen keys and skip insert when a row's key is already present
- [x] 2.2 Count skipped rows so the run reports how many collapsed
- [x] 2.3 Re-run the import over unchanged inputs and assert 0 new rows

## 3. Dedupe log

- [x] 3.1 Append each skipped row to `dedupe.log` on collision
- [x] 3.2 Record the source file and line number for every logged drop

## 4. Verification

- [x] 4.1 Run the unit tests for `normalize_key` and the skip path (`pytest`)
- [x] 4.2 Import the two sample files; confirm 41 unique contacts from 57 raw rows
- [x] 4.3 Manual smoke: import a second time and confirm no rows are added
- [x] 4.4 Inspect `dedupe.log` and confirm each drop names its source line
