"""Project a loop run into a loop-engineer/verdict@1 predicate body.

This module builds a document. It NEVER signs one, never verifies a signature,
never constructs an in-toto Statement, and never reads an environment variable.
The signer lane (action.yml -> actions/attest) owns the envelope, the subject,
and every cryptographic operation. See docs/adr/0002-ci-attested-verdict.md.
"""

from __future__ import annotations

import json
from typing import Any

from ._resources import schemas_dir

VERDICT_SCHEMA_ID = "loop-engineer/verdict@1"
PREDICATE_TYPE = "urn:loop-engineer:verdict:1"


class VerdictError(ValueError):
    """A verdict cannot be projected from this workspace."""


def _load_verdict_schema() -> dict[str, Any]:
    return json.loads((schemas_dir() / "verdict.schema.json").read_text(encoding="utf-8"))
