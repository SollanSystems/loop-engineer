"""Adversarial chain tests: what the chain catches, and — pinned deliberately —
what it does NOT catch without an external anchor.

If a *_pinned test starts FAILING, the kernel gained a stronger property: update
reference/repo-os-contract.md #16 (Integrity boundary) in the same commit.
"""
import json
import sqlite3

import pytest

from chain_fixtures import drop_triggers, make_legacy_store, restore_triggers
from loop.chain import compute_event_hash
from loop.contract import doctor_report
from loop.events import SQLiteEventStore
from loop.scaffold import scaffold

_EVENT_SCHEMA_ID = "loop-engineer/event@1"

# SQLite gained ALTER TABLE ... DROP COLUMN in 3.35; the downgrade attack cannot
# be staged below that, so those tests are skipped rather than errored.
_DROP_COLUMN = pytest.mark.skipif(
    sqlite3.sqlite_version_info < (3, 35),
    reason="ALTER TABLE ... DROP COLUMN requires SQLite >= 3.35",
)

# Same shape as the live chain DDL minus the NOT NULL on event_hash. The adversary
# owns the file: a table rebuild is how a row loses its hash in practice (a
# pre-0.10.0 writer appending to a chained store leaves the same footprint).
_NULLABLE_CHAIN_DDL = """
CREATE TABLE events (
    run_id TEXT NOT NULL, sequence INTEGER NOT NULL, event_id TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL, actor TEXT NOT NULL, causation_id TEXT, correlation_id TEXT,
    ts TEXT NOT NULL, payload TEXT NOT NULL, artifact_hashes TEXT NOT NULL,
    prev_event_hash TEXT, event_hash TEXT,
    PRIMARY KEY (run_id, sequence)
)"""


def _codes(report):
    return {issue["code"] for issue in report["issues"]}


def _chain_block(report):
    return report["event_store"]["chain"]


def _store_path(target):
    return target / ".loop" / "events.db"


def _sync_state(target, **fields):
    """Write projection-agreeing values into state.json so _state_divergence stays quiet."""
    path = target / ".loop" / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state.update(fields)
    path.write_text(json.dumps(state), encoding="utf-8")


def _chained_workspace(tmp_path, name="workspace"):
    """A synced workspace over a 4-event chained store (>= 3 events, spliceable middle).

    Deliberately self-contained rather than imported from test_doctor_eventstore:
    that module imports loop.migrate/loop.runner at module level, which the
    negative-control overlay (chain.py + chain_fixtures.py + this file, on main)
    cannot satisfy.
    """
    target = tmp_path / name
    scaffold(target)
    store = SQLiteEventStore(_store_path(target))
    store.append("run-1", "contract_opened", {"workspace": name}, actor="test")
    store.append("run-1", "iteration_appended", {"iteration_id": 1, "outcome": "task_failed"}, actor="test")
    store.append("run-1", "iteration_appended", {"iteration_id": 2, "outcome": "task_passed"}, actor="test")
    store.append("run-1", "receipt_appended",
                 {"iteration_id": 2, "role": "write", "model": "test-model", "outcome": "ok"}, actor="test")
    _sync_state(target, iteration_id=2, active_task=None)
    return target


def _terminal_workspace(tmp_path, name="workspace"):
    """A chained run that honestly ended FailedBlocked, with both projection files in sync."""
    target = tmp_path / name
    scaffold(target)
    store = SQLiteEventStore(_store_path(target))
    store.append("run-1", "contract_opened", {"workspace": name}, actor="test")
    store.append("run-1", "iteration_appended", {"iteration_id": 1, "outcome": "task_failed"}, actor="test")
    store.append("run-1", "terminal_written",
                 {"state": "FailedBlocked", "criteria_met": {"gate": False},
                  "evidence": ["red-bundle.json"], "false_completion": False}, actor="test")
    _sync_state(target, iteration_id=1, active_task=None, state="terminal", terminal_state="FailedBlocked")
    _write_terminal_file(target, "FailedBlocked", {"gate": False}, ["red-bundle.json"])
    return target


