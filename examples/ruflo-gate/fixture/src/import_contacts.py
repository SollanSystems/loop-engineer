"""The swarm's work product — the code the recorded run left behind.

Vendored so the supervisor's anti-cheat trajectory names files that actually
exist in the replayed workspace. Nothing in this module runs during the recipe.
"""

from __future__ import annotations


def normalize_key(email: str, phone: str) -> tuple[str, str]:
    return email.strip().lower(), phone.strip().lower()


def dedupe_rows(rows):
    seen: set[tuple[str, str]] = set()
    kept, dropped = [], []
    for source, line_no, email, phone in rows:
        key = normalize_key(email, phone)
        if key in seen:
            dropped.append((source, line_no, key))
            continue
        seen.add(key)
        kept.append((email, phone))
    return kept, dropped
