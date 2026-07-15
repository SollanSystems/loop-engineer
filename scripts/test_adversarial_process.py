"""Adversarial process/security tests that intentionally kill child processes."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from loop import emit
from loop.events import DuplicateEventError, SQLiteEventStore
from loop.evidence import EVIDENCE_SCHEMA_ID, verify_evidence


def _run_and_expect_sigkill(script: Path, *args: Path) -> None:
    proc = subprocess.run(
        [sys.executable, "-B", str(script), *(str(arg) for arg in args)], cwd=os.getcwd(), timeout=15,
    )
    assert proc.returncode == -signal.SIGKILL


def _evidence(uri: str, content: bytes) -> dict[str, object]:
    return {
        "schema": EVIDENCE_SCHEMA_ID,
        "id": "evidence-1",
        "kind": "report",
        "uri": uri,
        "sha256": hashlib.sha256(content).hexdigest(),
        "media_type": "text/plain",
        "produced_by": {"run_id": "run-1", "task_id": "task-1", "attempt": 1, "executor": "test"},
        "verified_by": None,
        "created_at": "2026-07-15T00:00:00Z",
        "policy_result": None,
    }


def test_crash_injection_before_commit_leaves_no_lost_or_torn_event(tmp_path) -> None:
    path = tmp_path / "events.db"
    script = tmp_path / "before_commit.py"
    script.write_text(
        """import os, sys
sys.path.insert(0, os.getcwd())
import signal
import sqlite3

real_connect = sqlite3.connect
class KillBeforeCommit(sqlite3.Connection):
    def execute(self, sql, *args, **kwargs):
        if isinstance(sql, str) and sql.strip().upper() == "COMMIT":
            os.kill(os.getpid(), signal.SIGKILL)
        return super().execute(sql, *args, **kwargs)
sqlite3.connect = lambda *args, **kwargs: real_connect(*args, factory=KillBeforeCommit, **kwargs)

from loop.events import SQLiteEventStore
SQLiteEventStore(sys.argv[1]).append("run", "contract_opened", {"workspace": "w"}, actor="test", event_id="before-commit")
""",
        encoding="utf-8",
    )

    _run_and_expect_sigkill(script, path)

    store = SQLiteEventStore(path)
    assert store.read("run") == []
    assert store.latest_sequence("run") is None
    assert store.append("run", "contract_opened", {"workspace": "w"}, actor="test")["sequence"] == 0


def test_crash_injection_after_commit_persists_exactly_once(tmp_path) -> None:
    path = tmp_path / "events.db"
    event_id = "after-commit"
    script = tmp_path / "after_commit.py"
    script.write_text(
        """import os, sys
sys.path.insert(0, os.getcwd())
import signal
import sqlite3

real_connect = sqlite3.connect
class KillAfterCommit(sqlite3.Connection):
    def execute(self, sql, *args, **kwargs):
        result = super().execute(sql, *args, **kwargs)
        if isinstance(sql, str) and sql.strip().upper() == "COMMIT":
            os.kill(os.getpid(), signal.SIGKILL)
        return result
sqlite3.connect = lambda *args, **kwargs: real_connect(*args, factory=KillAfterCommit, **kwargs)

from loop.events import SQLiteEventStore
SQLiteEventStore(sys.argv[1]).append("run", "contract_opened", {"workspace": "w"}, actor="test", event_id="after-commit")
""",
        encoding="utf-8",
    )

    _run_and_expect_sigkill(script, path)

    store = SQLiteEventStore(path)
    records = store.read("run")
    assert len(records) == 1
    assert records[0]["event_id"] == event_id
    with pytest.raises(DuplicateEventError):
        store.append("run", "contract_opened", {"workspace": "w"}, actor="test", event_id=event_id)


def test_crash_injection_terminal_link_before_state_stamp_recovers_via_sync_and_monitor(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    script = tmp_path / "terminal_link.py"
    script.write_text(
        """import os, sys
sys.path.insert(0, os.getcwd())
import signal
import loop.emit as emit

emit.open_contract(sys.argv[1])
real_link = emit.os.link
def kill_after_link(*args, **kwargs):
    result = real_link(*args, **kwargs)
    os.kill(os.getpid(), signal.SIGKILL)
    return result
emit.os.link = kill_after_link
emit.terminate(sys.argv[1], state="Succeeded", criteria_met={"done": True}, evidence=["proof.txt"], iteration_id=1)
""",
        encoding="utf-8",
    )

    _run_and_expect_sigkill(script, workspace)

    state_path = workspace / ".loop" / "state.json"
    before_sync = json.loads(state_path.read_text(encoding="utf-8"))
    assert before_sync["terminal_state"] is None
    assert before_sync["state"] != "terminal"

    spec = importlib.util.spec_from_file_location(
        "runtime_monitor", Path(__file__).parent / "runtime_monitor.py"
    )
    runtime_monitor = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(runtime_monitor)
    report = runtime_monitor.health_report(workspace)
    assert report["status"] == "ok"
    assert report["recommendation"] == "done"
    assert report["terminal_state"] == "Succeeded"

    emit.sync_state_to_terminal(workspace)
    after_sync = json.loads(state_path.read_text(encoding="utf-8"))
    assert after_sync["state"] == "terminal"
    assert after_sync["terminal_state"] == "Succeeded"


def test_evidence_verify_never_caches_and_catches_post_hash_tamper(tmp_path) -> None:
    path = tmp_path / "proof.txt"
    original = b"original"
    path.write_bytes(original)
    record = _evidence("proof.txt", original)

    assert verify_evidence(record, workspace_root=tmp_path)["ok"] is True
    path.write_bytes(b"tampered")
    report = verify_evidence(record, workspace_root=tmp_path)
    assert report["ok"] is False
    assert report["checks"]["hash_match"] is False
    assert {issue["code"] for issue in report["issues"]} == {"hash_mismatch"}


def test_sqlite_raw_file_tamper_bypassing_sql_interface_is_not_detected(tmp_path) -> None:
    path = tmp_path / "events.db"
    store = SQLiteEventStore(path)
    store.append("run", "contract_opened", {"workspace": "w"}, actor="test")
    needle = b'{"workspace": "w"}'
    replacement = b'{"workspace": "X"}'
    raw = path.read_bytes()
    offset = raw.find(needle)
    assert offset >= 0
    path.write_bytes(raw[:offset] + replacement + raw[offset + len(needle):])

    assert SQLiteEventStore(path).read("run")[0]["payload"] == {"workspace": "X"}


@pytest.mark.xfail(
    strict=True,
    reason="follow-up verify_evidence TOCTOU hardening: containment is not rechecked before the read",
)
def test_symlink_swap_between_containment_check_and_hash_read_escapes_workspace(tmp_path, monkeypatch) -> None:
    inside = tmp_path / "proof.txt"
    outside = tmp_path.parent / f"{tmp_path.name}-outside-proof.txt"
    inside.write_bytes(b"inside")
    outside.write_bytes(b"outside")
    record = _evidence("proof.txt", b"outside")
    real_is_file = Path.is_file

    def swap_after_containment(path: Path) -> bool:
        if path == inside:
            inside.unlink()
            os.symlink(outside, inside)
        return real_is_file(path)

    monkeypatch.setattr(Path, "is_file", swap_after_containment)

    try:
        report = verify_evidence(record, workspace_root=tmp_path)
    finally:
        outside.unlink(missing_ok=True)

    assert report["ok"] is False
