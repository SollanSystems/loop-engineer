"""Explicit legacy-store migration: add chain columns; never rewrites rows.

Backfilling hashes onto existing rows is deliberately impossible — the
append-only triggers forbid UPDATE — so migration only widens the table and
stamps user_version=2. Pre-migration rows stay an *unchained prefix* that
doctor reports explicitly; the first post-migration append is a chain genesis.
Migrated columns stay nullable (legacy rows are NULL), so unlike a fresh store
a migrated store cannot refuse a pre-0.10.0 writer at the DB layer — see the
compatibility rule in reference/repo-os-contract.md #16.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .events import has_chain_columns
from .paths import resolve_loop_paths
from .runtime import RuntimeStoreError


def migrate_store(target: str | Path) -> dict[str, Any]:
    path = resolve_loop_paths(target).loop_dir / "events.db"
    if not path.exists():
        raise RuntimeStoreError("missing_store", f"event store does not exist: {path}")
    try:
        conn = sqlite3.connect(str(path), isolation_level=None, timeout=5.0)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            already = has_chain_columns(conn)
            if not already:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("ALTER TABLE events ADD COLUMN prev_event_hash TEXT")
                conn.execute("ALTER TABLE events ADD COLUMN event_hash TEXT")
                conn.execute("COMMIT")
            conn.execute("PRAGMA user_version = 2")
            unchained = conn.execute("SELECT COUNT(*) FROM events WHERE event_hash IS NULL").fetchone()[0]
            top = conn.execute("SELECT MAX(sequence) FROM events").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise RuntimeStoreError("corrupt_store", f"cannot migrate event store: {exc}") from exc
    return {"ok": True, "migrated": not already, "store": str(path), "user_version": 2,
            "unchained_rows": unchained, "chained_from_sequence": 0 if top is None else top + 1}
