"""A host-side supervisor around a ruflo swarm, whose only path to a completion
claim is a real acceptance gate.

ruflo has no swarm-terminal callback and no Python API: `ruflo hive-mind spawn
"<objective>" --claude` spawns the Claude Code CLI as the swarm's body, blocks
until that child exits, and maps `exit 0` to success. That exit code is the
swarm's SELF-report, and so is everything in the `sparc-gates` memory namespace.
This supervisor replaces both with one gate the swarm never saw: the withheld
holdout split (`holdout_gate.decide`) plus the trajectory sweep
(`anticheat_scan.scan`), projected through `to_terminal_state` and recorded by
`loop.emit` — which refuses a dishonest `Succeeded` before anything hits disk.

    python swarm_example.py <fresh-workspace-dir> [flags]

      --sabotage-holdout          work product passes the visible check and
                                  fails the withheld one -> FailedUnverifiable
                                  with false_completion: true
      --simulate-interrupt        the operator-interrupt path, deterministically
      --declare-unmapped-criterion  the swarm declares an AC no check covers
                                  -> FailedSpecGap
      --live                      really invoke ruflo (needs Node, the `claude`
                                  binary, credentials and model spend)

By default the swarm is REPLAYED from the committed `fixture/` recording, so
this runs offline. Only the swarm is recorded: the gate, the projection, the
emit writes, `loop doctor` and `loop metrics` all execute for real.
"""

from __future__ import annotations

import json
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from loop import emit
from loop._resources import tools_dir
from loop.integrations import EngineOutcome, to_terminal_state

sys.path.insert(0, str(tools_dir()))
import anticheat_scan  # noqa: E402
import holdout_gate  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixture"
RUFLO_VERSION = "3.32.9"
OBJECTIVE = (
    "collapse duplicate contacts on a normalized (email, phone) key, keep the "
    "first-seen row, and log every dropped row with its source line"
)
# The one blocking verb the supervisor drives. `ruflo verify` is deliberately
# absent: it checks the SHA-256/Ed25519 integrity of the INSTALLED artifact, not
# the run, so it can never stand in for an acceptance gate.
LIVE_COMMAND = ["npx", f"ruflo@{RUFLO_VERSION}", "hive-mind", "spawn",
                OBJECTIVE, "--claude", "--non-interactive"]

# The swarm's terminal states as ruflo records them in .swarm/state.json.
_SETTLED_SWARM_STATUS = {"ready", "initialized", "stopped"}

_interrupted = False


def _on_sigint(_signum, _frame) -> None:
    global _interrupted
    _interrupted = True


def install_interrupt_handler() -> None:
    """ruflo's own SIGINT path prints "Pausing session" and calls
    `process.exit(0)` — an interrupted run is indistinguishable from a
    successful one by exit code. The supervisor therefore records the interrupt
    itself; `human_abort` is never inferred from ruflo."""
    signal.signal(signal.SIGINT, _on_sigint)


def mark_interrupted() -> None:
    """Deterministic stand-in for a real Ctrl-C, for the demo and the tests."""
    global _interrupted
    _interrupted = True


@dataclass(frozen=True)
class SwarmRun:
    """What the supervisor knows about the run — never what the swarm claims."""

    returncode: int
    mode: str
    human_abort: bool = False
    budget_exhausted: bool = False


def replay_swarm(workspace: Path, *, sabotage: bool = False,
                 unmapped_criterion: bool = False, fixture: Path = FIXTURE) -> SwarmRun:
    """Materialize the recorded run directory, then apply the requested demo."""
    shutil.copytree(fixture, workspace, dirs_exist_ok=True)
    if sabotage:
        # The work product still SAYS 41 unique rows (the visible claim), but the
        # dropped-row log the withheld check reads is truncated.
        log = workspace / "dedupe.log"
        kept = log.read_text(encoding="utf-8").splitlines()[:3]
        log.write_text("\n".join(kept) + "\n", encoding="utf-8")
    if unmapped_criterion:
        _declare_extra_criterion(workspace)
    return SwarmRun(returncode=0, mode="replay", human_abort=_interrupted)


def run_swarm_live(workspace: Path) -> SwarmRun:
    """Drive the real CLI. It blocks until the Claude Code child exits, and its
    handler maps `exit 0` to success — which is exactly the claim the gate
    downstream replaces."""
    workspace.mkdir(parents=True, exist_ok=True)
    install_interrupt_handler()
    proc = subprocess.run(LIVE_COMMAND, cwd=workspace, text=True)
    subprocess.run(
        ["npx", f"ruflo@{RUFLO_VERSION}", "memory", "export", "-o", ".swarm/memory-export.json"],
        cwd=workspace, text=True, check=False,
    )
    return SwarmRun(returncode=proc.returncode, mode="live", human_abort=_interrupted)


