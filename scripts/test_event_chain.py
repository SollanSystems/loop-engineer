"""scripts/test_event_chain.py — chain canonicalization, store chaining, migration."""
import pytest

from loop.chain import ChainHashError, canonical_json, compute_event_hash


def _record(**overrides):
    base = {
        "schema": "loop-engineer/event@1", "event_id": "e1", "run_id": "r1",
        "sequence": 0, "type": "contract_opened", "actor": "operator",
        "causation_id": None, "correlation_id": None, "ts": "2026-07-24T00:00:00+00:00",
        "payload": {"workspace": "ws"}, "artifact_hashes": [], "prev_event_hash": None,
    }
    base.update(overrides)
    return base


def test_canonical_json_is_compact_sorted_utf8():
    assert canonical_json({"b": 1, "a": [1, "é"]}) == '{"a":[1,"é"],"b":1}'


def test_canonical_json_rejects_non_finite_floats():
    with pytest.raises(ChainHashError):
        canonical_json({"x": float("nan")})


def test_canonical_json_rejects_lone_surrogates():
    with pytest.raises(ChainHashError):
        canonical_json({"x": "\ud800"})


def test_canonical_json_rejects_non_json_values():
    with pytest.raises(ChainHashError):
        canonical_json({"x": object()})


def test_event_hash_is_stable_and_key_order_independent():
    a = _record()
    b = dict(reversed(list(_record().items())))
    assert compute_event_hash(a) == compute_event_hash(b)
    assert len(compute_event_hash(a)) == 64


def test_event_hash_excludes_event_hash_but_includes_prev_and_ts_and_actor():
    base = _record()
    with_own_hash = dict(base, event_hash="f" * 64)
    assert compute_event_hash(base) == compute_event_hash(with_own_hash)
    assert compute_event_hash(base) != compute_event_hash(dict(base, prev_event_hash="a" * 64))
    assert compute_event_hash(base) != compute_event_hash(dict(base, ts="2026-07-25T00:00:00+00:00"))
    assert compute_event_hash(base) != compute_event_hash(dict(base, actor="worker"))


def test_event_hash_treats_absent_optionals_as_null():
    explicit = _record()
    implicit = {k: v for k, v in _record().items()
                if k not in ("causation_id", "correlation_id", "prev_event_hash")}
    assert compute_event_hash(explicit) == compute_event_hash(implicit)


from loop.chain import link_issue, verify_chain


def _chained(seq, prev_hash, **overrides):
    rec = _record(sequence=seq, event_id=f"e{seq}", prev_event_hash=prev_hash,
                  type="iteration_appended" if seq else "contract_opened",
                  payload={"iteration_id": seq, "outcome": "task_passed"} if seq else {"workspace": "ws"})
    rec.update(overrides)
    rec["event_hash"] = compute_event_hash(rec)
    return rec


def test_link_issue_genesis_requires_null_prev():
    assert link_issue(_chained(0, None), None) is None
    assert "prev_event_hash mismatch" in link_issue(_chained(0, "a" * 64), None)


def test_link_issue_detects_recompute_mismatch():
    rec = _chained(0, None)
    rec["payload"] = {"workspace": "tampered"}
    assert "event_hash mismatch" in link_issue(rec, None)


def test_link_issue_unchained_after_chained_is_a_break_and_names_the_likely_cause():
    head = {"sequence": 0, "event_hash": "b" * 64}
    unchained = _record(sequence=1, event_id="e1")
    message = link_issue(unchained, head)
    assert "unchained event after chained prefix" in message
    assert "pre-0.10.0 writer" in message           # self-diagnosing per design change D1
    assert link_issue(unchained, None) is None


def test_verify_chain_happy_path_and_head():
    e0 = _chained(0, None)
    e1 = _chained(1, e0["event_hash"])
    report = verify_chain([e0, e1])
    assert report["ok"] and report["chained_events"] == 2 and report["unchained_prefix"] == 0
    assert report["head"] == {"sequence": 1, "event_hash": e1["event_hash"]}


def test_verify_chain_legacy_prefix_then_genesis():
    legacy = _record(sequence=0)          # no event_hash key at all
    e1 = _chained(1, None)                # genesis after unchained prefix
    report = verify_chain([legacy, e1])
    assert report["ok"] and report["unchained_prefix"] == 1 and report["chained_events"] == 1


def test_verify_chain_detects_splice():
    e0 = _chained(0, None)
    e1 = _chained(1, e0["event_hash"])
    forged = dict(e1, payload={"iteration_id": 1, "outcome": "task_failed"})
    forged["event_hash"] = compute_event_hash(forged)   # recomputed own hash...
    e2 = _chained(2, e1["event_hash"])                  # ...but successor cites the original
    report = verify_chain([e0, forged, e2])
    assert not report["ok"] and any("prev_event_hash mismatch" in i for i in report["issues"])


