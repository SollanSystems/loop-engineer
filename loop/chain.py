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
