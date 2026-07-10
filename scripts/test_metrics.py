"""Tests for scripts/metrics.py — FCR / RP derivation, recompute-and-reject, and
the gated baseline (ST1 AC2-AC5). Fixtures build real .loop/ trees under tmp_path
so the command is exercised on evidence, never narration."""

from __future__ import annotations

import json
from pathlib import Path

import metrics

from loop import emit

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


def _holdout_verdict(*, false_completion: bool = False) -> dict:
    """A structurally-valid held-out verdict in ``holdout_gate.decide`` shape —
    per-check visible/holdout arrays plus flags re-derivable from them."""
    holdout_passed = not false_completion
    return {
        "verdict": "FailedUnverifiable" if false_completion else "Succeeded",
        "reason": "fixture",
        "passed_visible": True,
        "passed_holdout": holdout_passed,
        "false_completion": false_completion,
        "visible": [{"id": "unit", "passed": True, "returncode": 0}],
        "holdout": [{"id": "probe", "passed": holdout_passed,
                     "returncode": 0 if holdout_passed else 1}],
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
        gate_verdict=_holdout_verdict(),
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
        gate_verdict=_holdout_verdict(),
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
        gate_verdict=_holdout_verdict(),
    )
    ok, _sc, reasons = metrics.build_baseline(ws, "ws")
    assert ok is False
    assert any("rejected" in r for r in reasons)


def test_baseline_writes_scorecard_over_gate_backed_run(tmp_path):
    prod = _repair_record(0.5, 0.8, True)
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        # The claim's own green evidence (0.8) plus a red pre-repair bundle (0.5)
        # anchor the repair record's before/after scores to real verify evidence.
        verify={"verify-A.json": {"task": "A", "outcome": "PASS", "score": 0.8},
                "verify-before.json": {"task": "A", "outcome": "FAIL", "score": 0.5}},
        repair={"iter-001.json": prod},
        gate_verdict=_holdout_verdict(),
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
    assert sc["provenance"]["unanchored_records"] == []
    assert sc["provenance"]["unrecognized_outcomes"] == []
    assert sc["provenance"]["fcr_methods_agree"] is True


# --- evidence_backed honesty (P1/P2): comment/prose/stub are NOT invocations ---


def test_runlog_prose_mention_of_gate_is_not_evidence(tmp_path):
    # Exploit A: a bare RUNLOG mention (even a negation) is not a gate invocation.
    ws = _make_loop(
        tmp_path,
        runlog="# RUNLOG\n\n## Iteration 1 — t\n\n"
        "- note: we never ran holdout_gate.py here; TODO wire it up.\n",
    )
    assert metrics.compute_metrics(ws)["evidence_backed"] is False


def test_hand_authored_verdict_without_check_arrays_is_not_evidence(tmp_path):
    # Exploit A2: a 4-field stub carries no per-check visible/holdout results a
    # real holdout_gate.decide emits — it is not a gate run.
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        verify={"verify-A.json": {"task": "A", "outcome": "PASS", "score": 1.0}},
        gate_verdict={"verdict": "Succeeded", "passed_visible": True,
                      "passed_holdout": True, "false_completion": False},
    )
    sc = metrics.compute_metrics(ws)
    assert sc["evidence_backed"] is False
    assert sc["provenance"]["holdout_verdicts"] == []
    ok, _sc, _reasons = metrics.build_baseline(ws, "ws")
    assert ok is False


def test_valid_verdict_is_evidence_and_sha256_recorded(tmp_path):
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        verify={"verify-A.json": {"task": "A", "outcome": "PASS", "score": 1.0}},
        gate_verdict=_holdout_verdict(),
    )
    prov = metrics.compute_metrics(ws)["provenance"]
    assert len(prov["holdout_verdicts"]) == 1
    assert len(prov["holdout_verdicts"][0]["sha256"]) == 64


def test_comment_only_gate_line_in_verify_script_is_not_evidence(tmp_path):
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        verify={"verify-A.json": {"task": "A", "outcome": "PASS", "score": 1.0}},
    )
    (ws / "scripts").mkdir()
    (ws / "scripts" / "verify-full").write_text(
        "#!/bin/sh\n# TODO: someday call scripts/holdout_gate.py here\necho PASS\n",
        encoding="utf-8",
    )
    assert metrics.compute_metrics(ws)["evidence_backed"] is False


def test_executed_gate_line_in_verify_script_is_evidence(tmp_path):
    # Path (b) requires the loop's OWN workspace to carry the gate script.
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        verify={"verify-A.json": {"task": "A", "outcome": "PASS", "score": 1.0}},
    )
    (ws / "scripts").mkdir()
    (ws / "scripts" / "holdout_gate.py").write_text("# loop-local gate\n", encoding="utf-8")
    (ws / "scripts" / "verify-full").write_text(
        "#!/bin/sh\npython3 scripts/holdout_gate.py manifest.json\n", encoding="utf-8"
    )
    assert metrics.compute_metrics(ws)["evidence_backed"] is True


