"""scripts/test_doctor_anchor_ancestry.py — the doctor ancestry gate (D3/D5).

`--expect-chain-head` is exact current-head equality, so it fails by construction on
a store that legitimately grew (F3). `--expect-chain-ancestor` asks the cross-run
question instead — "was this digest ever my head?" — established by replay, and
`--anchor` resolves that digest from a tracked anchor@1 file.

An absent, unreadable or empty store with an ancestor supplied FAILS; it never skips.
"""

import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from chain_fixtures import drop_triggers, restore_triggers
from loop.chain import canonical_json, compute_event_hash
from loop.contract import doctor_report
from loop.events import SQLiteEventStore
from loop.scaffold import scaffold

ROOT = Path(__file__).resolve().parent.parent
_EVENT_SCHEMA_ID = "loop-engineer/event@1"
_ANCHOR_CODES = ("chain_anchor_not_ancestor", "anchor_file_unreadable", "anchor_file_invalid")

# Captured from the tree BEFORE the runtime edit that added the ancestry gate, with
# only the genuinely volatile values placeheld (tmp paths, the run's own hashes, and
# the jsonschema-vs-fallback mode fields). Regenerating this after the change would
# pin nothing; it is a literal on purpose.
_PRE_CHANGE_DOCTOR_REPORT = (
    '{"event_store":{"chain":{"head":{"event_hash":"<sha256>","sequence":3},'
    '"unchained_prefix":0},"deterministic":true,"event_count":4,"legal_sequence":true,'
    '"present":true,"readable":true,"run_id":"run-1","state_json_agrees":true},'
    '"issues":[],"lifecycle":"running","ok":true,"paths":"<paths>",'
    '"requested_mode":"auto","schemas_checked":"<schemas>","validation_mode":"<mode>"}'
)
_HEX64 = re.compile(r"[0-9a-f]{64}")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-B", "-m", "loop", *args],
                          cwd=ROOT, text=True, capture_output=True)


def _codes(report):
    return {issue["code"] for issue in report["issues"]}


def _store_path(target):
    return Path(target) / ".loop" / "events.db"


def _sync_state(target, **fields):
    path = Path(target) / ".loop" / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state.update(fields)
    path.write_text(json.dumps(state), encoding="utf-8")


def _chained_workspace(tmp_path, name="workspace"):
    """A synced workspace over a 4-event chained store (spliceable middle)."""
    target = tmp_path / name
    scaffold(target)
    store = SQLiteEventStore(_store_path(target))
    store.append("run-1", "contract_opened", {"workspace": name}, actor="test")
    store.append("run-1", "iteration_appended", {"iteration_id": 1, "outcome": "task_failed"}, actor="test")
    store.append("run-1", "iteration_appended", {"iteration_id": 2, "outcome": "task_passed"}, actor="test")
    store.append("run-1", "receipt_appended",
                 {"iteration_id": 2, "role": "write", "model": "test-model", "outcome": "ok"}, actor="test")
    _sync_state(target, iteration_id=2, active_task=None)
    return target


def _grow(target, iterations=(3, 4)):
    """Append more chained events, keeping the contract doctor-clean."""
    store = SQLiteEventStore(_store_path(target))
    for iteration_id in iterations:
        store.append("run-1", "iteration_appended",
                     {"iteration_id": iteration_id, "outcome": "task_passed"}, actor="test")
    _sync_state(target, iteration_id=iterations[-1])
    return _head(target)


def _head(target):
    return ((doctor_report(target)["event_store"]["chain"] or {}).get("head") or {}).get("event_hash")


def _record_at(conn, sequence, prev_event_hash):
    row = conn.execute(
        "SELECT run_id, sequence, event_id, type, actor, causation_id, correlation_id, ts, "
        "payload, artifact_hashes FROM events WHERE sequence = ?", (sequence,)).fetchone()
    return {"schema": _EVENT_SCHEMA_ID, "run_id": row[0], "sequence": row[1], "event_id": row[2],
            "type": row[3], "actor": row[4], "causation_id": row[5], "correlation_id": row[6],
            "ts": row[7], "payload": json.loads(row[8]), "artifact_hashes": json.loads(row[9]),
            "prev_event_hash": prev_event_hash}


