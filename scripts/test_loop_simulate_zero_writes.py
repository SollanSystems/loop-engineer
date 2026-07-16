"""Proofs that simulate observes a workspace without mutating it."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from loop import emit, runner
from loop.events import SQLiteEventStore
from loop.simulate import simulate_run

ROOT = Path(__file__).resolve().parent.parent
RUN_ID = "run-1"


def _task(status="pending"):
    return {"id": "T-1", "title": "T-1", "status": status, "criterion_ref": "T-1", "verify": "true", "depends_on": [], "attempts": 0, "evidence": None}


def _ws(tmp_path, task=None):
    w = tmp_path / "workspace"; emit.open_contract(w)
    (w / "TASKS.json").write_text(json.dumps({"schema": "loop-engineer/tasks@1", "tasks": [task or _task()]}), encoding="utf-8")
    store = SQLiteEventStore(w / ".loop" / "events.db"); store.append(RUN_ID, "contract_opened", {"workspace": "workspace"}, actor="test")
    for n, state in enumerate(("plan", "critique-plan", "queue-tasks", "execute-task"), 1):
        store.append(RUN_ID, "iteration_appended", {"iteration_id": n, "outcome": "replanned", "state": state}, actor="test")
        emit.append_iteration(w, iteration_id=n, outcome="replanned", state=state)
    _, projection = runner._projection(w, None)
    emit.sync_state_to_projection(w, projection)
    state_path = w / ".loop" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")); state["active_task"] = None
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return w, store


def _tree_hashes(workspace):
    return {str(path.relative_to(workspace)): hashlib.sha256(path.read_bytes()).hexdigest() for path in workspace.rglob("*") if path.is_file()}


def _without_shm(hashes):
    return {name: value for name, value in hashes.items() if not name.endswith("events.db-shm")}


def test_simulate_on_pristine_store_creates_zero_new_files_and_full_workspace_tree_byte_hash_unchanged(tmp_path):
    w, store = _ws(tmp_path); (w / "subdir").mkdir(); (w / "subdir" / "sentinel.txt").write_text("same", encoding="utf-8")
    before = _tree_hashes(w); report = simulate_run(w); after = _tree_hashes(w)
    assert report["would"]["action"] == "would_dispatch" and _without_shm(before) == _without_shm(after) and len(store.read(RUN_ID)) == 5


def test_simulate_on_crash_left_wal_sidecar_leaves_events_db_and_wal_bytes_unchanged_shm_exempted(tmp_path):
    w, _ = _ws(tmp_path)
    # A child keeps its WAL frames by exiting without closing the connection.
    code = "import os,sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('PRAGMA journal_mode=WAL'); c.execute('CREATE TABLE IF NOT EXISTS sidecar_probe (x)'); c.execute('INSERT INTO sidecar_probe VALUES (1)'); c.commit(); os._exit(0)"
    subprocess.run([sys.executable, "-c", code, str(w / ".loop" / "events.db")], check=True)
    wal = w / ".loop" / "events.db-wal"; assert wal.exists()
    before = _tree_hashes(w); report = simulate_run(w); after = _tree_hashes(w)
    assert report["would"]["action"] == "would_dispatch" and _without_shm(before) == _without_shm(after)


def test_simulate_read_connection_uri_is_mode_ro_and_a_live_write_attempt_through_it_raises_operational_error(tmp_path, monkeypatch):
    w, _ = _ws(tmp_path); real_connect = sqlite3.connect; seen = []
    def record(*args, **kwargs):
        seen.append(args[0]); return real_connect(*args, **kwargs)
    monkeypatch.setattr(sqlite3, "connect", record); simulate_run(w)
    assert seen and all("mode=ro" in uri for uri in seen)
    conn = real_connect(seen[0], uri=True)
    try:
        try:
            conn.execute("INSERT INTO events(run_id, sequence) VALUES ('bad', 999)")
        except sqlite3.OperationalError:
            pass
        else:
            raise AssertionError("read-only event URI accepted INSERT")
    finally:
        conn.close()


def test_simulate_on_terminal_run_with_desynced_terminal_file_does_not_repair_it_full_workspace_tree_bytes_unchanged(tmp_path):
    w, _ = _ws(tmp_path, _task(status="done")); runner.dispatch_once(w, verifier=lambda task, root: runner.VerifyOutcome(True)); (w / ".loop" / "terminal_state.json").unlink()
    before = _tree_hashes(w); report = simulate_run(w); after = _tree_hashes(w)
    assert report["terminal_desync"] is not None and report["ok"] is False and _without_shm(before) == _without_shm(after)


def test_simulate_never_invokes_subprocess_even_when_selected_task_has_a_real_declared_verify_command(tmp_path, monkeypatch):
    w, _ = _ws(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("simulate invoked subprocess.run")
    monkeypatch.setattr(subprocess, "run", forbidden); report = simulate_run(w)
    assert report["would"]["action"] == "would_dispatch"
