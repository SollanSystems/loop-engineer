"""scripts/test_chain_ancestry.py — head_sequence: ancestry established by replay.

D3: --expect-chain-head is exact current-head equality, so feeding run N's head to
run N+1 fails by construction on any growing store. The meaningful cross-run check
is "the previously attested head still appears in my chain" — and it is established
by REPLAY (recomputing every hash), never by trusting the stored event_hash column.
"""
from types import MappingProxyType

import pytest

from loop.chain import compute_event_hash, head_sequence, verify_chain


def _record(**overrides):
    base = {
        "schema": "loop-engineer/event@1", "event_id": "e1", "run_id": "r1",
        "sequence": 0, "type": "contract_opened", "actor": "operator",
        "causation_id": None, "correlation_id": None, "ts": "2026-07-24T00:00:00+00:00",
        "payload": {"workspace": "ws"}, "artifact_hashes": [], "prev_event_hash": None,
    }
    base.update(overrides)
    return base


def _chain(count, *, run_id="r1"):
    """A well-formed chained stream of `count` events, sequence 0..count-1."""
    events = []
    prev = None
    for seq in range(count):
        record = _record(sequence=seq, event_id=f"e{seq}", run_id=run_id,
                         prev_event_hash=prev)
        record["event_hash"] = compute_event_hash(record)
        prev = record["event_hash"]
        events.append(record)
    return events


def test_head_sequence_finds_the_current_head():
    events = _chain(4)
    assert head_sequence(events, events[3]["event_hash"]) == 3


def test_head_sequence_finds_an_earlier_head_after_the_chain_grew():
    events = _chain(7)
    anchored = events[3]["event_hash"]
    # The whole point: the anchored head is still an ancestor after 4-6 were appended,
    # while exact head equality (verify_chain's expected_head) fails by construction.
    assert head_sequence(events[:4], anchored) == 3
    assert head_sequence(events, anchored) == 3
    assert events[6]["event_hash"] != anchored
    assert verify_chain(events, expected_head=anchored)["ok"] is False


def test_head_sequence_returns_none_for_an_unknown_digest():
    assert head_sequence(_chain(3), "b" * 64) is None


def test_head_sequence_returns_none_for_an_empty_stream():
    assert head_sequence([], "b" * 64) is None


def test_head_sequence_ignores_an_unchained_prefix():
    # A migrated store: legacy rows carry event_hash None, then chaining begins.
    legacy = [_record(sequence=seq, event_id=f"legacy-e{seq}") for seq in range(2)]
    for record in legacy:
        record["event_hash"] = None
    chained = []
    prev = None
    for seq in (2, 3, 4):
        record = _record(sequence=seq, event_id=f"e{seq}", prev_event_hash=prev)
        record["event_hash"] = compute_event_hash(record)
        prev = record["event_hash"]
        chained.append(record)
    events = [*legacy, *chained]
    report = verify_chain(events)
    assert report["ok"] is True and report["unchained_prefix"] == 2
    # The prefix contributes no sequence and does not abort the walk.
    assert head_sequence(events, chained[0]["event_hash"]) == 2
    assert head_sequence(events, chained[2]["event_hash"]) == 4


def test_head_sequence_recomputes_and_refuses_a_forged_event_hash_column():
    # D10.5: a tamperer who can rewrite the store can also insert a row bearing the
    # anchored digest. Only recomputation refuses that row.
    events = _chain(4)
    anchored = "c" * 64
    events[2]["event_hash"] = anchored          # forged column, hash NOT recomputed
    assert head_sequence(events, anchored) is None


def test_head_sequence_stops_at_a_broken_link():
    events = _chain(5)
    later_head = events[4]["event_hash"]
    earlier_head = events[0]["event_hash"]
    events[1] = dict(events[1], prev_event_hash="a" * 64)   # splice, hash left stale
    # The walk stops exactly where verify_chain stops.
    report = verify_chain(events)
    assert report["ok"] is False and "sequence 1" in report["issues"][0]
    assert head_sequence(events, later_head) is None
    assert head_sequence(events, earlier_head) == 0


def test_head_sequence_accepts_any_ordered_mapping_sequence():
    # The module's portability contract: works over any ordered Mapping stream
    # (a JSONL export), no store and no dict-specific behavior involved.
    events = tuple(MappingProxyType(record) for record in _chain(3))
    assert head_sequence(events, events[2]["event_hash"]) == 2
    assert head_sequence(iter(events), events[1]["event_hash"]) == 1


def test_head_sequence_finds_the_digest_at_sequence_zero():
    # The boundary a `if seq:` truth test would silently swallow: 0 is a legitimate
    # ancestor, so callers must compare against None, never truthiness.
    events = _chain(3)
    found = head_sequence(events, events[0]["event_hash"])
    assert found == 0
    assert found is not None


def test_head_sequence_refuses_a_malformed_digest_argument():
    # A silent None on a typo would read as "rewrite detected". Exactly ValueError —
    # NOT ChainHashError, which its own docstring scopes to canonicalization failures.
    # Because ChainHashError IS a ValueError, a bare pytest.raises(ValueError) would
    # pass for either class and pin nothing.
    malformed = ["A" * 64, "a" * 63, "a" * 65, "z" * 64, "", None, 42]
    for digest in malformed:
        with pytest.raises(ValueError) as excinfo:
            head_sequence(_chain(2), digest)
        assert type(excinfo.value) is ValueError, digest