def _write_terminal_file(target, state, criteria_met, evidence):
    (target / ".loop" / "terminal_state.json").write_text(json.dumps({
        "schema": "loop-engineer/terminal@1", "state": state, "criteria_met": criteria_met,
        "evidence": evidence, "false_completion": False,
    }), encoding="utf-8")


def _record_at(conn, sequence, prev_event_hash):
    """Rebuild one row into the record dict read_event_rows projects (hash preimage shape)."""
    row = conn.execute(
        "SELECT run_id, sequence, event_id, type, actor, causation_id, correlation_id, ts, "
        "payload, artifact_hashes FROM events WHERE sequence = ?", (sequence,)).fetchone()
    return {"schema": _EVENT_SCHEMA_ID, "run_id": row[0], "sequence": row[1], "event_id": row[2],
            "type": row[3], "actor": row[4], "causation_id": row[5], "correlation_id": row[6],
            "ts": row[7], "payload": json.loads(row[8]), "artifact_hashes": json.loads(row[9]),
            "prev_event_hash": prev_event_hash}


def _head(target):
    return _chain_block(doctor_report(target))["head"]["event_hash"]


def test_splice_detected(tmp_path):
    ws = _chained_workspace(tmp_path)
    store_path = ws / ".loop" / "events.db"
    drop_triggers(store_path)
    conn = sqlite3.connect(str(store_path))
    try:
        conn.execute("UPDATE events SET payload = '{\"iteration_id\":1,\"outcome\":\"task_passed\"}' "
                     "WHERE sequence = 1")
        # recompute ONLY the spliced row's own hash: its successor still cites the original
        row = conn.execute("SELECT run_id, sequence, event_id, type, actor, causation_id, "
                           "correlation_id, ts, payload, artifact_hashes, prev_event_hash "
                           "FROM events WHERE sequence = 1").fetchone()
        record = {"schema": _EVENT_SCHEMA_ID, "run_id": row[0], "sequence": row[1],
                  "event_id": row[2], "type": row[3], "actor": row[4], "causation_id": row[5],
                  "correlation_id": row[6], "ts": row[7], "payload": json.loads(row[8]),
                  "artifact_hashes": json.loads(row[9]), "prev_event_hash": row[10]}
        conn.execute("UPDATE events SET event_hash = ? WHERE sequence = 1",
                     (compute_event_hash(record),))
        conn.commit()
    finally:
        conn.close()
    restore_triggers(store_path)
    assert "event_chain_broken" in _codes(doctor_report(ws))


def test_reorder_detected(tmp_path):
    """Swapping two same-type rows' payloads leaves both hashes citing the wrong content."""
    ws = _chained_workspace(tmp_path)
    store_path = _store_path(ws)
    drop_triggers(store_path)
    conn = sqlite3.connect(str(store_path))
    try:
        first, second = (conn.execute(
            "SELECT payload FROM events WHERE sequence = ?", (sequence,)).fetchone()[0]
            for sequence in (1, 2))
        conn.execute("UPDATE events SET payload = ? WHERE sequence = 1", (second,))
        conn.execute("UPDATE events SET payload = ? WHERE sequence = 2", (first,))
        conn.commit()
    finally:
        conn.close()
    restore_triggers(store_path)
    assert "event_chain_broken" in _codes(doctor_report(ws))


def test_midstream_hash_strip_breaks_chain(tmp_path):
    """An unchained row after a chained prefix is a break, not a legacy prefix."""
    ws = _chained_workspace(tmp_path)
    store_path = _store_path(ws)
    drop_triggers(store_path)
    conn = sqlite3.connect(str(store_path))
    try:
        conn.execute("ALTER TABLE events RENAME TO events_old")
        conn.execute(_NULLABLE_CHAIN_DDL)
        conn.execute("INSERT INTO events SELECT * FROM events_old")
        conn.execute("DROP TABLE events_old")
        conn.execute("UPDATE events SET event_hash = NULL WHERE sequence = 2")
        conn.commit()
    finally:
        conn.close()
    restore_triggers(store_path)
    report = doctor_report(ws)
    assert "event_chain_broken" in _codes(report)
    assert _chain_block(report)["head"] is None


