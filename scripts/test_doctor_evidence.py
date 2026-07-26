"""Doctor's evidence@1 discovery, the self-verification finding, and the orphan-bundle tripwire."""
from __future__ import annotations

import hashlib
import json

import pytest

from loop.contract import doctor_report, validate_contract
from loop.scaffold import scaffold


def _codes(report):
    return {issue["code"] for issue in report["issues"]}


_BUNDLE_TEXT = json.dumps({"outcome": "PASS", "passed": True})
_BUNDLE_SHA = hashlib.sha256(_BUNDLE_TEXT.encode("utf-8")).hexdigest()
# A legacy bundle name: doctor now hash-verifies a record's uri, so the file must
# exist, and a runner-shaped verify-iter<N>.json would need its own record.
_RECORD_BUNDLE_NAME = "verify-T1.json"


def _record(executor="worker-a", by="ci", **overrides):
    record = {
        "schema": "loop-engineer/evidence@1", "id": "e1", "kind": "verify-bundle",
        "uri": f".loop/artifacts/{_RECORD_BUNDLE_NAME}", "sha256": _BUNDLE_SHA,
        "media_type": "application/json", "created_at": "2026-07-25T00:00:00+00:00",
        "produced_by": {"run_id": "run-1", "task_id": "T-1", "attempt": 1, "executor": executor},
        "verified_by": {"by": by, "at": "2026-07-25T00:00:00+00:00",
                        "command": "./scripts/verify-fast.sh",
                        "code_digest": "a" * 64, "code_digest_basis": "workspace_file",
                        "policy_digest": "b" * 64},
    }
    record.update(overrides)
    return record


def _ws(tmp_path, records=(), bundles=(), name="workspace"):
    target = tmp_path / name
    scaffold(target)
    artifacts = target / ".loop" / "artifacts"
    if records:
        directory = target / ".loop" / "evidence"
        directory.mkdir(parents=True, exist_ok=True)
        for index, record in enumerate(records):
            text = record if isinstance(record, str) else json.dumps(record)
            (directory / f"evidence-iter{index}.json").write_text(text, encoding="utf-8")
        # Every _record() names this uri, so it must exist with exactly the bytes
        # the record commits to.
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / _RECORD_BUNDLE_NAME).write_text(_BUNDLE_TEXT, encoding="utf-8")
    for bundle_name in bundles:
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / bundle_name).write_text(_BUNDLE_TEXT, encoding="utf-8")
    return target


def _tree(workspace):
    return {str(p.relative_to(workspace)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in workspace.rglob("*") if p.is_file()}


def test_absent_evidence_directory_is_a_byte_stable_no_op(tmp_path):
    target = _ws(tmp_path)
    assert doctor_report(target) == {**validate_contract(target), "event_store": {"present": False}}


def test_independent_verifier_identity_is_doctor_clean(tmp_path):
    report = doctor_report(_ws(tmp_path, [_record()], ["verify-iter0.json"]))
    assert report["ok"] is True, report["issues"]
    assert "loop-engineer/evidence@1" in report["schemas_checked"]


@pytest.mark.parametrize("mode", ["basic", "strict"])
def test_self_verified_evidence_fails_doctor(tmp_path, mode):
    if mode == "strict":
        pytest.importorskip("jsonschema")
    report = doctor_report(_ws(tmp_path, [_record(executor="worker-a", by="worker-a")]), mode=mode)
    assert report["ok"] is False and "self_verified_evidence" in _codes(report)


@pytest.mark.parametrize("mode", ["basic", "strict"])
def test_malformed_evidence_record_fails_doctor_rather_than_being_skipped(tmp_path, mode):
    if mode == "strict":
        pytest.importorskip("jsonschema")
    bad = _record()
    bad["verified_by"]["code_digest"] = "NOTHEX"
    report = doctor_report(_ws(tmp_path, [bad]), mode=mode)
    assert report["ok"] is False and "invalid_evidence" in _codes(report)


@pytest.mark.parametrize("mode", ["basic", "strict"])
def test_unparseable_evidence_json_fails_doctor(tmp_path, mode):
    if mode == "strict":
        pytest.importorskip("jsonschema")
    report = doctor_report(_ws(tmp_path, ["{not json"]), mode=mode)
    assert report["ok"] is False


def test_self_verification_detection_survives_case_and_whitespace_evasion(tmp_path):
    report = doctor_report(_ws(tmp_path, [_record(executor=" Worker-A ", by="worker-a")]))
    assert "self_verified_evidence" in _codes(report)


def test_finding_names_the_record_and_the_colliding_identity(tmp_path):
    report = doctor_report(_ws(tmp_path, [_record(executor="worker-a", by="worker-a")]))
    finding = next(i for i in report["issues"] if i["code"] == "self_verified_evidence")
    assert "evidence-iter0.json" in finding["message"] and "worker-a" in finding["message"]


def test_only_the_colliding_record_is_reported(tmp_path):
    """Two records, one collision — exactly one finding, naming the guilty file."""
    target = _ws(tmp_path, [_record(), _record(executor="solo", by="solo")],
                 ["verify-iter0.json", "verify-iter1.json"])
    findings = [i for i in doctor_report(target)["issues"] if i["code"] == "self_verified_evidence"]
    assert len(findings) == 1 and "evidence-iter1.json" in findings[0]["message"]


def test_null_verified_by_is_not_a_finding_in_this_slice(tmp_path):
    report = doctor_report(_ws(tmp_path, [_record(verified_by=None)], ["verify-iter0.json"]))
    assert report["ok"] is True, report["issues"]


def test_a_bundle_whose_record_was_deleted_is_reported(tmp_path):
    """The residue tripwire, mirroring §22's missing_event_store."""
    report = doctor_report(_ws(tmp_path, bundles=["verify-iter5.json"]))
    assert report["ok"] is False and "missing_evidence_record" in _codes(report)


def test_neither_bundle_nor_record_is_clean(tmp_path):
    """The negative control: absent-everything must stay byte-stable."""
    assert "missing_evidence_record" not in _codes(doctor_report(_ws(tmp_path)))


def test_legacy_bundle_names_never_trip_the_orphan_tripwire(tmp_path):
    """Shipped examples use verify-T1.json / verify-T1-iter1.json — not the runner's
    verify-iter<N>.json — and must stay doctor-clean."""
    target = _ws(tmp_path, bundles=["verify-T1.json", "verify-T1-iter1.json"])
    assert "missing_evidence_record" not in _codes(doctor_report(target))


def test_doctor_evidence_scan_writes_nothing(tmp_path):
    target = _ws(tmp_path, [_record()], ["verify-iter0.json"])
    before = _tree(target)
    doctor_report(target)
    assert _tree(target) == before
