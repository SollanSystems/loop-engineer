import json
import re

import pytest

from loop.events import SQLiteEventStore
from loop.scaffold import scaffold


def _workspace_with_terminal(tmp_path, name="workspace", *, completion_policy=None):
    target = tmp_path / name
    scaffold(target)
    (target / ".loop" / "terminal_state.json").write_text(
        json.dumps({
            "schema": "loop-engineer/terminal@1",
            "state": "Succeeded",
            "criteria_met": {"gate": True},
            "evidence": [],
            "false_completion": False,
            "completion_policy": {"mode": "all_required"} if completion_policy is None else completion_policy,
        }),
        encoding="utf-8",
    )
    return target


def test_schema_id_and_predicate_type_are_pinned():
    from loop.verdict import PREDICATE_TYPE, VERDICT_SCHEMA_ID

    assert VERDICT_SCHEMA_ID == "loop-engineer/verdict@1"
    assert PREDICATE_TYPE == "urn:loop-engineer:verdict:1"


def test_predicate_type_is_derived_from_the_schema_id():
    """The two constants are one identity in two encodings, not two names.

    ADR 0002 chose a URN matching the schema $id. A URN cannot idiomatically
    carry '/' or '@', so the mapping is a transliteration -- which means
    nothing stops the two from silently drifting apart unless it is asserted.
    """
    from loop.verdict import PREDICATE_TYPE, VERDICT_SCHEMA_ID

    assert PREDICATE_TYPE == "urn:" + VERDICT_SCHEMA_ID.replace("/", ":").replace("@", ":")


def test_schema_file_declares_the_matching_id():
    from loop._resources import schemas_dir
    from loop.verdict import VERDICT_SCHEMA_ID

    schema = json.loads((schemas_dir() / "verdict.schema.json").read_text(encoding="utf-8"))
    assert schema["$id"] == VERDICT_SCHEMA_ID
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_verdict_schema_is_not_a_contract_artifact():
    # SCHEMA_IDS is the contract-object tuple (manifest/state/tasks/terminal).
    # verdict@1 is a projection, not a contract object, and must stay out of it.
    from loop.contract import SCHEMA_IDS
    from loop.verdict import VERDICT_SCHEMA_ID

    assert VERDICT_SCHEMA_ID not in SCHEMA_IDS


def test_build_verdict_has_the_required_top_level_shape(tmp_path):
    from loop.verdict import build_verdict

    verdict = build_verdict(_workspace_with_terminal(tmp_path))

    assert set(verdict) == {"schema", "run_id", "tool", "doctor", "chain", "terminal", "evidence"}
    assert verdict["schema"] == "loop-engineer/verdict@1"
    assert verdict["tool"]["name"] == "loop-engineer"
    assert verdict["evidence"] == []


def test_build_verdict_projects_nonempty_normalized_doctor_issue_codes(tmp_path):
    from loop.verdict import build_verdict

    target = _workspace_with_terminal(tmp_path)
    (target / "scripts" / "verify-fast").unlink()
    (target / "scripts" / "verify-full").unlink()

    doctor = build_verdict(target)["doctor"]

    assert set(doctor) == {"ok", "validation_mode", "issue_codes", "schemas_checked"}
    assert doctor["issue_codes"]
    assert doctor["issue_codes"] == sorted(set(doctor["issue_codes"]))
    assert "unresolved_task_verify" in doctor["issue_codes"]
    assert all(" " not in code and "/" not in code for code in doctor["issue_codes"])


def test_build_verdict_projects_terminal_and_requires_terminal_record(tmp_path):
    from loop.verdict import VerdictError, build_verdict

    target = _workspace_with_terminal(tmp_path)
    terminal = build_verdict(target)["terminal"]

    assert set(terminal) == {"state", "completion_policy", "false_completion"}
    assert terminal["completion_policy"] == "all_required"

    no_policy = _workspace_with_terminal(tmp_path, "no-policy", completion_policy=None)
    (no_policy / ".loop" / "terminal_state.json").write_text(
        json.dumps({"state": "Succeeded", "false_completion": False}), encoding="utf-8"
    )
    assert build_verdict(no_policy)["terminal"]["completion_policy"] is None

    non_object_policy = _workspace_with_terminal(tmp_path, "non-object-policy", completion_policy="all_required")
    assert build_verdict(non_object_policy)["terminal"]["completion_policy"] is None

    plain = tmp_path / "plain"
    scaffold(plain)
    with pytest.raises(VerdictError, match="no terminal record"):
        build_verdict(plain)
    with pytest.raises(VerdictError):
        build_verdict(tmp_path / "missing")