def _declare_extra_criterion(workspace: Path) -> None:
    path = workspace / ".swarm" / "memory-export.json"
    export = json.loads(path.read_text(encoding="utf-8"))
    for entry in export["entries"]:
        if entry["namespace"] == "sparc-phases" and entry["key"].startswith("spec-"):
            spec = json.loads(entry["value"])
            spec["acceptanceCriteria"].append(
                "AC-4: Given a contact with no phone, when it imports, then it is retained once"
            )
            entry["value"] = json.dumps(spec)
            break
    path.write_text(json.dumps(export, indent=2) + "\n", encoding="utf-8")


# --- observation: everything readable WITHOUT touching ruflo -----------------


def observe(workspace: Path) -> dict:
    """Read the run's documented JSON surfaces. The authoritative state lives in
    binary SQLite (`.swarm/memory.db`, `.hive-mind/hive.db`); those are never
    parsed — `ruflo memory export` is the supported serialization."""
    swarm = Path(workspace) / ".swarm"
    return {
        "state": json.loads((swarm / "state.json").read_text(encoding="utf-8")),
        "tasks": [json.loads(p.read_text(encoding="utf-8"))
                  for p in sorted((swarm / "tasks").glob("*.json"))],
        "agents": [json.loads(p.read_text(encoding="utf-8"))
                   for p in sorted((swarm / "agents").glob("*.json"))],
        "coordination": [json.loads(p.read_text(encoding="utf-8"))
                         for p in sorted((swarm / "coordination").glob("*.json"))],
        "export": json.loads((swarm / "memory-export.json").read_text(encoding="utf-8")),
    }


def declared_criteria(export: dict) -> list[str]:
    """The acceptance-criteria ids the swarm itself declared, read as a
    VOCABULARY only. Their truth is decided by the holdout gate below."""
    for entry in export["entries"]:
        if entry["namespace"] == "sparc-phases" and entry["key"].startswith("spec-"):
            spec = json.loads(entry["value"])
            return [ac.split(":", 1)[0].strip() for ac in spec.get("acceptanceCriteria", [])]
    return []


def swarm_self_report(export: dict) -> dict:
    """The `sparc-gates` row — the swarm grading its own homework. Surfaced so
    the contract records what was claimed, never used to decide the terminal."""
    for entry in export["entries"]:
        if entry["namespace"] == "sparc-gates":
            gates = json.loads(entry["value"]).get("gates", [])
            completion = next((g for g in gates if g.get("name") == "completion"), {})
            return {
                "all_gates_pass": bool(gates) and all(g.get("result") == "pass" for g in gates),
                "truth_score": completion.get("truthScore"),
                "source": f"{entry['namespace']}/{entry['key']}",
            }
    return {"all_gates_pass": False, "truth_score": None, "source": None}


def agent_trails(obs: dict) -> list[str]:
    """The issue's "agent trails": every path the agents recorded touching, plus
    the coordination rows. ruflo exposes no merged diff, so a live supervisor
    passes its own `git diff` as `diff_text`."""
    trails: list[str] = []
    for agent in obs["agents"]:
        trails.extend(agent.get("touchedPaths", []))
    trails.extend(f"consensus:{row.get('round')}" for row in obs["coordination"])
    return trails


# --- the gate the swarm never saw -------------------------------------------


def visible_checks(workspace: Path) -> list[dict]:
    """What the swarm could see while it worked — its own report claim."""
    report = Path(workspace) / "dedupe-report.json"
    claim = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else {}
    return [
        {"id": "report-exists", "passed": report.is_file()},
        {"id": "report-claims-dedupe", "passed": claim.get("unique_rows") == 41},
    ]


def holdout_checks(workspace: Path) -> list[dict]:
    """Withheld until terminal verification, one per declared criterion."""
    ws = Path(workspace)
    report_path, log_path = ws / "dedupe-report.json", ws / "dedupe.log"
    claim = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    log_lines = [line for line in log_path.read_text(encoding="utf-8").splitlines()
                 if line.strip()] if log_path.is_file() else []
    dropped = claim.get("dropped_rows")
    return [
        {"id": "AC-1", "passed": claim.get("input_rows") == 57
         and claim.get("unique_rows") == 41
         and dropped == 16},
        {"id": "AC-2", "passed": claim.get("second_run_inserted") == 0},
        {"id": "AC-3", "passed": len(log_lines) == dropped
         and all(":" in line.split(" ", 1)[0] for line in log_lines)},
    ]