def test_verify_chain_reports_first_record_failure_without_counting_it():
    bad = _chained(0, "a" * 64)                          # bad genesis
    report = verify_chain([bad])
    assert not report["ok"] and report["chained_events"] == 0
    assert report["unchained_prefix"] == 0 and report["head"] is None


def test_verify_chain_truncation_needs_expected_head():
    e0 = _chained(0, None)
    e1 = _chained(1, e0["event_hash"])
    assert verify_chain([e0])["ok"]                      # honest limit: shorter valid chain verifies
    report = verify_chain([e0], expected_head=e1["event_hash"])
    assert not report["ok"] and any("chain head" in i for i in report["issues"])


def test_verify_chain_reports_missing_head_when_anchor_supplied_on_unchained_stream():
    report = verify_chain([_record(sequence=0)], expected_head="a" * 64)
    assert not report["ok"] and any("no chained events" in i for i in report["issues"])


import sqlite3

from chain_fixtures import make_legacy_store
from loop.events import SQLiteEventStore, has_chain_columns, read_event_rows, store_user_version


def test_fresh_store_has_chain_columns_and_user_version_2(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.db")
    store.append("r1", "contract_opened", {"workspace": "ws"}, actor="operator")
    conn = sqlite3.connect(str(tmp_path / "events.db"))
    try:
        assert has_chain_columns(conn) and store_user_version(conn) == 2
        notnull = {row[1]: row[3] for row in conn.execute("PRAGMA table_info(events)")}
        assert notnull["event_hash"] == 1 and notnull["prev_event_hash"] == 0
    finally:
        conn.close()


def test_legacy_store_is_not_upgraded_by_connect(tmp_path):
    path = make_legacy_store(tmp_path / "events.db")
    SQLiteEventStore(path).read("r1")     # any connect on a legacy store
    conn = sqlite3.connect(str(path))
    try:
        assert not has_chain_columns(conn) and store_user_version(conn) == 0
    finally:
        conn.close()


def test_read_event_rows_projects_hash_keys_on_legacy_store(tmp_path):
    path = make_legacy_store(tmp_path / "events.db")
    conn = sqlite3.connect(str(path))
    try:
        rows = read_event_rows(conn, "r1")
    finally:
        conn.close()
    assert rows[0]["prev_event_hash"] is None and rows[0]["event_hash"] is None


def test_read_event_rows_raises_typed_error_on_corrupt_payload_json(tmp_path):
    from loop.events import EventRowDecodeError
    path = make_legacy_store(tmp_path / "events.db")
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("DROP TRIGGER events_no_update")
        conn.execute("UPDATE events SET payload = 'not json' WHERE sequence = 0")
        conn.commit()
        with pytest.raises(EventRowDecodeError):
            read_event_rows(conn, "r1")
    finally:
        conn.close()


from loop.chain import compute_event_hash as _hash
from loop.events import EventStoreOperationalError


def test_read_projects_store_computed_hash_on_fresh_store(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.db")
    record = store.append("r2", "contract_opened", {"workspace": "ws"}, actor="operator")
    assert store.read("r2")[0]["event_hash"] == record["event_hash"]


def test_append_chains_on_fresh_store(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.db")
    e0 = store.append("r1", "contract_opened", {"workspace": "ws"}, actor="operator")
    e1 = store.append("r1", "iteration_appended", {"iteration_id": 1, "outcome": "task_passed"},
                      actor="operator")
    assert e0["prev_event_hash"] is None and e0["event_hash"] == _hash(e0)
    assert e1["prev_event_hash"] == e0["event_hash"] and e1["event_hash"] == _hash(e1)


def test_append_ignores_caller_supplied_chain_fields(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.db")
    store.append("r1", "contract_opened", {"workspace": "ws"}, actor="operator")
    smuggled = store.append("r1", "iteration_appended",
                            {"iteration_id": 1, "outcome": "task_passed", "event_hash": "f" * 64},
                            actor="operator")
    assert smuggled["event_hash"] != "f" * 64 and smuggled["event_hash"] == _hash(smuggled)


def test_append_on_legacy_store_stays_unchained_and_working(tmp_path):
    path = make_legacy_store(tmp_path / "events.db")
    record = SQLiteEventStore(path).append(
        "r1", "iteration_appended", {"iteration_id": 1, "outcome": "task_passed"}, actor="operator")
    assert record["prev_event_hash"] is None and record["event_hash"] is None
    assert SQLiteEventStore(path).read("r1")[1]["event_hash"] is None


def test_legacy_style_ten_column_insert_is_refused_by_a_fresh_store(tmp_path):
    """Design change D1: a pre-0.10.0 writer cannot silently unchain a v2 store."""
    path = tmp_path / "events.db"
    SQLiteEventStore(path).append("r1", "contract_opened", {"workspace": "ws"}, actor="operator")
    conn = sqlite3.connect(str(path))
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO events (run_id, sequence, event_id, type, actor, causation_id, "
                "correlation_id, ts, payload, artifact_hashes) VALUES "
                "('r1',1,'old-writer','iteration_appended','worker',NULL,NULL,"
                "'2026-07-24T00:00:00+00:00','{\"iteration_id\":1,\"outcome\":\"task_passed\"}','[]')")
    finally:
        conn.close()


def test_append_wraps_schema_drift_as_typed_error(tmp_path):
    path = tmp_path / "events.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE events (run_id TEXT, sequence INTEGER)")   # wrong shape entirely
    conn.commit(); conn.close()
    with pytest.raises(EventStoreOperationalError):
        SQLiteEventStore(path).append("r1", "contract_opened", {"workspace": "ws"}, actor="operator")


import subprocess
import sys
from pathlib import Path

from loop.runtime import RuntimeStoreError

_ROOT = Path(__file__).resolve().parent.parent


def _drifted_store(path):
    """An events table that reads and writes nothing the kernel expects."""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE events (run_id TEXT, sequence INTEGER)")
        conn.execute("INSERT INTO events VALUES ('r1', 0)")
        conn.commit()
    finally:
        conn.close()
    return Path(path)


def test_runcontrol_append_translates_operational_error_to_typed_store_error(tmp_path):
    from loop import runcontrol

    workspace = tmp_path / "workspace"
    (workspace / ".loop").mkdir(parents=True)
    _drifted_store(workspace / ".loop" / "events.db")
    with pytest.raises(RuntimeStoreError, match="event_store_unusable"):
        runcontrol._append_event(workspace, "r1", {"last_sequence": 0}, "contract_opened",
                                 {"workspace": "ws"})


def test_runner_append_translates_operational_error_to_typed_store_error(tmp_path):
    from loop.runner import _store_append

    path = _drifted_store(tmp_path / "events.db")
    with pytest.raises(RuntimeStoreError, match="event_store_unusable"):
        _store_append(SQLiteEventStore(path), "r1", "contract_opened", {"workspace": "ws"},
                      actor="loop.run")


@pytest.mark.parametrize("command,extra", [("run", []), ("pause", ["--reason", "drift probe"])])
def test_cli_refuses_a_schema_drifted_store_without_a_traceback(tmp_path, command, extra):
    workspace = tmp_path / "workspace"
    (workspace / ".loop").mkdir(parents=True)
    _drifted_store(workspace / ".loop" / "events.db")
    proc = subprocess.run([sys.executable, "-B", "-m", "loop", command, *extra, str(workspace)],
                          cwd=_ROOT, text=True, capture_output=True)
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr
    assert proc.stderr.strip().startswith(f"{command}: ")


from loop.migrate import migrate_store
from loop.runtime import RuntimeStoreError


def _workspace_with_legacy_store(tmp_path):
    loop_dir = tmp_path / ".loop"
    loop_dir.mkdir()
    make_legacy_store(loop_dir / "events.db")
    return tmp_path


def test_migrate_adds_columns_sets_version_and_reports_unchained(tmp_path):
    ws = _workspace_with_legacy_store(tmp_path)
    report = migrate_store(ws)
    assert report["ok"] and report["migrated"] is True
    assert report["user_version"] == 2 and report["unchained_rows"] == 1
    assert report["chained_from_sequence"] == 1
    conn = sqlite3.connect(str(ws / ".loop" / "events.db"))
    try:
        assert has_chain_columns(conn) and store_user_version(conn) == 2
    finally:
        conn.close()


def test_migrate_is_idempotent(tmp_path):
    ws = _workspace_with_legacy_store(tmp_path)
    migrate_store(ws)
    assert migrate_store(ws)["migrated"] is False


def test_migrate_missing_store_raises_typed(tmp_path):
    (tmp_path / ".loop").mkdir()
    with pytest.raises(RuntimeStoreError):
        migrate_store(tmp_path)


def test_post_migration_appends_chain_with_genesis_after_legacy_prefix(tmp_path):
    ws = _workspace_with_legacy_store(tmp_path)
    migrate_store(ws)
    record = SQLiteEventStore(ws / ".loop" / "events.db").append(
        "r1", "iteration_appended", {"iteration_id": 1, "outcome": "task_passed"}, actor="operator")
    assert record["prev_event_hash"] is None            # genesis after unchained prefix
    assert record["event_hash"] == _hash(record)


from loop.events import validate_event


@pytest.mark.parametrize("mode", ["strict", "basic"])
def test_chain_fields_validate_in_both_modes(mode):
    if mode == "strict":
        pytest.importorskip("jsonschema")
    good = _chained(0, None)
    assert validate_event(good, mode=mode)["ok"]
    report = validate_event(dict(good, event_hash="not-hex"), mode=mode)
    assert not report["ok"]
    assert validate_event(dict(good, prev_event_hash=17), mode=mode)["ok"] is False