def test_build_verdict_projects_chain_head_from_real_store(tmp_path):
    from loop.verdict import build_verdict

    target = _workspace_with_terminal(tmp_path)
    head = SQLiteEventStore(target / ".loop" / "events.db").append(
        "run-1", "contract_opened", {"workspace": target.name}, actor="test"
    )

    chain = build_verdict(target)["chain"]

    assert chain["head"] is not None
    assert re.fullmatch(r"[0-9a-f]{64}", chain["head"])
    assert chain["sequence"] == head["sequence"]


def test_build_verdict_handles_an_absent_event_store(tmp_path):
    from loop.verdict import build_verdict

    verdict = build_verdict(_workspace_with_terminal(tmp_path))

    assert verdict["chain"] == {"head": None, "sequence": None, "unchained_prefix": 0}


def test_build_verdict_degrades_for_an_unreadable_event_store(tmp_path):
    from loop.verdict import build_verdict

    target = _workspace_with_terminal(tmp_path)
    store_path = target / ".loop" / "events.db"
    SQLiteEventStore(store_path).append(
        "run-1", "contract_opened", {"workspace": target.name}, actor="test"
    )
    store_path.write_bytes(b"not a SQLite database")

    verdict = build_verdict(target)

    assert verdict["chain"] == {"head": None, "sequence": None, "unchained_prefix": 0}
    assert verdict["doctor"]["issue_codes"]


def test_build_verdict_rejects_terminal_without_false_completion(tmp_path):
    from loop.verdict import VerdictError, build_verdict

    target = _workspace_with_terminal(tmp_path)
    terminal_path = target / ".loop" / "terminal_state.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    del terminal["false_completion"]
    terminal_path.write_text(json.dumps(terminal), encoding="utf-8")

    with pytest.raises(VerdictError, match="false_completion"):
        build_verdict(target)


# None is the original defect value: bool(None) is False, so the fail-open
# projection this guard replaced would have claimed "not a false completion"
# for a null flag. JSON null round-trips to None, so the key IS present and
# only the isinstance check stands between it and a signed false claim.
@pytest.mark.parametrize("value", ["false", 1, None])
def test_build_verdict_rejects_non_boolean_false_completion(tmp_path, value):
    from loop.verdict import VerdictError, build_verdict

    target = _workspace_with_terminal(tmp_path)
    terminal_path = target / ".loop" / "terminal_state.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    terminal["false_completion"] = value
    terminal_path.write_text(json.dumps(terminal), encoding="utf-8")

    with pytest.raises(VerdictError, match="false_completion"):
        build_verdict(target)


def test_build_verdict_reports_an_invalid_mode_as_a_contract_read_failure(tmp_path):
    """An invalid mode= is a contract-read failure, not a path-resolution one.

    ValidationModeError subclasses RuntimeError, so a single guard around both
    resolution and doctor_report would label it "cannot resolve a loop
    workspace" -- a misleading frame for an argument error.
    """
    from loop.verdict import VerdictError, build_verdict

    target = _workspace_with_terminal(tmp_path)

    with pytest.raises(VerdictError, match="cannot read the contract"):
        build_verdict(target, mode="not-a-validation-mode")


def test_build_verdict_rejects_non_object_terminal_record(tmp_path):
    from loop.verdict import VerdictError, build_verdict

    target = _workspace_with_terminal(tmp_path)
    (target / ".loop" / "terminal_state.json").write_text("[]", encoding="utf-8")

    with pytest.raises(VerdictError, match="not an object"):
        build_verdict(target)


def test_build_verdict_wraps_path_resolution_runtime_errors_as_verdict_error(
    tmp_path, monkeypatch
):
    import loop.verdict as verdict
    from loop.verdict import VerdictError, build_verdict

    def raise_symlink_loop(_target):
        raise RuntimeError("Symlink loop from 'x'")

    monkeypatch.setattr(verdict, "resolve_loop_paths", raise_symlink_loop)

    with pytest.raises(VerdictError):
        build_verdict(tmp_path / "anything")


def test_build_verdict_validates_against_its_loaded_schema(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    from loop.verdict import _load_verdict_schema, build_verdict

    schema = _load_verdict_schema()
    verdict = build_verdict(_workspace_with_terminal(tmp_path))
    invalid_verdict = {**verdict, "chain": {**verdict["chain"], "head": "not-a-hash"}}

    assert schema["$id"] == "loop-engineer/verdict@1"
    jsonschema.validate(verdict, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid_verdict, schema)
