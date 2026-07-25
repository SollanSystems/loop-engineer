"""Live schema-drift alarm for the OpenHands recipe.

``base_state.json`` is a ``model_dump_json()`` of a fast-moving pydantic model,
and ``ConversationErrorEvent.code`` is a free-form ``str`` — ``"MaxIterationsReached"``
is a source literal, not a contract. So the recipe's committed fixtures are pinned
against the INSTALLED SDK here: if OpenHands renames a constant, drops an execution
status, or stops emitting that error code, this fires.

Skipped everywhere the SDK is absent (it requires python >=3.12); the behavioural
e2e in ``test_openhands_recipe.py`` is fixture-driven and needs no install.
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("openhands.sdk")

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_DIR = REPO_ROOT / "examples" / "openhands-certify"
CONVERSATIONS = EXAMPLE_DIR / "fixtures" / "conversations"

sys.path.insert(0, str(EXAMPLE_DIR))
import certify_run  # noqa: E402


def test_persistence_constants_match_the_certifier():
    from openhands.sdk.conversation import persistence_const as pc

    assert pc.BASE_STATE == certify_run.BASE_STATE
    assert pc.EVENTS_DIR == certify_run.EVENTS_DIR
    assert pc.EVENT_FILE_PATTERN == "event-{idx:05d}-{event_id}.json"
    assert pc.EVENT_NAME_RE.match("event-00000-5a1d5379-b1d4-4772-9292-7b002555b529.json")


def test_every_fixture_status_is_a_live_execution_status():
    from openhands.sdk.conversation.state import ConversationExecutionStatus

    live = {member.value for member in ConversationExecutionStatus}
    assert {"finished", "error", "stuck", "paused", "running", "idle"} <= live

    for base_state in sorted(CONVERSATIONS.glob("*/base_state.json")):
        status = json.loads(base_state.read_text(encoding="utf-8"))["execution_status"]
        assert status in live, (base_state, status)


def test_error_event_still_serializes_the_shape_the_mapper_reads():
    from openhands.sdk.event.conversation_error import ConversationErrorEvent

    event = json.loads(
        ConversationErrorEvent(
            source="environment", code="MaxIterationsReached", detail="…"
        ).model_dump_json()
    )
    assert event["kind"] == certify_run.ERROR_EVENT_KIND
    assert event["code"] == certify_run.MAX_ITERATIONS_CODE
    assert "detail" in event


def test_max_iterations_code_is_still_the_run_loop_literal():
    from openhands.sdk.conversation.impl import local_conversation

    assert certify_run.MAX_ITERATIONS_CODE in inspect.getsource(local_conversation)


def test_fixture_records_still_read_through_the_certifier():
    for conv_dir in sorted(p.parent for p in CONVERSATIONS.glob("*/base_state.json")):
        record = certify_run.read_conversation(conv_dir)
        assert record["state"]["execution_status"]
        assert record["event_paths"]
