# Standards for CSV Dedupe

> Fictional sample content for the vendored fixture. Not a real project.

These are the standards that govern this change. Their full text is inlined
below so the spec folder stands alone as build context.

---

## backend/data-imports

Every importer is idempotent and de-duplicates before it writes.

- Build a normalization key from the lowercased, trimmed identifying fields
- Keep the first row seen for a key; drop any later row that collides
- Never insert a row whose key already exists in the target table
- Append each dropped row to a log with its source file and line number

```python
key = (email.strip().lower(), phone.strip().lower())
```

- Re-running an import over the same source inserts zero new rows
- Drop-log format: one line per discard — `<source>:<lineno> dropped (kept <first_lineno>)`
- The count of dropped rows plus the count of kept rows equals the rows read
