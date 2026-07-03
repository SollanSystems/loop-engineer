"""AC1 schema tests: the two canonical record schemas validate the shipped
example repair record and a rollout-ledger fixture. Runs a stdlib structural
check always, and full JSON-Schema validation when jsonschema is installed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SCHEMAS = _REPO / "schemas"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _structural_ok(schema: dict, instance: dict) -> list[str]:
    """Minimal stdlib validation: required keys present + `const` fields match."""
    errors = []
    for key in schema.get("required", []):
        if key not in instance:
            errors.append(f"missing required key {key!r}")
    for key, subschema in schema.get("properties", {}).items():
        if key in instance and isinstance(subschema, dict) and "const" in subschema:
            if instance[key] != subschema["const"]:
                errors.append(f"{key} != const {subschema['const']!r}")
    return errors


def _jsonschema_errors(schema: dict, instance: dict) -> list[str]:
    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(schema)
    return [e.message for e in validator.iter_errors(instance)]


_ROLLOUT_FIXTURE = {
    "id": "cand-2",
    "parent": "cand-1",
    "verdict": "Succeeded",
    "score": 0.90,
    "score_delta": 0.10,
    "coherent_with_prior_winner": True,
    "productive": True,
}


def test_repair_schema_exists_with_expected_id():
    schema = _load(_SCHEMAS / "repair-record.schema.json")
    assert schema["$id"] == "loop-engineer/repair@1"


def test_rollout_schema_exists_with_expected_id():
    schema = _load(_SCHEMAS / "rollout-record.schema.json")
    assert schema["$id"] == "loop-engineer/rollout@1"


def test_repair_schema_validates_shipped_example_record():
    schema = _load(_SCHEMAS / "repair-record.schema.json")
    record = _load(_REPO / "examples" / "coverage-repair" / ".loop" / "repair" / "iter-002.json")
    assert _structural_ok(schema, record) == []
    assert record["verification_before"]["score"] is not None
    assert record["verification_after"]["score"] is not None


def test_rollout_schema_validates_ledger_fixture():
    schema = _load(_SCHEMAS / "rollout-record.schema.json")
    assert _structural_ok(schema, _ROLLOUT_FIXTURE) == []


def test_repair_schema_jsonschema_validation_of_example():
    schema = _load(_SCHEMAS / "repair-record.schema.json")
    record = _load(_REPO / "examples" / "coverage-repair" / ".loop" / "repair" / "iter-002.json")
    assert _jsonschema_errors(schema, record) == []


def test_rollout_schema_jsonschema_validation_of_fixture():
    schema = _load(_SCHEMAS / "rollout-record.schema.json")
    assert _jsonschema_errors(schema, _ROLLOUT_FIXTURE) == []


def test_repair_schema_rejects_missing_score():
    schema = _load(_SCHEMAS / "repair-record.schema.json")
    record = _load(_REPO / "examples" / "coverage-repair" / ".loop" / "repair" / "iter-002.json")
    del record["verification_after"]["score"]
    assert _jsonschema_errors(schema, record) != []
