"""ST3 acceptance for the Temporal recipe: a certify ACTIVITY is the workflow's
only path to a returned result; the emitted contract passes doctor; the
false-completion invariant holds under sabotage; cancellation maps to
AbortedByHuman. Env-guarded: temporalio is a dev dependency of the example
only — the package stays zero-dependency. Uses asyncio.run (no pytest-asyncio).
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import subprocess
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import pytest

pytest.importorskip("temporalio")

from temporalio.client import WorkflowFailureError  # noqa: E402
from temporalio.testing import WorkflowEnvironment  # noqa: E402
from temporalio.worker import Worker  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_EXAMPLE_DIR = REPO_ROOT / "examples" / "temporal-certify"
# The example dir must be importable by name: Temporal's workflow sandbox
# re-imports the workflow's module (CertifiedGoalWorkflow.__module__ ==
# "workflow_example") through the normal import machinery to prepare a
# deterministic copy, so "workflow_example" has to be findable on sys.path.
if str(_EXAMPLE_DIR) not in sys.path:
    sys.path.insert(0, str(_EXAMPLE_DIR))

_spec = importlib.util.spec_from_file_location("workflow_example", _EXAMPLE_DIR / "workflow_example.py")
recipe = importlib.util.module_from_spec(_spec)
# Register before exec (the stdlib "importing a source file directly" recipe): the
# example's `from __future__ import annotations` + @dataclass WorkArgs makes the
# dataclass machinery resolve KW_ONLY via sys.modules[cls.__module__]; an
# unregistered module makes that None -> AttributeError on py3.10-3.12.
sys.modules["workflow_example"] = recipe
_spec.loader.exec_module(recipe)


def _doctor(workspace: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "loop", "doctor", str(workspace)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    return json.loads(proc.stdout)


def _terminal(workspace: Path) -> dict:
    return json.loads((workspace / ".loop" / "terminal_state.json").read_text())


def test_recipe_end_to_end(tmp_path):
    async def scenario():
        async with await WorkflowEnvironment.start_local() as env:
            async with Worker(
                env.client,
                task_queue=recipe.TASK_QUEUE,
                workflows=[recipe.CertifiedGoalWorkflow],
                activities=[recipe.do_work_activity, recipe.certify_activity],
            ):
                await recipe.run_and_certify(
                    env.client, str(tmp_path / "happy"), sabotage=False,
                    wf_id=f"happy-{uuid.uuid4()}",
                )
                await recipe.run_and_certify(
                    env.client, str(tmp_path / "sabotaged"), sabotage=True,
                    wf_id=f"sab-{uuid.uuid4()}",
                )
                # Cancellation -> AbortedByHuman (mapped host-side)
                ws_cancel = tmp_path / "cancelled"
                recipe.emit.open_contract(ws_cancel)
                handle = await env.client.start_workflow(
                    recipe.CertifiedGoalWorkflow.run,
                    recipe.WorkArgs(workspace=str(ws_cancel), sabotage=False, hold_seconds=30),
                    id=f"cancel-{uuid.uuid4()}", task_queue=recipe.TASK_QUEUE,
                )
                await handle.cancel()
                try:
                    await handle.result()
                except WorkflowFailureError as exc:
                    recipe.certify_workflow_failure(str(ws_cancel), exc.cause)
                else:  # pragma: no cover - cancellation must surface
                    raise AssertionError("expected WorkflowFailureError after cancel")

    asyncio.run(scenario())

    happy = _terminal(tmp_path / "happy")
    assert happy["state"] == "Succeeded"
    assert happy["false_completion"] is False
    assert happy["evidence"]
    assert _doctor(tmp_path / "happy")["ok"] is True

    sab = _terminal(tmp_path / "sabotaged")
    assert sab["state"] == "FailedUnverifiable"
    assert sab["state"] != "Succeeded"
    assert sab["false_completion"] is True
    assert _doctor(tmp_path / "sabotaged")["ok"] is True

    cancelled = _terminal(tmp_path / "cancelled")
    assert cancelled["state"] == "AbortedByHuman"
    assert _doctor(tmp_path / "cancelled")["ok"] is True


def test_map_workflow_failure_covers_blocked_and_budget():
    from temporalio.exceptions import ActivityError, TimeoutError as TemporalTimeoutError

    blocked = recipe.map_workflow_failure(
        ActivityError("activity failed", *_activity_error_extra_args())
        if False else _make(ActivityError, "activity failed")
    )
    assert blocked.external_error
    budget = recipe.map_workflow_failure(_make(TemporalTimeoutError, "workflow timeout"))
    assert budget.budget_exhausted is True


def _make(exc_type, message):
    """Best-effort construction of a temporalio failure for the pure mapper.
    If a class needs richer args in the installed version, fall back to a
    minimal subclass instance carrying only the type identity."""
    try:
        return exc_type(message)
    except TypeError:
        stub = type(exc_type.__name__, (exc_type,), {"__init__": lambda self: None})
        return stub()


def _activity_error_extra_args():  # placeholder for versions needing more args
    return ()
