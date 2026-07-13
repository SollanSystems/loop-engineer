from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


def _errors(extra_states):
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((ROOT / "schemas" / "manifest.schema.json").read_text(encoding="utf-8"))
    instance = {
        "schema": "loop-engineer/manifest@1",
        "loop": "demo",
        "policies": {"plan_then_execute": True},
        "terminal_states": [
            "Succeeded",
            "FailedUnverifiable",
            "FailedBlocked",
            "FailedBudget",
            "FailedSafety",
            "FailedSpecGap",
            "AbortedByHuman",
        ],
        "extra_states": extra_states,
    }
    return list(jsonschema.Draft202012Validator(schema).iter_errors(instance))


def test_manifest_schema_accepts_extra_states_array():
    assert _errors(["domain-review", "domain-publish"]) == []


def test_manifest_schema_rejects_non_string_extra_states_items():
    assert _errors(["domain-review", 7])
