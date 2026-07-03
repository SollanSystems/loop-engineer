"""Tests for scripts/metrics.py — FCR / RP derivation, recompute-and-reject, and
the gated baseline (ST1 AC2-AC5). Fixtures build real .loop/ trees under tmp_path
so the command is exercised on evidence, never narration."""

from __future__ import annotations

import json
from pathlib import Path

import metrics

_REPO = Path(__file__).resolve().parent.parent
_EXAMPLE = _REPO / "examples" / "coverage-repair"


# --- fixture builder ----------------------------------------------------------


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")


def _make_loop(
    tmp_path: Path,
    *,
    runlog: str,
    verify: dict[str, dict] | None = None,
    repair: dict[str, dict] | None = None,
    terminal: dict | None = None,
    gate_verdict: dict | None = None,
    receipts: list[dict] | None = None,
) -> Path:
    ws = tmp_path / "ws"
    (ws / ".loop").mkdir(parents=True, exist_ok=True)
    _write(ws / "RUNLOG.md", runlog)
    for name, bundle in (verify or {}).items():
        _write(ws / ".loop" / "artifacts" / name, bundle)
    for name, record in (repair or {}).items():
        _write(ws / ".loop" / "repair" / name, record)
    if terminal is not None:
        _write(ws / ".loop" / "terminal_state.json", terminal)
    if gate_verdict is not None:
        _write(ws / ".loop" / "artifacts" / "holdout-verdict.json", gate_verdict)
    if receipts is not None:
        lines = "\n".join(json.dumps(r) for r in receipts) + "\n"
        _write(ws / ".loop" / "receipts" / "run.jsonl", lines)
    return ws


def _repair_record(before: float, after: float, productive: bool) -> dict:
    return {
        "schema": "loop-engineer/repair@1",
        "iteration_id": "iter-001",
        "attempt": 1,
        "failure_mode": "deterministic-fail",
        "hypothesis": "h",
        "repair_action": "a",
        "verification_before": {"score": before},
        "verification_after": {"score": after},
        "remaining_delta": "none",
        "productive": productive,
    }


# --- recheck_productive (AC2) -------------------------------------------------


def test_recheck_productive_repair_agrees_when_score_improved():
    v = metrics.recheck_productive(_repair_record(0.74, 0.83, True))
    assert v["kind"] == "repair"
    assert v["expected"] is True
    assert v["valid"] is True


def test_recheck_productive_repair_agrees_on_churn():
    v = metrics.recheck_productive(_repair_record(0.80, 0.80, False))
    assert v["expected"] is False
    assert v["valid"] is True


def test_recheck_productive_repair_rejects_disagreement():
    v = metrics.recheck_productive(_repair_record(0.80, 0.80, True))  # stored lies
    assert v["valid"] is False
    assert "disagree" in v["reason"]


def test_recheck_productive_repair_rejects_missing_score():
    rec = _repair_record(0.74, 0.83, True)
    del rec["verification_after"]["score"]
    v = metrics.recheck_productive(rec)
    assert v["valid"] is False
    assert "score" in v["reason"]


def test_recheck_productive_rollout_agrees_on_positive_delta():
    rec = {"id": "c1", "parent": None, "verdict": "ok", "score": 0.9,
           "score_delta": 0.1, "coherent_with_prior_winner": True, "productive": True}
    v = metrics.recheck_productive(rec)
    assert v["kind"] == "rollout"
    assert v["valid"] is True


def test_recheck_productive_rollout_rejects_disagreement():
    rec = {"id": "c1", "parent": None, "verdict": "ok", "score": 0.9,
           "score_delta": 0.0, "coherent_with_prior_winner": True, "productive": True}
    v = metrics.recheck_productive(rec)
    assert v["valid"] is False


