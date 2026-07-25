"""The object-store collision handler must not raise a raw OSError.

``write_verify_evidence`` places the content-addressed object with a create-once hard
link and treats an existing object as idempotent success once its bytes match. The
match check reads the existing object from INSIDE the ``except FileExistsError``
handler, where the sibling ``except OSError`` cannot reach it — so an
``IsADirectoryError`` or ``PermissionError`` at the object path escaped the writer
untyped, past the API's typed-error contract.
"""
from __future__ import annotations

import json

import pytest

from loop import emit
from loop.evidence import artifact_object_path
from loop.verifier import injected_verifier_identity

_TASK = {"id": "T-1", "title": "T-1", "status": "pending", "criterion_ref": "C-1",
         "verify": "./scripts/verify-fast.sh", "depends_on": [], "attempts": 0, "evidence": None}


def _contract(tmp_path, name="workspace"):
    workspace = tmp_path / name
    emit.open_contract(workspace)
    (workspace / "TASKS.json").write_text(
        json.dumps({"schema": "loop-engineer/tasks@1", "tasks": [_TASK]}), encoding="utf-8")
    return workspace


def _built(workspace):
    return emit.build_verify_evidence(workspace, run_id="run-1", iteration_id=1, task=_TASK,
                                      passed=True, code_identity=injected_verifier_identity())


def test_an_unreadable_existing_object_is_a_typed_emit_error(tmp_path):
    workspace = _contract(tmp_path)
    built = _built(workspace)
    # A DIRECTORY at the object path: the hard link refuses it (FileExistsError) and the
    # collision read then raises IsADirectoryError from inside the handler.
    built.object_path.mkdir(parents=True)
    with pytest.raises(emit.EmitError, match="cannot be read"):
        emit.write_verify_evidence(workspace, run_id="run-1", iteration_id=1, task=_TASK,
                                   passed=True, code_identity=injected_verifier_identity())


def test_a_colliding_object_with_different_bytes_is_still_the_refusal_it_was(tmp_path):
    """Control: the pre-existing typed refusal for a genuine digest collision is unchanged."""
    workspace = _contract(tmp_path)
    built = _built(workspace)
    built.object_path.parent.mkdir(parents=True, exist_ok=True)
    built.object_path.write_text("different bytes\n", encoding="utf-8")
    with pytest.raises(emit.EmitError, match="refusing to overwrite"):
        emit.write_verify_evidence(workspace, run_id="run-1", iteration_id=1, task=_TASK,
                                   passed=True, code_identity=injected_verifier_identity())


def test_an_identical_existing_object_is_idempotent_success(tmp_path):
    """Control: a re-run of the same dispatch still writes cleanly."""
    workspace = _contract(tmp_path)
    first = emit.write_verify_evidence(workspace, run_id="run-1", iteration_id=1, task=_TASK,
                                       passed=True, code_identity=injected_verifier_identity())
    second = emit.write_verify_evidence(workspace, run_id="run-1", iteration_id=1, task=_TASK,
                                        passed=True, code_identity=injected_verifier_identity())
    assert first["sha256"] == second["sha256"]
    assert artifact_object_path(workspace, first["sha256"]).is_file()