def test_full_rewrite_with_recompute_passes_without_anchor_pinned(tmp_path):
    """The competent adversary: rewrite history, re-chain from genesis, and forge the
    projection files too. The chain alone does NOT catch this — the anchor does."""
    ws = _terminal_workspace(tmp_path)
    store_path = _store_path(ws)
    original_head = _chain_block(doctor_report(ws))["head"]["event_hash"]
    forged_terminal = {"state": "Succeeded", "criteria_met": {"gate": True},
                       "evidence": ["forged-bundle.json"], "false_completion": False}
    drop_triggers(store_path)
    conn = sqlite3.connect(str(store_path))
    try:
        conn.execute("UPDATE events SET payload = replace(payload, '\"task_failed\"', "
                     "'\"task_passed\"') WHERE type = 'iteration_appended'")
        conn.execute("UPDATE events SET payload = ? WHERE type = 'terminal_written'",
                     (json.dumps(forged_terminal, sort_keys=True),))
        prev = None
        for row in conn.execute("SELECT sequence FROM events ORDER BY sequence ASC").fetchall():
            record = _record_at(conn, row[0], prev)
            digest = compute_event_hash(record)
            conn.execute("UPDATE events SET prev_event_hash = ?, event_hash = ? WHERE sequence = ?",
                         (prev, digest, row[0]))
            prev = digest
        conn.commit()
    finally:
        conn.close()
    restore_triggers(store_path)
    _sync_state(ws, terminal_state="Succeeded")
    _write_terminal_file(ws, "Succeeded", forged_terminal["criteria_met"], forged_terminal["evidence"])

    unanchored = doctor_report(ws)
    assert "event_chain_broken" not in _codes(unanchored)        # PINNED LIMITATION
    assert _chain_block(unanchored)["head"] is not None
    # the forge is complete: no projection check fires either, so nothing but the anchor is
    # left. These are the event-store block's own flags, so ANY new event-store-layer
    # detection flips the pin — an absence-of-known-codes assertion would not.
    assert not _codes(unanchored) & {"state_field_mismatch", "desynced_terminal_window",
                                     "terminal_state_mismatch"}
    store_block = unanchored["event_store"]
    assert store_block["state_json_agrees"] is True
    assert store_block["deterministic"] is True
    assert store_block["legal_sequence"] is True

    anchored = doctor_report(ws, expect_chain_head=original_head)
    assert "chain_anchor_mismatch" in _codes(anchored)           # the anchor is the control


def test_truncation_alone_not_detected_but_anchor_catches_it(tmp_path):
    """Dropping the trailing receipt leaves a shorter but internally valid chain."""
    ws = _chained_workspace(tmp_path)
    store_path = _store_path(ws)
    original_head = _head(ws)
    drop_triggers(store_path)
    conn = sqlite3.connect(str(store_path))
    try:
        conn.execute("DELETE FROM events WHERE type = 'receipt_appended'")
        conn.commit()
    finally:
        conn.close()
    restore_triggers(store_path)

    unanchored = doctor_report(ws)
    assert "event_chain_broken" not in _codes(unanchored)        # PINNED LIMITATION
    assert _chain_block(unanchored)["head"] is not None
    assert "state_field_mismatch" not in _codes(unanchored)

    anchored = doctor_report(ws, expect_chain_head=original_head)
    assert "chain_anchor_mismatch" in _codes(anchored)           # the anchor is the control


