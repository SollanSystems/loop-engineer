"""A minimal LangGraph graph that ships proof-of-done through loop.emit.

The graph does real (tiny) work, verifies it from the filesystem, and the
terminal node records the outcome via emit.terminate(...) — which refuses an
evidence-free Succeeded. Run:

    python graph_example.py <fresh-workspace-dir>
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from loop import emit


class State(TypedDict):
    workspace: str
    verified: bool


def do_work(state: State) -> dict:
    out = Path(state["workspace"]) / "artifact.txt"
    out.write_text("hello from langgraph\n", encoding="utf-8")
    return {}


def verify(state: State) -> dict:
    artifact = Path(state["workspace"]) / "artifact.txt"
    ok = artifact.is_file() and "hello" in artifact.read_text(encoding="utf-8")
    return {"verified": ok}


def conclude(state: State) -> dict:
    ws = state["workspace"]
    passed = state["verified"]
    emit.append_iteration(
        ws, iteration_id=1, outcome="task_passed" if passed else "task_failed",
        task_id="T1", actions=["wrote artifact.txt", "re-read and checked content"],
        verify_cmd="verify node (filesystem re-read)", verify_outcome="pass" if passed else "fail",
    )
    if passed:
        emit.terminate(
            ws, state="Succeeded", criteria_met={"1": True},
            evidence=["artifact.txt"], reason="artifact written and independently re-read",
            iteration_id=1,
        )
    else:
        emit.terminate(
            ws, state="FailedUnverifiable", criteria_met={"1": False},
            evidence=[], reason="verification failed", iteration_id=1,
        )
    return {}


def main(workspace: str) -> int:
    emit.open_contract(workspace)
    graph = (
        StateGraph(State)
        .add_node(do_work)
        .add_node(verify)
        .add_node(conclude)
        .add_edge(START, "do_work")
        .add_edge("do_work", "verify")
        .add_edge("verify", "conclude")
        .add_edge("conclude", END)
        .compile()
    )
    graph.invoke({"workspace": workspace, "verified": False})
    print(f"contract emitted at {workspace}/.loop — run: python3 -m loop doctor {workspace}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python graph_example.py <fresh-workspace-dir>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