def _rewrite_history(target, *, forge_event_hash_at=None, forged_digest=None):
    """The competent adversary: rewrite payloads and re-chain from genesis.

    With forge_event_hash_at, additionally plant `forged_digest` in one row's
    event_hash column WITHOUT recomputing — the attack only replay refuses.
    """
    store_path = _store_path(target)
    drop_triggers(store_path)
    conn = sqlite3.connect(str(store_path))
    try:
        conn.execute("UPDATE events SET payload = replace(payload, '\"task_failed\"', "
                     "'\"task_passed\"') WHERE type = 'iteration_appended'")
        prev = None
        for row in conn.execute("SELECT sequence FROM events ORDER BY sequence ASC").fetchall():
            record = _record_at(conn, row[0], prev)
            digest = compute_event_hash(record)
            conn.execute("UPDATE events SET prev_event_hash = ?, event_hash = ? WHERE sequence = ?",
                         (prev, digest, row[0]))
            prev = digest
        if forge_event_hash_at is not None:
            conn.execute("UPDATE events SET event_hash = ? WHERE sequence = ?",
                         (forged_digest, forge_event_hash_at))
        conn.commit()
    finally:
        conn.close()
    restore_triggers(store_path)


def _write_anchor(path, head, **extra):
    document = {"schema": "loop-engineer/anchor@1", "chain_head": head, **extra}
    Path(path).write_text(json.dumps(document), encoding="utf-8")
    return path


# --- the ancestry gate itself -------------------------------------------------


def test_ancestor_flag_passes_when_the_anchored_head_is_in_the_chain(tmp_path):
    ws = _chained_workspace(tmp_path)
    report = doctor_report(ws, expect_chain_ancestor=_head(ws))
    assert report["ok"] is True
    assert not _codes(report) & set(_ANCHOR_CODES)


def test_ancestor_flag_passes_after_the_chain_grew(tmp_path):
    ws = _chained_workspace(tmp_path)
    anchored = _head(ws)
    grown = _grow(ws)
    assert grown != anchored
    report = doctor_report(ws, expect_chain_ancestor=anchored)
    assert report["ok"] is True, report["issues"]
    assert report["event_store"]["anchor"] == {"expected": anchored, "sequence": 3}


def test_expect_chain_head_fails_on_the_same_grown_store(tmp_path):
    """F3, mechanical: the negative control proving ancestry is strictly more useful."""
    ws = _chained_workspace(tmp_path)
    anchored = _head(ws)
    _grow(ws)
    report = doctor_report(ws, expect_chain_head=anchored)
    assert report["ok"] is False
    assert "chain_anchor_mismatch" in _codes(report)


def test_ancestor_flag_fails_with_chain_anchor_not_ancestor_on_an_unknown_head(tmp_path):
    ws = _chained_workspace(tmp_path)
    report = doctor_report(ws, expect_chain_ancestor="b" * 64)
    assert report["ok"] is False
    assert "chain_anchor_not_ancestor" in _codes(report)


def test_ancestry_detects_a_wholesale_rewrite_that_self_verifies_clean(tmp_path):
    """D10.4: history rewritten, re-chained from genesis, then grown. The chain alone
    reports nothing — the anchored ancestor is the only control left."""
    ws = _chained_workspace(tmp_path)
    anchored = _head(ws)
    _rewrite_history(ws)
    _grow(ws)
    unanchored = doctor_report(ws)
    assert "event_chain_broken" not in _codes(unanchored)          # PINNED LIMITATION
    assert unanchored["event_store"]["chain"]["head"] is not None
    anchored_report = doctor_report(ws, expect_chain_ancestor=anchored)
    assert "chain_anchor_not_ancestor" in _codes(anchored_report)


def test_ancestry_refuses_a_forged_row_bearing_the_anchored_digest_end_to_end(tmp_path):
    """D10.5 at doctor level: the rewrite plants the anchored digest in a row's
    event_hash column. A column-trusting gate would call that ancestry satisfied."""
    ws = _chained_workspace(tmp_path)
    anchored = _head(ws)
    _rewrite_history(ws, forge_event_hash_at=1, forged_digest=anchored)
    with sqlite3.connect(str(_store_path(ws))) as conn:
        planted = conn.execute("SELECT event_hash FROM events WHERE sequence = 1").fetchone()[0]
    assert planted == anchored, "the forged column must really carry the anchored digest"
    report = doctor_report(ws, expect_chain_ancestor=anchored)
    assert "chain_anchor_not_ancestor" in _codes(report)
    assert report["ok"] is False


# --- D5: never skip ----------------------------------------------------------


def test_absent_store_with_an_ancestor_fails_and_never_skips(tmp_path):
    target = tmp_path / "storeless"
    scaffold(target)
    report = doctor_report(target, expect_chain_ancestor="b" * 64)
    assert report["event_store"]["present"] is False
    assert "chain_anchor_not_ancestor" in _codes(report)
    assert report["ok"] is False