def certify(workspace: Path, run: SwarmRun) -> dict:
    ws = Path(workspace)
    obs = observe(ws)

    gate = holdout_gate.decide(visible_checks(ws), holdout_checks(ws))
    ac = anticheat_scan.scan(diff_text="", trajectory=agent_trails(obs))

    proven = {check["id"]: check["passed"] for check in gate["holdout"]}
    criteria_met = {cid: proven.get(cid) for cid in declared_criteria(obs["export"])}

    art_dir = ws / ".loop" / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "holdout-verdict.json").write_text(
        json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    (art_dir / "swarm-observation.json").write_text(
        json.dumps({
            "mode": run.mode,
            "returncode": run.returncode,
            "human_abort": run.human_abort,
            "swarm_status": obs["state"]["status"],
            "task_status": [t["status"] for t in obs["tasks"]],
            "agents": [a["id"] for a in obs["agents"]],
            "trails": agent_trails(obs),
            "swarm_self_report": swarm_self_report(obs["export"]),
        }, indent=2) + "\n", encoding="utf-8")
    bundle = {
        "task": "T1",
        "verify": "supervisor gate — holdout_gate.decide over visible+withheld swarm output",
        "outcome": "PASS" if gate["verdict"] == "Succeeded" else "FAIL",
        "iteration_id": 1,
        "criteria": {cid: value is True for cid, value in criteria_met.items()},
    }
    (art_dir / "verify-T1.json").write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")

    completed = [t for t in obs["tasks"] if t["status"] in {"completed", "done"}]
    terminal = to_terminal_state(
        outcome=EngineOutcome(
            reached_end=run.returncode == 0
            and obs["state"]["status"] in _SETTLED_SWARM_STATUS,
            external_error=None if run.returncode == 0 or completed
            else f"ruflo exited {run.returncode} with no completed tasks",
            budget_exhausted=run.budget_exhausted,
            human_abort=run.human_abort,
            artifacts=[".loop/artifacts/verify-T1.json",
                       ".loop/artifacts/holdout-verdict.json",
                       ".loop/artifacts/swarm-observation.json"],
        ),
        gate_verdict=gate, anticheat=ac, criteria_met=criteria_met,
    )

    passed = terminal["state"] == "Succeeded"
    emit.append_iteration(
        ws, iteration_id=1, outcome="task_passed" if passed else "task_failed", task_id="T1",
        actions=[f"supervised ruflo hive-mind spawn ({run.mode} mode)",
                 "read .swarm/ state, tasks, agents, coordination and the memory export",
                 "ran holdout_gate.decide + anticheat_scan.scan over the swarm's output"],
        verify_cmd="holdout_gate.decide(visible, holdout)", verify_outcome=gate["verdict"],
        notes="verify bundle: verify-T1.json; gate verdict: holdout-verdict.json; "
              "swarm self-report recorded in swarm-observation.json (not trusted)",
    )
    emit.append_receipt(ws, iteration_id=1, role="orchestrate",
                        model="deterministic-demo", outcome="ok")
    emit.terminate(
        ws, state=terminal["state"], criteria_met=terminal["criteria_met"],
        evidence=terminal["evidence"], false_completion=terminal["false_completion"],
        reason=terminal["reason"], iteration_id=1,
    )
    return terminal


def main(workspace: str, *, live: bool, sabotage: bool,
         unmapped_criterion: bool, simulate_interrupt: bool) -> int:
    ws = Path(workspace)
    if simulate_interrupt:
        mark_interrupted()
    run = (run_swarm_live(ws) if live
           else replay_swarm(ws, sabotage=sabotage, unmapped_criterion=unmapped_criterion))
    emit.open_contract(ws)
    terminal = certify(ws, run)
    print(f"terminal: {terminal['state']} — validate: python3 -m loop doctor {workspace}")
    return 0 if terminal["state"] == "Succeeded" else 1


if __name__ == "__main__":
    argv = sys.argv[1:]
    targets = [a for a in argv if not a.startswith("--")]
    if len(targets) != 1:
        print("usage: python swarm_example.py <fresh-workspace-dir> "
              "[--sabotage-holdout] [--simulate-interrupt] "
              "[--declare-unmapped-criterion] [--live]", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(
        targets[0],
        live="--live" in argv,
        sabotage="--sabotage-holdout" in argv,
        unmapped_criterion="--declare-unmapped-criterion" in argv,
        simulate_interrupt="--simulate-interrupt" in argv,
    ))
