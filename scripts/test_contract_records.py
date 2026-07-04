"""AC6: validate_contract() validates .loop/repair/*.json and .loop/*.jsonl (and
.loop/receipts/*.jsonl) against their schemas WHEN PRESENT — absence is never an
error, and the shipped example / repo contract still validate clean."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loop.contract import _validate_optional_records, validate_contract  # noqa: E402
from loop.paths import resolve_loop_paths  # noqa: E402


def _valid_repair() -> dict:
    return {
        "schema": "loop-engineer/repair@1",
        "iteration_id": "iter-001",
        "attempt": 1,
        "failure_mode": "deterministic-fail",
        "hypothesis": "h",
        "repair_action": "a",
        "verification_before": {"score": 0.5},
        "verification_after": {"score": 0.9},
        "remaining_delta": "none",
        "productive": True,
    }


def _optional_issues(loop_dir: Path) -> list[dict]:
    paths = resolve_loop_paths(loop_dir)
    issues: list[dict] = []
    _validate_optional_records(paths, "structural-fallback", issues)
    return issues


def test_absent_record_files_are_not_an_error(tmp_path):
    (tmp_path / ".loop").mkdir()
    assert _optional_issues(tmp_path) == []


def test_present_valid_repair_record_passes(tmp_path):
    repair_dir = tmp_path / ".loop" / "repair"
    repair_dir.mkdir(parents=True)
    (repair_dir / "iter-001.json").write_text(json.dumps(_valid_repair()), encoding="utf-8")
    assert _optional_issues(tmp_path) == []


def test_present_repair_record_missing_field_is_flagged(tmp_path):
    repair_dir = tmp_path / ".loop" / "repair"
    repair_dir.mkdir(parents=True)
    bad = _valid_repair()
    del bad["hypothesis"]
    (repair_dir / "iter-001.json").write_text(json.dumps(bad), encoding="utf-8")
    issues = _optional_issues(tmp_path)
    assert any("hypothesis" in i["message"] for i in issues)


def test_present_repair_record_non_numeric_score_is_flagged(tmp_path):
    repair_dir = tmp_path / ".loop" / "repair"
    repair_dir.mkdir(parents=True)
    bad = _valid_repair()
    del bad["verification_after"]["score"]
    (repair_dir / "iter-001.json").write_text(json.dumps(bad), encoding="utf-8")
    issues = _optional_issues(tmp_path)
    assert any("verification_after.score" in i["message"] for i in issues)


def test_present_rollout_jsonl_bad_line_is_flagged(tmp_path):
    loop_dir = tmp_path / ".loop"
    loop_dir.mkdir()
    good = {"id": "c1", "parent": None, "verdict": "ok", "score": 0.9,
            "score_delta": 0.1, "coherent_with_prior_winner": True, "productive": True}
    bad = {"id": "c2"}  # missing the rest of the required rollout fields
    (loop_dir / "rollout.jsonl").write_text(
        json.dumps(good) + "\n" + json.dumps(bad) + "\n", encoding="utf-8"
    )
    issues = _optional_issues(tmp_path)
    assert any("rollout.jsonl" in i["message"] for i in issues)


def test_present_valid_receipt_jsonl_passes(tmp_path):
    receipts = tmp_path / ".loop" / "receipts"
    receipts.mkdir(parents=True)
    rec = {"schema": "loop-engineer/receipt@1", "iteration_id": 1,
           "role": "write", "model": "opus", "outcome": "ok"}
    (receipts / "run.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    assert _optional_issues(tmp_path) == []


def test_schemas_checked_reports_repair_when_a_repair_record_is_validated():
    # P3: schemas_checked must not under-report — a loop with repair records shows
    # the repair schema id, not just the 4 core contract schemas.
    report = validate_contract(ROOT / "examples" / "coverage-repair")
    assert "loop-engineer/repair@1" in report["schemas_checked"]
    assert report["schemas_checked"][:4] == [
        "loop-engineer/manifest@1",
        "loop-engineer/state@1",
        "loop-engineer/tasks@1",
        "loop-engineer/terminal@1",
    ]


def test_schemas_checked_omits_record_schemas_when_no_record_files(tmp_path):
    (tmp_path / ".loop").mkdir()
    (tmp_path / "RUNLOG.md").write_text("# RUNLOG\n", encoding="utf-8")
    report = validate_contract(tmp_path)
    assert report["schemas_checked"] == [
        "loop-engineer/manifest@1",
        "loop-engineer/state@1",
        "loop-engineer/tasks@1",
        "loop-engineer/terminal@1",
    ]


def test_flagship_example_contract_validates_clean_with_repair_record():
    report = validate_contract(ROOT / "examples" / "coverage-repair")
    assert report["ok"] is True, report["issues"]


def test_repo_own_contract_still_validates_clean():
    # The repo's live .loop run-state is gitignored, so a fresh checkout (CI)
    # has none; the live-contract gate is a local/operator check.
    if not (ROOT / ".loop" / "state.json").exists():
        pytest.skip("no live .loop contract in this checkout (gitignored run-state)")
    report = validate_contract(ROOT / ".loop")
    assert report["ok"] is True, report["issues"]
