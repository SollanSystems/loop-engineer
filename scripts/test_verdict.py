import hashlib
import json
import re

import pytest

from loop import emit
from loop.completion import VERIFIED_EVIDENCE_MODE
from loop.events import SQLiteEventStore
from loop.runner import dispatch_once
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


def _ready(tmp_path):
    """A real task workspace positioned for its first dispatched iteration."""
    workspace = tmp_path / "dispatched"
    emit.open_contract(workspace)
    task = {
        "id": "T-1", "title": "T-1", "status": "pending", "criterion_ref": "T-1",
        "verify": "./scripts/verify-fast.sh", "depends_on": [], "attempts": 0,
        "evidence": None,
    }
    (workspace / "TASKS.json").write_text(
        json.dumps({"schema": "loop-engineer/tasks@1", "tasks": [task]}), encoding="utf-8"
    )
    verifier = workspace / "scripts" / "verify-fast.sh"
    verifier.parent.mkdir(parents=True, exist_ok=True)
    verifier.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    verifier.chmod(0o755)
    store = SQLiteEventStore(workspace / ".loop" / "events.db")
    store.append("run-1", "contract_opened", {"workspace": workspace.name}, actor="test")
    for state in ("plan", "critique-plan", "queue-tasks", "execute-task"):
        store.append("run-1", "iteration_appended", {
            "iteration_id": 0, "outcome": "replanned", "state": state,
        }, actor="test")
    return workspace


def _dispatched_workspace(tmp_path):
    workspace = _ready(tmp_path)
    dispatch_once(workspace)
    return workspace


def _handwritten_record(workspace, *, name="evidence-handwritten.json"):
    """Create self-consistent evidence that is only chain-bound in storeless workspaces."""
    bundle = workspace / ".loop" / "artifacts" / "verify-handwritten.json"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle_bytes = b'{"outcome": "PASS", "passed": true}'
    bundle.write_bytes(bundle_bytes)
    record = {
        "schema": "loop-engineer/evidence@1", "id": "hand:1:verify",
        "kind": "verify-bundle", "uri": ".loop/artifacts/verify-handwritten.json",
        "sha256": hashlib.sha256(bundle_bytes).hexdigest(), "media_type": "application/json",
        "produced_by": {"run_id": "run-1", "task_id": None, "attempt": 1,
                        "executor": "worker-a"},
        "created_at": "2026-07-25T00:00:00+00:00",
        "verified_by": {"by": "ci", "at": "2026-07-25T00:00:00+00:00"},
    }
    path = workspace / ".loop" / "evidence" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    return f".loop/evidence/{name}"


def _rewrite_terminal_evidence(workspace, evidence):
    path = workspace / ".loop" / "terminal_state.json"
    terminal = json.loads(path.read_text(encoding="utf-8"))
    terminal["evidence"] = evidence
    path.write_text(json.dumps(terminal, sort_keys=True) + "\n", encoding="utf-8")


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


def test_evidence_carries_only_entries_that_pass_the_strict_bar(tmp_path, monkeypatch):
    import loop.verdict as verdict

    monkeypatch.setattr(verdict, "_strict_evidence_failure",
                        lambda entry, _paths, _bound: None if entry == "good" else "bad")
    monkeypatch.setattr(verdict, "_evidence_digests", lambda entry, _paths: {
        "digest": "a" * 64, "code_digest": None, "policy_digest": None,
    } if entry == "good" else {"digest": "b" * 64, "code_digest": None,
                             "policy_digest": None})
    target = _workspace_with_terminal(tmp_path)
    _rewrite_terminal_evidence(target, ["good", "bad"])

    assert verdict.build_verdict(target)["evidence"] == [
        {"digest": "a" * 64, "code_digest": None, "policy_digest": None}
    ]


def test_evidence_entries_carry_digests_only(tmp_path):
    from loop.verdict import build_verdict

    workspace = _dispatched_workspace(tmp_path)
    emit.terminate(workspace, state="Succeeded", criteria_met={"C-1": True},
                   evidence=[".loop/evidence/evidence-iter1.json"],
                   completion_policy=VERIFIED_EVIDENCE_MODE)

    evidence = build_verdict(workspace)["evidence"]
    assert evidence
    assert all(set(entry) == {"digest", "code_digest", "policy_digest"} for entry in evidence)


def test_evidence_is_sorted_by_digest(tmp_path, monkeypatch):
    import loop.verdict as verdict

    digests = {
        "later": {"digest": "f" * 64, "code_digest": None, "policy_digest": None},
        "first": {"digest": "0" * 64, "code_digest": None, "policy_digest": None},
    }
    monkeypatch.setattr(verdict, "_strict_evidence_failure", lambda *_args: None)
    monkeypatch.setattr(verdict, "_evidence_digests", lambda entry, _paths: digests[entry])
    target = _workspace_with_terminal(tmp_path)
    _rewrite_terminal_evidence(target, ["later", "first"])

    assert [entry["digest"] for entry in verdict.build_verdict(target)["evidence"]] == [
        "0" * 64, "f" * 64,
    ]


