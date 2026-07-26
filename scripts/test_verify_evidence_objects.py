"""build_verify_evidence purity, the content-addressed object, and the bound digest set."""
from __future__ import annotations

import hashlib
import json

import pytest

from loop import emit
from loop.evidence import artifact_object_path
from loop.verifier import executed_verifier_identity


def _task(**overrides):
    base = {"id": "T-1", "title": "t", "status": "pending", "criterion_ref": "C-1",
            "verify": "./scripts/verify-fast.sh", "depends_on": [], "attempts": 0, "evidence": None}
    base.update(overrides)
    return base


def _ws(tmp_path):
    workspace = tmp_path / "workspace"
    emit.open_contract(workspace)
    script = workspace / "scripts" / "verify-fast.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    return workspace


def _tree(workspace):
    return {str(p.relative_to(workspace)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in workspace.rglob("*") if p.is_file()}


def _build(workspace, *, iteration_id=1, task=None, passed=True, **kwargs):
    task = task or _task()
    kwargs.setdefault("code_identity", executed_verifier_identity(task["verify"], workspace))
    return emit.build_verify_evidence(workspace, run_id="run-1", iteration_id=iteration_id,
                                      task=task, passed=passed, **kwargs)


def test_build_writes_nothing(tmp_path):
    workspace = _ws(tmp_path)
    before = _tree(workspace)
    _build(workspace)
    assert _tree(workspace) == before


def test_build_and_write_agree_on_every_byte(tmp_path):
    workspace = _ws(tmp_path)
    built = _build(workspace)
    written = emit.write_verify_evidence(workspace, run_id="run-1", iteration_id=1,
                                         task=_task(), passed=True,
                                         code_identity=executed_verifier_identity(
                                             _task()["verify"], workspace),
                                         built=built)
    assert written["bundle"].read_text(encoding="utf-8") == built.bundle_text
    assert written["evidence"].read_text(encoding="utf-8") == built.record_text


def test_write_places_the_content_addressed_object(tmp_path):
    workspace = _ws(tmp_path)
    built = _build(workspace)
    written = emit.write_verify_evidence(workspace, run_id="run-1", iteration_id=1,
                                         task=_task(), passed=True,
                                         code_identity=executed_verifier_identity(
                                             _task()["verify"], workspace), built=built)
    assert written["object"].is_file()
    assert hashlib.sha256(written["object"].read_bytes()).hexdigest() == built.sha256


def test_object_path_matches_artifact_object_path(tmp_path):
    workspace = _ws(tmp_path)
    built = _build(workspace)
    assert built.object_path == artifact_object_path(workspace, built.sha256)


def test_artifact_hashes_cover_bundle_object_and_record(tmp_path):
    workspace = _ws(tmp_path)
    built = _build(workspace)
    by_path = {entry["path"]: entry["sha256"] for entry in built.artifact_hashes}
    assert len(built.artifact_hashes) == 3
    assert by_path[".loop/artifacts/verify-iter1.json"] == built.sha256
    assert by_path[".loop/evidence/evidence-iter1.json"] == built.record_sha256
    assert by_path[built.object_path.relative_to(workspace).as_posix()] == built.sha256


def test_artifact_hashes_entries_are_workspace_relative_posix(tmp_path):
    built = _build(_ws(tmp_path))
    for entry in built.artifact_hashes:
        assert not entry["path"].startswith("/") and "\\" not in entry["path"]
        assert len(entry["sha256"]) == 64


def test_record_sha256_still_commits_to_the_bundle_bytes(tmp_path):
    built = _build(_ws(tmp_path))
    record = json.loads(built.record_text)
    assert record["sha256"] == hashlib.sha256(built.bundle_text.encode("utf-8")).hexdigest()


def test_rewriting_the_bundle_leaves_the_object_intact(tmp_path):
    workspace = _ws(tmp_path)
    built = _build(workspace)
    written = emit.write_verify_evidence(workspace, run_id="run-1", iteration_id=1,
                                         task=_task(), passed=True,
                                         code_identity=executed_verifier_identity(
                                             _task()["verify"], workspace), built=built)
    written["bundle"].write_text('{"outcome": "PASS", "passed": true}', encoding="utf-8")
    assert hashlib.sha256(written["object"].read_bytes()).hexdigest() == built.sha256


def test_a_second_identical_build_reuses_the_object_without_error(tmp_path):
    workspace = _ws(tmp_path)
    identity = executed_verifier_identity(_task()["verify"], workspace)
    first = emit.write_verify_evidence(workspace, run_id="run-1", iteration_id=1,
                                       task=_task(), passed=True, code_identity=identity)
    second = emit.write_verify_evidence(workspace, run_id="run-1", iteration_id=1,
                                        task=_task(), passed=True, code_identity=identity)
    assert first["object"] == second["object"] and first["sha256"] == second["sha256"]


def test_an_object_collision_with_different_bytes_raises_emit_error(tmp_path):
    workspace = _ws(tmp_path)
    built = _build(workspace)
    built.object_path.parent.mkdir(parents=True, exist_ok=True)
    built.object_path.write_text("not the bundle", encoding="utf-8")
    with pytest.raises(emit.EmitError, match="object store"):
        emit.write_verify_evidence(workspace, run_id="run-1", iteration_id=1, task=_task(),
                                   passed=True,
                                   code_identity=executed_verifier_identity(
                                       _task()["verify"], workspace), built=built)


def test_a_non_canonicalizable_task_raises_a_typed_emit_error_at_build_time(tmp_path):
    workspace = _ws(tmp_path)
    with pytest.raises(emit.EmitError, match="canonical"):
        _build(workspace, task=_task(criterion_ref=float("nan")))


def test_a_failed_record_write_leaves_no_metrics_visible_bundle_and_no_partial_object(tmp_path):
    workspace = _ws(tmp_path)
    built = _build(workspace)
    (workspace / ".loop" / "evidence").mkdir(parents=True, exist_ok=True)
    (workspace / ".loop" / "evidence" / "evidence-iter1.json").mkdir()   # write must fail
    with pytest.raises((OSError, emit.EmitError)):
        emit.write_verify_evidence(workspace, run_id="run-1", iteration_id=1, task=_task(),
                                   passed=True,
                                   code_identity=executed_verifier_identity(
                                       _task()["verify"], workspace), built=built)
    assert not list((workspace / ".loop" / "artifacts").glob("verify-*.json"))
