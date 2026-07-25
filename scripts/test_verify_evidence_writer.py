"""The verify-bundle + evidence@1 writer: shape, digests, and metrics compatibility."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import metrics  # the shipped metrics reader — compatibility is the point
from loop import emit
from loop.evidence import validate_evidence, verify_evidence
from loop.verifier import executed_verifier_identity, injected_verifier_identity


def _task(**overrides):
    base = {"id": "T-1", "title": "t", "status": "pending", "criterion_ref": "C-1",
            "verify": "./scripts/verify-fast.sh", "depends_on": [], "attempts": 2, "evidence": None}
    base.update(overrides)
    return base


def _ws(tmp_path):
    workspace = tmp_path / "workspace"
    emit.open_contract(workspace)
    script = workspace / "scripts" / "verify-fast.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    return workspace


def _write(workspace, **overrides):
    kwargs = {"run_id": "run-1", "iteration_id": 5, "task": _task(), "passed": True,
              "summary": "ok",
              "code_identity": executed_verifier_identity("./scripts/verify-fast.sh", workspace)}
    kwargs.update(overrides)
    return emit.write_verify_evidence(workspace, **kwargs)


def test_bundle_is_green_by_the_shipped_metrics_convention(tmp_path):
    workspace = _ws(tmp_path)
    written = _write(workspace)
    bundle = json.loads(Path(written["bundle"]).read_text(encoding="utf-8"))
    assert bundle["outcome"] == "PASS" and bundle["passed"] is True
    assert bundle["iteration_id"] == 5 and bundle["task"] == "T-1"
    assert Path(written["bundle"]).parent.name == "artifacts"


def test_metrics_sees_exactly_one_bundle_and_no_gate_verdict(tmp_path):
    workspace = _ws(tmp_path)
    _write(workspace)
    loop_dir = workspace / ".loop"
    bundles = metrics._load_verify_bundles(loop_dir)
    assert [b["name"] for b in bundles] == ["verify-iter5.json"]
    assert bundles[0]["green"] is True and bundles[0]["iter"] == "5"
    assert metrics._load_gate_verdicts(loop_dir) == []


def test_failing_verification_writes_a_red_bundle(tmp_path):
    workspace = _ws(tmp_path)
    written = _write(workspace, passed=False, summary="boom")
    bundle = json.loads(Path(written["bundle"]).read_text(encoding="utf-8"))
    assert bundle["outcome"] == "FAIL" and bundle["passed"] is False
    assert metrics._load_verify_bundles(workspace / ".loop")[0]["green"] is False


def test_bundle_records_verifier_identity_and_partition(tmp_path):
    workspace = _ws(tmp_path)
    written = _write(workspace)
    bundle = json.loads(Path(written["bundle"]).read_text(encoding="utf-8"))
    script = (workspace / "scripts" / "verify-fast.sh").read_bytes()
    assert bundle["verifier"]["code_digest"] == hashlib.sha256(script).hexdigest()
    assert bundle["verifier"]["code_digest_basis"] == "workspace_file"
    assert bundle["verifier"]["by"] == emit.DEFAULT_VERIFIER_IDENTITY
    assert bundle["partition"] == {"visible": ["C-1"], "holdout": [],
                                   "declared": False, "holdout_executed": False}


def test_bundle_names_the_verdict_source(tmp_path):
    """outcome/passed came from SOMETHING — the bundle says what, so a reader of
    metrics can tell a declared-command gate from an injected callable."""
    workspace = _ws(tmp_path)
    declared = json.loads(Path(_write(workspace)["bundle"]).read_text(encoding="utf-8"))
    injected = json.loads(Path(
        _write(workspace, iteration_id=6, code_identity=injected_verifier_identity())["bundle"]
    ).read_text(encoding="utf-8"))
    assert declared["verifier"]["source"] == "declared_command"
    assert injected["verifier"]["source"] == "injected_callable"


def test_injected_verifier_identity_records_nulls_not_a_fabricated_digest(tmp_path):
    """The declared verify command did not run; recording it would be a fabrication."""
    workspace = _ws(tmp_path)
    written = _write(workspace, code_identity=injected_verifier_identity())
    record = json.loads(Path(written["evidence"]).read_text(encoding="utf-8"))
    assert record["verified_by"]["command"] is None
    assert record["verified_by"]["code_digest"] is None
    assert record["verified_by"]["code_digest_basis"] == "injected_verifier"


def test_record_sha256_commits_to_the_bundle_bytes(tmp_path):
    workspace = _ws(tmp_path)
    written = _write(workspace)
    record = json.loads(Path(written["evidence"]).read_text(encoding="utf-8"))
    assert record["sha256"] == hashlib.sha256(Path(written["bundle"]).read_bytes()).hexdigest()
    assert verify_evidence(record, workspace_root=workspace)["ok"] is True


@pytest.mark.parametrize("mode", ["basic", "strict"])
def test_record_validates_as_evidence_at_1(tmp_path, mode):
    if mode == "strict":
        pytest.importorskip("jsonschema")
    workspace = _ws(tmp_path)
    record = json.loads(Path(_write(workspace)["evidence"]).read_text(encoding="utf-8"))
    assert validate_evidence(record, mode=mode)["ok"] is True


def test_defaults_never_collide_so_a_default_run_is_not_self_verified(tmp_path):
    workspace = _ws(tmp_path)
    record = json.loads(Path(_write(workspace)["evidence"]).read_text(encoding="utf-8"))
    assert record["produced_by"]["executor"] == emit.UNATTRIBUTED_EXECUTOR
    assert record["verified_by"]["by"] == emit.DEFAULT_VERIFIER_IDENTITY
    assert record["produced_by"]["executor"] != record["verified_by"]["by"]


def test_supplied_identities_are_recorded_verbatim(tmp_path):
    workspace = _ws(tmp_path)
    record = json.loads(Path(
        _write(workspace, executor="worker-a", verifier_identity="worker-a", attempt=3)["evidence"]
    ).read_text(encoding="utf-8"))
    assert record["produced_by"]["executor"] == "worker-a"
    assert record["verified_by"]["by"] == "worker-a"
    assert record["produced_by"]["attempt"] == 3


def test_attempt_is_null_when_the_caller_supplies_none(tmp_path):
    """The kernel does not track TASKS.json `attempts` (zero references in loop/),
    so an unsupplied attempt is null, never task['attempts'] + 1."""
    workspace = _ws(tmp_path)
    record = json.loads(Path(_write(workspace)["evidence"]).read_text(encoding="utf-8"))
    assert record["produced_by"]["attempt"] is None


def test_rewrite_of_the_same_iteration_is_idempotent_in_path(tmp_path):
    workspace = _ws(tmp_path)
    first, second = _write(workspace), _write(workspace)
    assert first["bundle"] == second["bundle"] and first["evidence"] == second["evidence"]
    assert first["sha256"] == second["sha256"]
    assert [p.name for p in sorted((workspace / ".loop" / "artifacts").iterdir())] == ["verify-iter5.json"]


def test_writer_refuses_a_workspace_with_no_contract(tmp_path):
    with pytest.raises(emit.EmitError):
        emit.write_verify_evidence(tmp_path / "nope", run_id="r", iteration_id=1,
                                   task=_task(), passed=True,
                                   code_identity=injected_verifier_identity())


def test_a_non_canonicalizable_task_raises_a_typed_emit_error(tmp_path):
    """json.loads accepts NaN by default; canonical_json sets allow_nan=False. The
    resulting ChainHashError must never escape the writer untyped."""
    workspace = _ws(tmp_path)
    task = json.loads('{"id": "T-1", "criterion_ref": NaN, "verify": "true", "depends_on": []}')
    with pytest.raises(emit.EmitError, match="canonical"):
        _write(workspace, task=task)


def test_a_failed_record_write_leaves_no_metrics_visible_bundle(tmp_path, monkeypatch):
    """Bundle goes to a temp name, record next, bundle placed last — so an error
    between them cannot leave an orphan green marker for FCR to read."""
    workspace = _ws(tmp_path)
    real = emit._atomic_write_text

    def explode(path, text):
        if path.name.startswith("evidence-iter"):
            raise OSError("disk full")
        return real(path, text)

    monkeypatch.setattr(emit, "_atomic_write_text", explode)
    with pytest.raises(OSError):
        _write(workspace)
    assert metrics._load_verify_bundles(workspace / ".loop") == []
