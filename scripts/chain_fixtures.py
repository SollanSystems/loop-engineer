"""Shared test fixtures for chain work: byte-faithful v0.9.0 store builders.

Imported by test_event_chain.py, test_adversarial_chain.py,
test_doctor_eventstore.py and test_loop_simulate_zero_writes.py as
`from chain_fixtures import make_legacy_store` — pytest's prepend import mode
puts scripts/ on sys.path (there is no scripts/__init__.py).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

LEGACY_DDL = """
CREATE TABLE events (
    run_id TEXT NOT NULL, sequence INTEGER NOT NULL, event_id TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL, actor TEXT NOT NULL, causation_id TEXT, correlation_id TEXT,
    ts TEXT NOT NULL, payload TEXT NOT NULL, artifact_hashes TEXT NOT NULL,
    PRIMARY KEY (run_id, sequence)
)"""

LEGACY_TRIGGERS = (
    "CREATE TRIGGER events_no_update BEFORE UPDATE ON events "
    "BEGIN SELECT RAISE(ABORT, 'events table is append-only: UPDATE is forbidden'); END",
    "CREATE TRIGGER events_no_delete BEFORE DELETE ON events "
    "BEGIN SELECT RAISE(ABORT, 'events table is append-only: DELETE is forbidden'); END",
)


def make_legacy_store(path: str | Path, *, run_id: str = "r1") -> Path:
    """Write a v0.9.0-shaped store holding one contract_opened event."""
    path = Path(path)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(LEGACY_DDL)
        for trigger in LEGACY_TRIGGERS:
            conn.execute(trigger)
        conn.execute(
            "INSERT INTO events VALUES (?, 0, 'legacy-e0', 'contract_opened', 'operator', "
            "NULL, NULL, '2026-07-24T00:00:00+00:00', '{\"workspace\":\"ws\"}', '[]')",
            (run_id,))
        conn.commit()
    finally:
        conn.close()
    return path


def drop_triggers(path: str | Path) -> None:
    """Adversary helper: remove the append-only triggers (they are DDL, not a security control)."""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("DROP TRIGGER IF EXISTS events_no_update")
        conn.execute("DROP TRIGGER IF EXISTS events_no_delete")
        conn.commit()
    finally:
        conn.close()


def restore_triggers(path: str | Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        for trigger in LEGACY_TRIGGERS:
            conn.execute(trigger.replace("CREATE TRIGGER", "CREATE TRIGGER IF NOT EXISTS"))
        conn.commit()
    finally:
        conn.close()
