"""scripts/test_event_chain.py — chain canonicalization, store chaining, migration."""
import pytest

from loop.chain import _PREIMAGE_FIELDS, ChainHashError, canonical_json, compute_event_hash


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
from loop.events import DuplicateEventError, EventStoreOperationalError


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


def test_append_maps_a_reused_event_id_to_duplicate(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.db")
    store.append("r1", "contract_opened", {"workspace": "ws"}, actor="operator", event_id="same")
    with pytest.raises(DuplicateEventError):
        store.append("r2", "contract_opened", {"workspace": "ws"}, actor="operator", event_id="same")


def test_append_wraps_a_non_duplicate_integrity_failure_as_typed_error(tmp_path, monkeypatch):
    """A NOT NULL refusal is not a retryable duplicate — retrying it would loop forever."""
    real_connect = sqlite3.connect

    class RefuseInsert(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if isinstance(sql, str) and sql.lstrip().upper().startswith("INSERT INTO EVENTS"):
                raise sqlite3.IntegrityError("NOT NULL constraint failed: events.event_hash")
            return super().execute(sql, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect",
                        lambda *args, **kwargs: real_connect(*args, factory=RefuseInsert, **kwargs))
    with pytest.raises(EventStoreOperationalError, match="NOT NULL constraint failed"):
        SQLiteEventStore(tmp_path / "events.db").append(
            "r1", "contract_opened", {"workspace": "ws"}, actor="operator")


def test_append_wraps_a_non_operational_database_error_as_typed_error(tmp_path, monkeypatch):
    """append, read, and latest_sequence agree on the whole sqlite3.Error family."""
    real_connect = sqlite3.connect

    class MalformedOnCommit(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if isinstance(sql, str) and sql.strip().upper() == "COMMIT":
                raise sqlite3.DatabaseError("database disk image is malformed")
            return super().execute(sql, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect",
                        lambda *args, **kwargs: real_connect(*args, factory=MalformedOnCommit, **kwargs))
    with pytest.raises(EventStoreOperationalError, match="database disk image is malformed"):
        SQLiteEventStore(tmp_path / "events.db").append(
            "r1", "contract_opened", {"workspace": "ws"}, actor="operator")


_STORE_VERBS = {
    "append": lambda store: store.append("r1", "contract_opened", {"workspace": "ws"}, actor="operator"),
    "read": lambda store: store.read("r1"),
    "latest_sequence": lambda store: store.latest_sequence("r1"),
}


@pytest.mark.parametrize("verb", sorted(_STORE_VERBS))
def test_unopenable_store_raises_typed_error_from_every_verb(tmp_path, verb):
    path = tmp_path / "events.db"
    path.mkdir()
    with pytest.raises(EventStoreOperationalError):
        _STORE_VERBS[verb](SQLiteEventStore(path))


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


def test_runner_read_path_retries_plain_mode_ro_before_declaring_corruption(tmp_path, monkeypatch):
    """Design change D4 on the run/simulate surface: one lost race is not corruption."""
    from loop import runner

    workspace = tmp_path / "workspace"
    (workspace / ".loop").mkdir(parents=True)
    _drifted_store(workspace / ".loop" / "events.db")
    seen = []
    real_connect = sqlite3.connect

    def record(*args, **kwargs):
        seen.append(args[0])
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", record)
    with pytest.raises(RuntimeStoreError) as excinfo:
        runner.dispatch_once(workspace)
    assert excinfo.value.code == "corrupt_store"      # real corruption fails BOTH attempts
    assert len(seen) == 2 and all("mode=ro" in uri for uri in seen)
    assert "immutable=1" in seen[0] and "immutable=1" not in seen[1]


from loop.migrate import migrate_store


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


@pytest.mark.parametrize("mode", ["strict", "basic"])
@pytest.mark.parametrize("field", ["prev_event_hash", "event_hash", "artifact_hashes"])
def test_validation_rejects_a_hash_with_a_trailing_newline_in_both_modes(mode, field):
    # jsonschema `pattern` is re.search-semantics, so "$" alone admits a trailing
    # newline; the schemas pair it with maxLength 64 to close the same hole the
    # structural validator closes with fullmatch.
    if mode == "strict":
        pytest.importorskip("jsonschema")
    clean = _chained(0, None, artifact_hashes=[{"path": "p", "sha256": "a" * 64}])
    assert validate_event(clean, mode=mode)["ok"] is True
    dirty = ([{"path": "p", "sha256": "a" * 64 + "\n"}] if field == "artifact_hashes"
             else "a" * 64 + "\n")
    assert validate_event(dict(clean, **{field: dirty}), mode=mode)["ok"] is False


from loop.chain import verify_chain
from loop.reducer import ChainBreakError, reduce_events


def test_reducer_folds_chained_stream_and_exposes_head(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.db")
    store.append("r1", "contract_opened", {"workspace": "ws"}, actor="operator")
    last = store.append("r1", "iteration_appended",
                        {"iteration_id": 1, "outcome": "task_passed"}, actor="operator")
    projection = reduce_events(store.read("r1"))
    assert projection["chain_head"] == {"sequence": 1, "event_hash": last["event_hash"]}
    assert projection["unchained_prefix"] == 0


def test_reducer_raises_chain_break_on_tampered_payload(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.db")
    store.append("r1", "contract_opened", {"workspace": "ws"}, actor="operator")
    events = store.read("r1")
    events[0]["payload"] = {"workspace": "tampered"}
    with pytest.raises(ChainBreakError):
        reduce_events(events)


def test_reducer_accepts_legacy_unchained_stream(tmp_path):
    make_legacy_store(tmp_path / "events.db")
    projection = reduce_events(SQLiteEventStore(tmp_path / "events.db").read("r1"))
    assert projection["chain_head"] is None and projection["unchained_prefix"] == 1


def test_reducer_resume_from_initial_chain_head(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.db")
    store.append("r1", "contract_opened", {"workspace": "ws"}, actor="operator")
    store.append("r1", "iteration_appended", {"iteration_id": 1, "outcome": "task_passed"}, actor="operator")
    events = store.read("r1")
    snapshot = reduce_events(events[:1])
    resumed = reduce_events(events[1:], initial=snapshot)
    assert resumed["chain_head"] == reduce_events(events)["chain_head"]
    forged = dict(events[1], prev_event_hash="a" * 64)
    forged["event_hash"] = compute_event_hash(forged)
    with pytest.raises(ChainBreakError):
        reduce_events([forged], initial=snapshot)


@pytest.mark.parametrize("generation", ["fresh", "legacy", "migrated"])
def test_verify_chain_agrees_with_reducer(tmp_path, generation):
    """Two verifiers, one truth — guards against lockstep drift (design decision 8)."""
    path = tmp_path / "events.db"
    if generation == "fresh":
        store = SQLiteEventStore(path)
    else:
        make_legacy_store(path)
        if generation == "migrated":
            (tmp_path / ".loop").mkdir(exist_ok=True)
            # migrate_store takes a workspace; migrate this file in place via the same DDL
            conn = sqlite3.connect(str(path))
            conn.execute("ALTER TABLE events ADD COLUMN prev_event_hash TEXT")
            conn.execute("ALTER TABLE events ADD COLUMN event_hash TEXT")
            conn.execute("PRAGMA user_version = 2")
            conn.commit(); conn.close()
        store = SQLiteEventStore(path)
    if generation == "fresh":
        store.append("r1", "contract_opened", {"workspace": "ws"}, actor="operator")
    store.append("r1", "iteration_appended", {"iteration_id": 1, "outcome": "task_passed"},
                 actor="operator")
    events = store.read("r1")
    projection = reduce_events(events)
    report = verify_chain(events)
    assert report["head"] == projection["chain_head"]
    assert report["unchained_prefix"] == projection["unchained_prefix"]


# --- documented conformance vectors (reference/repo-os-contract.md #16) -------
# Literal records + literal digests. The digests are also asserted to appear in
# the contract document, so the spec and the implementation cannot drift apart.

_VECTOR_GENESIS = {
    "schema": "loop-engineer/event@1", "run_id": "run-1", "sequence": 0,
    "event_id": "e0", "type": "contract_opened", "actor": "operator",
    "ts": "2026-07-24T00:00:00+00:00", "causation_id": None, "correlation_id": None,
    "payload": {"workspace": "ws"}, "artifact_hashes": [], "prev_event_hash": None,
}
_DIGEST_GENESIS = "3ca65d4da7d87a98616441a86c6866ff39b5513ccd156d8526abfd6df7ec88a7"

_VECTOR_SECOND = {
    "schema": "loop-engineer/event@1", "run_id": "run-1", "sequence": 1,
    "event_id": "e1", "type": "iteration_appended", "actor": "operator",
    "ts": "2026-07-24T00:00:01+00:00", "causation_id": None, "correlation_id": None,
    "payload": {"iteration_id": 1, "outcome": "task_passed", "state": "execute-task"},
    "artifact_hashes": [], "prev_event_hash": _DIGEST_GENESIS,
}
_DIGEST_SECOND = "bb40984d1b98bda565d93dd90a39ea212be999078a66cf013f37cbed650c155d"

_VECTOR_UNICODE = {
    "schema": "loop-engineer/event@1", "run_id": "run-1", "sequence": 2,
    "event_id": "e2", "type": "receipt_appended", "actor": "operator",
    "ts": "2026-07-24T00:00:02+00:00", "causation_id": None, "correlation_id": None,
    "payload": {"iteration_id": 1, "note": "café — naïve ✅", "summary": "日本語"},
    "artifact_hashes": [], "prev_event_hash": _DIGEST_SECOND,
}
_DIGEST_UNICODE = "0d0413aa0a1903a46a802f98f0a28abafd10ca09d5e312622f729482cfc40a19"

_CONFORMANCE_VECTORS = (
    ("genesis", _VECTOR_GENESIS, _DIGEST_GENESIS),
    ("second", _VECTOR_SECOND, _DIGEST_SECOND),
    ("unicode-payload", _VECTOR_UNICODE, _DIGEST_UNICODE),
)


def test_documented_conformance_vectors():
    """The three vectors published in the contract are exactly what chain.py computes,
    and the published digests AND canonical preimages are still literally in the document."""
    contract = (_ROOT / "reference" / "repo-os-contract.md").read_text(encoding="utf-8")
    for name, record, digest in _CONFORMANCE_VECTORS:
        assert compute_event_hash(record) == digest, f"vector {name} drifted from chain.py"
        assert digest in contract, f"vector {name} digest is not documented in the contract"
        preimage = canonical_json({field: record.get(field) for field in _PREIMAGE_FIELDS})
        assert preimage in contract, f"vector {name} preimage is not documented in the contract"
    chained = [dict(record, event_hash=digest) for _, record, digest in _CONFORMANCE_VECTORS]
    assert verify_chain(chained, expected_head=_DIGEST_UNICODE)["ok"] is True
