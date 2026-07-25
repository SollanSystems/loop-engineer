# Hash-Linked Event Chain (Tamper-Evident Provenance, Slice 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every event@1 store a per-run SHA-256 hash chain with an externally anchorable head, a hard doctor gate on chain breaks, an explicit `loop migrate` path for legacy stores, and honestly documented limits — closing the "the worker can just rewrite events.db" objection before the Show HN launch.

**Architecture:** A new pure leaf module `loop/chain.py` owns canonical-JSON hashing and incremental link verification; `SQLiteEventStore.append` computes `prev_event_hash`/`event_hash` store-side inside the existing BEGIN IMMEDIATE transaction; the reducer enforces the chain at fold time (the single chokepoint all folding verbs pass through) via a typed `ChainBreakError`; doctor surfaces chain health nested under its existing `event_store` key and gains an `--expect-chain-head` anchor comparison; the GitHub Action records the head in the job step summary and as a declared action output — a medium the in-loop worker cannot rewrite.

**Tech Stack:** Python 3.10+ stdlib only (`hashlib`, `json`, `sqlite3`). No new runtime dependencies. Tests via pytest under `uv run`.

**Baseline (fresh worktree, main @ `c39a909` / v0.9.0):** 933 passed / 16 skipped with `[schemas,yaml]` extras; 864 / 85 pyyaml-only. Live checkout reads +2/−2 (two checked-when-present tests). All zero-regression claims are against the **fresh-worktree** numbers.

**Review status:** this plan was adversarially reviewed by three lenses (design-lint, kernel-reality, threat-honesty) before execution; 2 BLOCKERs, 17 MAJORs, 9 MINORs and 1 NIT were applied. The changes that altered the *design* (not just the prose) are listed in "Post-review design changes" below.

## Global Constraints

- **Zero new runtime dependencies.** `loop/` imports stdlib only; `pyproject.toml` `[project.optional-dependencies]` stays exactly `yaml`, `schemas`, `dev`.
- **event@1 stays event@1.** `schemas/event.schema.json` `required` is untouched; new fields are optional and `["string","null"]`-typed. Both validation modes get parity type checks (repo-os-contract.md §16 commits to fallback parity).
- **Absent-store doctor byte-stability is preserved.** With no store, no sidecars, and no `--expect-chain-head`, `doctor_report` stays byte-identical to `validate_contract` for every key except `event_store` (`scripts/test_doctor_eventstore.py:62-67` pins this).
- **Read verbs stay read-only.** `status`/`replay`/`simulate`/`doctor` gain no writes; migration is a new explicitly write-classed verb. The zero-write tree-hash proofs (`scripts/test_loop_simulate_zero_writes.py`, `scripts/test_loop_architect_cli.py:142-146`) must pass on both store generations.
- **Legacy stores must never regress to `corrupt_store`.** A v0.9.0 store with no chain columns stays doctor-`ok` (if it was ok) and reports an explicit unchained state — never a silent pass, never a false failure.
- **Chain fields are store-computed, never caller-supplied.**
- **Typed fail-loud everywhere.** Every new error path exits 2 with a typed message and no traceback; no new code path may "skip" on error (the R007 lesson: an errored verifier must FAIL, not skip).
- **Honest framing is part of the deliverable.** Docs and CHANGELOG must state what the chain does NOT protect against: full in-workspace recompute without an anchor, chain-column downgrade, store deletion, well-formed lies in payloads, the never-migrated prefix, and **the mid-run window** (an anchor certifies the log only up to the anchored head). "Tamper-proof" is forbidden; "tamper-evident relative to an anchored head" is the claim.
- **`evals/cases/structural.json` is untouched** (no new skill/reference/template/schema *file*). New modules and test files are not pinned there.
- **Version bumps live only in the release-cut PR** (Task 15): pyproject + plugin.json + README version surfaces + `scripts/test_docs_version.py` + CHANGELOG move together.
- Repo env quirks: no system pytest — run tests via `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider ...`; the Bash deny-list blocks `rm`, bare `cd`, `VAR=` prefixes, `timeout`, `printf`, `source` — use `git -C`, absolute paths, `bash -c`.

---

## Program context (what this plan is Slice 1 of)

Source: `review/2026-07-24-graph-engineering-report-assessment.md` (adjudication of an external "graph engineering" report; 32/32 repo claims confirmed, 6 proposal blockers). The accepted program is **tamper-evident provenance** — the "graph engineering" framing itself was rejected.

| Slice | Scope contract | Own plan authored when |
|---|---|---|
| **1 (this plan)** | Hash-linked chain, `loop migrate`, doctor chain gate + `--expect-chain-head`, absent-store hardening, downgrade cross-check, sidecar-residue fix, CI head anchor, honest-limitation tests/docs. Ships as **v0.10.0**. | now |
| 2 | Verifier identity + independence: `verified_by.code_digest`/`policy_digest` on evidence@1 (runner hashes the verify script it actually executed), `produced_by.executor == verified_by.by` becomes a doctor-surfaced anti-cheat finding, held-out/visible criterion partition recorded in verify bundles. | after Slice 1 lands |
| 3 | Wire evidence@1 into writer + doctor (the §17 deferral): emit writes hashed evidence records + content-addressed objects via `artifact_object_path`; doctor hash-verifies evidence referenced by criteria; `Succeeded` tightens from non-empty paths to hash-verified evidence. | after Slice 2 |
| 4 | CI-attested verdict: action.yml emits a verdict JSON (doctor ok, chain head, evidence digests, commit sha) in in-toto Statement shape, attested keyless via GitHub OIDC. No signing code in the kernel; needs its own ADR (reverses ADR 0001 non-goal). | after Slice 3 |
| 5 | Docs/interop pass: Mermaid FSM + event→projection diagrams in reference/docs only (PyPI does not render Mermaid in README), W3C trace-context-as-data note, JSONL-export + Cypher-import recipe doc. | anytime post-launch |

Rejected permanently (do not resurrect): `graph` CLI verbs + query DSL, FastAPI HTTP API/SDK, Neo4j/Qdrant integrations, unanchored Merkle checkpoints, local DSSE/HMAC signing.

