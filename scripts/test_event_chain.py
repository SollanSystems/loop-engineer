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
