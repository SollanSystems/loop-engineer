"""Doctor integration tests for the read-only EventStore consistency gate."""

import json

import pytest

from loop.contract import doctor_report, validate_contract
from loop.events import SQLiteEventStore
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


def test_doctor_event_store_reads_do_not_leave_wal_or_shm_sidecars(tmp_path):
    target = _fresh_contract(tmp_path)
    _sync_active_task(target)
    _open(_store(target))
    sidecars = (target / ".loop" / "events.db-wal", target / ".loop" / "events.db-shm")
    assert all(not path.exists() for path in sidecars)
    report = doctor_report(target)
    assert report["event_store"]["present"] is True
    assert all(not path.exists() for path in sidecars)
