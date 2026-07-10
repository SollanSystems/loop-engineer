# References for CSV Dedupe

> Fictional sample content for the vendored fixture. Not a real project.

## Similar Implementations

### Existing contact importer

- **Location:** `import_contacts.py`
- **Relevance:** This is the module being changed. Its current load path parses
  each CSV row and inserts it directly, with no membership check, which is the
  source of the duplicate rows.
- **Key patterns:** Reuse the existing CSV parsing and the row-to-record
  mapping; wrap only the raw insert with the new key-membership guard so the
  parsing behavior is unchanged.

### Sample source files

- **Location:** `fixtures/contacts_a.csv`, `fixtures/contacts_b.csv`
- **Relevance:** The two overlapping exports that motivate the work — together
  57 rows that should collapse to 41 unique contacts.
- **Key patterns:** The overlap is same-person, different-casing, which is why
  the key lowercases email and phone rather than comparing raw strings.