def test_gate_script_outside_loop_does_not_confer_evidence(tmp_path):
    # loop-engineer itself ships holdout_gate.py; that must not vacuously satisfy
    # the "gate script exists" clause for a foreign loop that carries none.
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        verify={"verify-A.json": {"task": "A", "outcome": "PASS", "score": 1.0}},
    )
    (ws / "scripts").mkdir()
    (ws / "scripts" / "verify-full").write_text(
        "#!/bin/sh\npython3 scripts/holdout_gate.py manifest.json\n", encoding="utf-8"
    )
    assert metrics.compute_metrics(ws)["evidence_backed"] is False


# --- FCR cross-join laundering (P2) -------------------------------------------


def test_unrelated_green_bundle_does_not_launder_a_red_claimed_task(tmp_path):
    # Exploit F: the claimed task's gate is RED; an unrelated green must not clear it.
    ws = _make_loop(
        tmp_path,
        runlog="# RUNLOG\n\n## Iteration 3 — t\n\n- **outcome:** advanced\n"
        "- refs: .loop/artifacts/verify-T3.json and .loop/artifacts/verify-unrelated.json\n",
        verify={
            "verify-T3.json": {"task": "T3", "outcome": "FAIL", "score": 0.1},
            "verify-unrelated.json": {"task": "T1", "outcome": "PASS", "score": 1.0},
        },
    )
    sc = metrics.compute_metrics(ws)
    assert sc["false_completions"] == 1
    assert sc["false_completion_rate"] == 1.0


def test_honest_intermediate_red_later_repaired_is_not_a_false_completion(tmp_path):
    # The real flagship shape: iteration 1 claims progress (`advanced`) with a
    # green T1 beside an honest red T2; T2 reaches green in a STRICTLY LATER
    # iteration. That is a repaired intermediate, not a laundered completion.
    ws = _make_loop(
        tmp_path,
        runlog="# RUNLOG\n\n## Iteration 1 — t\n\n- **outcome:** advanced\n"
        "- refs: .loop/artifacts/verify-T1.json and .loop/artifacts/verify-T2-iter1.json\n"
        "\n## Iteration 2 — t\n\n- **outcome:** repair_triggered\n"
        "- refs: .loop/artifacts/verify-T2.json\n",
        verify={
            "verify-T1.json": {"task": "T1", "outcome": "PASS", "score": 0.74},
            "verify-T2-iter1.json": {"task": "T2", "outcome": "FAIL", "score": 0.74},
            "verify-T2.json": {"task": "T2", "outcome": "PASS", "score": 0.83},
        },
    )
    assert metrics.compute_metrics(ws)["false_completions"] == 0


# --- success-token allow-list surfacing + vacuous refusal (P2) -----------------


def test_unrecognized_outcome_token_is_surfaced_and_not_a_claim(tmp_path):
    # Exploit B: a synonym escapes the denominator but is surfaced, not silent.
    ws = _make_loop(
        tmp_path,
        runlog="# RUNLOG\n\n## Iteration 1 — t\n\n- **outcome:** shipped\n"
        "- refs: .loop/artifacts/verify-red.json\n",
        verify={"verify-red.json": {"iteration_id": 1, "outcome": "FAIL", "score": 0.0}},
    )
    sc = metrics.compute_metrics(ws)
    assert "shipped" in sc["provenance"]["unrecognized_outcomes"]
    assert sc["iterations_claiming_success"] == 0


def test_baseline_refuses_vacuous_zero_claim_run(tmp_path):
    ws = _make_loop(
        tmp_path,
        runlog="# RUNLOG\n\n## Iteration 1 — t\n\n- **outcome:** shipped\n",
        gate_verdict=_holdout_verdict(),
    )
    ok, _sc, reasons = metrics.build_baseline(ws, "ws")
    assert ok is False
    assert any("claim" in r.lower() for r in reasons)


# --- two-way FCR disagreement refusal (P1) ------------------------------------


def test_baseline_refuses_when_fcr_methods_disagree(tmp_path):
    # A clean deterministic cross-join (fcr_a=0) over a run whose held-out gate
    # flags a false completion (fcr_b=1) must not publish a laundered 0.0.
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        verify={"verify-A.json": {"task": "A", "outcome": "PASS", "score": 1.0}},
        gate_verdict=_holdout_verdict(false_completion=True),
    )
    sc = metrics.compute_metrics(ws)
    assert sc["provenance"]["fcr_methods_agree"] is False
    ok, _sc, reasons = metrics.build_baseline(ws, "ws")
    assert ok is False
    assert any("agree" in r.lower() for r in reasons)


