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
    assert report["recommendation"] in {"replan", "revert", "approval", "terminate"}
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
    assert report["recommendation"] in {"replan", "revert", "approval", "terminate"}
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
    assert report["recommendation"] in {"replan", "revert", "approval", "terminate"}
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
    assert rc == 0
