"""The write-time and read-time views of "bound" must agree on every tree.

Two defects lived in the gap between them.

**The append-only forge.** ``bound_artifact_digests`` built a ``{path: sha256}`` dict
comprehension over every event, so a path bound twice collapsed LAST-WINS. No trigger
drop and no re-chain were needed: rewrite a bound record (``emit.terminate`` correctly
refuses — "bound at a different digest"), then append ONE ordinary event binding that
path at the NEW digest, and the writer's view said "bound, and it matches" while
``_bound_evidence_issues`` — which checks PER EVENT — still reported
``evidence_chain_mismatch`` on the same tree. A path carrying two or more different
digests is ambiguous, and ambiguous is not proof, so the view now returns the whole
conflict set and the strict bar refuses it.

**The unbounded read of an attacker-named path.** ``event@1`` constrains a bound
``path`` only to ``minLength: 1``, and the walk joined it straight onto the workspace,
so an appended event could make ``loop doctor`` open and hash ``/etc/hostname``. Every
other workspace-bearing layer containment-checks; this one now does too, BEFORE it
opens anything, and reads under a cap.

``bound_artifact_digests`` shipped with no direct test at all (Task-3 carry-forward);
it has one now.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from loop import emit
from loop.completion import VERIFIED_EVIDENCE_MODE
from loop.contract import doctor_report
from loop.evidence import hash_bound_artifact
from loop.events import SQLiteEventStore
from loop.runner import dispatch_once
from loop.runtime import RuntimeStoreError, bound_artifact_digests
from loop.scaffold import scaffold

_VERIFY = "./scripts/verify-fast.sh"
_RAMP = ("plan", "critique-plan", "queue-tasks", "execute-task")
_RUN_ID = "run-1"
_RECORD = ".loop/evidence/evidence-iter1.json"


def _codes(report):
    return {issue["code"] for issue in report["issues"]}


def _store(workspace):
    return SQLiteEventStore(workspace / ".loop" / "events.db")


def _dispatched(tmp_path, name="workspace"):
    workspace = tmp_path / name
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
    store = _store(workspace)
    store.append(_RUN_ID, "contract_opened", {"workspace": name}, actor="test")
    for state in _RAMP:
        store.append(_RUN_ID, "iteration_appended",
                     {"iteration_id": 0, "outcome": "replanned", "state": state}, actor="test")
    dispatch_once(workspace)
    return workspace


def _append_binding(workspace, artifact_hashes, *, iteration_id=2):
    _store(workspace).append(
        _RUN_ID, "iteration_appended",
        {"iteration_id": iteration_id, "outcome": "task_passed", "state": "execute-task"},
        actor="forge", artifact_hashes=artifact_hashes)


# --- the append-only forge ----------------------------------------------------


def _forge(workspace):
    """Rewrite the bound record, then re-bind it at its new digest by APPENDING."""
    record_path = workspace / ".loop" / "evidence" / "evidence-iter1.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["verified_by"]["by"] = "forged-ci"
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    record_path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_an_append_only_forge_cannot_launder_a_tampered_record(tmp_path):
    workspace = _dispatched(tmp_path)
    digest = _forge(workspace)
    # Control: before the re-bind BOTH layers already refuse, for the same reason.
    with pytest.raises(emit.EmitError, match="bound at a different digest"):
        emit.terminate(workspace, state="Succeeded", criteria_met={"T-1": True},
                       evidence=[_RECORD], completion_policy=VERIFIED_EVIDENCE_MODE)
    assert "evidence_chain_mismatch" in _codes(doctor_report(workspace))

    _append_binding(workspace, [{"path": _RECORD, "sha256": digest}])
    # The read-time walk still reports the FIRST binding's mismatch...
    assert "evidence_chain_mismatch" in _codes(doctor_report(workspace))
    # ...and the write-time view no longer disagrees with it.
    with pytest.raises(emit.EmitError, match="ambiguous binding is not proof"):
        emit.terminate(workspace, state="Succeeded", criteria_met={"T-1": True},
                       evidence=[_RECORD], completion_policy=VERIFIED_EVIDENCE_MODE)


# --- bound_artifact_digests, directly -----------------------------------------


def test_no_store_returns_none_and_nothing_bound_returns_an_empty_dict(tmp_path):
    scaffolded = tmp_path / "scaffolded"
    scaffold(scaffolded)
    assert bound_artifact_digests(scaffolded) is None
    bare = tmp_path / "bare"
    emit.open_contract(bare)
    _store(bare).append(_RUN_ID, "contract_opened", {"workspace": "bare"}, actor="test")
    assert bound_artifact_digests(bare) == {}


def test_a_dispatch_binds_three_paths_each_at_exactly_one_digest(tmp_path):
    workspace = _dispatched(tmp_path)
    bound = bound_artifact_digests(workspace)
    assert set(bound) == {".loop/artifacts/verify-iter1.json", _RECORD,
                          *(p for p in bound if p.startswith(".loop/artifacts/objects/"))}
    assert all(len(digests) == 1 for digests in bound.values())


def test_repeat_bindings_at_the_same_digest_stay_one_element(tmp_path):
    workspace = _dispatched(tmp_path)
    same = bound_artifact_digests(workspace)[_RECORD][0]
    _append_binding(workspace, [{"path": _RECORD, "sha256": same}])
    assert bound_artifact_digests(workspace)[_RECORD] == (same,)


def test_conflicting_bindings_are_returned_in_first_bound_order(tmp_path):
    workspace = _dispatched(tmp_path)
    first = bound_artifact_digests(workspace)[_RECORD][0]
    second, third = "a" * 64, "b" * 64
    _append_binding(workspace, [{"path": _RECORD, "sha256": second}], iteration_id=2)
    _append_binding(workspace, [{"path": _RECORD, "sha256": third}], iteration_id=3)
    assert bound_artifact_digests(workspace)[_RECORD] == (first, second, third)


def test_an_unreadable_store_raises_rather_than_returning_an_empty_view(tmp_path):
    workspace = _dispatched(tmp_path)
    for sidecar in ("events.db-wal", "events.db-shm"):
        (workspace / ".loop" / sidecar).unlink(missing_ok=True)
    (workspace / ".loop" / "events.db").write_bytes(b"not a sqlite database" * 64)
    with pytest.raises(RuntimeStoreError):
        bound_artifact_digests(workspace)


# --- containment in the binding walk ------------------------------------------


@pytest.mark.parametrize("escaping", [
    "/etc/hostname",
    "../../../../etc/hostname",
    "nested/../../outside.txt",
    "C:/Windows/system.ini",
    "..\\..\\etc\\hostname",
    " ",
])
def test_an_escaping_bound_path_is_reported_not_read(tmp_path, escaping):
    workspace = _dispatched(tmp_path)
    _append_binding(workspace, [{"path": escaping, "sha256": "0" * 64}])
    report = doctor_report(workspace)
    assert "bound_evidence_escape" in _codes(report)
    assert report["ok"] is False


def test_the_lexical_containment_check_touches_no_filesystem(tmp_path, monkeypatch):
    """Proof, not assertion: with ``os.open`` and ``Path.resolve`` booby-trapped, an
    escaping path still returns a verdict — so nothing was opened or even stat'd."""
    def boom(*args, **kwargs):                      # pragma: no cover - must never run
        raise AssertionError("the walk touched the filesystem before containment")

    monkeypatch.setattr("loop.evidence.os.open", boom)
    monkeypatch.setattr(Path, "resolve", boom)
    code, detail = hash_bound_artifact(tmp_path, "../../../../etc/hostname")
    assert code == "escape" and ".." in detail