def test_recheck_productive_rollout_null_delta_is_not_productive():
    rec = {"id": "c1", "parent": None, "verdict": "ok", "score": None,
           "score_delta": None, "coherent_with_prior_winner": True, "productive": False}
    v = metrics.recheck_productive(rec)
    assert v["expected"] is False
    assert v["valid"] is True


def test_recheck_productive_unknown_shape_is_rejected():
    v = metrics.recheck_productive({"productive": True})
    assert v["kind"] == "unknown"
    assert v["valid"] is False


# --- FCR cross-join (AC3/AC4) -------------------------------------------------


_RUNLOG_ONE_CLAIM = (
    "# RUNLOG\n\n## Iteration 1 — t\n\n### Outcome\n\n`task_passed`\n"
    "- **evidence:** .loop/artifacts/verify-A.json\n"
)


def test_fcr_is_one_when_claim_not_backed_by_green_verify(tmp_path):
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        verify={"verify-A.json": {"task": "A", "outcome": "FAIL", "score": 0.5}},
    )
    sc = metrics.compute_metrics(ws)
    assert sc["iterations_claiming_success"] == 1
    assert sc["false_completions"] == 1
    assert sc["false_completion_rate"] == 1.0


def test_fcr_is_zero_when_claim_backed_by_green_verify(tmp_path):
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        verify={"verify-A.json": {"task": "A", "outcome": "PASS", "score": 1.0}},
    )
    sc = metrics.compute_metrics(ws)
    assert sc["false_completions"] == 0
    assert sc["false_completion_rate"] == 0.0


def test_fcr_unmatched_success_claim_fails_closed(tmp_path):
    # A claim with no verify bundle at all is a false completion (§8 fail-closed).
    ws = _make_loop(tmp_path, runlog=_RUNLOG_ONE_CLAIM)
    sc = metrics.compute_metrics(ws)
    assert sc["false_completions"] == 1
    assert sc["false_completion_rate"] == 1.0


# --- evidence_backed (AC4) ----------------------------------------------------


def test_evidence_backed_false_when_claim_set_but_gate_never_run(tmp_path):
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        verify={"verify-A.json": {"task": "A", "outcome": "PASS", "score": 1.0}},
        terminal={"state": "Succeeded", "iteration_id": 1,
                  "criteria_met": {"1": True}, "false_completion": False,
                  "evidence": [".loop/artifacts/verify-A.json"]},
    )
    sc = metrics.compute_metrics(ws)
    assert sc["evidence_backed"] is False


def test_evidence_backed_true_when_holdout_verdict_present(tmp_path):
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        verify={"verify-A.json": {"task": "A", "outcome": "PASS", "score": 1.0}},
        gate_verdict={"verdict": "Succeeded", "passed_visible": True,
                      "passed_holdout": True, "false_completion": False},
    )
    sc = metrics.compute_metrics(ws)
    assert sc["evidence_backed"] is True
    assert sc["provenance"]["false_completion_rate_holdout"] == 0.0
    assert sc["provenance"]["fcr_methods_agree"] is True


# --- RP (AC2) -----------------------------------------------------------------


def test_rp_is_half_over_one_productive_and_one_churn(tmp_path):
    prod = _repair_record(0.5, 0.8, True)
    prod["iteration_id"] = "iter-001"
    churn = _repair_record(0.8, 0.8, False)
    churn["iteration_id"] = "iter-002"
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        repair={"iter-001.json": prod, "iter-002.json": churn},
    )
    sc = metrics.compute_metrics(ws)
    assert sc["repair_passes"] == 2
    assert sc["productive_repairs"] == 1
    assert sc["repair_productivity"] == 0.5