# --- RP anchoring against verify bundles (P2) ---------------------------------


def test_rp_record_with_fabricated_scores_is_rejected_when_bundles_exist(tmp_path):
    # Exploit C: before/after unrelated to any real verify bundle score → rejected.
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        verify={"verify-A.json": {"task": "A", "outcome": "PASS", "score": 0.9}},
        repair={"iter-001.json": _repair_record(0.0, 1.0, True)},
    )
    sc = metrics.compute_metrics(ws)
    rejected = sc["provenance"]["rejected_records"]
    assert any(r["record"].endswith("iter-001.json") for r in rejected)
    assert sc["repair_productivity"] is None


def test_rp_record_anchors_cleanly_against_matching_bundles(tmp_path):
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        verify={
            "verify-before.json": {"task": "T2", "outcome": "FAIL", "score": 0.74},
            "verify-after.json": {"task": "T2", "outcome": "PASS", "score": 0.83},
        },
        repair={"iter-001.json": _repair_record(0.74, 0.83, True)},
    )
    sc = metrics.compute_metrics(ws)
    assert sc["provenance"]["rejected_records"] == []
    assert sc["provenance"]["unanchored_records"] == []
    assert sc["repair_productivity"] == 1.0


# --- round-2 adversarial regressions: outcome classes, verdict-only baseline, ---
# --- task-keyed RP anchoring (re-verify findings) --------------------------------


def test_completion_claim_with_red_bundle_is_false_completion_even_if_later_repaired(tmp_path):
    # Exploits G0/G2/H1: a COMPLETION-class claim (task_passed/succeeded/terminal)
    # over a red gate is a false completion, full stop — a later repair of the
    # same task never excuses it (that escape is progress-class only).
    ws = _make_loop(
        tmp_path,
        runlog="# RUNLOG\n\n## Iteration 1 — t\n\n- **outcome:** succeeded\n"
        "- refs: .loop/artifacts/verify-T1.json and .loop/artifacts/verify-T2-iter1.json\n"
        "\n## Iteration 2 — t\n\n- **outcome:** repair_triggered\n"
        "- refs: .loop/artifacts/verify-T2.json\n",
        verify={
            "verify-T1.json": {"task": "T1", "outcome": "PASS", "score": 0.74},
            "verify-T2-iter1.json": {"task": "T2", "outcome": "FAIL", "score": 0.74},
            "verify-T2.json": {"task": "T2", "outcome": "PASS", "score": 0.83},
        },
    )
    sc = metrics.compute_metrics(ws)
    assert sc["false_completions"] == 1
    assert sc["false_completion_rate"] == 1.0


def test_progress_claim_same_iteration_green_does_not_excuse_its_own_tasks_red(tmp_path):
    # Exploit G3 class: a green sibling of the SAME task in the SAME iteration
    # proves nothing about order (within-iteration chronology is unknowable) —
    # fail closed.
    ws = _make_loop(
        tmp_path,
        runlog="# RUNLOG\n\n## Iteration 1 — t\n\n- **outcome:** advanced\n"
        "- refs: .loop/artifacts/verify-T2-a.json and .loop/artifacts/verify-T2-b.json\n",
        verify={
            "verify-T2-a.json": {"task": "T2", "outcome": "FAIL", "score": 0.74},
            "verify-T2-b.json": {"task": "T2", "outcome": "PASS", "score": 0.83},
        },
    )
    assert metrics.compute_metrics(ws)["false_completions"] == 1


def test_progress_claim_over_regressed_task_is_false_completion(tmp_path):
    # Exploit H2: task green EARLIER, red at claim time — "later reached green"
    # must be order-aware, not a global green-anywhere set.
    ws = _make_loop(
        tmp_path,
        runlog="# RUNLOG\n\n## Iteration 1 — t\n\n- **outcome:** repair_triggered\n"
        "- refs: .loop/artifacts/verify-X-early.json\n"
        "\n## Iteration 2 — t\n\n- **outcome:** advanced\n"
        "- refs: .loop/artifacts/verify-X-late.json\n",
        verify={
            "verify-X-early.json": {"task": "X", "outcome": "PASS", "score": 0.9},
            "verify-X-late.json": {"task": "X", "outcome": "FAIL", "score": 0.4},
        },
    )
    assert metrics.compute_metrics(ws)["false_completions"] == 1


