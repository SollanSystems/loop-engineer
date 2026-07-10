# Design: dedupe-csv-rows

## Context

`import_contacts.py` reads each source file row by row and inserts
unconditionally. The two operator exports share people but format the same
address inconsistently — `Ada@Site.io` in one, `ada@site.io` in the other — so
identical contacts slip past any exact-string check and land twice.

## Goals / Non-Goals

**Goals:**
- Recognize a repeated contact regardless of letter casing or stray whitespace.
- Keep the earliest occurrence so the first file remains the authority.
- Leave an auditable trail of what was dropped and where it came from.
- Make a repeated import produce no new rows.

**Non-Goals:**
- Fuzzy or typo-tolerant matching beyond case and whitespace folding.
- Merging differing fields across the two rows — the first row is kept whole.
- Changing the source export format or the downstream contact schema.

## Decisions

### Decision 1: Fold the key on `(lower(email), lower(phone))`
Casing is the only difference that made true duplicates read as distinct, so
the identity key lowercases and strips both fields before comparison. Folding
both fields keeps two genuinely different people apart while catching the
casing collisions the operators actually hit.

### Decision 2: First-seen row wins
The importer walks rows in file order and inserts a contact only when its folded
key is unseen. Retaining the first occurrence makes the outcome deterministic
and independent of how later files are ordered.

### Decision 3: Log drops rather than fail
A collision is expected, not an error, so a skipped row is appended to
`dedupe.log` with its source file and line number and processing continues.
The log lets an operator confirm what collapsed without blocking the import.

## Risks / Trade-offs

- Folding only case and whitespace leaves near-duplicates with a mistyped
  address (`ada@sight.io` vs `ada@site.io`) reading as separate people →
  accepted, since typo-tolerant matching is an explicit Non-Goal; the log makes
  any residual duplicate visible for a manual pass.
- First-seen-wins discards a later row even when it carries a field the first
  row left blank → accepted as the price of a deterministic, order-stable
  outcome; merging fields across rows is out of scope for this change.
