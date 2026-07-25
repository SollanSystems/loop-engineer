"""Certify a finished OpenHands run from its persisted Conversation record.

OpenHands has no "certify node" seam — a run ends when the agent sets its own
execution status. So the recipe is a POST-RUN CERTIFIER: it reads the
conversation directory the SDK already wrote (``base_state.json`` +
``events/event-*.json``), runs the same visible + withheld-holdout split the
loop optimized against through the real gate, projects the engine terminal
through ``loop.integrations``, and records it via ``loop.emit`` — which refuses
a dishonest ``Succeeded`` before anything hits disk.

    python certify_run.py <out-dir> --conversation <conv-dir> --agent-workspace <dir>

It imports no ``openhands`` package: the layout is documented and the record is
plain JSON, so the certifier stays stdlib-only on Python 3.10 while the SDK
itself requires 3.12.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from loop import emit
from loop._resources import tools_dir
from loop.integrations import EngineOutcome, to_terminal_state

sys.path.insert(0, str(tools_dir()))
import anticheat_scan  # noqa: E402
import holdout_gate  # noqa: E402

# openhands-sdk 1.37.1: openhands/sdk/conversation/persistence_const.py
BASE_STATE = "base_state.json"
EVENTS_DIR = "events"
EVENT_GLOB = "event-*.json"
ERROR_EVENT_KIND = "ConversationErrorEvent"
MAX_ITERATIONS_CODE = "MaxIterationsReached"

EXPECTED = "hello from openhands\n"


def _event_order(path: Path) -> tuple[int, str]:
    """``event-{idx:05d}-{uuid}.json`` — past 99999 the index outgrows its zero
    padding and lexical order stops agreeing with write order."""
    parts = path.name.split("-", 2)
    try:
        return (int(parts[1]), path.name)
    except (IndexError, ValueError):
        return (-1, path.name)


def read_conversation(conv_dir: str | Path) -> dict:
    """Pure-stdlib reader over the SDK's on-disk layout, tolerant of unknown
    fields — ``base_state.json`` is a dump of a fast-moving pydantic model, so
    only ``execution_status`` and the event log are treated as contract."""
    conv_dir = Path(conv_dir)
    state = json.loads((conv_dir / BASE_STATE).read_text(encoding="utf-8"))
    events = sorted((conv_dir / EVENTS_DIR).glob(EVENT_GLOB), key=_event_order)
    return {"state": state, "event_paths": [str(p) for p in events]}


def last_error(event_paths: list[str]) -> tuple[str, str]:
    """The last ``ConversationErrorEvent``'s ``(code, detail)``; ``("", "")`` if
    the run recorded none."""
    for path in reversed(event_paths):
        event = json.loads(Path(path).read_text(encoding="utf-8"))
        if event.get("kind") == ERROR_EVENT_KIND:
            return str(event.get("code", "")), str(event.get("detail", ""))
    return "", ""


def to_engine_outcome(record: dict, artifacts: list[str]) -> EngineOutcome:
    """Project ``execution_status`` (+ the error code) onto EngineOutcome.

    Exactly ONE of ``external_error`` / ``budget_exhausted`` is ever set: a
    max-iteration stop arrives as ``execution_status == "error"``, and since
    blocked outranks budget in ``to_terminal_state``, setting both would report
    ``FailedBlocked`` and silently lose the budget signal.
    """
    status = str(record["state"].get("execution_status", "")).lower()
    code, detail = last_error(record["event_paths"])

    if status == "stuck":
        return EngineOutcome(reached_end=False, budget_exhausted=True, artifacts=artifacts)
    if status == "error":
        if code == MAX_ITERATIONS_CODE:
            return EngineOutcome(reached_end=False, budget_exhausted=True, artifacts=artifacts)
        # ConversationErrorEvent.code is a free-form str and the event may be
        # absent entirely; an empty external_error would fall through to the
        # gate, so an unclassified error still has to name itself.
        blocked = ": ".join(part for part in (code, detail) if part) or "unclassified engine error"
        return EngineOutcome(reached_end=False, external_error=blocked, artifacts=artifacts)
    if status == "paused":
        return EngineOutcome(reached_end=False, human_abort=True, artifacts=artifacts)
    return EngineOutcome(reached_end=(status == "finished"), artifacts=artifacts)


def certify(out_dir: Path, conv_dir: Path, agent_workspace: Path) -> dict:
    record = read_conversation(conv_dir)
    artifact = agent_workspace / "artifact.txt"

    # 1. The gate: visible = what the run optimized against; withheld = the rest.
    visible = [{"id": "artifact-exists", "passed": artifact.is_file()}]
    withheld = [{
        "id": "artifact-content",
        "passed": artifact.is_file() and artifact.read_text(encoding="utf-8") == EXPECTED,
    }]
    gate = holdout_gate.decide(visible, withheld)
    # The event log IS the trajectory — the "the runtime ran the tests but the
    # agent read the answer key" case OpenHands cannot catch about itself.
    ac = anticheat_scan.scan(diff_text="", trajectory=record["event_paths"])

    # 2. Evidence artifacts: the gate verdict + a verify bundle metrics can join.
    art_dir = out_dir / ".loop" / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "holdout-verdict.json").write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    bundle = {
        "task": "T1",
        "verify": "post-run certifier — holdout_gate.decide over visible+withheld",
        "outcome": "PASS" if gate["verdict"] == "Succeeded" else "FAIL",
        "iteration_id": 1,
        "criteria": {"1": gate["verdict"] == "Succeeded"},
    }
    (art_dir / "verify-T1.json").write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")

    # 3. Project the OpenHands terminal into a typed state; write via emit only.
    terminal = to_terminal_state(
        outcome=to_engine_outcome(
            record,
            [".loop/artifacts/verify-T1.json", ".loop/artifacts/holdout-verdict.json"],
        ),
        gate_verdict=gate,
        anticheat=ac,
        criteria_met={"1": gate["verdict"] == "Succeeded"},
    )
    passed = terminal["state"] == "Succeeded"
    status = str(record["state"].get("execution_status", "")).lower()
    emit.append_iteration(
        out_dir, iteration_id=1, outcome="task_passed" if passed else "task_failed",
        task_id="T1",
        actions=[
            f"read conversation record ({len(record['event_paths'])} events)",
            "ran holdout_gate.decide + anticheat_scan.scan",
        ],
        verify_cmd="holdout_gate.decide(visible, withheld)", verify_outcome=gate["verdict"],
        notes=f"execution_status: {status}; verify bundle: verify-T1.json; "
              f"gate verdict: holdout-verdict.json",
    )
    emit.append_receipt(out_dir, iteration_id=1, role="orchestrate", model="deterministic-demo", outcome="ok")
    emit.terminate(
        out_dir, state=terminal["state"], criteria_met=terminal["criteria_met"],
        evidence=terminal["evidence"], false_completion=terminal["false_completion"],
        reason=terminal["reason"], iteration_id=1,
    )
    return terminal


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out_dir", help="fresh directory for the emitted loop contract")
    parser.add_argument("--conversation", required=True,
                        help="the SDK conversation dir (holds base_state.json + events/)")
    parser.add_argument("--agent-workspace", required=True,
                        help="the workspace the run produced (base_state.json records it "
                             "as workspace.working_dir)")
    args = parser.parse_args(argv)

    emit.open_contract(args.out_dir)
    terminal = certify(Path(args.out_dir), Path(args.conversation), Path(args.agent_workspace))
    print(f"terminal: {terminal['state']} — validate: python3 -m loop doctor {args.out_dir}")
    return 0 if terminal["state"] == "Succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
