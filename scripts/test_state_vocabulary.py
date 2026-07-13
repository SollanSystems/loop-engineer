from __future__ import annotations

import json
import sys

import pytest

from loop import emit, fsm
from loop.contract import validate_contract


def _workspace(tmp_path):
    target = tmp_path / "vocabulary"
    emit.open_contract(target)
    return target


def _set_state(target, state):
    path = target / ".loop" / "state.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**data, "state": state}, indent=2) + "\n", encoding="utf-8")


@pytest.mark.parametrize("state", fsm.ALL_STATES)
def test_validate_contract_accepts_all_ten_canonical_states(tmp_path, state):
    target = _workspace(tmp_path)
    _set_state(target, state)
    assert validate_contract(target)["ok"] is True


def test_validate_contract_flags_unknown_state_as_error(tmp_path):
    target = _workspace(tmp_path)
    _set_state(target, "domain-review")
    report = validate_contract(target)
    assert report["ok"] is False
    assert any(issue["code"] == "unknown_state" for issue in report["issues"])


def test_validate_contract_accepts_manifest_declared_extra_state(tmp_path):
    target = _workspace(tmp_path)
    _set_state(target, "domain-review")
    manifest = target / ".loop" / "manifest.yaml"
    manifest.write_text(manifest.read_text(encoding="utf-8") + "extra_states:\n  - domain-review\n", encoding="utf-8")
    assert validate_contract(target)["ok"] is True


def test_state_vocabulary_check_runs_in_both_modes(tmp_path, monkeypatch):
    pytest.importorskip("jsonschema")
    target = _workspace(tmp_path)
    _set_state(target, "domain-review")

    jsonschema_report = validate_contract(target)
    assert jsonschema_report["validation_mode"] == "jsonschema"
    assert any(issue["code"] == "unknown_state" for issue in jsonschema_report["issues"])

    monkeypatch.setitem(sys.modules, "jsonschema", None)
    fallback_report = validate_contract(target)
    assert fallback_report["validation_mode"] == "structural-fallback"
    assert any(issue["code"] == "unknown_state" for issue in fallback_report["issues"])
