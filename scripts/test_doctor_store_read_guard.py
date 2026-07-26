"""Doctor's THIRD store read is guarded exactly like its two siblings (R007).

``event_consistency_issues`` reads the store three times: ``status_report``,
``replay_report``, and the chain-binding walk. The first two sat inside an
``except RuntimeStoreError`` that turns an unreadable store into a typed finding; the
walk sat OUTSIDE it, so a store that became unreadable between reads escaped
``doctor_report`` as an untyped traceback — an errored check must fail, never explode.
"""
from __future__ import annotations

import json

from loop import emit
from loop.contract import doctor_report
from loop.events import SQLiteEventStore
from loop.runner import dispatch_once
from loop.runtime import RuntimeStoreError

_VERIFY = "./scripts/verify-fast.sh"
_RAMP = ("plan", "critique-plan", "queue-tasks", "execute-task")


def _dispatched(tmp_path):
    workspace = tmp_path / "workspace"
    emit.open_contract(workspace)
    (workspace / "TASKS.json").write_text(json.dumps({
        "schema": "loop-engineer/tasks@1",
        "tasks": [{"id": "T-1", "title": "T-1", "status": "pending", "criterion_ref": "T-1",
                   "verify": _VERIFY, "depends_on": [], "attempts": 0, "evidence": None}],
    }), encoding="utf-8")
    script = workspace / "scripts" / "verify-fast.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    store = SQLiteEventStore(workspace / ".loop" / "events.db")
    store.append("run-1", "contract_opened", {"workspace": "workspace"}, actor="test")
    for state in _RAMP:
        store.append("run-1", "iteration_appended",
                     {"iteration_id": 0, "outcome": "replanned", "state": state}, actor="test")
    dispatch_once(workspace)
    return workspace


def test_a_store_that_dies_between_reads_is_a_typed_finding_not_a_traceback(
        tmp_path, monkeypatch):
    workspace = _dispatched(tmp_path)

    def boom(*args, **kwargs):
        raise RuntimeStoreError("corrupt_store", "the store died between reads")

    monkeypatch.setattr("loop.runtime._bound_evidence_issues", boom)
    report = doctor_report(workspace)                      # must not raise
    assert "corrupt_store" in {issue["code"] for issue in report["issues"]}
    assert report["event_store"] == {"present": True, "readable": False,
                                     "error_code": "corrupt_store"}
