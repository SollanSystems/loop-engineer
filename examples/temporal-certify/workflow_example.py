"""A Temporal workflow whose only path to a returned result is a certify
ACTIVITY — activities do I/O, the workflow stays deterministic.

Temporal owns durability (the run survives crashes); Loop Engineer owns the
on-disk success/evidence truth. The certify activity runs the visible/holdout
split through the real holdout gate + anticheat scan, projects through
loop.integrations, and records the result via loop.emit. Host-side failure
mapping: cancellation -> AbortedByHuman, retry-policy exhaustion on an
external dependency -> FailedBlocked, workflow timeout -> FailedBudget.

    python workflow_example.py <fresh-workspace-dir> [--sabotage-holdout]

(standalone mode starts a local Temporal dev server via
temporalio.testing.WorkflowEnvironment.start_local — first run downloads it)
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from temporalio import activity, workflow
from temporalio.client import Client, WorkflowFailureError
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, CancelledError
from temporalio.exceptions import TimeoutError as TemporalTimeoutError

with workflow.unsafe.imports_passed_through():
    from loop import emit
    from loop._resources import tools_dir
    from loop.integrations import EngineOutcome, to_terminal_state

sys.path.insert(0, str(tools_dir()))
with workflow.unsafe.imports_passed_through():
    import anticheat_scan  # noqa: E402
    import holdout_gate  # noqa: E402

EXPECTED = "hello from temporal\n"
TASK_QUEUE = "loop-engineer-certify-demo"


@dataclass
class WorkArgs:
    workspace: str
    sabotage: bool = False
    hold_seconds: int = 0


@activity.defn
async def do_work_activity(args: WorkArgs) -> str:
    out = Path(args.workspace) / "artifact.txt"
    out.write_text("HELLO stub\n" if args.sabotage else EXPECTED, encoding="utf-8")
    return str(out)


@activity.defn
async def certify_activity(args: WorkArgs) -> dict:
    ws = Path(args.workspace)
    artifact = ws / "artifact.txt"
    visible = [{"id": "artifact-exists", "passed": artifact.is_file()}]
    holdout = [{
        "id": "artifact-content",
        "passed": artifact.is_file() and artifact.read_text(encoding="utf-8") == EXPECTED,
    }]
    gate = holdout_gate.decide(visible, holdout)
    ac = anticheat_scan.scan(diff_text="", trajectory=[str(artifact)])

    art_dir = ws / ".loop" / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "holdout-verdict.json").write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")

    terminal = to_terminal_state(
        outcome=EngineOutcome(reached_end=True, artifacts=[".loop/artifacts/holdout-verdict.json"]),
        gate_verdict=gate, anticheat=ac,
        criteria_met={"1": gate["verdict"] == "Succeeded"},
    )
    passed = terminal["state"] == "Succeeded"
    emit.append_iteration(
        str(ws), iteration_id=1, outcome="task_passed" if passed else "task_failed",
        task_id="T1", actions=["do_work_activity wrote artifact.txt", "certify_activity gated it"],
        verify_cmd="holdout_gate.decide(visible, holdout)", verify_outcome=gate["verdict"],
    )
    emit.append_receipt(str(ws), iteration_id=1, role="orchestrate", model="deterministic-demo", outcome="ok")
    emit.terminate(
        str(ws), state=terminal["state"], criteria_met=terminal["criteria_met"],
        evidence=terminal["evidence"], false_completion=terminal["false_completion"],
        reason=terminal["reason"], iteration_id=1,
    )
    return {"state": terminal["state"], "false_completion": terminal["false_completion"]}


@workflow.defn
class CertifiedGoalWorkflow:
    @workflow.run
    async def run(self, args: WorkArgs) -> dict:
        if args.hold_seconds:
            await asyncio.sleep(args.hold_seconds)  # durable timer (cancel/timeout demos)
        await workflow.execute_activity(
            do_work_activity, args,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
        return await workflow.execute_activity(
            certify_activity, args,
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )


def map_workflow_failure(cause: BaseException | None) -> EngineOutcome:
    """Pure projection of a WorkflowFailureError cause onto EngineOutcome."""
    if isinstance(cause, CancelledError):
        return EngineOutcome(reached_end=False, human_abort=True)
    if isinstance(cause, TemporalTimeoutError):
        return EngineOutcome(reached_end=False, budget_exhausted=True)
    if isinstance(cause, ActivityError):
        return EngineOutcome(reached_end=False, external_error=f"activity retries exhausted: {cause}")
    return EngineOutcome(reached_end=False, external_error=str(cause) or "unknown engine failure")


def certify_workflow_failure(workspace: str, cause: BaseException | None) -> dict:
    """Terminate an already-opened contract from a workflow failure, honestly."""
    terminal = to_terminal_state(
        outcome=map_workflow_failure(cause), gate_verdict={}, anticheat={},
        criteria_met={"1": False},
    )
    emit.terminate(
        workspace, state=terminal["state"], criteria_met=terminal["criteria_met"],
        evidence=terminal["evidence"], false_completion=terminal["false_completion"],
        reason=terminal["reason"], iteration_id=1,
    )
    return terminal


async def run_and_certify(client: Client, workspace: str, *, sabotage: bool, wf_id: str) -> dict:
    emit.open_contract(workspace)
    try:
        return await client.execute_workflow(
            CertifiedGoalWorkflow.run, WorkArgs(workspace=workspace, sabotage=sabotage),
            id=wf_id, task_queue=TASK_QUEUE,
        )
    except WorkflowFailureError as exc:
        return certify_workflow_failure(workspace, exc.cause)


async def _amain(workspace: str, sabotage: bool) -> int:
    from temporalio.testing import WorkflowEnvironment
    from temporalio.worker import Worker

    async with await WorkflowEnvironment.start_local() as env:
        async with Worker(
            env.client, task_queue=TASK_QUEUE,
            workflows=[CertifiedGoalWorkflow],
            activities=[do_work_activity, certify_activity],
        ):
            result = await run_and_certify(env.client, workspace, sabotage=sabotage, wf_id="demo-run")
    print(f"terminal: {result['state']} — validate: python3 -m loop doctor {workspace}")
    return 0 if result["state"] == "Succeeded" else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    sabotage = "--sabotage-holdout" in args
    targets = [a for a in args if not a.startswith("--")]
    if len(targets) != 1:
        print("usage: python workflow_example.py <fresh-workspace-dir> [--sabotage-holdout]", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(_amain(targets[0], sabotage)))
