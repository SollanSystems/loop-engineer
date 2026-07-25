"""Doctor integration tests for the read-only EventStore consistency gate."""

import json
import sqlite3

import pytest
from chain_fixtures import drop_triggers, make_legacy_store

from loop.__main__ import main
from loop.contract import doctor_report, validate_contract
from loop.events import SQLiteEventStore
from loop.migrate import migrate_store
from loop.runner import dispatch_once
from loop.runtime import RuntimeStoreError, replay_report, status_report
from loop.scaffold import scaffold


def _fresh_contract(tmp_path, name="workspace"):
    target = tmp_path / name
    scaffold(target)
    return target


def _sync_active_task(target):
    path = target / ".loop" / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["active_task"] = None
    path.write_text(json.dumps(state), encoding="utf-8")


def _sync_iteration(target, iteration_id):
    path = target / ".loop" / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["iteration_id"] = iteration_id
    path.write_text(json.dumps(state), encoding="utf-8")


def _store(target):
    return SQLiteEventStore(target / ".loop" / "events.db")


def _open(store, run_id="run-1"):
    return store.append(run_id, "contract_opened", {"workspace": "workspace"}, actor="test")


def _terminal(store):
    opened = _open(store)
    return store.append(
        "run-1", "terminal_written",
        {"state": "Succeeded", "criteria_met": {"gate": True}, "evidence": ["proof"], "false_completion": False},
        actor="test", causation_id=opened["event_id"],
    )


def _force_structural_mode(monkeypatch):
    import loop.contract as contract

    monkeypatch.setattr(contract, "_validation_mode", lambda: "structural-fallback")


def _codes(report):
    return {issue["code"] for issue in report["issues"]}


def _terminal_file(state, *, evidence):
    return json.dumps({
        "schema": "loop-engineer/terminal@1",
        "state": state,
        "criteria_met": {"gate": True},
        "evidence": evidence,
        "false_completion": False,
    })


def _store_path(target):
    return target / ".loop" / "events.db"


def _chained_workspace(tmp_path, name="workspace"):
    """The synced happy-path workspace, whose store is a fresh (chained) generation."""
    target = _fresh_contract(tmp_path, name)
    _sync_active_task(target)
    _open(_store(target))
    return target


def _legacy_workspace(tmp_path, name="workspace"):
    """Same contract, but its store is a byte-faithful v0.9.0 unchained file."""
    target = _fresh_contract(tmp_path, name)
    _sync_active_task(target)
    make_legacy_store(_store_path(target))
    return target


def _tamper_payload(target, payload):
    """Rewrite a stored payload the way an in-workspace adversary would."""
    path = _store_path(target)
    drop_triggers(path)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("UPDATE events SET payload = ? WHERE sequence = 0", (payload,))
        conn.commit()
    finally:
        conn.close()


def test_absent_event_store_matches_pre_slice_doctor_shape(tmp_path):
    target = _fresh_contract(tmp_path)
    file_only = validate_contract(target)
    report = doctor_report(target)
    assert report["event_store"] == {"present": False}
    assert {key: value for key, value in report.items() if key != "event_store"} == file_only


@pytest.mark.parametrize("mode", ["jsonschema", "structural-fallback"])
def test_synced_happy_path_is_doctor_clean(tmp_path, monkeypatch, mode):
    if mode == "jsonschema":
        pytest.importorskip("jsonschema")
    else:
        _force_structural_mode(monkeypatch)
    target = _fresh_contract(tmp_path)
    _sync_active_task(target)
    _open(_store(target))
    report = doctor_report(target)
    assert report["validation_mode"] == mode
    assert report["ok"] is True, report["issues"]
    assert report["event_store"]["present"] is True
    assert report["event_store"]["state_json_agrees"] is True
    assert report["event_store"]["deterministic"] is True
    assert report["event_store"]["legal_sequence"] is True
    assert report["event_store"]["chain"]["head"]["sequence"] == 0
    assert report["event_store"]["chain"]["unchained_prefix"] == 0


@pytest.mark.parametrize("mode", ["jsonschema", "structural-fallback"])
def test_state_field_mismatch_fails_doctor(tmp_path, monkeypatch, mode):
    if mode == "jsonschema":
        pytest.importorskip("jsonschema")
    else:
        _force_structural_mode(monkeypatch)
    target = _fresh_contract(tmp_path)
    _sync_active_task(target)
    _open(_store(target))
    path = target / ".loop" / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["state"] = "plan"
    path.write_text(json.dumps(state), encoding="utf-8")
    report = doctor_report(target)
    assert report["validation_mode"] == mode
    assert report["ok"] is False
    assert "state_field_mismatch" in _codes(report)


def test_desynced_terminal_window_fails_doctor(tmp_path):
    target = _fresh_contract(tmp_path)
    _sync_active_task(target)
    _terminal(_store(target))
    (target / ".loop" / "terminal_state.json").write_text(
        _terminal_file("FailedBlocked", evidence=[]), encoding="utf-8"
    )
    report = doctor_report(target)
    assert report["ok"] is False
    assert "desynced_terminal_window" in _codes(report)


