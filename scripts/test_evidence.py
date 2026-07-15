"""Tests for the standalone loop-engineer/evidence@1 proof kernel."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from loop.contract import ValidationModeError
from loop.evidence import EVIDENCE_SCHEMA_ID, EvidenceError, artifact_object_path, validate_evidence, verify_evidence


ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "examples" / "evidence" / "valid-evidence.json"
INVALID = ROOT / "examples" / "evidence" / "invalid"


def evidence(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "schema": EVIDENCE_SCHEMA_ID,
        "id": "evidence-1",
        "kind": "report",
        "uri": "proof/report.txt",
        "sha256": "a" * 64,
        "media_type": "text/plain",
        "produced_by": {"run_id": "run-1", "task_id": "task-1", "attempt": 1, "executor": "test"},
        "verified_by": None,
        "created_at": "2026-07-13T00:00:00Z",
        "policy_result": None,
    }
    result.update(overrides)
    return result


def issue_codes(report: dict) -> set[str]:
    return {issue["code"] for issue in report["issues"]}


def test_schema_has_expected_id_and_surface() -> None:
    schema = json.loads((ROOT / "schemas" / "evidence.schema.json").read_text(encoding="utf-8"))
    assert schema["$id"] == EVIDENCE_SCHEMA_ID
    assert set(schema["properties"]) == {
        "schema", "id", "kind", "uri", "sha256", "media_type", "produced_by",
        "verified_by", "created_at", "policy_result",
    }
    assert schema["additionalProperties"] is True


def test_valid_golden_fixture_passes_both_modes() -> None:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert validate_evidence(data, mode="basic")["ok"] is True
    pytest.importorskip("jsonschema")
    assert validate_evidence(data, mode="release")["ok"] is True


@pytest.mark.parametrize(("filename", "code"), [
    ("missing-required-field.json", "invalid_evidence"),
    ("bad-sha256-pattern.json", "invalid_evidence"),
    ("absolute-uri.json", "invalid_uri"),
    ("scheme-uri.json", "invalid_uri"),
])
def test_invalid_golden_fixtures_fail_in_both_modes(filename: str, code: str) -> None:
    data = json.loads((INVALID / filename).read_text(encoding="utf-8"))
    assert code in issue_codes(validate_evidence(data, mode="basic"))
    pytest.importorskip("jsonschema")
    assert code in issue_codes(validate_evidence(data, mode="release"))


def test_basic_fallback_type_checks_every_field_and_matches_jsonschema_rejection() -> None:
    broken = evidence(
        schema=1, id=2, kind=3, uri=4, sha256=5, media_type=6, produced_by=7,
        verified_by=8, created_at=9, policy_result=10,
    )
    basic = validate_evidence(broken, mode="basic")
    assert basic["ok"] is False
    for field in ("schema", "id", "kind", "uri", "sha256", "media_type", "produced_by", "verified_by", "created_at", "policy_result"):
        assert any(issue["message"].startswith(f"{field} ") for issue in basic["issues"])
    pytest.importorskip("jsonschema")
    assert validate_evidence(broken, mode="release")["ok"] is False


@pytest.mark.parametrize(("mode", "field_prefixes"), [
    ("basic", ("produced_by.run_id", "produced_by.attempt", "verified_by.by", "verified_by.at", "policy_result.ok")),
    ("release", ("produced_by/run_id", "produced_by/attempt", "verified_by/by", "verified_by/at", "policy_result/ok")),
])
def test_nested_subkey_type_errors_are_rejected_with_field_identity_in_both_modes(
    mode: str, field_prefixes: tuple[str, ...],
) -> None:
    if mode == "release":
        pytest.importorskip("jsonschema")
    broken = evidence(
        produced_by={"run_id": 123, "task_id": "task-1", "attempt": "x", "executor": "test"},
        verified_by={"by": 123, "at": False},
        policy_result={"ok": "yes"},
    )

    report = validate_evidence(broken, mode=mode)

    assert report["ok"] is False
    for field_prefix in field_prefixes:
        assert any(issue["message"].startswith(field_prefix) for issue in report["issues"])


@pytest.mark.parametrize("mode", ["strict", "release"])
def test_strict_and_release_require_jsonschema(mode: str, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "jsonschema", None)
    with pytest.raises(ValidationModeError):
        validate_evidence(evidence(), mode=mode)


def test_verify_evidence_accepts_matching_file(tmp_path) -> None:
    path = tmp_path / "proof.txt"
    path.write_bytes(b"evidence")
    report = verify_evidence(evidence(uri="proof.txt", sha256=hashlib.sha256(b"evidence").hexdigest()), workspace_root=tmp_path)
    assert report == {"ok": True, "checks": {"structural": True, "within_workspace": True, "path_exists": True, "hash_match": True}, "issues": []}


def test_verify_evidence_rejects_hash_mismatch(tmp_path) -> None:
    (tmp_path / "proof.txt").write_text("evidence", encoding="utf-8")
    report = verify_evidence(evidence(uri="proof.txt", sha256="0" * 64), workspace_root=tmp_path)
    assert report["ok"] is False
    assert "hash_mismatch" in issue_codes(report)


def test_verify_evidence_rejects_missing_path_and_directory(tmp_path) -> None:
    missing = verify_evidence(evidence(uri="missing.txt"), workspace_root=tmp_path)
    assert "missing_evidence_path" in issue_codes(missing)
    (tmp_path / "proof").mkdir()
    directory = verify_evidence(evidence(uri="proof"), workspace_root=tmp_path)
    assert "not_a_file" in issue_codes(directory)


def test_verify_evidence_rejects_parent_traversal_and_symlink_escape(tmp_path) -> None:
    outside = tmp_path.parent / "outside-evidence.txt"
    outside.write_text("outside", encoding="utf-8")
    try:
        (tmp_path / "sub").mkdir()
        traversal = verify_evidence(evidence(uri="sub/../../outside-evidence.txt"), workspace_root=tmp_path)
        assert "workspace_escape" in issue_codes(traversal)
        os.symlink(outside, tmp_path / "escape.txt")
        symlink = verify_evidence(evidence(uri="escape.txt"), workspace_root=tmp_path)
        assert "workspace_escape" in issue_codes(symlink)
    finally:
        outside.unlink(missing_ok=True)


def test_verify_evidence_rejects_intermediate_symlink_directory_escape(tmp_path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-directory"
    outside.mkdir()
    try:
        (outside / "proof.txt").write_text("outside", encoding="utf-8")
        os.symlink(outside, tmp_path / "intermediate", target_is_directory=True)

        report = verify_evidence(evidence(uri="intermediate/proof.txt"), workspace_root=tmp_path)

        assert report["ok"] is False
        assert issue_codes(report) == {"workspace_escape"}
    finally:
        (outside / "proof.txt").unlink(missing_ok=True)
        outside.rmdir()


def test_verify_evidence_rejects_symlink_loop_without_raising(tmp_path) -> None:
    path = tmp_path / "loop_a"
    os.symlink(path, path)

    report = verify_evidence(evidence(uri="loop_a/x"), workspace_root=tmp_path)

    assert report["ok"] is False
    assert issue_codes(report) == {"missing_evidence_path"}
    assert report["checks"] == {
        "structural": True,
        "within_workspace": None,
        "path_exists": False,
        "hash_match": None,
    }


def test_verify_evidence_rejects_bare_parent_uri_as_workspace_escape(tmp_path) -> None:
    report = verify_evidence(evidence(uri=".."), workspace_root=tmp_path)

    assert report["ok"] is False
    assert issue_codes(report) == {"workspace_escape"}


def test_verify_evidence_content_problems_never_raise_and_bad_root_does(tmp_path) -> None:
    invalid = verify_evidence(evidence(uri="https://example.com/proof"), workspace_root=tmp_path)
    assert invalid["checks"] == {"structural": False, "within_workspace": None, "path_exists": None, "hash_match": None}
    with pytest.raises(EvidenceError):
        verify_evidence(evidence(), workspace_root=tmp_path / "missing")
    file_root = tmp_path / "not-a-directory"
    file_root.write_text("x", encoding="utf-8")
    with pytest.raises(EvidenceError):
        verify_evidence(evidence(), workspace_root=file_root)


def test_verify_evidence_rejects_embedded_nul_uri_without_raising(tmp_path) -> None:
    nul_uri = "proof\x00.txt"
    # JSON Schema accepts this string; path resolution must reject it safely instead.
    assert validate_evidence(evidence(uri=nul_uri), mode="basic")["ok"] is True

    report = verify_evidence(evidence(uri=nul_uri), workspace_root=tmp_path)

    assert report["ok"] is False
    assert report["checks"] == {
        "structural": True,
        "within_workspace": None,
        "path_exists": None,
        "hash_match": None,
    }
    assert issue_codes(report) == {"invalid_uri"}


def test_verify_evidence_handles_artifact_io_failure_without_raising(tmp_path, monkeypatch) -> None:
    path = tmp_path / "proof.txt"
    path.write_text("evidence", encoding="utf-8")

    def unavailable(*args, **kwargs):
        raise PermissionError("unavailable")

    monkeypatch.setattr(os, "open", unavailable)
    report = verify_evidence(evidence(uri="proof.txt"), workspace_root=tmp_path)
    assert "missing_evidence_path" in issue_codes(report)


def test_artifact_object_path_is_pure_and_uses_content_addressed_layout(tmp_path) -> None:
    before = list(tmp_path.iterdir())
    digest = "ab" + "c" * 62
    assert artifact_object_path(tmp_path, digest) == tmp_path / ".loop" / "artifacts" / "objects" / "ab" / digest
    assert list(tmp_path.iterdir()) == before