**Launch gate (operator decision, not this plan's):** Slice 1 is the only pre-launch item and is timeboxed — if it does not land clean within a few days, post Show HN on v0.9.0 as-is and ship the chain as a visible fast follow.

---

## Design decisions (binding)

1. **Canonicalization:** `json.dumps(value, sort_keys=True, separators=(",",":"), ensure_ascii=False, allow_nan=False)` encoded UTF-8. Key sort is code-point order; all current keys are ASCII and the docs pin that recommendation. Non-finite floats, non-JSON values and lone surrogates raise typed `ChainHashError`. Finite floats are allowed (receipt payloads carry `cost_usd`); Python shortest-repr float formatting is the pinned behavior, documented as a cross-language caveat.
2. **Preimage:** the 12 fields `schema, run_id, sequence, event_id, type, actor, ts, causation_id, correlation_id, payload, artifact_hashes, prev_event_hash` — always all 12, absent optionals materialized as `null`. `event_hash` itself is excluded. `prev_event_hash` inside makes it a chain; `ts` and `actor` inside make history rewrites break it.
3. **Genesis rule:** the first *chained* event in a run has `prev_event_hash = null` — whether it is sequence 0 (fresh store) or the first post-migration append (legacy prefix). `null` is the only root convention; all-zeros is invalid.
4. **Store generations:** detected by column presence (`PRAGMA table_info(events)` contains `event_hash`). Fresh stores are created with chain columns and `PRAGMA user_version = 2`; **on fresh stores `event_hash` is `NOT NULL`** (see design change D1) so a pre-0.10.0 writer cannot silently append an unchained row. Legacy stores keep working unchanged: append writes 10-column rows, reads project both hash fields as `None`. `loop migrate` is the only upgrade path (`ALTER TABLE ADD COLUMN` — works despite the append-only triggers; `UPDATE` backfill is trigger-blocked and deliberately impossible, so migrated columns are nullable).
5. **Enforcement point:** the reducer. `chain.link_issue()` runs per event inside `_reduce_one`; a violation raises `ChainBreakError(EventReplayError)`. Every folding verb refuses broken chains. **All four folding surfaces report the same code `event_chain_broken`**: `runtime.status_report`/`replay_report` map it directly, and `runner._projection` maps it *before* its generic `except ValueError` (which would otherwise relabel it `invalid_event_stream` — see design change D3).
6. **Doctor surface:** chain health nests under the existing `event_store` key (`{"chain": {"head": {...}|null, "unchained_prefix": N}}`). New issue codes: `event_chain_broken`, `chain_anchor_mismatch`, `missing_event_store`, `chain_columns_missing`. The absent-store shape `{"present": false}` is unchanged when no sidecars and no anchor flag.
7. **Anchor:** `loop doctor --expect-chain-head <64-hex>` fails hard when the store is missing, unreadable, has no chained head, or the head differs. The action records the head in `$GITHUB_STEP_SUMMARY` **and** as a declared composite-action output, on success *and* failure. The docs carry the anchor's trust assumptions explicitly (Task 13 Step 2b).
8. **Shared row reader:** the three duplicated SELECT sites collapse onto one `read_event_rows(conn, run_id, *, since_sequence=None)` in `loop/events.py` that feature-detects columns **and owns the JSON-decode error translation** all three sites perform today.
9. **Two pre-existing defects fixed in-scope:** (a) `runtime._events` discards per-event validation verdicts — now a failing event raises `RuntimeStoreError("invalid_event", ...)`, matching `runner._projection`; the `assert validation is not None` (evaporates under `python -O`) becomes a typed error. (b) `runtime.py` read connections adopt the conditional immutable-URI pattern so read verbs stop leaving `-wal`/`-shm` sidecars (the PR #77 H4b finding) — with a single plain-`mode=ro` retry so a concurrent writer cannot produce a false `corrupt_store` (design change D4).
10. **Feature PR vs release-cut PR:** Tasks 1–14 land as one feature PR (no version changes). Task 15 is a separate release-cut PR.

### Post-review design changes (added after adversarial review)

- **D1 — `event_hash NOT NULL` on fresh stores.** A pre-0.10.0 `SQLiteEventStore.append` INSERTs 10 columns; against a chained store that leaves NULL hashes, which the reducer reads as "unchained event after chained prefix" → permanent, unrepairable `event_chain_broken` (UPDATE is trigger-blocked). A false tamper alarm damages the brand as much as a false pass. `NOT NULL` on fresh stores makes the old-writer INSERT fail closed at the DB. Migrated stores cannot use `NOT NULL` (legacy rows are NULL), so for them the hazard is handled by a self-diagnosing message + a documented compatibility rule.
- **D2 — `chain_columns_missing` downgrade cross-check.** SQLite ≥3.35 (this env: 3.45.1) supports `ALTER TABLE events DROP COLUMN event_hash`: one statement converts a chained history into a doctor-clean "legacy" store. Doctor now fails when `PRAGMA user_version >= 2` but the columns are absent. This only catches the lazy downgrade (resetting `user_version`, or drop-then-`loop migrate`, is indistinguishable from an honest legacy store) — the anchor remains the only real control, and the docs must say so.
- **D3 — `runner._projection` maps `ChainBreakError` first**, so `run`/`simulate`/run-control verbs report `event_chain_broken`, not `invalid_event_stream`.
- **D4 — shared `_read_only_connect` with one retry.** `immutable=1` tells SQLite the file cannot change; a concurrent append mid-read can surface as `SQLITE_CORRUPT` → a false `corrupt_store` alarm from a monitoring verb. Retry once with plain `mode=ro`: real corruption fails both attempts, a lost race succeeds on the second.
- **D5 — `read_event_rows` owns JSON-decode translation** via typed `EventRowDecodeError`, preserving the "corrupt store fails doctor without a traceback" invariant for in-row payload corruption (a class no existing test covers).
- **D6 — honest-limitation tests assert the CHAIN predicate, not global `doctor ok`.** Doctor also runs `_state_divergence` and `_terminal_desync`, so a global-`ok` assertion either fails for unrelated reasons or passes while pinning nothing.
- **D7 — shared test fixture module `scripts/chain_fixtures.py`.** Four test files need a byte-identical legacy-store builder; duplicating the DDL recreates exactly the lockstep hazard decision 8 removes. The wheel force-includes scripts individually (`pyproject.toml:44-48`), so a test-only helper does not ship.

## File structure

| File | Change | Responsibility |
|---|---|---|
| `loop/chain.py` | **create** | Pure canonical-JSON + hash + link verification. stdlib only, imports nothing from `loop.*`. |
| `loop/migrate.py` | **create** | Explicit legacy→v2 store migration. |
| `loop/events.py` | modify | DDL + fresh-store versioning/NOT NULL, shared `read_event_rows`, chain computation in `append`, typed error surface, structural parity checks. |
| `loop/reducer.py` | modify | `ChainBreakError`, per-event chain enforcement, `chain_head`/`unchained_prefix` in the projection. |
| `loop/runtime.py` | modify | `_read_only_connect`, validation-verdict enforcement, `event_chain_broken`, chain + downgrade checks in `event_consistency_issues`, absent-store tripwire, `expect_chain_head`. |
| `loop/contract.py` | modify (~754-761) | `doctor_report(..., expect_chain_head=None)` pass-through. |
| `loop/runner.py` | modify (~119-146) | `_read_only_connect` + `read_event_rows`; `ChainBreakError` → `event_chain_broken`. |
| `loop/runcontrol.py` | modify (~28-38) | map `EventStoreOperationalError` → `RuntimeStoreError("event_store_unusable", …)`. |
| `loop/__main__.py` | modify | `migrate` verb, `--expect-chain-head` (extracted in the early flag region), flag-misuse guard, usage/help. |
| `schemas/event.schema.json` | modify | optional `prev_event_hash`/`event_hash` properties. |
| `action.yml` | modify | `expect-chain-head` input, `outputs.chain-head`, always-run anchor step. |
| `scripts/chain_fixtures.py` | **create** | Shared test helpers: legacy-store DDL/builder, chained-workspace builder. Test-only; not wheel-bundled. |
| `scripts/test_event_chain.py` | **create** | chain module + store + migrate + reducer chain tests + conformance vectors. |
| `scripts/test_adversarial_chain.py` | **create** | splice/reorder/tamper attacks + the four pinned honest limitations. |
| `scripts/test_migrate_cli.py` | **create** | CLI-level migrate verb tests (exit codes, idempotence, usage). |
| `scripts/test_doctor_eventstore.py` | extend | chain-in-doctor, anchor flag + CLI-level anchor invocation, downgrade, sidecar tripwire, byte-stability regression. |
| `scripts/test_loop_simulate_zero_writes.py` | extend | legacy-store variant + zero-carve-out assertions. |
| `reference/repo-os-contract.md` | modify §16/§22 | normative canonicalization + vectors, integrity boundary, anchor trust assumptions, doctor codes, migrate verb, **and amend three now-false sentences**. |
| `README.md` | modify | Task 13: prose (chain + limitation). Task 15: badge, action pin, release table. |
| `CHANGELOG.md`, `pyproject.toml`, `.claude-plugin/plugin.json`, `scripts/test_docs_version.py` | modify (Task 15) | release cut v0.10.0. |

Interfaces produced (used across tasks — exact signatures):

```python
# loop/chain.py
class ChainHashError(ValueError): ...
def canonical_json(value: Any) -> str: ...
def compute_event_hash(record: Mapping[str, Any]) -> str: ...          # hex sha256
def link_issue(record: Mapping[str, Any], prev_head: Mapping[str, Any] | None) -> str | None: ...
def verify_chain(events: Iterable[Mapping[str, Any]], *, expected_head: str | None = None) -> dict[str, Any]: ...
# report: {"ok", "issues", "chained_events", "unchained_prefix", "head": {"sequence", "event_hash"} | None}
# NOTE: requires a COMPLETE run stream beginning at sequence 0 (no suffix verification).

# loop/events.py
class EventStoreOperationalError(RuntimeError): ...     # table unusable: schema drift, lock
class EventRowDecodeError(ValueError): ...              # a stored payload/artifact_hashes column is not JSON
def has_chain_columns(conn: sqlite3.Connection) -> bool: ...
def store_user_version(conn: sqlite3.Connection) -> int: ...
def read_event_rows(conn, run_id: str, *, since_sequence: int | None = None) -> list[dict[str, Any]]: ...
# records ALWAYS carry "prev_event_hash" and "event_hash" keys (None on legacy rows)

# loop/migrate.py
def migrate_store(target: str | Path) -> dict[str, Any]: ...
# {"ok": True, "migrated": bool, "store": str, "user_version": 2,
#  "unchained_rows": int, "chained_from_sequence": int}

# loop/reducer.py
class ChainBreakError(EventReplayError): ...
# projection gains: "chain_head": {"sequence": int, "event_hash": str} | None, "unchained_prefix": int

# loop/runtime.py
def _read_only_connect(path: Path) -> sqlite3.Connection: ...    # immutable when safe, one mode=ro retry
def event_consistency_issues(target, *, mode=None, expect_chain_head: str | None = None) -> tuple[dict, list]: ...

# loop/contract.py
def doctor_report(target, *, mode=None, expect_chain_head: str | None = None) -> dict: ...
```

---

### Task 0: Branch setup

**Files:** none.

- [ ] **Step 1:** `git -C /mnt/c/Dev/projects/loop-engineer checkout -b feat/event-chain main` (main protection blocks direct pushes; all work lands via PR).
- [ ] **Step 2:** Verify baseline: `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts` — expect 935 passed / 14 skipped in the live checkout. Record the exact numbers; every later "no regressions" means these numbers plus that task's predicted delta.

### Task 1: `loop/chain.py` — canonicalizer and hash

**Files:** Create `loop/chain.py`; Create `scripts/test_event_chain.py`.

**Interfaces:** Produces `ChainHashError`, `canonical_json`, `compute_event_hash`, `_PREIMAGE_FIELDS`.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2:** Run: `uv run --with pyyaml --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_event_chain.py` — expect FAIL: `ModuleNotFoundError: No module named 'loop.chain'`.
- [ ] **Step 3: Implement `loop/chain.py`**

```python
"""Pure hash-chain canonicalization and verification for event@1 records.

Stdlib-only and import-free of other loop modules: verify_chain() must work over
any ordered event list (a SQLite read or a JSONL export) so third parties can
re-verify a chain without this package's store code. Canonical form is
json.dumps(sort_keys, separators=(",",":"), ensure_ascii=False, allow_nan=False)
encoded UTF-8 — pinned normatively in reference/repo-os-contract.md #16.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping

_PREIMAGE_FIELDS = (
    "schema", "run_id", "sequence", "event_id", "type", "actor", "ts",
    "causation_id", "correlation_id", "payload", "artifact_hashes",
    "prev_event_hash",
)


class ChainHashError(ValueError):
    """A value cannot be canonically hashed (non-JSON type, non-finite float, lone surrogate)."""


def canonical_json(value: Any) -> str:
    try:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ChainHashError(f"value is not canonically serializable: {exc}") from exc
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ChainHashError(f"value contains a lone surrogate: {exc}") from exc
    return text


def compute_event_hash(record: Mapping[str, Any]) -> str:
    preimage = {field: record.get(field) for field in _PREIMAGE_FIELDS}
    return hashlib.sha256(canonical_json(preimage).encode("utf-8")).hexdigest()
```

- [ ] **Step 4:** Re-run the Step 2 command — expect all Task-1 tests PASS.
- [ ] **Step 5:** Commit: `git -C ... add loop/chain.py scripts/test_event_chain.py && git -C ... commit -m "feat(chain): canonical-JSON event hashing (pure stdlib leaf module)"`.

### Task 2: `loop/chain.py` — link verification

**Files:** Modify `loop/chain.py`; extend `scripts/test_event_chain.py`.

**Interfaces:** Produces `link_issue(record, prev_head) -> str | None`, `verify_chain(events, *, expected_head=None) -> dict`.

- [ ] **Step 1: Write the failing tests** (append to `scripts/test_event_chain.py`)

```python
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
```

- [ ] **Step 2:** Run the test file — expect FAIL: `ImportError: cannot import name 'link_issue'`.
- [ ] **Step 3: Implement** (append to `loop/chain.py`)

```python
def link_issue(record: Mapping[str, Any], prev_head: Mapping[str, Any] | None) -> str | None:
    """One incremental chain check; None means record legally extends prev_head."""
    sequence = record.get("sequence")
    stored = record.get("event_hash")
    if stored is None:
        if prev_head is None:
            return None
        return (f"unchained event after chained prefix at sequence {sequence!r} "
                "(a pre-0.10.0 writer appended to a chained store, or the row was tampered)")
    expected_prev = prev_head["event_hash"] if prev_head is not None else None
    if record.get("prev_event_hash") != expected_prev:
        return f"prev_event_hash mismatch at sequence {sequence!r}"
    try:
        recomputed = compute_event_hash(record)
    except ChainHashError as exc:
        return f"unhashable record at sequence {sequence!r}: {exc}"
    if recomputed != stored:
        return f"event_hash mismatch at sequence {sequence!r}"
    return None


def verify_chain(events: Iterable[Mapping[str, Any]], *, expected_head: str | None = None) -> dict[str, Any]:
    """Verify a COMPLETE run stream's hash chain (sequence 0 onward); pure, I/O-free."""
    issues: list[str] = []
    unchained_prefix = 0
    chained_events = 0
    head: dict[str, Any] | None = None
    for record in events:
        issue = link_issue(record, head)
        if issue is not None:
            issues.append(issue)
            break
        if record.get("event_hash") is None:
            unchained_prefix += 1
            continue
        chained_events += 1
        head = {"sequence": record.get("sequence"), "event_hash": record["event_hash"]}
    if expected_head is not None and not issues:
        if head is None:
            issues.append("expected chain head, but the stream has no chained events")
        elif head["event_hash"] != expected_head:
            issues.append(f"chain head {head['event_hash']} does not match expected {expected_head}")
    return {"ok": not issues, "issues": issues, "chained_events": chained_events,
            "unchained_prefix": unchained_prefix, "head": head}
```

- [ ] **Step 4:** Re-run — expect PASS.
- [ ] **Step 5:** Commit: `feat(chain): incremental link verification + pure verify_chain over exported streams`.

### Task 3: Store generations — DDL, fresh-store versioning, shared reader

**Files:** Modify `loop/events.py`; Create `scripts/chain_fixtures.py`; extend `scripts/test_event_chain.py`.

**Interfaces:** Produces `has_chain_columns(conn)`, `store_user_version(conn)`, `read_event_rows(...)`, `EventRowDecodeError`; fresh stores get chain columns (`event_hash NOT NULL`) + `PRAGMA user_version=2`.

- [ ] **Step 1: Create the shared fixture module** `scripts/chain_fixtures.py` (test-only; the wheel force-includes scripts individually at `pyproject.toml:44-48`, so this does not ship):

```python
"""Shared test fixtures for chain work: byte-faithful v0.9.0 store builders.

Imported by test_event_chain.py, test_adversarial_chain.py,
test_doctor_eventstore.py and test_loop_simulate_zero_writes.py as
`from chain_fixtures import make_legacy_store` — pytest's prepend import mode
puts scripts/ on sys.path (there is no scripts/__init__.py).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

LEGACY_DDL = """
CREATE TABLE events (
    run_id TEXT NOT NULL, sequence INTEGER NOT NULL, event_id TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL, actor TEXT NOT NULL, causation_id TEXT, correlation_id TEXT,
    ts TEXT NOT NULL, payload TEXT NOT NULL, artifact_hashes TEXT NOT NULL,
    PRIMARY KEY (run_id, sequence)
)"""

LEGACY_TRIGGERS = (
    "CREATE TRIGGER events_no_update BEFORE UPDATE ON events "
    "BEGIN SELECT RAISE(ABORT, 'events table is append-only: UPDATE is forbidden'); END",
    "CREATE TRIGGER events_no_delete BEFORE DELETE ON events "
    "BEGIN SELECT RAISE(ABORT, 'events table is append-only: DELETE is forbidden'); END",
)


def make_legacy_store(path: str | Path, *, run_id: str = "r1") -> Path:
    """Write a v0.9.0-shaped store holding one contract_opened event."""
    path = Path(path)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(LEGACY_DDL)
        for trigger in LEGACY_TRIGGERS:
            conn.execute(trigger)
        conn.execute(
            "INSERT INTO events VALUES (?, 0, 'legacy-e0', 'contract_opened', 'operator', "
            "NULL, NULL, '2026-07-24T00:00:00+00:00', '{\"workspace\":\"ws\"}', '[]')",
            (run_id,))
        conn.commit()
    finally:
        conn.close()
    return path


def drop_triggers(path: str | Path) -> None:
    """Adversary helper: remove the append-only triggers (they are DDL, not a security control)."""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("DROP TRIGGER IF EXISTS events_no_update")
        conn.execute("DROP TRIGGER IF EXISTS events_no_delete")
        conn.commit()
    finally:
        conn.close()


def restore_triggers(path: str | Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        for trigger in LEGACY_TRIGGERS:
            conn.execute(trigger.replace("CREATE TRIGGER", "CREATE TRIGGER IF NOT EXISTS"))
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 2: Write the failing tests** (append to `scripts/test_event_chain.py`)

```python
import sqlite3

from chain_fixtures import make_legacy_store
from loop.events import SQLiteEventStore, has_chain_columns, read_event_rows, store_user_version


def test_fresh_store_has_chain_columns_and_user_version_2(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.db")
    store.append("r1", "contract_opened", {"workspace": "ws"}, actor="operator")
    conn = sqlite3.connect(str(tmp_path / "events.db"))
    try:
        assert has_chain_columns(conn) and store_user_version(conn) == 2
        notnull = {row[1]: row[3] for row in conn.execute("PRAGMA table_info(events)")}
        assert notnull["event_hash"] == 1 and notnull["prev_event_hash"] == 0
    finally:
        conn.close()


def test_legacy_store_is_not_upgraded_by_connect(tmp_path):
    path = make_legacy_store(tmp_path / "events.db")
    SQLiteEventStore(path).read("r1")     # any connect on a legacy store
    conn = sqlite3.connect(str(path))
    try:
        assert not has_chain_columns(conn) and store_user_version(conn) == 0
    finally:
        conn.close()


def test_read_event_rows_projects_hash_keys_on_legacy_store(tmp_path):
    path = make_legacy_store(tmp_path / "events.db")
    conn = sqlite3.connect(str(path))
    try:
        rows = read_event_rows(conn, "r1")
    finally:
        conn.close()
    assert rows[0]["prev_event_hash"] is None and rows[0]["event_hash"] is None


def test_read_event_rows_raises_typed_error_on_corrupt_payload_json(tmp_path):
    from loop.events import EventRowDecodeError
    path = make_legacy_store(tmp_path / "events.db")
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("DROP TRIGGER events_no_update")
        conn.execute("UPDATE events SET payload = 'not json' WHERE sequence = 0")
        conn.commit()
        with pytest.raises(EventRowDecodeError):
            read_event_rows(conn, "r1")
    finally:
        conn.close()
```

- [ ] **Step 3:** Run — expect FAIL: `ImportError: cannot import name 'has_chain_columns'`.
- [ ] **Step 4: Implement in `loop/events.py`:**
  - Extend `_CREATE_EVENTS_TABLE` with, after `artifact_hashes TEXT NOT NULL,`: `prev_event_hash TEXT,` and `event_hash TEXT NOT NULL,` (this DDL runs only when the table does not yet exist — legacy tables are untouched). Per design change D1 the NOT NULL makes a pre-0.10.0 10-column INSERT fail closed.
  - Add module-level `class EventRowDecodeError(ValueError): """A stored payload/artifact_hashes column is not valid JSON."""` next to the other exceptions.
  - Add:

```python
def has_chain_columns(conn: sqlite3.Connection) -> bool:
    return any(row[1] == "event_hash" for row in conn.execute("PRAGMA table_info(events)"))


def store_user_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


_BASE_COLUMNS = ("run_id", "sequence", "event_id", "type", "actor", "causation_id",
                 "correlation_id", "ts", "payload", "artifact_hashes")


def read_event_rows(conn: sqlite3.Connection, run_id: str, *,
                    since_sequence: int | None = None) -> list[dict[str, Any]]:
    """The single event-row projection shared by store, runtime, and runner reads.

    Records always carry prev_event_hash/event_hash keys; legacy stores project
    None. Owns the JSON-decode translation every call site used to repeat.
    """
    chained = has_chain_columns(conn)
    columns = _BASE_COLUMNS + (("prev_event_hash", "event_hash") if chained else ())
    operator, cursor = (">=", 0) if since_sequence is None else (">", since_sequence)
    rows = conn.execute(
        f"SELECT {', '.join(columns)} FROM events WHERE run_id = ? AND sequence {operator} ? "
        "ORDER BY sequence ASC", (run_id, cursor)).fetchall()
    records: list[dict[str, Any]] = []
    try:
        for row in rows:
            records.append({
                "schema": EVENT_SCHEMA_ID, "run_id": row[0], "sequence": row[1], "event_id": row[2],
                "type": row[3], "actor": row[4], "causation_id": row[5], "correlation_id": row[6],
                "ts": row[7], "payload": json.loads(row[8]), "artifact_hashes": json.loads(row[9]),
                "prev_event_hash": row[10] if chained else None,
                "event_hash": row[11] if chained else None})
    except (TypeError, json.JSONDecodeError) as exc:
        raise EventRowDecodeError(f"event row is not decodable: {exc}") from exc
    return records
```

  - In `_connect()`: before the DDL, probe `fresh = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'").fetchone() is None`; after the three CREATE statements, `if fresh: conn.execute("PRAGMA user_version = 2")`.
  - Rewrite `read()` to open its connection and `return read_event_rows(conn, run_id, since_sequence=since_sequence)`.
- [ ] **Step 5:** Run `scripts/test_event_chain.py` (all Task 1–3 tests PASS — Task 3 ends green; the fresh-store chaining assertions live in Task 4) and `scripts/test_eventstore.py`. Any existing test asserting an exact record key-set or exact `PRAGMA table_info` now sees 12 columns / 2 extra keys — update those in place as **reviewed edits**, listing each in the commit body.
- [ ] **Step 6:** Commit: `feat(events): store generations — chain columns + user_version, shared feature-detected row reader with typed decode errors`.

### Task 4: Chained `append()` + typed operational error

**Files:** Modify `loop/events.py`, `loop/runcontrol.py`; extend `scripts/test_event_chain.py`.

**Interfaces:** Produces `EventStoreOperationalError(RuntimeError)`. `append()` on chained stores returns store-computed `prev_event_hash`/`event_hash`; on legacy stores both `None`.

- [ ] **Step 1: Write the failing tests**

```python
from loop.chain import compute_event_hash as _hash
from loop.events import EventStoreOperationalError


def test_read_projects_store_computed_hash_on_fresh_store(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.db")
    record = store.append("r2", "contract_opened", {"workspace": "ws"}, actor="operator")
    assert store.read("r2")[0]["event_hash"] == record["event_hash"]


def test_append_chains_on_fresh_store(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.db")
    e0 = store.append("r1", "contract_opened", {"workspace": "ws"}, actor="operator")
    e1 = store.append("r1", "iteration_appended", {"iteration_id": 1, "outcome": "task_passed"},
                      actor="operator")
    assert e0["prev_event_hash"] is None and e0["event_hash"] == _hash(e0)
    assert e1["prev_event_hash"] == e0["event_hash"] and e1["event_hash"] == _hash(e1)


def test_append_ignores_caller_supplied_chain_fields(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.db")
    store.append("r1", "contract_opened", {"workspace": "ws"}, actor="operator")
    smuggled = store.append("r1", "iteration_appended",
                            {"iteration_id": 1, "outcome": "task_passed", "event_hash": "f" * 64},
                            actor="operator")
    assert smuggled["event_hash"] != "f" * 64 and smuggled["event_hash"] == _hash(smuggled)


def test_append_on_legacy_store_stays_unchained_and_working(tmp_path):
    path = make_legacy_store(tmp_path / "events.db")
    record = SQLiteEventStore(path).append(
        "r1", "iteration_appended", {"iteration_id": 1, "outcome": "task_passed"}, actor="operator")
    assert record["prev_event_hash"] is None and record["event_hash"] is None
    assert SQLiteEventStore(path).read("r1")[1]["event_hash"] is None


def test_legacy_style_ten_column_insert_is_refused_by_a_fresh_store(tmp_path):
    """Design change D1: a pre-0.10.0 writer cannot silently unchain a v2 store."""
    path = tmp_path / "events.db"
    SQLiteEventStore(path).append("r1", "contract_opened", {"workspace": "ws"}, actor="operator")
    conn = sqlite3.connect(str(path))
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO events (run_id, sequence, event_id, type, actor, causation_id, "
                "correlation_id, ts, payload, artifact_hashes) VALUES "
                "('r1',1,'old-writer','iteration_appended','worker',NULL,NULL,"
                "'2026-07-24T00:00:00+00:00','{\"iteration_id\":1,\"outcome\":\"task_passed\"}','[]')")
    finally:
        conn.close()


def test_append_wraps_schema_drift_as_typed_error(tmp_path):
    path = tmp_path / "events.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE events (run_id TEXT, sequence INTEGER)")   # wrong shape entirely
    conn.commit(); conn.close()
    with pytest.raises(EventStoreOperationalError):
        SQLiteEventStore(path).append("r1", "contract_opened", {"workspace": "ws"}, actor="operator")
```

- [ ] **Step 2:** Run — expect FAIL (`KeyError: 'event_hash'` / raw `sqlite3.OperationalError`).
- [ ] **Step 3: Implement.** Module level in `loop/events.py`, beside the other exceptions:

```python
class EventStoreOperationalError(RuntimeError):
    """The events table exists but cannot service this operation (schema drift, lock)."""
```

  Add `from . import chain` at the top. Inside `append()`, after `record["sequence"] = next_sequence`:

```python
            chained = has_chain_columns(conn)
            if chained:
                prev_row = conn.execute(
                    "SELECT event_hash FROM events WHERE run_id = ? AND sequence = ?",
                    (run_id, next_sequence - 1)).fetchone() if next_sequence else None
                record["prev_event_hash"] = prev_row[0] if prev_row else None
                try:
                    record["event_hash"] = chain.compute_event_hash(record)
                except chain.ChainHashError as exc:
                    conn.execute("ROLLBACK")
                    raise EventValidationError(str(exc)) from exc
            else:
                record["prev_event_hash"] = None
                record["event_hash"] = None
```

  The genesis-after-legacy rule falls out: on a migrated store the pre-migration predecessor's `event_hash` is SQL `NULL`, so `prev_row[0]` is `None` and the first post-migration event is a genesis link. Make the INSERT column-conditional:

```python
                if chained:
                    conn.execute(
                        "INSERT INTO events (run_id, sequence, event_id, type, actor, causation_id, correlation_id, ts, payload, artifact_hashes, prev_event_hash, event_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (record["run_id"], record["sequence"], record["event_id"], record["type"], record["actor"],
                         record["causation_id"], record["correlation_id"], record["ts"], payload_json, hashes_json,
                         record["prev_event_hash"], record["event_hash"]))
                else:
                    conn.execute(  # legacy 10-column INSERT, byte-identical to v0.9.0
                        "INSERT INTO events (run_id, sequence, event_id, type, actor, causation_id, correlation_id, ts, payload, artifact_hashes) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (record["run_id"], record["sequence"], record["event_id"], record["type"], record["actor"],
                         record["causation_id"], record["correlation_id"], record["ts"], payload_json, hashes_json))
```

  Wrap the transaction body so schema drift and lock failures are typed — add this clause to the `try` that currently owns `BEGIN IMMEDIATE`, before `finally: conn.close()`:

```python
        except sqlite3.OperationalError as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise EventStoreOperationalError(f"event store cannot accept appends: {exc}") from exc
```

  Give the new error a handled CLI path (it is a `RuntimeError`, so no existing except tuple catches it): in `loop/runcontrol.py:_append_event`, add `except EventStoreOperationalError as exc: raise RuntimeStoreError("event_store_unusable", str(exc)) from exc` alongside the existing `SequenceConflictError`/`EventValidationError` handling; do the same at `runner`'s append sites (`runner.py` ~222 and ~239). Both `RunControlError`/`RuntimeStoreError` families are already caught in `__main__.py` (:344, :360) → exit 2, no traceback.
- [ ] **Step 4:** Run Task 3+4 tests plus `scripts/test_eventstore.py` and `scripts/test_runcontrol*.py` — PASS, no regressions. Add one probe: `loop run` and `loop pause` against a schema-drifted store exit 2 with no `Traceback` on stderr (put it in `scripts/test_migrate_cli.py`, which Task 6 creates — or inline here as a subprocess test in `test_event_chain.py`).
- [ ] **Step 5:** Commit: `feat(events): store-computed hash chain on append; typed operational error with a handled CLI path`.

### Task 5: Schema + structural-fallback parity

**Files:** Modify `schemas/event.schema.json`, `loop/events.py` (`_structural_validate_event`); extend `scripts/test_event_chain.py`.

- [ ] **Step 1: Write the failing tests**

```python
from loop.events import validate_event


@pytest.mark.parametrize("mode", ["strict", "basic"])
def test_chain_fields_validate_in_both_modes(mode):
    if mode == "strict":
        pytest.importorskip("jsonschema")
    good = _chained(0, None)
    assert validate_event(good, mode=mode)["ok"]
    report = validate_event(dict(good, event_hash="not-hex"), mode=mode)
    assert not report["ok"]
    assert validate_event(dict(good, prev_event_hash=17), mode=mode)["ok"] is False
```

  (`--mode basic` forces structural, `strict`/`release` require jsonschema — `loop/__main__.py:69-71`; mirror the `importorskip` pattern at `scripts/test_doctor_eventstore.py:70-75`.)
- [ ] **Step 2:** Run — the invalid cases FAIL in both modes today (no constraint exists).
- [ ] **Step 3: Implement.** In `schemas/event.schema.json` add to `properties` (leave `required` untouched):

```json
    "prev_event_hash": { "type": ["string", "null"], "pattern": "^[0-9a-f]{64}$" },
    "event_hash": { "type": ["string", "null"], "pattern": "^[0-9a-f]{64}$" }
```

  and append to the schema `description`: `"prev_event_hash/event_hash (additive, optional) carry the per-run hash chain; loop/chain.py pins the canonical preimage."` In `_structural_validate_event`, after the causation/correlation loop:

```python
    for field in ("prev_event_hash", "event_hash"):
        if field in data and data[field] is not None and (
                not isinstance(data[field], str)
                or re.search(r"^[0-9a-f]{64}$", data[field]) is None):
            issues.append(f"{field} must be null or a 64-character lowercase hex sha256")
```

- [ ] **Step 4:** Run — PASS both parametrizations. Also run `scripts/test_conformance.py` (it enumerates schema `$id`s; no new file, so it stays green untouched).
- [ ] **Step 5:** Commit: `feat(schema): optional event@1 chain fields with structural-fallback parity`.

### Task 6: `loop/migrate.py` + `loop migrate` verb

**Files:** Create `loop/migrate.py`, `scripts/test_migrate_cli.py`; modify `loop/__main__.py`; extend `scripts/test_event_chain.py`.

**Interfaces:** `migrate_store(target) -> dict`. CLI: `python3 -m loop migrate <workspace>` — exit 0 ok, 2 on missing/corrupt store or usage error.

- [ ] **Step 1: Write the failing tests** (in `scripts/test_event_chain.py`)

```python
from loop.migrate import migrate_store
from loop.runtime import RuntimeStoreError


def _workspace_with_legacy_store(tmp_path):
    loop_dir = tmp_path / ".loop"
    loop_dir.mkdir()
    make_legacy_store(loop_dir / "events.db")
    return tmp_path


def test_migrate_adds_columns_sets_version_and_reports_unchained(tmp_path):
    ws = _workspace_with_legacy_store(tmp_path)
    report = migrate_store(ws)
    assert report["ok"] and report["migrated"] is True
    assert report["user_version"] == 2 and report["unchained_rows"] == 1
    assert report["chained_from_sequence"] == 1
    conn = sqlite3.connect(str(ws / ".loop" / "events.db"))
    try:
        assert has_chain_columns(conn) and store_user_version(conn) == 2
    finally:
        conn.close()


def test_migrate_is_idempotent(tmp_path):
    ws = _workspace_with_legacy_store(tmp_path)
    migrate_store(ws)
    assert migrate_store(ws)["migrated"] is False


def test_migrate_missing_store_raises_typed(tmp_path):
    (tmp_path / ".loop").mkdir()
    with pytest.raises(RuntimeStoreError):
        migrate_store(tmp_path)


def test_post_migration_appends_chain_with_genesis_after_legacy_prefix(tmp_path):
    ws = _workspace_with_legacy_store(tmp_path)
    migrate_store(ws)
    record = SQLiteEventStore(ws / ".loop" / "events.db").append(
        "r1", "iteration_appended", {"iteration_id": 1, "outcome": "task_passed"}, actor="operator")
    assert record["prev_event_hash"] is None            # genesis after unchained prefix
    assert record["event_hash"] == _hash(record)
```

- [ ] **Step 2:** Run — FAIL: no module `loop.migrate`.
- [ ] **Step 3: Implement `loop/migrate.py`:**

```python
"""Explicit legacy-store migration: add chain columns; never rewrites rows.

Backfilling hashes onto existing rows is deliberately impossible — the
append-only triggers forbid UPDATE — so migration only widens the table and
stamps user_version=2. Pre-migration rows stay an *unchained prefix* that
doctor reports explicitly; the first post-migration append is a chain genesis.
Migrated columns stay nullable (legacy rows are NULL), so unlike a fresh store
a migrated store cannot refuse a pre-0.10.0 writer at the DB layer — see the
compatibility rule in reference/repo-os-contract.md #16.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .events import has_chain_columns
from .paths import resolve_loop_paths
from .runtime import RuntimeStoreError


def migrate_store(target: str | Path) -> dict[str, Any]:
    path = resolve_loop_paths(target).loop_dir / "events.db"
    if not path.exists():
        raise RuntimeStoreError("missing_store", f"event store does not exist: {path}")
    try:
        conn = sqlite3.connect(str(path), isolation_level=None, timeout=5.0)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            already = has_chain_columns(conn)
            if not already:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("ALTER TABLE events ADD COLUMN prev_event_hash TEXT")
                conn.execute("ALTER TABLE events ADD COLUMN event_hash TEXT")
                conn.execute("COMMIT")
            conn.execute("PRAGMA user_version = 2")
            unchained = conn.execute("SELECT COUNT(*) FROM events WHERE event_hash IS NULL").fetchone()[0]
            top = conn.execute("SELECT MAX(sequence) FROM events").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise RuntimeStoreError("corrupt_store", f"cannot migrate event store: {exc}") from exc
    return {"ok": True, "migrated": not already, "store": str(path), "user_version": 2,
            "unchained_rows": unchained, "chained_from_sequence": 0 if top is None else top + 1}
```

  CLI wiring in `loop/__main__.py`: add `"migrate"` to `_COMMANDS` **and** `_READ_COMMANDS` (that tuple is the target-must-exist guard, not a purity claim — `run`/`approve`/`cancel` already live there); add it to `_USAGE` and a `_HELP` line: `migrate    Add hash-chain columns to a legacy events.db (explicit, idempotent; the only store-upgrade path).`; dispatch before the status/replay block:

```python
    if command == "migrate":
        from .migrate import migrate_store
        try:
            return _print_json(migrate_store(target))
        except RuntimeStoreError as exc:
            print(f"migrate: {exc}", file=sys.stderr)
            return 2
```

- [ ] **Step 4: Write `scripts/test_migrate_cli.py`** — subprocess-invoked by path (copy the invocation pattern from an existing `scripts/test_loop_*_cli.py`), covering: migrate on a legacy workspace exits 0 with `"migrated": true`; a second run exits 0 with `false`; a missing target exits 2 with the exists-guard hint; `--help` mentions `migrate`; and the Task-4 probe (`loop run`/`loop pause` on a schema-drifted store exit 2 with no `Traceback` in stderr).
- [ ] **Step 5:** Run the new files + `scripts/test_loop_cli.py` (its usage-string assertions must be updated for the new verb in this same commit).
- [ ] **Step 6:** Commit: `feat(migrate): explicit legacy-store chain migration verb`.

### Task 7: Reducer chain enforcement

**Files:** Modify `loop/reducer.py`; extend `scripts/test_event_chain.py`.

**Interfaces:** `ChainBreakError(EventReplayError)`; projection gains `"chain_head"`, `"unchained_prefix"`.

- [ ] **Step 1: Write the failing tests**

```python
from loop.chain import verify_chain
from loop.reducer import ChainBreakError, reduce_events


def test_reducer_folds_chained_stream_and_exposes_head(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.db")
    store.append("r1", "contract_opened", {"workspace": "ws"}, actor="operator")
    last = store.append("r1", "iteration_appended",
                        {"iteration_id": 1, "outcome": "task_passed"}, actor="operator")
    projection = reduce_events(store.read("r1"))
    assert projection["chain_head"] == {"sequence": 1, "event_hash": last["event_hash"]}
    assert projection["unchained_prefix"] == 0


def test_reducer_raises_chain_break_on_tampered_payload(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.db")
    store.append("r1", "contract_opened", {"workspace": "ws"}, actor="operator")
    events = store.read("r1")
    events[0]["payload"] = {"workspace": "tampered"}
    with pytest.raises(ChainBreakError):
        reduce_events(events)


def test_reducer_accepts_legacy_unchained_stream(tmp_path):
    make_legacy_store(tmp_path / "events.db")
    projection = reduce_events(SQLiteEventStore(tmp_path / "events.db").read("r1"))
    assert projection["chain_head"] is None and projection["unchained_prefix"] == 1


def test_reducer_resume_from_initial_chain_head(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.db")
    store.append("r1", "contract_opened", {"workspace": "ws"}, actor="operator")
    store.append("r1", "iteration_appended", {"iteration_id": 1, "outcome": "task_passed"}, actor="operator")
    events = store.read("r1")
    snapshot = reduce_events(events[:1])
    resumed = reduce_events(events[1:], initial=snapshot)
    assert resumed["chain_head"] == reduce_events(events)["chain_head"]
    forged = dict(events[1], prev_event_hash="a" * 64)
    forged["event_hash"] = compute_event_hash(forged)
    with pytest.raises(ChainBreakError):
        reduce_events([forged], initial=snapshot)


@pytest.mark.parametrize("generation", ["fresh", "legacy", "migrated"])
def test_verify_chain_agrees_with_reducer(tmp_path, generation):
    """Two verifiers, one truth — guards against lockstep drift (design decision 8)."""
    path = tmp_path / "events.db"
    if generation == "fresh":
        store = SQLiteEventStore(path)
    else:
        make_legacy_store(path)
        if generation == "migrated":
            (tmp_path / ".loop").mkdir(exist_ok=True)
            # migrate_store takes a workspace; migrate this file in place via the same DDL
            conn = sqlite3.connect(str(path))
            conn.execute("ALTER TABLE events ADD COLUMN prev_event_hash TEXT")
            conn.execute("ALTER TABLE events ADD COLUMN event_hash TEXT")
            conn.execute("PRAGMA user_version = 2")
            conn.commit(); conn.close()
        store = SQLiteEventStore(path)
    if generation == "fresh":
        store.append("r1", "contract_opened", {"workspace": "ws"}, actor="operator")
    store.append("r1", "iteration_appended", {"iteration_id": 1, "outcome": "task_passed"},
                 actor="operator")
    events = store.read("r1")
    projection = reduce_events(events)
    report = verify_chain(events)
    assert report["head"] == projection["chain_head"]
    assert report["unchained_prefix"] == projection["unchained_prefix"]
```

- [ ] **Step 2:** Run — FAIL: `ImportError: cannot import name 'ChainBreakError'`.
- [ ] **Step 3: Implement in `loop/reducer.py`:** import `from . import chain`, add

```python
class ChainBreakError(EventReplayError):
    """The event stream's hash chain is broken, forged, or has an illegal gap."""
```

  In `_empty_projection`, add `"chain_head": None, "unchained_prefix": 0`. In `_reduce_one`, immediately after the non-monotonic-sequence check (reducer.py:80-82):

```python
    issue = chain.link_issue(event, state["chain_head"])
    if issue is not None:
        raise ChainBreakError(f"event chain broken: {issue}")
```

  and in the `new_state` construction:

```python
    if event.get("event_hash") is None:
        new_state["unchained_prefix"] = state["unchained_prefix"] + 1
    else:
        new_state["chain_head"] = {"sequence": event["sequence"], "event_hash": event["event_hash"]}
```

  `reduce_events(initial=...)` needs no special casing: the merged initial carries `chain_head`, and `_empty_projection` supplies `None`/`0` defaults when an older snapshot omits the keys.
- [ ] **Step 4:** Run Task 7 tests + `scripts/test_reducer.py` + `scripts/test_adversarial_kernel.py` + `scripts/test_adversarial_process.py` — no regressions. (Hand-built event dicts in those files carry no `event_hash`, so they read as an unchained stream and `link_issue` returns `None` — verify by running, not by assuming. If `test_adversarial_process.py`'s raw-byte boundary pin conflicts, adjudicate toward keeping BOTH pins honest; do not weaken either.)
- [ ] **Step 5:** Commit: `feat(reducer): enforce hash chain at fold time via typed ChainBreakError`.

### Task 8: Runtime + runner — shared read path, validation enforcement, chain surface

**Files:** Modify `loop/runtime.py`, `loop/runner.py`; extend `scripts/test_doctor_eventstore.py`.

Every test below builds its workspace with the file's existing helpers (`scripts/test_doctor_eventstore.py:12-30` supplies the fresh-contract + store-opening helpers — read them and reuse the exact call sequence), and legacy variants use `from chain_fixtures import make_legacy_store`. A legacy-store doctor fixture must have its `state.json` synced to the legacy `contract_opened` projection, or `_state_divergence` (runtime.py:90-110) makes it dirty for unrelated reasons.

- [ ] **Step 1: Write the failing tests**

```python
def test_status_and_replay_expose_chain_head(tmp_path):
    ws = <existing fresh-contract helper>(tmp_path)      # chained store
    report = status_report(ws)
    assert report["chain_head"] is not None
    assert replay_report(ws)["chain_head"] == report["chain_head"]


def test_doctor_nests_chain_under_event_store(tmp_path):
    report = doctor_report(ws)
    assert report["event_store"]["chain"]["head"]["sequence"] >= 0
    assert report["event_store"]["chain"]["unchained_prefix"] == 0


def test_legacy_store_doctor_ok_and_chain_null(tmp_path):
    # workspace whose .loop/events.db is a make_legacy_store file, state.json synced
    report = doctor_report(ws)
    assert report["ok"] and report["event_store"]["chain"] == {"head": None, "unchained_prefix": 1}


def test_migrated_store_doctor_reports_unchained_prefix(tmp_path):
    migrate_store(ws)
    report = doctor_report(ws)
    assert report["ok"] and report["event_store"]["chain"]["head"] is None
    assert report["event_store"]["chain"]["unchained_prefix"] == 1


def test_migrated_store_after_append_reports_genesis_head(tmp_path):
    migrate_store(ws); <append one iteration through the store + sync state.json>
    chain_block = doctor_report(ws)["event_store"]["chain"]
    assert chain_block["head"]["sequence"] == 1 and chain_block["unchained_prefix"] == 1


def test_tampered_store_fails_doctor_status_and_replay_with_event_chain_broken(tmp_path):
    drop_triggers(store_path)                             # from chain_fixtures
    conn = sqlite3.connect(str(store_path))
    conn.execute("UPDATE events SET payload = '{\"workspace\":\"tampered\"}' WHERE sequence = 0")
    conn.commit(); conn.close()
    for report in (doctor_report(ws), status_report(ws), replay_report(ws)):
        codes = {i["code"] for i in report.get("issues", report.get("divergence", []) + report.get("findings", []))}
        assert "event_chain_broken" in codes


def test_run_on_tampered_store_reports_event_chain_broken(tmp_path):
    """Design change D3: runner must not relabel it invalid_event_stream."""
    with pytest.raises(RuntimeStoreError) as excinfo:
        dispatch_once(ws)
    assert excinfo.value.code == "event_chain_broken"


def test_invalid_event_now_fails_status_instead_of_being_discarded(tmp_path):
    # insert a row whose payload violates event@1 (iteration_appended without outcome)
    with pytest.raises(RuntimeStoreError) as excinfo:
        status_report(ws)
    assert excinfo.value.code == "invalid_event"


def test_in_row_json_corruption_fails_doctor_without_traceback(tmp_path):
    # design change D5: payload column set to non-JSON text
    report = doctor_report(ws)
    assert not report["ok"] and report["event_store"]["error_code"] == "corrupt_store"


def test_read_verbs_leave_no_wal_sidecars_on_clean_store(tmp_path):
    status_report(ws); replay_report(ws); doctor_report(ws)
    assert not (ws / ".loop" / "events.db-wal").exists()
    assert not (ws / ".loop" / "events.db-shm").exists()
```

- [ ] **Step 2:** Run — expect the new tests FAIL.
- [ ] **Step 3: Implement.** In `loop/runtime.py`:
  - Add the shared read connector (design change D4), and use it in `_read_events_readonly` and `_discover_run_id`:

```python
def _read_only_connect(path: Path) -> sqlite3.Connection:
    """Read-only connection; immutable when no WAL sidecar exists so reads leave no files.

    immutable=1 assumes no concurrent writer. A live append can surface as
    SQLITE_CORRUPT, so a failed immutable open is retried once as plain mode=ro
    before the caller may conclude corruption: real corruption fails both.
    """
    uri = path.absolute().as_uri()
    if not path.with_name(path.name + "-wal").exists():
        try:
            return sqlite3.connect(f"{uri}?mode=ro&immutable=1", uri=True)
        except sqlite3.DatabaseError:
            pass
    return sqlite3.connect(f"{uri}?mode=ro", uri=True)
```

    In `_read_events_readonly`, delegate row projection to `events.read_event_rows(conn, run_id)` and map `EventRowDecodeError` → `RuntimeStoreError("corrupt_store", ...)` alongside the existing `sqlite3.DatabaseError` handler. **Wrap the first `conn.execute` of a read in a retry too**: if the immutable open succeeded but the first query raises `sqlite3.DatabaseError`, close, reopen with plain `mode=ro`, and retry once before raising `corrupt_store`.
  - `_events`: enforce verdicts and remove the `assert`:

```python
    validation: dict[str, Any] | None = None
    for event in events:
        validation = validate_event(event, mode=mode)
        if not validation["ok"]:
            raise RuntimeStoreError("invalid_event",
                                    f"event store contains invalid event: {validation['issues']}")
    if validation is None:
        raise RuntimeStoreError("empty_store", f"event store is empty: {path}")
```

  - `status_report`: catch `ChainBreakError` **before** `EventReplayError`, emitting `ContractIssue("event_chain_broken", str(exc))`; add `"chain_head": None, "unchained_prefix": 0` to the degraded projection literal (runtime.py:132-133) and report with `.get` so no path can KeyError:

```python
        "chain_head": projection.get("chain_head"),
        "unchained_prefix": projection.get("unchained_prefix", 0),
```

  - `replay_report`: same `ChainBreakError`-first handling (a chain break sets `legal_sequence = False`), same two report keys via `.get`.
  - In `loop/runner.py`: use `_read_only_connect` (import from `.runtime`) and `read_event_rows`; map `EventRowDecodeError` → `RuntimeStoreError("corrupt_store", ...)`; and insert **before** the existing `except ValueError` at runner.py:145:

```python
    except ChainBreakError as exc:
        raise RuntimeStoreError("event_chain_broken", str(exc)) from exc
```

    (import `ChainBreakError` from `.reducer`.)
- [ ] **Step 4:** Run the extended file + `scripts/test_runner_verifier.py` + `scripts/test_loop_simulate_zero_writes.py`. The pre-existing `test_absent_event_store_matches_pre_slice_doctor_shape` must still pass unmodified; `test_synced_happy_path_is_doctor_clean` gains the `"chain"` key deliberately (a reviewed edit, listed in the commit body).
- [ ] **Step 5:** Commit: `feat(runtime): chain surfaced through status/replay/doctor/run; enforce event validation; race-safe immutable reads leave no sidecars`.

### Task 9: Doctor anchor — `--expect-chain-head`, downgrade + absent-store hardening

**Files:** Modify `loop/runtime.py`, `loop/contract.py` (~754-761), `loop/__main__.py`; extend `scripts/test_doctor_eventstore.py`.

- [ ] **Step 1: Write the failing tests** (build `ws` with the same helpers as Task 8)

```python
def test_expect_chain_head_matching_passes(tmp_path):
    head = doctor_report(ws)["event_store"]["chain"]["head"]["event_hash"]
    assert doctor_report(ws, expect_chain_head=head)["ok"]


def test_expect_chain_head_mismatch_fails_doctor(tmp_path):
    report = doctor_report(ws, expect_chain_head="a" * 64)
    assert not report["ok"] and any(i["code"] == "chain_anchor_mismatch" for i in report["issues"])


def test_expect_chain_head_with_missing_store_fails_doctor(tmp_path):
    report = doctor_report(ws_without_store, expect_chain_head="a" * 64)
    assert not report["ok"] and any(i["code"] == "chain_anchor_mismatch" for i in report["issues"])


def test_expect_chain_head_with_unreadable_store_fails_doctor(tmp_path):
    # corrupt the file bytes, then anchor
    report = doctor_report(ws, expect_chain_head="a" * 64)
    assert not report["ok"] and any(i["code"] == "chain_anchor_mismatch" for i in report["issues"])


def test_sidecar_residue_without_db_fails_doctor(tmp_path):
    (ws / ".loop" / "events.db-wal").write_bytes(b"")     # events.db deleted
    report = doctor_report(ws)
    assert not report["ok"] and any(i["code"] == "missing_event_store" for i in report["issues"])


def test_chain_columns_dropped_but_version_2_fails_doctor(tmp_path):
    """Design change D2: the lazy downgrade attack."""
    conn = sqlite3.connect(str(store_path))
    conn.execute("ALTER TABLE events DROP COLUMN event_hash")
    conn.commit(); conn.close()
    report = doctor_report(ws)
    assert not report["ok"] and any(i["code"] == "chain_columns_missing" for i in report["issues"])


def test_absent_store_without_flag_or_sidecars_stays_byte_stable(tmp_path):
    assert doctor_report(ws_without_store)["event_store"] == {"present": False}


def test_cli_doctor_accepts_flag_before_target(tmp_path):
    """The action.yml invocation shape: flag BEFORE the positional target."""
    head = doctor_report(ws)["event_store"]["chain"]["head"]["event_hash"]
    assert main(["doctor", "--expect-chain-head", head, str(ws)]) == 0
    assert main(["doctor", "--expect-chain-head", "a" * 64, str(ws)]) == 1


def test_cli_rejects_flag_on_other_commands_and_creates_nothing(tmp_path):
    target = tmp_path / "fresh"
    assert main(["scaffold", "--expect-chain-head", "a" * 64, str(target)]) == 2
    assert not target.exists()
    assert main(["status", "--expect-chain-head", "a" * 64, str(ws)]) == 2


def test_cli_rejects_malformed_anchor_value(tmp_path):
    assert main(["doctor", "--expect-chain-head", "nothex", str(ws)]) == 2
```

- [ ] **Step 2:** Run — FAIL (`TypeError: unexpected keyword argument 'expect_chain_head'`).
- [ ] **Step 3: Implement.**
  - `event_consistency_issues(target, *, mode=None, expect_chain_head=None)`. Absent-store branch:

```python
    if not path.exists():
        issues: list[dict[str, Any]] = []
        residue = [suffix for suffix in ("-wal", "-shm")
                   if path.with_name(path.name + suffix).exists()]
        if residue:
            issues.append(ContractIssue(
                "missing_event_store",
                "events.db is absent but SQLite sidecar files remain — the store was deleted"))
        if expect_chain_head is not None:
            issues.append(ContractIssue(
                "chain_anchor_mismatch",
                "an anchored chain head was supplied but no event store is present"))
        if issues:
            return {"present": False, "sidecar_residue": bool(residue)}, issues
        return {"present": False}, []
```

    Unreadable path (`RuntimeStoreError`): append the same `chain_anchor_mismatch` issue when the flag is set. Readable path: add the `chain` block, the downgrade cross-check, and the anchor comparison:

```python
    chain_block = {"head": status["chain_head"], "unchained_prefix": status["unchained_prefix"]}
    if _store_declares_chain_without_columns(path):        # user_version >= 2 and not has_chain_columns
        issues.append(ContractIssue(
            "chain_columns_missing",
            "store declares user_version >= 2 but the chain columns are absent — "
            "the chain was dropped (this check only catches the lazy downgrade; "
            "an anchored head is the real control)"))
    if expect_chain_head is not None:
        actual = (status["chain_head"] or {}).get("event_hash")
        if actual != expect_chain_head:
            issues.append(ContractIssue(
                "chain_anchor_mismatch",
                f"chain head {actual!r} does not match expected {expect_chain_head!r}"))
```

    `_store_declares_chain_without_columns` opens via `_read_only_connect` and uses `store_user_version` + `has_chain_columns`.
  - `contract.py doctor_report`: add `expect_chain_head: str | None = None` and pass through.
  - `loop/__main__.py`: extract in the **early flag region**, immediately after the existing `_extract_mode_flag` block (~line 238) and **before** the `if not argv: ... target = Path(argv[0])` block (~line 281) — this is what makes `loop doctor --expect-chain-head <hex> <target>` work, and it is exactly the invocation `action.yml` uses:

```python
    expect_chain_head = None
    if command in {"doctor", "validate", "verify"}:
        try:
            expect_chain_head, argv = _extract_value_flag(argv, "--expect-chain-head")
        except ValueError as exc:
            print(f"{command}: {exc}", file=sys.stderr)
            print(_USAGE, file=sys.stderr)
            return 2
        if expect_chain_head is not None and re.fullmatch(r"[0-9a-f]{64}", expect_chain_head) is None:
            print(f"{command}: --expect-chain-head must be a 64-character lowercase hex sha256",
                  file=sys.stderr)
            return 2
    elif any(a == "--expect-chain-head" or a.startswith("--expect-chain-head=") for a in argv):
        print(f"{command}: --expect-chain-head is only valid for doctor/validate/verify",
              file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 2
```

    (No generic unknown-flag guard exists for `status`/`replay`/`simulate`/`run`/`plan-lint`/`inspect`, and `scaffold` would otherwise CREATE a directory named after the flag — this explicit `elif` is required, not decorative.) Pass `expect_chain_head=expect_chain_head` to `doctor_report`, and update `_USAGE`/`_HELP`.
- [ ] **Step 4:** Run the file — all new tests PASS, and the byte-stability pin still yields exactly `{"present": False}`.
- [ ] **Step 5:** Commit: `feat(doctor): --expect-chain-head anchor gate, downgrade cross-check, absent-store sidecar tripwire`.

### Task 10: Adversarial + honest-limitation tests

**Files:** Create `scripts/test_adversarial_chain.py`.

These pin the *claims boundary*. Four assert an attack SUCCEEDS — they keep the docs honest, like the pinned SQLite raw-byte boundary in `test_adversarial_process.py`. **They assert the chain predicate, not global `doctor ok`** (design change D6): doctor also runs `_state_divergence`/`_terminal_desync`, so a global-ok assertion would either fail for unrelated reasons or pass while pinning nothing.

- [ ] **Step 1: Write the tests.** Header and the two fully-worked examples; write the remaining three in the same shape.

```python
"""Adversarial chain tests: what the chain catches, and — pinned deliberately —
what it does NOT catch without an external anchor.

If a *_pinned test starts FAILING, the kernel gained a stronger property: update
reference/repo-os-contract.md #16 (Integrity boundary) in the same commit.
"""
import sqlite3

import pytest

from chain_fixtures import drop_triggers, make_legacy_store, restore_triggers
from loop.chain import compute_event_hash
from loop.contract import doctor_report


def _codes(report):
    return {issue["code"] for issue in report["issues"]}


def _chain_block(report):
    return report["event_store"]["chain"]


def test_splice_detected(tmp_path):
    ws = <chained workspace helper>(tmp_path)          # >= 3 events, state.json synced
    store_path = ws / ".loop" / "events.db"
    drop_triggers(store_path)
    conn = sqlite3.connect(str(store_path))
    try:
        conn.execute("UPDATE events SET payload = '{\"iteration_id\":1,\"outcome\":\"task_passed\"}' "
                     "WHERE sequence = 1")
        # recompute ONLY the spliced row's own hash: its successor still cites the original
        row = conn.execute("SELECT run_id, sequence, event_id, type, actor, causation_id, "
                           "correlation_id, ts, payload, artifact_hashes, prev_event_hash "
                           "FROM events WHERE sequence = 1").fetchone()
        record = {"schema": "loop-engineer/event@1", "run_id": row[0], "sequence": row[1],
                  "event_id": row[2], "type": row[3], "actor": row[4], "causation_id": row[5],
                  "correlation_id": row[6], "ts": row[7], "payload": json.loads(row[8]),
                  "artifact_hashes": json.loads(row[9]), "prev_event_hash": row[10]}
        conn.execute("UPDATE events SET event_hash = ? WHERE sequence = 1",
                     (compute_event_hash(record),))
        conn.commit()
    finally:
        conn.close()
    restore_triggers(store_path)
    assert "event_chain_broken" in _codes(doctor_report(ws))


def test_full_rewrite_with_recompute_passes_without_anchor_pinned(tmp_path):
    """The competent adversary: rewrite history, re-chain from genesis, and forge the
    projection files too. The chain alone does NOT catch this — the anchor does."""
    ws = <chained workspace helper>(tmp_path)
    store_path = ws / ".loop" / "events.db"
    original_head = _chain_block(doctor_report(ws))["head"]["event_hash"]
    drop_triggers(store_path)
    conn = sqlite3.connect(str(store_path))
    try:
        conn.execute("UPDATE events SET payload = replace(payload, '\"task_failed\"', "
                     "'\"task_passed\"') WHERE type = 'iteration_appended'")
        prev = None
        for row in conn.execute("SELECT sequence FROM events ORDER BY sequence ASC").fetchall():
            <rebuild the record dict exactly as read_event_rows does, with prev_event_hash=prev>
            digest = compute_event_hash(record)
            conn.execute("UPDATE events SET prev_event_hash = ?, event_hash = ? WHERE sequence = ?",
                         (prev, digest, row[0]))
            prev = digest
        conn.commit()
    finally:
        conn.close()
    restore_triggers(store_path)
    <rewrite state.json (and terminal_state.json if present) to match the forged projection>

    unanchored = doctor_report(ws)
    assert "event_chain_broken" not in _codes(unanchored)        # PINNED LIMITATION
    assert _chain_block(unanchored)["head"] is not None

    anchored = doctor_report(ws, expect_chain_head=original_head)
    assert "chain_anchor_mismatch" in _codes(anchored)           # the anchor is the control
```

  The remaining three, same shape:
  - `test_reorder_detected` — swap two chained rows' payloads without recomputing; assert `event_chain_broken`.
  - `test_truncation_alone_not_detected_but_anchor_catches_it` — delete the trailing **`receipt_appended`** (state-neutral, so `_state_divergence` stays clean); assert `"event_chain_broken" not in codes` and `chain["head"] is not None` unanchored, and `chain_anchor_mismatch` with the pre-attack head.
  - `test_legacy_store_tamper_is_undetectable_pinned` — on a never-migrated store, edit an iteration entry's `summary` (a field the projection carries but `_state_divergence` does not compare); assert no `event_chain_broken` and `chain == {"head": None, "unchained_prefix": N}`. **No retroactive coverage.**
  - `test_column_drop_downgrade_is_silent_without_anchor_pinned` — `ALTER TABLE events DROP COLUMN event_hash` **and** `PRAGMA user_version = 0` (defeating the D2 cross-check); assert no `event_chain_broken` and `chain["head"] is None` unanchored, and `chain_anchor_mismatch` with the pre-attack head.
- [ ] **Step 2:** Run the file — all PASS. Any failure is a Task 1–9 bug; fix there, not here.
- [ ] **Step 3: Negative control.** `git -C ... worktree add /abs/path/.tmp/chain-negctl main`; overlay exactly `loop/chain.py`, `scripts/chain_fixtures.py` and `scripts/test_adversarial_chain.py`; run `test_splice_detected`. It must fail as an **assertion failure on the missing `event_chain_broken` code** — not a collection or import error. If it errors on import, the overlay set is wrong (the test must not import `loop.migrate` or any other new module); trim the test's imports until the control is clean. Record the failing output in the PR body, then remove the worktree.
- [ ] **Step 4:** Commit: `test(chain): adversarial coverage + four pinned honest limitations (recompute, truncation, downgrade, legacy)`.

### Task 11: Zero-write proofs on both store generations

**Files:** Extend `scripts/test_loop_simulate_zero_writes.py`.

- [ ] **Step 1: Write the tests:**
  - A legacy-store variant of the pristine-store tree-hash test (`from chain_fixtures import make_legacy_store`; state.json synced), asserting `_without_shm(before) == _without_shm(after)` after `simulate`, plus `status_report(ws)["chain_head"] is None`.
  - A chained-store test running `doctor` + `status` + `replay` on a clean, checkpointed store and asserting **zero-carve-out** full-tree hash equality (possible now the immutable-URI fix landed). Keep `_without_shm` for the crash-left-WAL case only.
- [ ] **Step 2:** Run — the zero-carve-out test FAILS if Task 8's read-connector work is incomplete; fix there, not here.
- [ ] **Step 3:** Run the whole existing file — pre-existing tests pass (their fixtures now produce v2 stores, which is the desired default).
- [ ] **Step 4:** Commit: `test(zero-writes): read verbs proven side-effect-free on both store generations, zero carve-out on clean stores`.

### Task 12: action.yml anchor surface

**Files:** Modify `action.yml`.

- [ ] **Step 1:** Add the input and a **top-level `outputs:` block** (a composite action's internal step outputs are invisible to callers without one — `action.yml` has no `outputs:` key today):

```yaml
  expect-chain-head:
    description: >-
      Fail the gate unless the store's chain head equals this 64-hex value (an
      externally remembered anchor). Empty performs NO cross-run tamper
      detection — the gate then only records the head for a later comparison.
    required: false
    default: ""

outputs:
  chain-head:
    description: "Chain head event_hash observed by this gate run ('' when the store has no chained events)."
    value: ${{ steps.chain-head.outputs.chain-head }}
```

- [ ] **Step 2:** Thread the flag in the doctor step (flag **before** the target, matching the `--mode` convention):

```yaml
      env:
        LOOP_PATH: "${{ inputs.path }}"
        LOOP_EXPECT_HEAD: "${{ inputs.expect-chain-head }}"
      run: |
        if [ -n "$LOOP_EXPECT_HEAD" ]; then
          loop doctor --expect-chain-head "$LOOP_EXPECT_HEAD" "$LOOP_PATH" | tee "${RUNNER_TEMP}/doctor.json"
        else
          loop doctor "$LOOP_PATH" | tee "${RUNNER_TEMP}/doctor.json"
        fi
        # (existing validation-mode assertion block stays verbatim below)
```

  Then the anchor step — **`if: always()`**, because a failing doctor aborts the composite under `-eo pipefail` and the anchor-mismatch run is exactly when an operator needs the observed head recorded:

```yaml
    - name: chain head (anchor surface)
      id: chain-head
      if: always()
      shell: bash
      run: |
        [ -s "${RUNNER_TEMP}/doctor.json" ] || exit 0
        python - "${RUNNER_TEMP}/doctor.json" "$GITHUB_STEP_SUMMARY" "$GITHUB_OUTPUT" <<'PY'
        import json, sys
        try:
            doctor = json.load(open(sys.argv[1]))
        except (OSError, json.JSONDecodeError):
            doctor = {}
        chain = (doctor.get("event_store") or {}).get("chain") or {}
        head = chain.get("head") or {}
        value = head.get("event_hash") or ""
        line = (f"**loop-engineer chain head:** `{value}` (sequence {head.get('sequence')})"
                if value else "**loop-engineer chain head:** none (no chained events)")
        open(sys.argv[2], "a").write(line + "\n")
        open(sys.argv[3], "a").write(f"chain-head={value}\n")
        PY
```

- [ ] **Step 3:** Validate: `uv run --with pyyaml python3 -c "import yaml; d=yaml.safe_load(open('/mnt/c/Dev/projects/loop-engineer/action.yml')); assert d['outputs']['chain-head']['value'] == '\${{ steps.chain-head.outputs.chain-head }}'; assert d['inputs']['expect-chain-head']['default'] == ''"`. (No live CI test pre-merge; the repo's own CI exercises the action post-merge.)
- [ ] **Step 4:** Commit: `feat(action): record the chain head on every run and optionally enforce it as an anchor`.

### Task 13: Docs — normative canonicalization, integrity boundary, and the three stale sentences

**Files:** Modify `reference/repo-os-contract.md` (§16, §22), `README.md`.

No new file in `reference/` (structural.json pins the 8-filename list).

- [ ] **Step 1: §16 additions.** A `### Hash chain (v0.10.0+)` subsection covering: the two additive fields; the canonical form pinned exactly (`json.dumps(preimage, sort_keys=True, separators=(",",":"), ensure_ascii=False, allow_nan=False)` UTF-8, the 12-field preimage list, absent-optionals-as-null, genesis `prev_event_hash: null`, Python shortest-repr float caveat, ASCII-keys recommendation); **three conformance vectors** (genesis event, second linked event, unicode-payload event — literal JSON in, literal sha256 out, generated by running `loop/chain.py` and pasted verbatim); `loop.chain.verify_chain(events, expected_head=...)` named as the normative third-party re-verification entry point, **scoped**: it requires a complete run stream beginning at sequence 0. One normative interop sentence: *"Populating the chain fields is optional per run but all-or-nothing after the first chained event: once an event carries `event_hash`, every later event in that run must too and must match the canonical preimage exactly, or the reference implementation hard-fails the store."* One compatibility rule: *"A pre-0.10.0 writer must not append to a chained store. A fresh v0.10.0 store refuses such an append at the database (`event_hash NOT NULL`); a migrated store cannot, and an unchained row appended after a chained prefix is reported as `event_chain_broken` and is unrepairable, because UPDATE is trigger-blocked. Pin your loop-engineer (and action) version per store."*

  Then a `### Integrity boundary` subsection, in plain language. **Detects:** splice, reorder, edit-without-recompute, corruption, and any divergence from an anchored head. **Does not detect:** (a) a full in-workspace recompute — a process with write access can rewrite history, re-chain from genesis, and forge `state.json`/`terminal_state.json` to match; (b) dropping the chain columns or rebuilding the store without them — a chained history downgrades to an unchained one, and an unchained/legacy doctor report is *not* proof of provenance (the `chain_columns_missing` check catches only the lazy variant); (c) deleting the store outright when no sidecars remain and no anchor is supplied; (d) well-formed lies in payloads; (e) anything in a never-migrated prefix. Plus the **mid-run window**: *"An anchor certifies the log only up to the anchored head. Everything appended after the last externally-read anchor — including a rewrite of the suffix — is unverified until the next anchor is read and remembered outside the workspace. The chain narrows the tampering window; it does not close it."* Close with: the append-only triggers are an anti-footgun, not a security control (any writer can `DROP TRIGGER`); the chain is one of several cross-checks (`_state_divergence`, `_terminal_desync`, G1) that a full rewrite must satisfy simultaneously; and `scripts/test_adversarial_chain.py` pins both sides of this boundary.
- [ ] **Step 2: §22 additions:** the `chain` block nested under `event_store`; the four new issue codes; the `loop migrate` verb; the never-elided unchained-prefix rule; and *"read verbs assume no concurrent writer — the sidecar-free guarantee holds only for a store whose last writer closed cleanly."*
- [ ] **Step 2b: §22 "Anchor trust assumptions"** — the anchor is outside the worker's trust domain only when (a) the action is pinned to a released tag/SHA of a repo the worker cannot write **and** the `version` input is non-empty, so the kernel is not installed from the worker's own checkout (`action.yml:43-47` installs from `github.action_path` when `version` is empty); (b) the invoking workflow is protected from worker edits (required workflow, CODEOWNERS on `.github/`, or a branch ruleset) — for a same-repo PR the workflow that runs is the PR head's; (c) the expected head is remembered outside the workspace. State plainly: *"with the default empty `expect-chain-head`, this action performs no cross-run tamper detection; it records the head for a comparison someone else must make."* Recommend always passing an anchor in CI, because a bare `loop doctor` treats a fully deleted store as a valid never-ran contract.
- [ ] **Step 3: Amend the three now-false normative sentences** (this file is the repo's tool-agnostic spec, so a stale sentence is a published false claim):
  - §16 (~587-589) "the triggers refuse mutation or removal of a committed row, regardless of caller" → "…refuse mutation or removal **through the store API**, regardless of caller; a process with direct write access to the database file can `DROP TRIGGER` — the triggers are an anti-footgun, not a security control (see Integrity boundary)."
  - §16 (~634-635) "a second, independent enforcement point that a tampered or foreign-sourced event stream still cannot talk past" → "…cannot talk past **without constructing a stream that is itself FSM-legal, G1-satisfying and hash-chain-consistent; a determined in-workspace rewriter can construct one — see Integrity boundary.**"
  - §22 (~770-771) "An absent store is conformant: doctor reports `"event_store": {"present": false}`" → "An absent store **with no SQLite sidecar residue and no `--expect-chain-head`** is conformant…; sidecar residue (`missing_event_store`) or a supplied anchor (`chain_anchor_mismatch`) fails doctor."
- [ ] **Step 4: README prose** (version surfaces are Task 15): extend the event-sourced-runtime bullet with one sentence — "events are hash-chained; `loop doctor --expect-chain-head` verifies the log against an externally anchored head" — and one honest clause: "the chain is tamper-evident **relative to an anchor**; an adversary with workspace write access can rewrite an unanchored log." Do **not** touch the "how it compares" heading or the FCR/RP markers (structural.json `readme_differentiation` pins them).
- [ ] **Step 5: Pin the vectors with a test.** Append `test_documented_conformance_vectors` to `scripts/test_event_chain.py`: the three literal records and their three literal digests as module constants; assert `compute_event_hash(record) == digest` for each, **and** that each digest string appears in `reference/repo-os-contract.md` — so docs and code cannot drift.
- [ ] **Step 6:** Run `uv run --with pyyaml python3 -B scripts/self_eval.py` (13/13 — proves the pins survived), `scripts/test_docs_adoption.py`, and the extended `scripts/test_event_chain.py`.
- [ ] **Step 7:** Commit: `docs(contract): normative chain canonicalization, conformance vectors, integrity boundary, anchor trust assumptions`.

### Task 14: Full-suite gate + feature PR

**Files:** none new.

- [ ] **Step 1:** Full suite, extras: `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts`. Compute the expected count first (Task-0 baseline + a per-file tally of every test added in Tasks 1–13) and compare — a mismatch in either direction is a stop-and-explain.
- [ ] **Step 2:** Full suite, pyyaml-only. The jsonschema-parametrized halves skip; predict that arithmetic separately (the two deltas differ — this repo's known asymmetric-baseline class).
- [ ] **Step 3:** Fresh-worktree verification: `git -C ... worktree add /abs/path/.tmp/chain-fresh feat/event-chain`, run both suites there, record both numbers as the PR-body baselines (live checkout reads +2/−2). Remove the worktree.
- [ ] **Step 4:** `uv run --with pyyaml python3 -B scripts/validate_frontmatter.py` (9/9) and `scripts/self_eval.py` (13/13).
- [ ] **Step 5:** Push, open PR **non-draft** (single `opened` event — the CI-wedge lesson): `feat(kernel): hash-linked event chain with anchored doctor gate (v0.10.0, slice 1/5)`. Body carries: the integrity-boundary statement verbatim, the Task-10 Step-3 negative-control output, both fresh-worktree baselines, and the behavior matrix below with the **named test** for each row. The 6 required checks + auto-merge per repo ruleset.

**Behavior matrix — each row names the test that proves it:**

| Store | Verb(s) | Expected | Test |
|---|---|---|---|
| legacy (never migrated) | doctor | `ok`; `chain == {"head": null, "unchained_prefix": N}` | `test_legacy_store_doctor_ok_and_chain_null` |
| legacy | status/replay | unchanged; `chain_head` is `None` | `test_legacy_store_doctor_ok_and_chain_null` + Task 11 legacy variant |
| legacy | simulate | zero writes, tree-hash equal | Task 11 legacy variant |
| legacy, tampered | doctor | no `event_chain_broken` (pinned limitation) | `test_legacy_store_tamper_is_undetectable_pinned` |
| migrated, no new appends | doctor | `ok`; unchained prefix reported | `test_migrated_store_doctor_reports_unchained_prefix` |
| migrated + appends | doctor | `ok`; genesis-after-prefix head | `test_migrated_store_after_append_reports_genesis_head` |
| fresh v2 | status/replay/doctor | `ok`; chain head present | `test_status_and_replay_expose_chain_head`, `test_doctor_nests_chain_under_event_store` |
| fresh v2, payload flipped | doctor/status/replay | hard fail `event_chain_broken` | `test_tampered_store_fails_doctor_status_and_replay_with_event_chain_broken` |
| fresh v2, payload flipped | run | `RuntimeStoreError("event_chain_broken")` | `test_run_on_tampered_store_reports_event_chain_broken` |
| fresh v2, splice / reorder | doctor | hard fail `event_chain_broken` | `test_splice_detected`, `test_reorder_detected` |
| fresh v2, full recompute + forged state | doctor (no flag) | no `event_chain_broken` (pinned) | `test_full_rewrite_with_recompute_passes_without_anchor_pinned` |
| fresh v2, full recompute | doctor `--expect-chain-head` | hard fail `chain_anchor_mismatch` | same test, second half |
| fresh v2, truncated tail | doctor / doctor+anchor | pass / `chain_anchor_mismatch` | `test_truncation_alone_not_detected_but_anchor_catches_it` |
| fresh v2, columns dropped + version 2 | doctor | hard fail `chain_columns_missing` | `test_chain_columns_dropped_but_version_2_fails_doctor` |
| fresh v2, columns dropped + version reset | doctor / +anchor | pass (pinned) / `chain_anchor_mismatch` | `test_column_drop_downgrade_is_silent_without_anchor_pinned` |
| pre-0.10.0 10-column INSERT | fresh store | refused by the DB | `test_legacy_style_ten_column_insert_is_refused_by_a_fresh_store` |
| in-row JSON corruption | doctor | `corrupt_store`, no traceback | `test_in_row_json_corruption_fails_doctor_without_traceback` |
| schema-invalid event row | status | `RuntimeStoreError("invalid_event")` | `test_invalid_event_now_fails_status_instead_of_being_discarded` |
| absent store, no sidecars, no flag | doctor | byte-stable `{"present": false}` | `test_absent_store_without_flag_or_sidecars_stays_byte_stable` |
| absent store + sidecars | doctor | hard fail `missing_event_store` | `test_sidecar_residue_without_db_fails_doctor` |
| absent / unreadable store + flag | doctor | hard fail `chain_anchor_mismatch` | `test_expect_chain_head_with_missing_store_fails_doctor`, `..._with_unreadable_store_...` |
| clean stores, both generations | simulate/status/replay/doctor | zero new files, tree-hash equal (no carve-out) | `test_read_verbs_leave_no_wal_sidecars_on_clean_store` + Task 11 |
| CLI, flag before target | doctor | resolves the real target; exit 0/1 | `test_cli_doctor_accepts_flag_before_target` |
| CLI, flag on other verbs | scaffold/status | exit 2, nothing created | `test_cli_rejects_flag_on_other_commands_and_creates_nothing` |

### Task 15: Release cut v0.10.0 (separate PR, after Task 14 merges)

**Files:** Modify `pyproject.toml`, `.claude-plugin/plugin.json`, `README.md`, `scripts/test_docs_version.py`, `CHANGELOG.md`.

- [ ] **Step 1:** Branch `release/v0.10.0` off updated main. Bump `version = "0.10.0"` in pyproject and plugin.json.
- [ ] **Step 2: README version surfaces** (four, none currently machine-pinned): the badge at line 8 (`release-0.9.0` → `release-0.10.0`), the documented action pin at line 331 (`SollanSystems/loop-engineer@v0.9.0` → `@v0.10.0`), and the release/tag table rows at lines 424-425.
- [ ] **Step 3:** `scripts/test_docs_version.py`: retarget the version pin to `"0.10.0"` (line 20), add `"## 0.10.0"` to the CHANGELOG-headings assertions, **and add new assertions that the README badge and the documented action pin match `plugin["version"]`** so this surface is machine-pinned from now on.
- [ ] **Step 4: CHANGELOG `## 0.10.0`** — chain fields + store-side computation; `loop migrate`; doctor `chain` block, `--expect-chain-head`, and the four new issue codes; plus these explicit behavioral flags:
  - (a) status/replay/doctor now **reject** stores containing schema-invalid events (previously silently ignored).
  - (b) read verbs no longer leave `-wal`/`-shm` sidecars on clean stores — resolves the 0.9.0 known limitation (**update that 0.9.0 line with a pointer; do not delete it**).
  - (c) the integrity-boundary paragraph, including the mid-run-window sentence verbatim from Task 13.
  - (d) **compatibility, both directions:** pre-0.10.0 readers CAN read v2 stores (their explicit 10-column SELECT is unaffected by the extra columns); pre-0.10.0 **writers must not append to a chained store** — a fresh v0.10.0 store refuses the append at the database, and on a migrated store such an append produces a permanent, unrepairable `event_chain_broken` (UPDATE is trigger-blocked). Pin your loop-engineer/action version per store.
- [ ] **Step 5:** Full suite + `python3 -m loop --version` smoke. PR, merge, then tag per the standing flow (`git tag v0.10.0 <squash-sha> && git push origin v0.10.0` → PyPI publish), verify PyPI + `uvx loop-engineer@0.10.0 inspect examples/coverage-repair` from a scratch clone, refresh the plugin cache (`git archive HEAD | tar -x -C <cache-dir>`; `diff -rq` to verify).

---

## Self-review

- **Coverage vs the assessment's Slice-1 scope:** chain ✔ (T1-7), anchor ✔ (T9/T12), migrate ✔ (T6), absent-store fix ✔ (T9), downgrade cross-check ✔ (T9), discarded-validation fix ✔ (T8), sidecar fix ✔ (T8/T11), honest-limitation tests ✔ (T10), behavior matrix with named tests ✔ (T14), honest docs incl. stale-sentence amendments ✔ (T13), release ✔ (T15). `payload_digest` column and Merkle checkpoints deliberately absent (assessment: dropped/deferred).
- **Names consistent across tasks:** `chain.link_issue`/`compute_event_hash`/`verify_chain`/`canonical_json`, `has_chain_columns`, `store_user_version`, `read_event_rows`, `EventRowDecodeError`, `EventStoreOperationalError`, `ChainBreakError`, `migrate_store`, `_read_only_connect`, `expect_chain_head`, `chain_fixtures.make_legacy_store`/`drop_triggers`/`restore_triggers`.
- **Every task ends green.** Task 3's fresh-store chaining assertion was moved into Task 4 so no task commits a knowingly-red test.
- **Open risks for the implementer:** (1) existing tests pinning exact record key-sets or `event_store` key-sets need deliberate in-place updates (T3 Step 5, T8 Step 4 — treat each as a reviewed edit and list it in the commit body); (2) new-test counts must be tallied per file before the T14 gate — this plan does not guess them; (3) `test_adversarial_process.py`'s raw-byte-boundary pin may interact with chain enforcement — run it at T7 Step 4 and adjudicate toward keeping both pins honest; (4) the `<chained workspace helper>` and `<existing fresh-contract helper>` placeholders in Tasks 8-10 must be resolved to the real helper names in `scripts/test_doctor_eventstore.py:12-30` at execution time — read that file first, then write the tests.