def test_legacy_store_tamper_is_undetectable_pinned(tmp_path):
    """A never-migrated store has no hashes to break: there is no retroactive coverage."""
    target = tmp_path / "workspace"
    scaffold(target)
    store_path = _store_path(target)
    make_legacy_store(store_path)
    conn = sqlite3.connect(str(store_path))
    try:
        conn.execute(
            "INSERT INTO events VALUES ('r1', 1, 'legacy-e1', 'iteration_appended', 'operator', "
            "NULL, NULL, '2026-07-24T00:00:01+00:00', "
            "'{\"iteration_id\": 1, \"outcome\": \"task_failed\", \"summary\": \"gate red\"}', '[]')")
        conn.commit()
    finally:
        conn.close()
    _sync_state(target, iteration_id=1, active_task=None)
    drop_triggers(store_path)
    conn = sqlite3.connect(str(store_path))
    try:
        conn.execute("UPDATE events SET payload = replace(payload, 'gate red', 'gate green') "
                     "WHERE sequence = 1")
        conn.commit()
        tampered = conn.execute("SELECT payload FROM events WHERE sequence = 1").fetchone()[0]
    finally:
        conn.close()
    restore_triggers(store_path)
    # staging self-guard: a non-detection claim is worthless if the tamper never landed
    assert "gate green" in tampered

    report = doctor_report(target)
    assert "event_chain_broken" not in _codes(report)             # PINNED LIMITATION
    assert _chain_block(report) == {"head": None, "unchained_prefix": 2}


def test_unhashable_record_breaks_chain(tmp_path):
    """A row whose payload json.loads accepts but canonical_json refuses (bare NaN).

    Pins link_issue's "unhashable record" branch end-to-end: the recompute raises
    before it can compare, and doctor must report a broken chain rather than
    propagate a ChainHashError. The required payload fields are kept intact on
    purpose — a payload that also violates event@1 is refused by validate_event
    before the fold and surfaces as invalid_event instead (§22).
    """
    ws = _chained_workspace(tmp_path)
    store_path = _store_path(ws)
    drop_triggers(store_path)
    conn = sqlite3.connect(str(store_path))
    try:
        conn.execute("UPDATE events SET payload = ? WHERE sequence = 1",
                     ('{"iteration_id": 1, "outcome": "task_failed", "x": NaN}',))
        conn.commit()
    finally:
        conn.close()
    restore_triggers(store_path)

    report = doctor_report(ws)                    # must not raise ChainHashError
    assert "event_chain_broken" in _codes(report)
    assert any("unhashable record" in issue["message"] for issue in report["issues"]
               if issue["code"] == "event_chain_broken")
    assert _chain_block(report)["head"] is None


def test_never_chained_store_with_anchor_fails(tmp_path):
    """An anchor over a store that never chained cannot match: fail hard, never skip."""
    target = tmp_path / "workspace"
    scaffold(target)
    make_legacy_store(_store_path(target))
    _sync_state(target, active_task=None)
    report = doctor_report(target, expect_chain_head="a" * 64)
    assert not report["ok"]
    assert "chain_anchor_mismatch" in _codes(report)


@_DROP_COLUMN
def test_column_drop_downgrade_is_silent_without_anchor_pinned(tmp_path):
    """Dropping the columns AND the user_version defeats the D2 cross-check; only the
    anchor survives a full downgrade."""
    ws = _chained_workspace(tmp_path)
    original_head = _head(ws)
    conn = sqlite3.connect(str(_store_path(ws)))
    try:
        conn.execute("ALTER TABLE events DROP COLUMN event_hash")
        conn.execute("ALTER TABLE events DROP COLUMN prev_event_hash")
        conn.execute("PRAGMA user_version = 0")
        conn.commit()
    finally:
        conn.close()

    unanchored = doctor_report(ws)
    assert "event_chain_broken" not in _codes(unanchored)         # PINNED LIMITATION
    assert "chain_columns_missing" not in _codes(unanchored)
    assert _chain_block(unanchored)["head"] is None

    anchored = doctor_report(ws, expect_chain_head=original_head)
    assert "chain_anchor_mismatch" in _codes(anchored)            # the anchor is the control