def test_terminal_state_mismatch_fails_doctor(tmp_path):
    target = _fresh_contract(tmp_path)
    _sync_active_task(target)
    _terminal(_store(target))
    (target / ".loop" / "terminal_state.json").write_text(
        _terminal_file("Succeeded", evidence=["different"]), encoding="utf-8"
    )
    report = doctor_report(target)
    assert report["ok"] is False
    assert "terminal_state_mismatch" in _codes(report)


def test_illegal_event_sequence_fails_doctor(tmp_path):
    target = _fresh_contract(tmp_path)
    _store(target).append("run-1", "iteration_appended", {"iteration_id": 0, "outcome": "task_passed"}, actor="test")
    report = doctor_report(target)
    assert report["ok"] is False
    assert "illegal_event_sequence" in _codes(report)


def test_corrupt_store_fails_doctor_without_traceback(tmp_path):
    target = _fresh_contract(tmp_path)
    path = target / ".loop" / "events.db"
    path.write_text("not sqlite", encoding="utf-8")
    report = doctor_report(target)
    assert report["ok"] is False
    assert report["event_store"]["error_code"] == "corrupt_store"
    assert "corrupt_store" in _codes(report)


def test_empty_store_fails_doctor(tmp_path):
    target = _fresh_contract(tmp_path)
    _store(target)._connect().close()
    report = doctor_report(target)
    assert report["ok"] is False
    assert report["event_store"]["error_code"] == "empty_store"
    assert "empty_store" in _codes(report)


def test_ambiguous_run_id_fails_doctor(tmp_path):
    target = _fresh_contract(tmp_path)
    store = _store(target)
    _open(store, "run-a")
    _open(store, "run-b")
    report = doctor_report(target)
    assert report["ok"] is False
    assert report["event_store"]["error_code"] == "ambiguous_run_id"
    assert "ambiguous_run_id" in _codes(report)


def test_status_and_replay_expose_chain_head(tmp_path):
    ws = _chained_workspace(tmp_path)
    report = status_report(ws)
    assert report["chain_head"] is not None
    assert replay_report(ws)["chain_head"] == report["chain_head"]


def test_doctor_nests_chain_under_event_store(tmp_path):
    ws = _chained_workspace(tmp_path)
    report = doctor_report(ws)
    assert report["ok"] is True, report["issues"]
    assert report["event_store"]["chain"]["head"]["sequence"] >= 0
    assert report["event_store"]["chain"]["unchained_prefix"] == 0


def test_legacy_store_doctor_ok_and_chain_null(tmp_path):
    ws = _legacy_workspace(tmp_path)
    report = doctor_report(ws)
    assert report["ok"], report["issues"]
    assert report["event_store"]["chain"] == {"head": None, "unchained_prefix": 1}


def test_migrated_store_doctor_reports_unchained_prefix(tmp_path):
    ws = _legacy_workspace(tmp_path)
    migrate_store(ws)
    report = doctor_report(ws)
    assert report["ok"], report["issues"]
    assert report["event_store"]["chain"]["head"] is None
    assert report["event_store"]["chain"]["unchained_prefix"] == 1


def test_migrated_store_after_append_reports_genesis_head(tmp_path):
    ws = _legacy_workspace(tmp_path)
    migrate_store(ws)
    SQLiteEventStore(_store_path(ws)).append(
        "r1", "iteration_appended", {"iteration_id": 1, "outcome": "task_passed"}, actor="test")
    _sync_iteration(ws, 1)
    chain_block = doctor_report(ws)["event_store"]["chain"]
    assert chain_block["head"]["sequence"] == 1 and chain_block["unchained_prefix"] == 1


def test_tampered_store_fails_doctor_status_and_replay_with_event_chain_broken(tmp_path):
    ws = _chained_workspace(tmp_path)
    _tamper_payload(ws, '{"workspace":"tampered"}')
    for report in (doctor_report(ws), status_report(ws), replay_report(ws)):
        codes = {issue["code"] for issue in
                 report.get("issues", report.get("divergence", []) + report.get("findings", []))}
        assert "event_chain_broken" in codes


def test_run_on_tampered_store_reports_event_chain_broken(tmp_path):
    """Design change D3: runner must not relabel it invalid_event_stream."""
    ws = _chained_workspace(tmp_path)
    _tamper_payload(ws, '{"workspace":"tampered"}')
    with pytest.raises(RuntimeStoreError) as excinfo:
        dispatch_once(ws)
    assert excinfo.value.code == "event_chain_broken"


def test_invalid_event_now_fails_status_instead_of_being_discarded(tmp_path):
    ws = _legacy_workspace(tmp_path)
    conn = sqlite3.connect(str(_store_path(ws)))
    try:
        conn.execute(
            "INSERT INTO events VALUES ('r1', 1, 'legacy-e1', 'iteration_appended', 'operator', "
            "NULL, NULL, '2026-07-24T00:00:01+00:00', '{\"iteration_id\": 1}', '[]')")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(RuntimeStoreError) as excinfo:
        status_report(ws)
    assert excinfo.value.code == "invalid_event"


