"""scripts/test_event_chain.py — chain canonicalization, store chaining, migration."""
import pytest

from loop.chain import ChainHashError, canonical_json, compute_event_hash


def _record(**overrides):
    base = {
        "schema": "loop-engineer/event@1", "event_id": "e1", "run_id": "r1",
        "sequence": 0, "type": "contract_opened", "actor": "operator",
        "causation_id": None, "correlation_id": None, "ts": "2026-07-24T00:00:00+00:00",
        "payload": {"workspace": "ws"}, "artifact_hashes": [], "prev_event_hash": None,
    }
    base.update(overrides)
    return base


def test_canonical_json_is_compact_sorted_utf8():
    assert canonical_json({"b": 1, "a": [1, "é"]}) == '{"a":[1,"é"],"b":1}'


def test_canonical_json_rejects_non_finite_floats():
    with pytest.raises(ChainHashError):
        canonical_json({"x": float("nan")})


def test_canonical_json_rejects_lone_surrogates():
    with pytest.raises(ChainHashError):
        canonical_json({"x": "\ud800"})


def test_canonical_json_rejects_non_json_values():
    with pytest.raises(ChainHashError):
        canonical_json({"x": object()})


def test_event_hash_is_stable_and_key_order_independent():
    a = _record()
    b = dict(reversed(list(_record().items())))
    assert compute_event_hash(a) == compute_event_hash(b)
    assert len(compute_event_hash(a)) == 64


def test_event_hash_excludes_event_hash_but_includes_prev_and_ts_and_actor():
    base = _record()
    with_own_hash = dict(base, event_hash="f" * 64)
    assert compute_event_hash(base) == compute_event_hash(with_own_hash)
    assert compute_event_hash(base) != compute_event_hash(dict(base, prev_event_hash="a" * 64))
    assert compute_event_hash(base) != compute_event_hash(dict(base, ts="2026-07-25T00:00:00+00:00"))
    assert compute_event_hash(base) != compute_event_hash(dict(base, actor="worker"))


def test_event_hash_treats_absent_optionals_as_null():
    explicit = _record()
    implicit = {k: v for k, v in _record().items()
                if k not in ("causation_id", "correlation_id", "prev_event_hash")}
    assert compute_event_hash(explicit) == compute_event_hash(implicit)


from loop.chain import link_issue, verify_chain


def _chained(seq, prev_hash, **overrides):
    rec = _record(sequence=seq, event_id=f"e{seq}", prev_event_hash=prev_hash,
                  type="iteration_appended" if seq else "contract_opened",
                  payload={"iteration_id": seq, "outcome": "task_passed"} if seq else {"workspace": "ws"})
    rec.update(overrides)
    rec["event_hash"] = compute_event_hash(rec)
    return rec


def test_link_issue_genesis_requires_null_prev():
    assert link_issue(_chained(0, None), None) is None
    assert "prev_event_hash mismatch" in link_issue(_chained(0, "a" * 64), None)


def test_link_issue_detects_recompute_mismatch():
    rec = _chained(0, None)
    rec["payload"] = {"workspace": "tampered"}
    assert "event_hash mismatch" in link_issue(rec, None)


def test_link_issue_unchained_after_chained_is_a_break_and_names_the_likely_cause():
    head = {"sequence": 0, "event_hash": "b" * 64}
    unchained = _record(sequence=1, event_id="e1")
    message = link_issue(unchained, head)
    assert "unchained event after chained prefix" in message
    assert "pre-0.10.0 writer" in message           # self-diagnosing per design change D1
    assert link_issue(unchained, None) is None


def test_verify_chain_happy_path_and_head():
    e0 = _chained(0, None)
    e1 = _chained(1, e0["event_hash"])
    report = verify_chain([e0, e1])
    assert report["ok"] and report["chained_events"] == 2 and report["unchained_prefix"] == 0
    assert report["head"] == {"sequence": 1, "event_hash": e1["event_hash"]}


def test_verify_chain_legacy_prefix_then_genesis():
    legacy = _record(sequence=0)          # no event_hash key at all
    e1 = _chained(1, None)                # genesis after unchained prefix
    report = verify_chain([legacy, e1])
    assert report["ok"] and report["unchained_prefix"] == 1 and report["chained_events"] == 1


def test_verify_chain_detects_splice():
    e0 = _chained(0, None)
    e1 = _chained(1, e0["event_hash"])
    forged = dict(e1, payload={"iteration_id": 1, "outcome": "task_failed"})
    forged["event_hash"] = compute_event_hash(forged)   # recomputed own hash...
    e2 = _chained(2, e1["event_hash"])                  # ...but successor cites the original
    report = verify_chain([e0, forged, e2])
    assert not report["ok"] and any("prev_event_hash mismatch" in i for i in report["issues"])


def test_verify_chain_reports_first_record_failure_without_counting_it():
    bad = _chained(0, "a" * 64)                          # bad genesis
    report = verify_chain([bad])
    assert not report["ok"] and report["chained_events"] == 0
    assert report["unchained_prefix"] == 0 and report["head"] is None


def test_verify_chain_truncation_needs_expected_head():
    e0 = _chained(0, None)
    e1 = _chained(1, e0["event_hash"])
    assert verify_chain([e0])["ok"]                      # honest limit: shorter valid chain verifies
    report = verify_chain([e0], expected_head=e1["event_hash"])
    assert not report["ok"] and any("chain head" in i for i in report["issues"])


def test_verify_chain_reports_missing_head_when_anchor_supplied_on_unchained_stream():
    report = verify_chain([_record(sequence=0)], expected_head="a" * 64)
    assert not report["ok"] and any("no chained events" in i for i in report["issues"])