def test_rp_excludes_a_lying_repair_record(tmp_path):
    honest = _repair_record(0.5, 0.8, True)
    honest["iteration_id"] = "iter-001"
    liar = _repair_record(0.8, 0.8, True)  # churn asserted productive
    liar["iteration_id"] = "iter-002"
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        repair={"iter-001.json": honest, "iter-002.json": liar},
    )
    sc = metrics.compute_metrics(ws)
    assert sc["repair_passes"] == 1  # only the honest one counts
    assert sc["repair_productivity"] == 1.0
    rejected = sc["provenance"]["rejected_records"]
    assert len(rejected) == 1
    assert rejected[0]["record"].endswith("iter-002.json")


# --- determinism (AC3) --------------------------------------------------------


def test_scorecard_is_byte_identical_across_runs(tmp_path):
    prod = _repair_record(0.5, 0.8, True)
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        verify={"verify-A.json": {"task": "A", "outcome": "PASS", "score": 1.0}},
        repair={"iter-001.json": prod},
        gate_verdict={"verdict": "Succeeded", "passed_visible": True,
                      "passed_holdout": True, "false_completion": False},
        receipts=[{"schema": "loop-engineer/receipt@1", "iteration_id": 1,
                   "role": "write", "model": "opus", "outcome": "ok", "cost_usd": 0.4}],
    )
    first = json.dumps(metrics.compute_metrics(ws, loop_label="ws"), indent=2)
    second = json.dumps(metrics.compute_metrics(ws, loop_label="ws"), indent=2)
    assert first == second


def test_cost_per_success_from_receipts(tmp_path):
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        verify={"verify-A.json": {"task": "A", "outcome": "PASS", "score": 1.0}},
        receipts=[{"cost_usd": 0.3}, {"cost_usd": 0.1}],
    )
    sc = metrics.compute_metrics(ws)
    assert sc["cost_per_success_usd"] == 0.4  # 0.4 total / 1 success


# --- baseline gating (AC5) ----------------------------------------------------


def test_baseline_refuses_non_evidence_backed_run_and_writes_nothing(tmp_path):
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        verify={"verify-A.json": {"task": "A", "outcome": "PASS", "score": 1.0}},
    )
    out = tmp_path / "docs" / "metrics-baseline.json"
    rc = metrics.write_baseline(ws, out, loop_label="ws")
    assert rc != 0
    assert not out.exists()


def test_baseline_refuses_when_a_record_is_rejected(tmp_path):
    liar = _repair_record(0.8, 0.8, True)
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        verify={"verify-A.json": {"task": "A", "outcome": "PASS", "score": 1.0}},
        repair={"iter-001.json": liar},
        gate_verdict={"verdict": "Succeeded", "passed_visible": True,
                      "passed_holdout": True, "false_completion": False},
    )
    ok, _sc, reasons = metrics.build_baseline(ws, "ws")
    assert ok is False
    assert any("rejected" in r for r in reasons)


def test_baseline_writes_scorecard_over_gate_backed_run(tmp_path):
    prod = _repair_record(0.5, 0.8, True)
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        verify={"verify-A.json": {"task": "A", "outcome": "PASS", "score": 1.0}},
        repair={"iter-001.json": prod},
        gate_verdict={"verdict": "Succeeded", "passed_visible": True,
                      "passed_holdout": True, "false_completion": False},
    )
    out = tmp_path / "docs" / "metrics-baseline.json"
    rc = metrics.write_baseline(ws, out, loop_label="ws")
    assert rc == 0
    written = json.loads(out.read_text())
    assert written["schema"] == "loop-engineer/metrics@1"
    assert written["baseline"]["source_example"] == "ws"
    assert "inputs" in written["baseline"]


# --- flagship regression (pins the published baseline numbers) ----------------


def test_metrics_on_flagship_example_is_clean_and_evidence_backed():
    sc = metrics.compute_metrics(_EXAMPLE, loop_label="examples/coverage-repair")
    assert sc["false_completion_rate"] == 0.0
    assert sc["repair_productivity"] == 1.0
    assert sc["evidence_backed"] is True
    assert sc["provenance"]["rejected_records"] == []
    assert sc["provenance"]["fcr_methods_agree"] is True