def test_in_row_json_corruption_fails_doctor_without_traceback(tmp_path):
    """Design change D5: read_event_rows owns the decode translation."""
    ws = _chained_workspace(tmp_path)
    _tamper_payload(ws, "not json")
    report = doctor_report(ws)
    assert not report["ok"] and report["event_store"]["error_code"] == "corrupt_store"


def test_run_on_in_row_json_corruption_reports_corrupt_store(tmp_path):
    """Without runner's EventRowDecodeError clause dispatch_once leaks a bare ValueError."""
    ws = _chained_workspace(tmp_path)
    _tamper_payload(ws, "not json")
    with pytest.raises(RuntimeStoreError) as excinfo:
        dispatch_once(ws)
    assert excinfo.value.code == "corrupt_store"


def _head_hash(target):
    return doctor_report(target)["event_store"]["chain"]["head"]["event_hash"]


def test_expect_chain_head_matching_passes(tmp_path):
    ws = _chained_workspace(tmp_path)
    report = doctor_report(ws, expect_chain_head=_head_hash(ws))
    assert report["ok"], report["issues"]


def test_expect_chain_head_mismatch_fails_doctor(tmp_path):
    ws = _chained_workspace(tmp_path)
    report = doctor_report(ws, expect_chain_head="a" * 64)
    assert not report["ok"]
    assert "chain_anchor_mismatch" in _codes(report)


def test_expect_chain_head_with_missing_store_fails_doctor(tmp_path):
    target = _fresh_contract(tmp_path)
    report = doctor_report(target, expect_chain_head="a" * 64)
    assert not report["ok"]
    assert "chain_anchor_mismatch" in _codes(report)


def test_expect_chain_head_with_unreadable_store_fails_doctor(tmp_path):
    ws = _chained_workspace(tmp_path)
    _store_path(ws).write_text("not sqlite", encoding="utf-8")
    report = doctor_report(ws, expect_chain_head="a" * 64)
    assert not report["ok"]
    assert {"corrupt_store", "chain_anchor_mismatch"} <= _codes(report)


def test_expect_chain_head_on_tampered_store_fails_doctor(tmp_path):
    """A broken chain degrades chain_head to None, so no anchor can ever match it."""
    ws = _chained_workspace(tmp_path)
    head = _head_hash(ws)
    _tamper_payload(ws, '{"workspace":"tampered"}')
    report = doctor_report(ws, expect_chain_head=head)
    assert not report["ok"]
    assert {"event_chain_broken", "chain_anchor_mismatch"} <= _codes(report)


def test_sidecar_residue_without_db_fails_doctor(tmp_path):
    ws = _chained_workspace(tmp_path)
    _store_path(ws).unlink()
    (ws / ".loop" / "events.db-wal").write_bytes(b"")
    report = doctor_report(ws)
    assert not report["ok"]
    assert "missing_event_store" in _codes(report)
    assert report["event_store"] == {"present": False, "sidecar_residue": True}


def test_chain_columns_dropped_but_version_2_fails_doctor(tmp_path):
    """Design change D2: the lazy downgrade attack."""
    ws = _chained_workspace(tmp_path)
    conn = sqlite3.connect(str(_store_path(ws)))
    try:
        conn.execute("ALTER TABLE events DROP COLUMN event_hash")
        conn.commit()
    finally:
        conn.close()
    report = doctor_report(ws)
    assert not report["ok"]
    assert "chain_columns_missing" in _codes(report)


def test_absent_store_without_flag_or_sidecars_stays_byte_stable(tmp_path):
    target = _fresh_contract(tmp_path)
    assert doctor_report(target)["event_store"] == {"present": False}


def test_cli_doctor_accepts_flag_before_target(tmp_path):
    """The action.yml invocation shape: flag BEFORE the positional target."""
    ws = _chained_workspace(tmp_path)
    head = _head_hash(ws)
    assert main(["doctor", "--expect-chain-head", head, str(ws)]) == 0
    assert main(["doctor", "--expect-chain-head", "a" * 64, str(ws)]) == 1


def test_cli_rejects_flag_on_other_commands_and_creates_nothing(tmp_path):
    ws = _chained_workspace(tmp_path)
    target = tmp_path / "fresh"
    assert main(["scaffold", "--expect-chain-head", "a" * 64, str(target)]) == 2
    assert not target.exists()
    assert main(["status", "--expect-chain-head", "a" * 64, str(ws)]) == 2


def test_cli_rejects_malformed_anchor_value(tmp_path):
    ws = _chained_workspace(tmp_path)
    assert main(["doctor", "--expect-chain-head", "nothex", str(ws)]) == 2


def test_read_verbs_leave_no_wal_sidecars_on_clean_store(tmp_path):
    ws = _chained_workspace(tmp_path)
    status_report(ws)
    replay_report(ws)
    doctor_report(ws)
    assert not (ws / ".loop" / "events.db-wal").exists()
    assert not (ws / ".loop" / "events.db-shm").exists()