def test_evidence_digest_is_the_chain_committed_record_digest(tmp_path):
    from loop.runtime import bound_artifact_digests
    from loop.verdict import build_verdict

    workspace = _dispatched_workspace(tmp_path)
    entry = ".loop/evidence/evidence-iter1.json"
    emit.terminate(workspace, state="Succeeded", criteria_met={"C-1": True}, evidence=[entry],
                   completion_policy=VERIFIED_EVIDENCE_MODE)
    record_path = workspace / entry
    record = json.loads(record_path.read_text(encoding="utf-8"))

    projected = build_verdict(workspace)["evidence"]
    expected = hashlib.sha256(record_path.read_bytes()).hexdigest()
    assert projected == [{"digest": expected,
                          "code_digest": record["verified_by"]["code_digest"],
                          "policy_digest": record["verified_by"]["policy_digest"]}]
    assert expected == bound_artifact_digests(workspace)[entry][0]
    assert expected != record["sha256"]


def test_unbound_record_is_excluded_when_a_store_exists(tmp_path):
    from loop.verdict import build_verdict

    workspace = _dispatched_workspace(tmp_path)
    bound_entry = ".loop/evidence/evidence-iter1.json"
    emit.terminate(workspace, state="Succeeded", criteria_met={"C-1": True},
                   evidence=[bound_entry], completion_policy=VERIFIED_EVIDENCE_MODE)
    unbound_entry = _handwritten_record(workspace)
    _rewrite_terminal_evidence(workspace, [bound_entry, unbound_entry])

    evidence = build_verdict(workspace)["evidence"]
    assert [entry["digest"] for entry in evidence] == [
        hashlib.sha256((workspace / bound_entry).read_bytes()).hexdigest()
    ]


def test_absent_store_projects_evidence_under_the_documented_degradation(tmp_path):
    from loop.verdict import build_verdict

    workspace = _workspace_with_terminal(tmp_path)
    entry = _handwritten_record(workspace)
    _rewrite_terminal_evidence(workspace, [entry])

    assert build_verdict(workspace)["evidence"] == [{
        "digest": hashlib.sha256((workspace / entry).read_bytes()).hexdigest(),
        "code_digest": None, "policy_digest": None,
    }]


def test_unreadable_store_projects_no_evidence_and_does_not_raise(tmp_path):
    from loop.verdict import build_verdict

    workspace = _workspace_with_terminal(tmp_path)
    entry = _handwritten_record(workspace)
    _rewrite_terminal_evidence(workspace, [entry])
    (workspace / ".loop" / "events.db").write_bytes(b"not a SQLite database")

    assert build_verdict(workspace)["evidence"] == []


def test_identical_evidence_entries_project_once(tmp_path):
    from loop.verdict import build_verdict

    workspace = _workspace_with_terminal(tmp_path)
    entry = _handwritten_record(workspace)
    _rewrite_terminal_evidence(workspace, [entry, entry])

    assert build_verdict(workspace)["evidence"] == [{
        "digest": hashlib.sha256((workspace / entry).read_bytes()).hexdigest(),
        "code_digest": None, "policy_digest": None,
    }]


def test_projection_digest_must_match_the_chain_committed_digest(tmp_path, monkeypatch):
    """The bar validates its own read of the record; the projection read must
    re-match the chain-committed digest, or the entry is dropped (TOCTOU)."""
    import loop.verdict as verdict

    workspace = _dispatched_workspace(tmp_path)
    entry = ".loop/evidence/evidence-iter1.json"
    emit.terminate(workspace, state="Succeeded", criteria_met={"C-1": True}, evidence=[entry],
                   completion_policy=VERIFIED_EVIDENCE_MODE)
    monkeypatch.setattr(verdict, "_evidence_digests", lambda _entry, _paths: {
        "digest": "f" * 64, "code_digest": None, "policy_digest": None,
    })

    assert verdict.build_verdict(workspace)["evidence"] == []


def test_populated_evidence_validates_against_the_schema(tmp_path):
    """A verdict carrying a non-empty evidence list satisfies verdict.schema.json."""
    jsonschema = pytest.importorskip("jsonschema")
    from loop.verdict import _load_verdict_schema, build_verdict

    workspace = _dispatched_workspace(tmp_path)
    emit.terminate(workspace, state="Succeeded", criteria_met={"C-1": True},
                   evidence=[".loop/evidence/evidence-iter1.json"],
                   completion_policy=VERIFIED_EVIDENCE_MODE)

    verdict = build_verdict(workspace)
    assert verdict["evidence"]
    jsonschema.validate(verdict, _load_verdict_schema())


def test_terminal_record_with_invalid_utf8_raises_verdict_error(tmp_path):
    """An undecodable terminal file must surface as VerdictError, never a raw
    UnicodeDecodeError. Today the doctor_report wrapper converts it (doctor
    raises UnicodeDecodeError, a ValueError); if projection order ever changes,
    _terminal_record's own guard becomes the conversion site - either way the
    typed contract holds, so no message is pinned."""
    from loop.verdict import VerdictError, build_verdict

    target = _workspace_with_terminal(tmp_path)
    (target / ".loop" / "terminal_state.json").write_bytes(b"\xff\xfe{}")

    with pytest.raises(VerdictError):
        build_verdict(target)
