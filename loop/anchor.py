"""Read a tracked ``anchor@1`` file that CARRIES a previously attested chain head.

Nothing here is trusted. The anchor is a *carried claim* whose only function is to
give an attestation lookup a digest to ask about: GitHub exposes no endpoint that
lists attestations without a subject digest, so an attestation can corroborate a
head but can never discover one. Anchor trust is therefore exactly ordinary write
access to the anchor file — no better, and the same class of limit as ADR 0002's
"the worker can edit the verifier".

Pure: no environment, no network, no signing, no subprocess.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ._resources import schemas_dir

ANCHOR_SCHEMA_ID = "loop-engineer/anchor@1"
DEFAULT_ANCHOR_FILENAME = "loop-anchor.json"

_HEAD_PATTERN = re.compile(r"[0-9a-f]{64}")
_LOOP_DIR_NAME = ".loop"

# Mirrors schemas/anchor.schema.json. The structural leg must refuse everything the
# schema refuses, for every field the schema declares — a schema-only check would let
# a jsonschema-less environment accept a document the schema rejects (the S3
# plan-lint mode-parity repair is the precedent).
_OPTIONAL_STRINGS = {"attestation_id": (0, 64), "run_id": (1, 256), "recorded_at": (0, 64)}
_KNOWN_KEYS = {"schema", "chain_head", "sequence", *_OPTIONAL_STRINGS}


class AnchorError(ValueError):
    """The anchor file is absent, unreadable, or not a conformant ``anchor@1``."""


def _load_anchor_schema() -> dict[str, Any]:
    return json.loads((schemas_dir() / "anchor.schema.json").read_text(encoding="utf-8"))


def _structural_violation(data: dict[str, Any]) -> str | None:
    """The first way ``data`` departs from ``anchor@1``, or ``None``."""
    if data.get("schema") != ANCHOR_SCHEMA_ID:
        return f"schema must be {ANCHOR_SCHEMA_ID!r}, found {data.get('schema')!r}"
    head = data.get("chain_head")
    if not isinstance(head, str):
        return "chain_head is required and must be a string"
    if _HEAD_PATTERN.fullmatch(head) is None:
        # fullmatch, never match: `pattern` in JSON Schema is re.search semantics, so
        # a prefix-anchored check alone accepts 64 hex followed by anything.
        return "chain_head must be 64 lowercase hex characters"
    unknown = sorted(set(data) - _KNOWN_KEYS)
    if unknown:
        return f"unknown field(s): {', '.join(unknown)}"
    sequence = data.get("sequence")
    if sequence is not None:
        # bool is an int subclass in Python; the schema means integer, not True.
        if isinstance(sequence, bool) or not isinstance(sequence, int):
            return "sequence must be an integer"
        if sequence < 0:
            return "sequence must be >= 0"
    for field, (minimum, maximum) in _OPTIONAL_STRINGS.items():
        value = data.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            return f"{field} must be a string"
        if not minimum <= len(value) <= maximum:
            return f"{field} must be {minimum}..{maximum} characters"
    return None


def _schema_violation(data: dict[str, Any]) -> str | None:
    """The first jsonschema violation, or ``None`` when jsonschema is unavailable.

    Defence in depth over the structural checks, never a replacement: ``iter_errors``
    *collects* errors and never raises, so there is no ``ValueError`` to catch here —
    every jsonschema call site in this package uses the same idiom.
    """
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return None
    validator = jsonschema.Draft202012Validator(_load_anchor_schema())
    for error in validator.iter_errors(data):
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        return f"{location}: {error.message}"
    return None


def read_anchor(path: str | Path) -> dict[str, Any]:
    """Read and validate an ``anchor@1`` document.

    Every failure is an :class:`AnchorError`. Nothing else escapes — a caller
    gating on an anchor must never receive a bare ``OSError`` or
    ``UnicodeDecodeError`` where it expected a typed refusal.
    """
    path = Path(path)
    if _LOOP_DIR_NAME in path.parts:
        raise AnchorError(
            f"anchor must not live under {_LOOP_DIR_NAME}/: {path} — an anchor inside "
            "the tree it certifies is gitignored, so it would never land in a commit"
        )
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AnchorError(f"anchor file is unreadable: {path}: {exc}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AnchorError(f"anchor file is not valid UTF-8: {path}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnchorError(f"anchor file is not valid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise AnchorError(f"anchor document must be an object: {path}")
    violation = _structural_violation(data) or _schema_violation(data)
    if violation is not None:
        raise AnchorError(f"anchor is not a conformant {ANCHOR_SCHEMA_ID}: {path}: {violation}")
    return data