def test_unreadable_store_with_an_ancestor_fails_and_never_skips(tmp_path):
    ws = _chained_workspace(tmp_path)
    _store_path(ws).write_bytes(b"this is not a sqlite database")
    report = doctor_report(ws, expect_chain_ancestor="b" * 64)
    codes = _codes(report)
    assert "chain_anchor_not_ancestor" in codes
    assert codes & {"corrupt_store", "invalid_event", "ambiguous_run_id"}
    assert report["event_store"]["readable"] is False


def test_empty_store_with_an_ancestor_fails_and_never_skips(tmp_path):
    target = tmp_path / "emptystore"
    scaffold(target)
    # A read materializes the DDL (the constructor alone does not touch the disk),
    # leaving a real but eventless store — distinct from an absent one.
    SQLiteEventStore(_store_path(target)).read("run-1")
    assert _store_path(target).exists()
    report = doctor_report(target, expect_chain_ancestor="b" * 64)
    codes = _codes(report)
    assert "chain_anchor_not_ancestor" in codes
    assert "empty_store" in codes


def test_ancestor_code_is_distinct_from_chain_anchor_mismatch(tmp_path):
    """D3: 'your head is not what I expected' and 'the head you anchored is not in my
    history at all' are different facts; one shared code would collapse them."""
    ws = _chained_workspace(tmp_path)
    anchored = _head(ws)
    _grow(ws)
    report = doctor_report(ws, expect_chain_head=anchored, expect_chain_ancestor=anchored)
    codes = _codes(report)
    assert "chain_anchor_mismatch" in codes
    assert "chain_anchor_not_ancestor" not in codes


# --- --anchor resolution (CLI layer) -----------------------------------------


def test_anchor_file_resolves_the_expected_ancestor(tmp_path):
    ws = _chained_workspace(tmp_path)
    anchored = _head(ws)
    _grow(ws)
    anchor = _write_anchor(tmp_path / "loop-anchor.json", anchored, sequence=3)
    resolved = _run("doctor", "--anchor", str(anchor), str(ws))
    explicit = _run("doctor", "--expect-chain-ancestor", anchored, str(ws))
    assert resolved.returncode == 0, resolved.stderr
    assert json.loads(resolved.stdout) == json.loads(explicit.stdout)


def test_unreadable_anchor_file_fails_with_anchor_file_unreadable(tmp_path):
    ws = _chained_workspace(tmp_path)
    result = _run("doctor", "--anchor", str(tmp_path / "absent.json"), str(ws))
    assert result.returncode == 1, result.stderr          # a report, not exit 2
    assert "anchor_file_unreadable" in _codes(json.loads(result.stdout))


def test_invalid_anchor_file_fails_with_anchor_file_invalid(tmp_path):
    ws = _chained_workspace(tmp_path)
    anchor = tmp_path / "loop-anchor.json"
    anchor.write_text(json.dumps({"schema": "loop-engineer/anchor@1"}), encoding="utf-8")
    result = _run("doctor", "--anchor", str(anchor), str(ws))
    assert result.returncode == 1, result.stderr
    assert "anchor_file_invalid" in _codes(json.loads(result.stdout))


@pytest.mark.parametrize("flavor", ["unreadable", "invalid"])
def test_anchor_file_failure_emits_a_full_doctor_report_shape(tmp_path, flavor):
    """Design rule 6's pinned shape: a consumer parsing validation_mode or
    event_store must not crash on the anchor-failure path."""
    ws = _chained_workspace(tmp_path)
    anchor = tmp_path / "loop-anchor.json"
    if flavor == "invalid":
        anchor.write_text('{"schema":"loop-engineer/anchor@1","chain_head":"nope"}', encoding="utf-8")
    result = _run("doctor", "--anchor", str(anchor), str(ws))
    report = json.loads(result.stdout)
    assert set(report) == {"paths", "ok", "validation_mode", "requested_mode",
                          "schemas_checked", "lifecycle", "issues", "event_store"}
    assert report["ok"] is False
    assert len(report["issues"]) == 1
    assert report["issues"][0]["code"] == f"anchor_file_{flavor}"
    # No digest was ever resolved, so the gate was asked nothing: one failure, one code.
    assert "chain_anchor_not_ancestor" not in _codes(report)
    assert "anchor" not in report["event_store"]


# --- the §22 habit: no flag, no change ---------------------------------------


