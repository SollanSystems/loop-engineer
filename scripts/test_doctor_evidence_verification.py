"""Doctor hash-verifies discovered records and compares their policy digest to TASKS.json."""
from __future__ import annotations

import hashlib
import json

import pytest

from loop.contract import doctor_report
from loop.scaffold import scaffold
from loop.verifier import verification_policy_digest

try:                                  # the repo's fallback-mode convention
    import jsonschema                 # noqa: F401
    _HAS_JSONSCHEMA = True
except ImportError:                   # pragma: no cover - exercised in the fallback leg
    _HAS_JSONSCHEMA = False

_MODES = [pytest.param("basic"),
          pytest.param("strict", marks=pytest.mark.skipif(not _HAS_JSONSCHEMA,
                                                          reason="jsonschema not installed"))]


def _codes(report):
    return {issue["code"] for issue in report["issues"]}


_TASK = {"id": "T-1", "title": "t", "status": "pending", "criterion_ref": "C-1",
         "verify": "./scripts/verify-fast.sh", "depends_on": [], "attempts": 0, "evidence": None}


def _ws(tmp_path, *, records, bundle_text='{"outcome": "PASS", "passed": true}', tasks=(_TASK,)):
    target = tmp_path / "workspace"
    scaffold(target)
    (target / "TASKS.json").write_text(json.dumps(
        {"schema": "loop-engineer/tasks@1", "project": "p", "tasks": list(tasks)}), encoding="utf-8")
    # scaffold ships scripts/verify-fast without an extension; _TASK declares the
    # .sh form, and a path-shaped task verify must resolve under the workspace.
    (target / "scripts" / "verify-fast.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (target / ".loop" / "artifacts").mkdir(parents=True, exist_ok=True)
    (target / ".loop" / "artifacts" / "verify-iter1.json").write_text(bundle_text, encoding="utf-8")
    directory = target / ".loop" / "evidence"
    directory.mkdir(parents=True, exist_ok=True)
    for iteration_id, record in records:
        (directory / f"evidence-iter{iteration_id}.json").write_text(
            json.dumps(record), encoding="utf-8")
    return target


def _record(*, iteration_id=1, policy_digest=None, uri=".loop/artifacts/verify-iter1.json",
            sha256=None, task_id="T-1"):
    text = '{"outcome": "PASS", "passed": true}'
    return {
        "schema": "loop-engineer/evidence@1", "id": f"run-1:{iteration_id}:verify",
        "kind": "verify-bundle", "uri": uri,
        "sha256": sha256 or hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "media_type": "application/json", "created_at": "2026-07-25T00:00:00+00:00",
        "produced_by": {"run_id": "run-1", "task_id": task_id, "attempt": 1,
                        "executor": "worker-a"},
        "verified_by": {"by": "ci", "at": "2026-07-25T00:00:00+00:00",
                        "command": "./scripts/verify-fast.sh", "code_digest": None,
                        "code_digest_basis": "path_lookup",
                        "policy_digest": policy_digest or verification_policy_digest(_TASK)},
    }


@pytest.mark.parametrize("mode", _MODES)
def test_a_hash_verified_record_is_clean(tmp_path, mode):
    target = _ws(tmp_path, records=[(1, _record())])
    assert doctor_report(target, mode=mode)["ok"] is True


@pytest.mark.parametrize("mode", _MODES)
def test_a_swapped_bundle_fails_doctor_with_hash_mismatch(tmp_path, mode):
    target = _ws(tmp_path, records=[(1, _record())])
    (target / ".loop" / "artifacts" / "verify-iter1.json").write_text("{}", encoding="utf-8")
    assert "hash_mismatch" in _codes(doctor_report(target, mode=mode))


def test_a_record_whose_uri_is_absent_reports_missing_evidence_path(tmp_path):
    target = _ws(tmp_path, records=[(1, _record(uri=".loop/artifacts/gone.json"))])
    assert "missing_evidence_path" in _codes(doctor_report(target))


def test_a_record_whose_uri_escapes_the_workspace_reports_workspace_escape(tmp_path):
    target = _ws(tmp_path, records=[(1, _record(uri="../escape.json"))])
    assert _codes(doctor_report(target)) & {"workspace_escape", "missing_evidence_path"}


@pytest.mark.parametrize("mode", _MODES)
def test_policy_digest_mismatch_against_the_live_task(tmp_path, mode):
    moved = dict(_TASK, verify="true")
    target = _ws(tmp_path, records=[(1, _record())], tasks=(moved,))
    assert "policy_digest_mismatch" in _codes(doctor_report(target, mode=mode))


def test_policy_digest_agreement_is_silent(tmp_path):
    target = _ws(tmp_path, records=[(1, _record())])
    assert "policy_digest_mismatch" not in _codes(doctor_report(target))


def test_only_the_latest_record_per_task_is_compared(tmp_path):
    stale = _record(iteration_id=1, policy_digest="d" * 64)
    current = _record(iteration_id=2)
    target = _ws(tmp_path, records=[(1, stale), (2, current)])
    assert "policy_digest_mismatch" not in _codes(doctor_report(target))


def test_a_record_naming_an_unknown_task_is_not_compared(tmp_path):
    target = _ws(tmp_path, records=[(1, _record(task_id="T-404", policy_digest="d" * 64))])
    assert "policy_digest_mismatch" not in _codes(doctor_report(target))


def test_a_record_without_a_policy_digest_is_not_compared(tmp_path):
    record = _record()
    record["verified_by"]["policy_digest"] = None
    target = _ws(tmp_path, records=[(1, record)])
    assert "policy_digest_mismatch" not in _codes(doctor_report(target))


def _nan_task():
    """A live entry json.loads accepts but verification_policy_digest cannot canonicalize."""
    return dict(_TASK, criterion_ref=float("nan"))


@pytest.mark.parametrize("mode", _MODES)
def test_a_non_canonicalizable_live_task_fails_closed_in_both_modes(tmp_path, mode):
    """An unrunnable comparison is not an agreement.

    jsonschema mode independently reports the malformed entry as a schema_violation,
    but structural-fallback has no tasks@1 type-check — skipping here left a stale
    goalpost reported by nothing, and doctor answered ok.
    """
    target = _ws(tmp_path, records=[(1, _record(policy_digest="d" * 64))],
                 tasks=(_nan_task(),))
    report = doctor_report(target, mode=mode)
    assert "policy_digest_mismatch" in _codes(report)
    assert report["ok"] is False


def test_a_non_canonicalizable_task_no_record_names_is_not_a_goalpost_finding(tmp_path):
    target = _ws(tmp_path, records=[(1, _record(task_id="T-404"))], tasks=(_nan_task(),))
    assert "policy_digest_mismatch" not in _codes(doctor_report(target))


@pytest.mark.parametrize("mode", _MODES)
def test_evidence_schema_id_still_joins_schemas_checked(tmp_path, mode):
    target = _ws(tmp_path, records=[(1, _record())])
    assert "loop-engineer/evidence@1" in doctor_report(target, mode=mode)["schemas_checked"]
