# Quickstart: CSV Contact Dedupe

**Phase 1 validation doc for** `specs/001-csv-dedupe/`. How to run the completed
import and the counts a correct run produces — the evidence behind the
"Run quickstart.md validation" task in `tasks.md`.

## Run the import

From the repository root, point the CLI at the two sample exports:

```bash
python -m src.cli.import_contacts \
  tests/fixtures/contacts_a.csv \
  tests/fixtures/contacts_b.csv \
  --out contacts.csv
```

## Expected result

- The two exports hold 57 rows between them.
- `contacts.csv` holds 41 unique contacts after case-varying duplicates are folded.
- `dedupe.log` names each of the 16 dropped rows with the source file and line it
  was read from.

## Confirm idempotency

Run the same command a second time over the produced list. A correct run reports
0 new rows and appends nothing further to `dedupe.log`, matching SC-002.

## Run the tests

```bash
pytest tests/
```

The unit test pins `normalize_key` on mixed-case input and the integration test
asserts the 41-row survivor count and the zero-new-rows re-run. Both pass on the
completed feature.