def test_baseline_requires_verdict_artifact_not_verify_script_reference(tmp_path):
    # Exploit N2 pinned: plain-mode evidence_backed via a loop-local gate script +
    # invocation line is a heuristic — it must NEVER qualify a published baseline.
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        verify={"verify-A.json": {"task": "A", "outcome": "PASS", "score": 1.0}},
    )
    (ws / "scripts").mkdir()
    (ws / "scripts" / "holdout_gate.py").write_text("# loop-local gate\n", encoding="utf-8")
    (ws / "scripts" / "verify-full").write_text(
        "#!/bin/sh\npython3 scripts/holdout_gate.py manifest.json\n", encoding="utf-8"
    )
    assert metrics.compute_metrics(ws)["evidence_backed"] is True
    out = tmp_path / "docs" / "metrics-baseline.json"
    rc = metrics.write_baseline(ws, out, loop_label="ws")
    assert rc != 0
    assert not out.exists()
    ok, _sc, reasons = metrics.build_baseline(ws, "ws")
    assert ok is False
    assert any("verdict" in r.lower() for r in reasons)


def test_rp_borrowed_cross_task_scores_are_rejected(tmp_path):
    # Exploit N3: before/after matching free-floating scores from DIFFERENT tasks
    # anchors nothing — only a same-task red→green pair corroborates a repair.
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        verify={
            "verify-zzz.json": {"task": "ZZZ", "outcome": "FAIL", "score": 0.74},
            "verify-A.json": {"task": "A", "outcome": "PASS", "score": 0.83},
        },
        repair={"iter-001.json": _repair_record(0.74, 0.83, True)},
    )
    sc = metrics.compute_metrics(ws)
    rejected = sc["provenance"]["rejected_records"]
    assert any(r["record"].endswith("iter-001.json") for r in rejected)
    assert sc["repair_productivity"] is None


def test_rp_pair_with_green_before_red_is_a_regression_not_an_anchor(tmp_path):
    # Order-aware anchoring: when both bundle iterations are known, the red must
    # precede the green; a green-then-red pair is a regression, not a repair.
    ws = _make_loop(
        tmp_path,
        runlog="# RUNLOG\n\n## Iteration 1 — t\n\n- **outcome:** task_passed\n"
        "- refs: .loop/artifacts/verify-good.json\n"
        "\n## Iteration 2 — t\n\n- **outcome:** repair_triggered\n"
        "- refs: .loop/artifacts/verify-bad.json\n",
        verify={
            "verify-good.json": {"task": "X", "outcome": "PASS", "score": 0.83},
            "verify-bad.json": {"task": "X", "outcome": "FAIL", "score": 0.74},
        },
        repair={"iter-001.json": _repair_record(0.74, 0.83, True)},
    )
    sc = metrics.compute_metrics(ws)
    rejected = sc["provenance"]["rejected_records"]
    assert any(r["record"].endswith("iter-001.json") for r in rejected)


def test_short_outcome_token_is_surfaced(tmp_path):
    # A <=2-char synonym ("ok") must be surfaced, not silently dropped.
    ws = _make_loop(
        tmp_path,
        runlog="# RUNLOG\n\n## Iteration 1 — t\n\n- **outcome:** ok\n",
    )
    sc = metrics.compute_metrics(ws)
    assert "ok" in sc["provenance"]["unrecognized_outcomes"]
    assert sc["iterations_claiming_success"] == 0


def test_baseline_refuses_when_a_counted_rp_record_is_unanchored(tmp_path):
    # A green claim-backing bundle with no numeric score leaves nothing to anchor
    # the repair record's before/after against → unanchored → baseline refuses.
    ws = _make_loop(
        tmp_path,
        runlog=_RUNLOG_ONE_CLAIM,
        verify={"verify-A.json": {"task": "A", "outcome": "PASS"}},
        repair={"iter-001.json": _repair_record(0.5, 0.8, True)},
        gate_verdict=_holdout_verdict(),
    )
    sc = metrics.compute_metrics(ws)
    unanchored = sc["provenance"]["unanchored_records"]
    assert len(unanchored) == 1 and unanchored[0].endswith("iter-001.json")
    ok, _sc, reasons = metrics.build_baseline(ws, "ws")
    assert ok is False
    assert any("anchor" in r.lower() for r in reasons)


def test_every_emitted_outcome_token_is_recognized(tmp_path):
    # Round-trip: every token emit.append_iteration will write must be a token
    # metrics.py recognizes — none may leak into provenance.unrecognized_outcomes.
    # Iterate the real tuple so a new emit outcome can't silently drift unrecognized.
    ws = tmp_path / "ws"
    emit.open_contract(ws)
    # Drop the scaffold-seeded RUNLOG (it carries the {{ITERATION_OUTCOME}} placeholder,
    # issue #40) so append_iteration writes a clean header and only real outcome tokens.
    (ws / "RUNLOG.md").unlink()
    for iteration_id, outcome in enumerate(emit._ITERATION_OUTCOMES, start=1):
        emit.append_iteration(ws, iteration_id=iteration_id, outcome=outcome)
    sc = metrics.compute_metrics(ws)
    assert sc["provenance"]["unrecognized_outcomes"] == []
