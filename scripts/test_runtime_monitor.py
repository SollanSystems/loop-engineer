# scripts/test_runtime_monitor.py
import importlib.util
import json
import pathlib

_spec = importlib.util.spec_from_file_location(
    "runtime_monitor", pathlib.Path(__file__).parent / "runtime_monitor.py"
)
runtime_monitor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runtime_monitor)


def _write_loop(tmp_path, state: dict, runlog: str) -> pathlib.Path:
    loop_dir = tmp_path / ".loop"
    loop_dir.mkdir()
    (loop_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    (loop_dir / "RUNLOG.md").write_text(runlog, encoding="utf-8")
    return loop_dir


def _runlog(rows) -> str:
    lines = ["# RUNLOG", ""]
    for it, task, score in rows:
        lines.append(
            f"- iter {it}: active_task={task} verify=PASS best_score={score}"
        )
    return "\n".join(lines) + "\n"


def test_stall_flagged_when_same_task_no_progress(tmp_path):
    # Arrange: same active_task across 4 iterations, best_score never moves.
    state = {"active_task": "M2", "best_score": 0.5, "iteration_id": "4"}
    runlog = _runlog(
        [(1, "M2", 0.5), (2, "M2", 0.5), (3, "M2", 0.5), (4, "M2", 0.5)]
    )
    loop_dir = _write_loop(tmp_path, state, runlog)

    # Act
    report = runtime_monitor.health_report(loop_dir)

    # Assert
    assert report["stalled"] is True
    assert report["recommendation"] == "replan"
    assert report["evidence"]


def test_repair_churn_flagged_when_repairs_dont_improve_score(tmp_path):
    # Arrange: repeated repair attempts, score flat/declining.
    state = {"active_task": "M3", "best_score": 0.6, "iteration_id": "5"}
    runlog = "\n".join(
        [
            "# RUNLOG",
            "",
            "- iter 1: active_task=M3 verify=FAIL best_score=0.6 repair attempt=1 productive=false",
            "- iter 2: active_task=M3 verify=FAIL best_score=0.6 repair attempt=2 productive=false",
            "- iter 3: active_task=M3 verify=FAIL best_score=0.6 repair attempt=3 productive=false",
        ]
    ) + "\n"
    loop_dir = _write_loop(tmp_path, state, runlog)

    # Act
    report = runtime_monitor.health_report(loop_dir)

    # Assert
    assert report["repair_churn"] is True
    assert report["recommendation"] == "revert"
    assert report["evidence"]


def test_budget_overrun_flagged_when_budget_exhausted(tmp_path):
    # Arrange: budget_remaining numerically exhausted.
    state = {
        "active_task": "M4",
        "best_score": 0.7,
        "iteration_id": "9",
        "budget_remaining": {"iterations": 0, "cost": 0},
    }
    runlog = _runlog([(i, "M4", 0.7) for i in range(1, 10)])
    loop_dir = _write_loop(tmp_path, state, runlog)

    # Act
    report = runtime_monitor.health_report(loop_dir)

    # Assert
    assert report["budget_overrun"] is True
    assert report["recommendation"] == "approval"
    assert report["evidence"]


def test_healthy_loop_flags_nothing(tmp_path):
    # Arrange: each iteration advances the task and improves the score.
    state = {
        "active_task": "M5",
        "best_score": 0.95,
        "iteration_id": "4",
        "budget_remaining": {"iterations": 6, "cost": 100},
    }
    runlog = _runlog(
        [(1, "M1", 0.4), (2, "M2", 0.6), (3, "M3", 0.8), (4, "M5", 0.95)]
    )
    loop_dir = _write_loop(tmp_path, state, runlog)

    # Act
    report = runtime_monitor.health_report(loop_dir)

    # Assert
    assert report["stalled"] is False
    assert report["repair_churn"] is False
    assert report["budget_overrun"] is False
    assert report["recommendation"] == "continue"


def test_cli_emits_json(tmp_path, capsys):
    # Arrange
    state = {"active_task": "M2", "best_score": 0.5, "iteration_id": "4"}
    runlog = _runlog(
        [(1, "M2", 0.5), (2, "M2", 0.5), (3, "M2", 0.5), (4, "M2", 0.5)]
    )
    loop_dir = _write_loop(tmp_path, state, runlog)

    # Act
    rc = runtime_monitor.main([str(loop_dir)])
    out = capsys.readouterr().out

    # Assert
    parsed = json.loads(out)
    assert parsed["stalled"] is True
    # A stalled loop recommends intervention (replan) -> nonzero exit (item 8).
    assert rc == 1


def _line(it, task, score_text):
    return f"- iter {it}: active_task={task} verify=PASS best_score={score_text}"


def test_score_parse_scientific_notation(tmp_path):
    # 1e-3 must parse to 0.001, not stop at the 'e' and read as 1.0.
    state = {"active_task": "M2", "best_score": 0.001, "iteration_id": "3"}
    runlog = (
        "\n".join(
            ["# RUNLOG", "", _line(1, "M2", "1e-3"), _line(2, "M2", "1e-3"), _line(3, "M2", "1e-3")]
        )
        + "\n"
    )
    loop_dir = _write_loop(tmp_path, state, runlog)

    rows = runtime_monitor._parse_runlog((loop_dir / "RUNLOG.md").read_text(encoding="utf-8"))

    assert [r["score"] for r in rows] == [0.001, 0.001, 0.001]


def test_score_parse_negative(tmp_path):
    # -0.5 must keep its sign, not drop the minus and read as +0.5.
    state = {"active_task": "M2", "best_score": -0.5, "iteration_id": "1"}
    runlog = "\n".join(["# RUNLOG", "", _line(1, "M2", "-0.5")]) + "\n"
    loop_dir = _write_loop(tmp_path, state, runlog)

    rows = runtime_monitor._parse_runlog((loop_dir / "RUNLOG.md").read_text(encoding="utf-8"))

    assert [r["score"] for r in rows] == [-0.5]


def test_score_parse_malformed_does_not_crash(tmp_path):
    # 1.2.3 is not a float — the parser must fail safe (skip the row), never crash.
    state = {"active_task": "M2", "best_score": 0.5, "iteration_id": "2"}
    runlog = (
        "\n".join(["# RUNLOG", "", _line(1, "M2", "1.2.3"), _line(2, "M2", "0.5")]) + "\n"
    )
    loop_dir = _write_loop(tmp_path, state, runlog)

    # Must not raise.
    report = runtime_monitor.health_report(loop_dir)

    # The malformed row is dropped; the valid 0.5 row survives.
    assert report["iterations_observed"] == 1


def test_health_report_resolves_root_runlog_when_called_with_loop_dir(tmp_path):
    # Arrange — repo-OS keeps RUNLOG.md at workspace root, while state.json lives
    # under .loop/. The monitor used to require .loop/RUNLOG.md and failed on the
    # canonical/example layout.
    workspace = tmp_path / "workspace"
    loop_dir = workspace / ".loop"
    loop_dir.mkdir(parents=True)
    (loop_dir / "state.json").write_text(
        json.dumps({"active_task": "T2", "best_score": 0.5, "iteration_id": 3}),
        encoding="utf-8",
    )
    (workspace / "RUNLOG.md").write_text(
        _runlog([(1, "T2", 0.5), (2, "T2", 0.5), (3, "T2", 0.5)]),
        encoding="utf-8",
    )

    # Act
    report = runtime_monitor.health_report(loop_dir)

    # Assert
    assert report["iterations_observed"] == 3
    assert report["stalled"] is True


def test_cross_task_repair_attempts_do_not_count_as_churn(tmp_path):
    # Arrange — three flat, unproductive attempts across different tasks are not
    # repair churn for one task and must not recommend revert.
    state = {"active_task": "T3", "best_score": 0.6, "iteration_id": "3"}
    runlog = "\n".join(
        [
            "# RUNLOG",
            "",
            "- iter 1: active_task=T1 verify=FAIL best_score=0.6 repair attempt=1 productive=false",
            "- iter 2: active_task=T2 verify=FAIL best_score=0.6 repair attempt=1 productive=false",
            "- iter 3: active_task=T3 verify=FAIL best_score=0.6 repair attempt=1 productive=false",
        ]
    ) + "\n"
    loop_dir = _write_loop(tmp_path, state, runlog)

    # Act
    report = runtime_monitor.health_report(loop_dir)

    # Assert
    assert report["repair_churn"] is False
    assert report["recommendation"] != "revert"


def test_missing_loop_state_returns_structured_error(tmp_path):
    # Arrange
    loop_dir = tmp_path / ".loop"
    loop_dir.mkdir()

    # Act
    report = runtime_monitor.health_report(loop_dir)

    # Assert — partial loop state is an actionable report, not a traceback.
    assert report["status"] == "error"
    assert report["error"] == "missing_loop_state"
    assert "state.json" in report["missing"]
    assert report["recommendation"] == "replan"


# --- dogfood regressions (monitor on real loops, v0.3.4) -------------------


def test_terminal_loop_is_not_told_to_continue(tmp_path):
    # F5: health_report never read terminal_state, so a finished loop
    # (RevenueOS FailedBlocked, the suite's own .loop Succeeded) got
    # recommendation="continue". A monitor must not advise continuing a
    # loop that has already reached a terminal state.
    state = {
        "active_task": None,
        "state": "terminal",
        "terminal_state": "FailedBlocked",
        "iteration_id": 7,
    }
    runlog = _runlog([(1, "T1", 0.5)])
    loop_dir = _write_loop(tmp_path, state, runlog)

    report = runtime_monitor.health_report(loop_dir)

    assert report["recommendation"] != "continue"
    assert report.get("terminal_state") == "FailedBlocked"


def test_unparseable_prose_runlog_is_not_reported_healthy(tmp_path):
    # F6: real loop-run RUNLOGs are prose ('## Iteration N', '- **active_task:**
    # `T1`'), which _ITER_RE does not match -> 0 rows. The monitor must NOT then
    # return the benign ok/continue/[] that is byte-identical to a healthy loop;
    # stall/repair-churn detection is silently inert on every real RUNLOG.
    state = {
        "active_task": "T2",
        "state": "execute",
        "iteration_id": 3,
        "best_score": 0.8,
    }
    runlog = (
        "# RUNLOG\n\n"
        "## Iteration 1\n"
        "- **state:** execute-task -> verify\n"
        "- **active_task:** `T1` -- do the thing\n"
        "- **score:** line_coverage 0.61 -> 0.74\n\n"
        "## Iteration 2\n"
        "- **active_task:** `T2`\n"
        "- **score:** 0.80\n"
    )
    loop_dir = _write_loop(tmp_path, state, runlog)

    report = runtime_monitor.health_report(loop_dir)

    assert report["iterations_observed"] == 0
    assert report["recommendation"] != "continue"
    assert report["status"] != "ok"
    assert report["evidence"]


def test_documented_cli_by_path_resolves_dotloop_runlog(tmp_path):
    # Regression: the runtime-monitor skill documents
    # `python3 scripts/runtime_monitor.py <loop>`. Invoked that way, sys.path[0]
    # is scripts/ — NOT the repo root — so `from loop.paths import ...` would
    # fall back to a degraded resolver that only looks for a root RUNLOG.md and
    # misses the canonical `.loop/RUNLOG.md` layout (returning "missing
    # RUNLOG.md"). The script must self-bootstrap the repo root so the documented
    # invocation uses the real dual-location resolver. Exec by path with
    # PYTHONPATH scrubbed and a neutral cwd to reproduce the real call.
    import os
    import subprocess
    import sys

    state = {"active_task": "M2", "best_score": 0.5, "iteration_id": "4"}
    _write_loop(
        tmp_path, state, _runlog([(i, "M2", 0.5) for i in range(1, 5)])
    )

    script = pathlib.Path(__file__).parent / "runtime_monitor.py"
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [sys.executable, str(script), str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=env,
    )

    # The loop is stalled, so the CLI exits 1 (intervention) rather than crashing
    # (a path-resolution failure would give a traceback + non-JSON stdout).
    assert proc.returncode == 1, proc.stderr
    report = json.loads(proc.stdout)
    assert report["status"] == "ok", report
    assert report["iterations_observed"] == 4, report
    assert report["stalled"] is True, report


# --- M4-CLI item 8: explicit CLI exit codes per outcome ---------------------


def test_cli_exit_zero_when_healthy(tmp_path):
    state = {
        "active_task": "M5",
        "best_score": 0.95,
        "iteration_id": "4",
        "budget_remaining": {"iterations": 6, "cost": 100},
    }
    runlog = _runlog([(1, "M1", 0.4), (2, "M2", 0.6), (3, "M3", 0.8), (4, "M5", 0.95)])
    loop_dir = _write_loop(tmp_path, state, runlog)

    assert runtime_monitor.main([str(loop_dir)]) == 0


def test_cli_exit_one_when_stalled(tmp_path):
    state = {"active_task": "M2", "best_score": 0.5, "iteration_id": "4"}
    runlog = _runlog([(1, "M2", 0.5), (2, "M2", 0.5), (3, "M2", 0.5), (4, "M2", 0.5)])
    loop_dir = _write_loop(tmp_path, state, runlog)

    # A loop that needs intervention (replan) must not exit 0.
    assert runtime_monitor.main([str(loop_dir)]) == 1


def test_cli_exit_one_when_repair_churn(tmp_path):
    state = {"active_task": "M3", "best_score": 0.6, "iteration_id": "5"}
    runlog = "\n".join(
        [
            "# RUNLOG",
            "",
            "- iter 1: active_task=M3 verify=FAIL best_score=0.6 repair attempt=1 productive=false",
            "- iter 2: active_task=M3 verify=FAIL best_score=0.6 repair attempt=2 productive=false",
            "- iter 3: active_task=M3 verify=FAIL best_score=0.6 repair attempt=3 productive=false",
        ]
    ) + "\n"
    loop_dir = _write_loop(tmp_path, state, runlog)

    assert runtime_monitor.main([str(loop_dir)]) == 1


def test_cli_exit_one_when_budget_overrun(tmp_path):
    state = {
        "active_task": "M4",
        "best_score": 0.7,
        "iteration_id": "9",
        "budget_remaining": {"iterations": 0, "cost": 0},
    }
    runlog = _runlog([(i, "M4", 0.7) for i in range(1, 10)])
    loop_dir = _write_loop(tmp_path, state, runlog)

    assert runtime_monitor.main([str(loop_dir)]) == 1


def test_cli_exit_two_when_state_missing(tmp_path):
    loop_dir = tmp_path / ".loop"
    loop_dir.mkdir()

    # A precondition/operational error (no state.json) is distinct from an
    # intervention recommendation.
    assert runtime_monitor.main([str(loop_dir)]) == 2


def test_cli_exit_one_when_runlog_unparseable(tmp_path):
    state = {"active_task": "T2", "state": "execute", "iteration_id": 3, "best_score": 0.8}
    runlog = (
        "# RUNLOG\n\n"
        "## Iteration 1\n"
        "- **active_task:** `T1`\n"
        "- **score:** 0.61\n"
    )
    loop_dir = _write_loop(tmp_path, state, runlog)

    assert runtime_monitor.main([str(loop_dir)]) == 1


def test_cli_exit_zero_when_terminal(tmp_path):
    state = {
        "active_task": None,
        "state": "terminal",
        "terminal_state": "Succeeded",
        "iteration_id": 7,
    }
    runlog = _runlog([(1, "T1", 0.5)])
    loop_dir = _write_loop(tmp_path, state, runlog)

    # A finished loop is a clean exit, not an intervention.
    assert runtime_monitor.main([str(loop_dir)]) == 0