@pytest.mark.parametrize("rel", ["", "   ", None, 7])
def test_a_path_that_is_not_a_path_is_an_escape_not_a_crash(tmp_path, rel):
    """``event@1``'s ``minLength: 1`` keeps the empty string out of a real store, so the
    helper's own total-ness is what stops a hand-built or future store from crashing the
    walk instead of reporting it."""
    code, detail = hash_bound_artifact(tmp_path, rel)
    assert code == "escape" and "non-empty path" in detail


def test_a_symlinked_escape_is_caught_after_resolution(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (workspace / "link.txt").symlink_to(outside)
    code, detail = hash_bound_artifact(workspace, "link.txt")
    assert code == "escape" and "outside the workspace" in detail


def test_a_contained_regular_file_hashes(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    assert hash_bound_artifact(tmp_path, "a.txt") == (
        "ok", hashlib.sha256(b"hello").hexdigest())


def test_a_non_regular_file_is_unreadable_rather_than_read_forever(tmp_path):
    os.mkfifo(tmp_path / "pipe")
    code, detail = hash_bound_artifact(tmp_path, "pipe")
    assert code == "unreadable" and "not a regular file" in detail


def test_the_read_is_capped(tmp_path):
    (tmp_path / "big.bin").write_bytes(b"x" * 4096)
    code, detail = hash_bound_artifact(tmp_path, "big.bin", max_bytes=16)
    assert code == "unreadable" and "read cap" in detail


def test_an_absent_bound_path_is_still_missing_bound_evidence(tmp_path):
    """The pre-existing code is unchanged for the pre-existing case."""
    workspace = _dispatched(tmp_path)
    (workspace / ".loop" / "evidence" / "evidence-iter1.json").unlink()
    assert "missing_bound_evidence" in _codes(doctor_report(workspace))
