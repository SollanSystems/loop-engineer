"""A LangGraph graph whose END is reachable only through a certify node.

The certify node runs the SAME split the loop optimized against — a visible
check plus a WITHHELD holdout check — through the real holdout gate and
anticheat scan, projects the graph's terminal through loop.integrations, and
records the result via loop.emit (which refuses a dishonest Succeeded).

    python graph_example.py <fresh-workspace-dir> [--sabotage-holdout]

--sabotage-holdout makes do_work write output that passes the visible check
but fails the holdout — the measurable false-completion event: the terminal
becomes FailedUnverifiable with false_completion: true, never Succeeded.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from loop import emit
from loop._resources import tools_dir
from loop.integrations import EngineOutcome, to_terminal_state

sys.path.insert(0, str(tools_dir()))
import anticheat_scan  # noqa: E402
import holdout_gate  # noqa: E402

EXPECTED = "hello from langgraph\n"


class State(TypedDict):
    workspace: str
    sabotage: bool
    terminal_state: str


def do_work(state: State) -> dict:
    out = Path(state["workspace"]) / "artifact.txt"
    out.write_text("HELLO stub\n" if state["sabotage"] else EXPECTED, encoding="utf-8")
    return {}


def certify(state: State) -> dict:
    ws = Path(state["workspace"])
    artifact = ws / "artifact.txt"

    # 1. The gate: visible = what the loop optimized against; holdout = withheld.
    visible = [{"id": "artifact-exists", "passed": artifact.is_file()}]
    holdout = [{
        "id": "artifact-content",
        "passed": artifact.is_file() and artifact.read_text(encoding="utf-8") == EXPECTED,
    }]
    gate = holdout_gate.decide(visible, holdout)
    ac = anticheat_scan.scan(diff_text="", trajectory=[str(artifact)])

    # 2. Evidence artifacts: the gate verdict + a verify bundle metrics can join.
    art_dir = ws / ".loop" / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "holdout-verdict.json").write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    bundle = {
        "task": "T1",
        "verify": "certify node — holdout_gate.decide over visible+holdout",
        "outcome": "PASS" if gate["verdict"] == "Succeeded" else "FAIL",
        "iteration_id": 1,
        "criteria": {"1": gate["verdict"] == "Succeeded"},
    }
    (art_dir / "verify-T1.json").write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")

    # 3. Project the graph terminal into a typed state; write via emit only.
    terminal = to_terminal_state(
        outcome=EngineOutcome(
            reached_end=True,
            artifacts=[".loop/artifacts/verify-T1.json", ".loop/artifacts/holdout-verdict.json"],
        ),
        gate_verdict=gate,
        anticheat=ac,
        criteria_met={"1": gate["verdict"] == "Succeeded"},
    )
    passed = terminal["state"] == "Succeeded"
    emit.append_iteration(
        ws, iteration_id=1, outcome="task_passed" if passed else "task_failed",
        task_id="T1",
        actions=["wrote artifact.txt", "ran holdout_gate.decide + anticheat_scan.scan"],
        verify_cmd="holdout_gate.decide(visible, holdout)", verify_outcome=gate["verdict"],
        notes="verify bundle: verify-T1.json; gate verdict: holdout-verdict.json",
    )
    emit.append_receipt(ws, iteration_id=1, role="orchestrate", model="deterministic-demo", outcome="ok")
    emit.terminate(
        ws, state=terminal["state"], criteria_met=terminal["criteria_met"],
        evidence=terminal["evidence"], false_completion=terminal["false_completion"],
        reason=terminal["reason"], iteration_id=1,
    )
    return {"terminal_state": terminal["state"]}


def main(workspace: str, sabotage: bool) -> int:
    emit.open_contract(workspace)
    graph = (
        StateGraph(State)
        .add_node(do_work)
        .add_node(certify)
        .add_edge(START, "do_work")
        .add_edge("do_work", "certify")
        .add_edge("certify", END)  # certify IS the only path to END
        .compile()
    )
    result = graph.invoke({"workspace": workspace, "sabotage": sabotage, "terminal_state": ""})
    print(f"terminal: {result['terminal_state']} — validate: python3 -m loop doctor {workspace}")
    return 0 if result["terminal_state"] == "Succeeded" else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    sabotage = "--sabotage-holdout" in args
    targets = [a for a in args if not a.startswith("--")]
    if len(targets) != 1:
        print("usage: python graph_example.py <fresh-workspace-dir> [--sabotage-holdout]", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(targets[0], sabotage))