def test_doctor_report_is_byte_identical_when_no_anchor_flag_is_supplied(tmp_path):
    def normalize(value, key=None):
        if key in ("paths", "schemas_checked", "validation_mode"):
            return {"paths": "<paths>", "schemas_checked": "<schemas>",
                    "validation_mode": "<mode>"}[key]
        if isinstance(value, dict):
            return {k: normalize(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [normalize(v) for v in value]
        if isinstance(value, str) and _HEX64.fullmatch(value):
            return "<sha256>"
        return value

    ws = _chained_workspace(tmp_path)
    assert canonical_json(normalize(doctor_report(ws))) == _PRE_CHANGE_DOCTOR_REPORT


def test_anchor_block_appears_only_when_an_ancestor_was_supplied(tmp_path):
    ws = _chained_workspace(tmp_path)
    assert "anchor" not in doctor_report(ws)["event_store"]
    supplied = doctor_report(ws, expect_chain_ancestor=_head(ws))["event_store"]["anchor"]
    assert set(supplied) == {"expected", "sequence"}


def test_expect_chain_head_and_expect_chain_ancestor_compose(tmp_path):
    """Equality and ancestry are different questions; both may be asked."""
    ws = _chained_workspace(tmp_path)
    anchored = _head(ws)
    grown = _grow(ws)
    both_satisfied = doctor_report(ws, expect_chain_head=grown, expect_chain_ancestor=anchored)
    assert both_satisfied["ok"] is True, both_satisfied["issues"]
    both_violated = doctor_report(ws, expect_chain_head="f" * 64, expect_chain_ancestor="e" * 64)
    assert _codes(both_violated) >= {"chain_anchor_mismatch", "chain_anchor_not_ancestor"}


# --- CLI guards --------------------------------------------------------------


def test_anchor_and_expect_chain_ancestor_are_mutually_exclusive(tmp_path):
    ws = _chained_workspace(tmp_path)
    anchor = _write_anchor(tmp_path / "loop-anchor.json", _head(ws))
    result = _run("doctor", "--anchor", str(anchor),
                  "--expect-chain-ancestor", _head(ws), str(ws))
    assert result.returncode == 2
    assert result.stdout == ""
    assert "mutually exclusive" in result.stderr


@pytest.mark.parametrize("command", ["scaffold", "verdict", "status"])
def test_ancestor_flag_rejected_for_non_doctor_commands(tmp_path, command):
    target = tmp_path / f"{command}-target"
    result = _run(command, "--expect-chain-ancestor", "a" * 64, str(target))
    assert result.returncode == 2
    assert "--expect-chain-ancestor is only valid for doctor" in result.stderr
    # scaffold resolves a relative target against its CWD, so an unguarded flag
    # creates the directory HERE, not under tmp_path.
    assert not (ROOT / "--expect-chain-ancestor").exists()


@pytest.mark.parametrize("command", ["scaffold", "verdict", "status"])
def test_anchor_flag_rejected_for_non_doctor_commands(tmp_path, command):
    target = tmp_path / f"{command}-target"
    result = _run(command, "--anchor", str(tmp_path / "loop-anchor.json"), str(target))
    assert result.returncode == 2
    assert "--anchor is only valid for doctor" in result.stderr
    assert not (ROOT / "--anchor").exists()


@pytest.mark.parametrize("value", ["A" * 64, "a" * 63, "a" * 65, "z" * 64])
def test_expect_chain_ancestor_must_be_64_lowercase_hex(tmp_path, value):
    ws = _chained_workspace(tmp_path)
    result = _run("doctor", "--expect-chain-ancestor", value, str(ws))
    assert result.returncode == 2
    assert "64-character lowercase hex" in result.stderr


def test_anchor_resolution_works_in_release_mode(tmp_path):
    pytest.importorskip("jsonschema")
    ws = _chained_workspace(tmp_path)
    anchor = _write_anchor(tmp_path / "loop-anchor.json", _head(ws))
    result = _run("doctor", "--mode", "release", "--anchor", str(anchor), str(ws))
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["validation_mode"] == "jsonschema"
    # The anchor must have been CONSUMED and resolved, not silently ignored.
    assert report["event_store"]["anchor"]["expected"] == _head(ws)


def test_new_doctor_codes_match_the_public_issue_code_pattern():
    """Doctor issue codes are the population verdict.doctor.issue_codes is drawn
    from — a permanent, public, append-only log."""
    for code in _ANCHOR_CODES:
        assert re.fullmatch(r"[a-z0-9_]{1,64}", code), code
