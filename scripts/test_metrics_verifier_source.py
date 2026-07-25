"""An injected-callable verdict is a caller's self-report, not gate evidence."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metrics import compute_metrics                                    # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent


def _bundle(source=None, *, green=True, task="T1", iteration_id=1):
    body = {"iteration_id": iteration_id, "task": task,
            "outcome": "PASS" if green else "FAIL", "passed": green, "score": 1.0 if green else 0.0}
    if source is not None:
        body["verifier"] = {"by": "loop.run", "source": source}
    return body


def _repair(*, before, after, iteration_id="iter-001"):
    return {"schema": "loop-engineer/repair@1", "iteration_id": iteration_id, "attempt": 1,
            "failure_mode": "deterministic-fail", "hypothesis": "h", "repair_action": "a",
            "verification_before": {"verify_full": "FAIL", "metric": "score",
                                    "failing": ["x"], "score": before},
            "verification_after": {"verify_full": "PASS", "metric": "score",
                                   "failing": [], "score": after},
            "remaining_delta": "none", "productive": True}


def _ws(tmp_path, bundles, repairs=()):
    target = tmp_path / "workspace"
    (target / ".loop" / "artifacts").mkdir(parents=True, exist_ok=True)
    (target / "RUNLOG.md").write_text(
        "# RUNLOG\n\n## Iteration 1 — 2026-07-25\n\n### Outcome\n\n`task_passed`\n",
        encoding="utf-8")
    (target / ".loop" / "state.json").write_text(json.dumps(
        {"schema": "loop-engineer/state@1", "state": "execute-task", "iteration_id": 1,
         "terminal_state": None}), encoding="utf-8")
    for name, body in bundles:
        (target / ".loop" / "artifacts" / name).write_text(json.dumps(body), encoding="utf-8")
    if repairs:
        (target / ".loop" / "repair").mkdir(parents=True, exist_ok=True)
        for name, body in repairs:
            (target / ".loop" / "repair" / name).write_text(json.dumps(body), encoding="utf-8")
    return target


def test_a_declared_command_bundle_is_gate_evidence(tmp_path):
    target = _ws(tmp_path, [("verify-iter1.json", _bundle("declared_command"))])
    assert compute_metrics(target)["false_completion_rate"] == 0.0


def test_an_injected_callable_bundle_is_not_gate_evidence(tmp_path):
    target = _ws(tmp_path, [("verify-iter1.json", _bundle("injected_callable"))])
    assert compute_metrics(target)["provenance"]["injected_verifier_bundles"] == ["verify-iter1.json"]


def test_an_injected_only_claim_is_a_false_completion(tmp_path):
    target = _ws(tmp_path, [("verify-iter1.json", _bundle("injected_callable"))])
    assert compute_metrics(target)["false_completion_rate"] == 1.0


def test_a_legacy_bundle_without_a_verifier_block_still_counts(tmp_path):
    target = _ws(tmp_path, [("verify-iter1.json", _bundle(None))])
    metrics = compute_metrics(target)
    assert metrics["false_completion_rate"] == 0.0
    assert metrics["provenance"]["injected_verifier_bundles"] == []


def test_excluded_bundles_are_named_under_provenance(tmp_path):
    target = _ws(tmp_path, [("verify-iter1.json", _bundle("injected_callable")),
                            ("verify-iter2.json", _bundle("declared_command", iteration_id=1))])
    assert compute_metrics(target)["provenance"]["injected_verifier_bundles"] == ["verify-iter1.json"]


def test_injected_bundles_do_not_anchor_a_repair(tmp_path):
    """An entirely self-reported red-to-green pair must not corroborate a repair.

    The repair record is load-bearing: without one on disk, ``repair_productivity``
    is ``None`` for the unrelated reason that nothing was validated, and the test
    passes against unchanged code. With one, the pair anchors before this change
    and cannot after it.

    It deliberately does not claim more than it proves. An unanchored record still
    counts toward plain-mode ``repair_productivity``; only ``--baseline`` refuses.
    """
    target = _ws(tmp_path,
                 [("verify-iter1.json", _bundle("injected_callable", green=False)),
                  ("verify-iter2.json", _bundle("injected_callable"))],
                 repairs=[("iter-001.json", _repair(before=0.0, after=1.0))])
    assert compute_metrics(target)["provenance"]["unanchored_records"] == [
        ".loop/repair/iter-001.json"]


def test_the_shipped_examples_keep_their_published_metrics():
    metrics = compute_metrics(_ROOT / "examples" / "flaky-test-triage")
    assert metrics["false_completion_rate"] == 0.0
    assert metrics["repair_productivity"] == 1.0
