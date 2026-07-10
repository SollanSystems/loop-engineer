"""Import contacts from CSV exports, collapsing case-variant duplicates.

Fictional sample deliverable for the vendored bmad-run fixture.
"""

import csv
from dataclasses import dataclass, field


def normalize_key(email, phone):
    """Return a case-insensitive match key, or None when both fields are blank."""
    e = (email or "").strip().lower()
    p = (phone or "").strip().lower()
    if not e and not p:
        return None
    return (e, p)


@dataclass
class ImportSummary:
    kept: int = 0
    skipped: int = 0
    dropped: list = field(default_factory=list)


def import_contacts(source_paths, seen=None, log_path="dedupe.log"):
    """Merge rows from source_paths into a roster, first-seen wins.

    seen carries the keys already in the roster so a repeated import adds nothing.
    Returns (roster_rows, ImportSummary).
    """
    seen = set() if seen is None else set(seen)
    roster = []
    summary = ImportSummary()
    drops = []

    for path in source_paths:
        with open(path, newline="", encoding="utf-8") as handle:
            for line_no, row in enumerate(csv.DictReader(handle), start=2):
                key = normalize_key(row.get("email"), row.get("phone"))
                if key is not None and key in seen:
                    summary.skipped += 1
                    drops.append((path, line_no, row))
                    continue
                if key is not None:
                    seen.add(key)
                roster.append(row)
                summary.kept += 1

    if drops:
        with open(log_path, "a", encoding="utf-8") as log:
            for path, line_no, row in drops:
                log.write(f"{path}:{line_no}\tdropped\t{row.get('email','')}\n")
    summary.dropped = drops
    return roster, summary
