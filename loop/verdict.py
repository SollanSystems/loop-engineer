"""Project a loop run into a loop-engineer/verdict@1 predicate body.

This module builds a document. It NEVER signs one, never verifies a signature,
never constructs an in-toto Statement, and never reads an environment variable.
The signer lane (action.yml -> actions/attest) owns the envelope claims and every
cryptographic operation. See docs/adr/0002-ci-attested-verdict.md.
"""

from __future__ import annotations

import hashlib
import json
import re
from importlib import metadata
from pathlib import Path
from typing import Any

from ._resources import schemas_dir
from .contract import ContractIssue, _strict_evidence_failure, doctor_report
from .paths import LoopPaths, resolve_loop_paths
from .runtime import RuntimeStoreError, bound_artifact_digests

VERDICT_SCHEMA_ID = "loop-engineer/verdict@1"
PREDICATE_TYPE = "urn:loop-engineer:verdict:1"
SUBJECT_NAME = "loop-chain-head"

_HEAD_PATTERN = re.compile(r"[0-9a-f]{64}")


class VerdictError(ValueError):
    """A verdict cannot be projected from this workspace."""


def subject_bytes(head: object) -> bytes:
    """The attested subject's bytes: exactly the 64-hex chain head, nothing else.

    ONE definition, so the signer side and the consumer side cannot disagree about
    64 bytes. The signer hands this file to ``actions/attest`` as ``subject-path``;
    a consumer regenerates byte-identical content from the head alone and hands it
    to ``gh attestation verify``. That is what makes verification runnable at all:
    the chain head is a SHA-256 over a synthesized event preimage, so no retrievable
    bytes hash to it, and ``gh attestation verify`` accepts only a file path or an
    OCI URI and hashes that file's *content* — so an attestation whose subject digest
    IS the head can never be presented an artifact.

    No trailing newline. The byte form is normative: a stray ``\\n`` would change the
    subject digest, so it is pinned by test rather than left to a shell's ``echo``.
    """
    if not isinstance(head, str) or _HEAD_PATTERN.fullmatch(head) is None:
        raise VerdictError(
            "subject requires a 64-character lowercase hex chain head; "
            f"refusing {head!r} (a store-less workspace has no subject to attest)"
        )
    return head.encode("ascii")


def _load_verdict_schema() -> dict[str, Any]:
    return json.loads((schemas_dir() / "verdict.schema.json").read_text(encoding="utf-8"))


def _tool_version() -> str | None:
    try:
        return metadata.version("loop-engineer")
    except metadata.PackageNotFoundError:
        return None


def _terminal_record(paths: LoopPaths) -> dict[str, Any]:
    path = paths.loop_dir / "terminal_state.json"
    if not path.is_file():
        raise VerdictError(
            "no terminal record: a verdict projects a finished run "
            f"({path.name} is absent)"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        # UnicodeDecodeError became reachable here once doctor_report stopped
        # raising it (#107); the site-agnostic typed-contract test depends on it.
        raise VerdictError(f"terminal record is unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise VerdictError("terminal record is not an object")
    if "false_completion" not in data:
        raise VerdictError("terminal record is missing required false_completion")
    if not isinstance(data["false_completion"], bool):
        raise VerdictError("terminal record false_completion must be a boolean")
    return data


def _evidence_digests(entry: object, paths: LoopPaths) -> dict[str, str | None] | None:
    """Return the chain-committed record digest and verifier digests for an entry."""
    if not isinstance(entry, str):
        return None
    try:
        record_bytes = (paths.workspace / entry).read_bytes()
        record = json.loads(record_bytes.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict):
        return None
    verified_by = record.get("verified_by")
    return {
        "digest": hashlib.sha256(record_bytes).hexdigest(),
        "code_digest": verified_by.get("code_digest") if isinstance(verified_by, dict) else None,
        "policy_digest": verified_by.get("policy_digest") if isinstance(verified_by, dict) else None,
    }


def _bound_evidence(paths: LoopPaths) -> dict[str, tuple[str, ...]] | None:
    """Read evidence record digests committed by the event chain."""
    return bound_artifact_digests(paths.workspace)


def _verified_evidence(
    terminal: dict[str, Any], paths: LoopPaths, bound: dict[str, tuple[str, ...]] | None
) -> list[dict[str, str | None]]:
    """Project only terminal evidence that clears the shared strict bar."""
    entries = terminal.get("evidence")
    if not isinstance(entries, list):
        return []
    projected = set()
    for entry in entries:
        if _strict_evidence_failure(entry, paths, bound) is not None:
            continue
        digests = _evidence_digests(entry, paths)
        if digests is None:
            continue
        if bound is not None and (digests["digest"],) != bound.get(entry):
            # The bar validated its own read of the record; this projection read
            # hashed differently, so the bytes moved between the two reads. A
            # digest the chain never committed must not enter a signed document.
            continue
        projected.add((digests["digest"], digests["code_digest"], digests["policy_digest"]))
    return [
        {"digest": digest, "code_digest": code_digest, "policy_digest": policy_digest}
        for digest, code_digest, policy_digest in sorted(
            projected, key=lambda item: (item[0], item[1] or "", item[2] or "")
        )
    ]


COMPARISON_CODES = (
    "verdict_run_id_disagreement",
    "verdict_head_disagreement",
    "verdict_terminal_disagreement",
    "verdict_evidence_disagreement",
)

_UNWRAP_HINT = (
    "compare accepts a BARE loop-engineer/verdict@1 predicate; extract it with "
    "`jq '.[0].verificationResult.statement.predicate'`"
)
_STATEMENT_KEYS = ("_type", "subject", "predicateType", "predicate")
_ENVELOPE_KEYS = ("verificationResult", "attestation")


def _refuse_unless_bare_predicate(attested: object) -> dict[str, Any]:
    """Typed refusals, before any comparison, so an operator who piped a `gh` envelope
    is told to unwrap rather than told their heads disagree.

    Best-effort unwrapping of a vendor envelope here is exactly how a trust boundary
    rots: the kernel would start depending on the shape of another tool's output.
    """
    if isinstance(attested, list):
        raise VerdictError(
            f"attested document is a top-level array — this is a `gh --format json` "
            f"envelope, not a predicate. {_UNWRAP_HINT}")
    if not isinstance(attested, dict):
        raise VerdictError(
            f"attested document is not a JSON object (found {type(attested).__name__}). "
            f"{_UNWRAP_HINT}")
    found = [key for key in _STATEMENT_KEYS if key in attested]
    if found:
        raise VerdictError(
            f"attested document carries {', '.join(found)} — this is an in-toto Statement, "
            f"not a predicate. {_UNWRAP_HINT}")
    wrapper = [key for key in _ENVELOPE_KEYS if key in attested]
    if wrapper:
        raise VerdictError(
            f"attested document carries {', '.join(wrapper)} — this is a `gh --format json` "
            f"envelope, not a predicate. {_UNWRAP_HINT}")
    if attested.get("schema") != VERDICT_SCHEMA_ID:
        raise VerdictError(
            f"attested document is not a {VERDICT_SCHEMA_ID} (schema is "
            f"{attested.get('schema')!r}). {_UNWRAP_HINT}")
    return attested


def _evidence_set(entries: object) -> frozenset[tuple[Any, Any, Any]] | None:
    """The comparable evidence identity: the de-duplicated three-tuple set.

    None for a malformed evidence field, which can never agree with a projection.
    """
    if not isinstance(entries, list):
        return None
    return frozenset(
        (entry.get("digest"), entry.get("code_digest"), entry.get("policy_digest"))
        if isinstance(entry, dict) else ("<non-object>", json.dumps(entry, default=str), None)
        for entry in entries
    )


def _evidence_view(entries: object) -> list[dict[str, Any]]:
    """Digest-only projection of an evidence list for the report's compared block."""
    items = _evidence_set(entries)
    if items is None:
        return []
    return [{"digest": digest, "code_digest": code, "policy_digest": policy}
            for digest, code, policy in sorted(items, key=lambda i: (str(i[0]), str(i[1]), str(i[2])))]


def compare_verdict(attested: object, target: str | Path, *,
                    mode: str | None = None) -> dict[str, Any]:
    """Compare an attested ``verdict@1`` predicate against this workspace's projection.

    This establishes AGREEMENT. ``gh attestation verify`` establishes AUTHENTICITY, it
    runs first, and neither implies the other — so ``signature_checked`` is the literal
    ``False`` on every path and no flag changes it. Four facets are compared: ``run_id``,
    ``chain.head``, the whole ``terminal`` object, and the ``evidence`` digest set.

    ``doctor`` and ``tool`` are deliberately NOT compared: both live inside the
    predicate and are environment-coupled (the same run projects a different
    ``doctor.validation_mode`` with and without jsonschema), so comparing them would
    make an honest environment difference read as tampering. Whether an attested
    ``doctor.ok`` should GATE is a policy question, not an agreement question.

    Refuses (``VerdictError``) anything that is not a bare predicate; the local side
    comes from :func:`build_verdict`, so its no-terminal-record refusal is inherited.
    """
    document = _refuse_unless_bare_predicate(attested)
    local = build_verdict(target, mode=mode)

    attested_chain = document.get("chain") if isinstance(document.get("chain"), dict) else {}
    attested_terminal = (document.get("terminal")
                         if isinstance(document.get("terminal"), dict) else {})
    terminal_facet = ("state", "completion_policy", "false_completion")

    compared = {
        "run_id": {"attested": document.get("run_id"), "local": local["run_id"]},
        "head": {"attested": attested_chain.get("head"), "local": local["chain"]["head"]},
        "terminal": {
            "attested": {key: attested_terminal.get(key) for key in terminal_facet},
            "local": {key: local["terminal"][key] for key in terminal_facet},
        },
        "evidence": {"attested": _evidence_view(document.get("evidence")),
                     "local": _evidence_view(local["evidence"])},
    }
    agreement = {
        "run_id": document.get("run_id") == local["run_id"],
        "head": attested_chain.get("head") == local["chain"]["head"],
        "terminal": compared["terminal"]["attested"] == compared["terminal"]["local"],
        "evidence": _evidence_set(document.get("evidence")) == _evidence_set(local["evidence"]),
    }
    for facet, agrees in agreement.items():
        compared[facet]["agrees"] = agrees

    issues: list[dict[str, Any]] = []
    for facet, code in (("run_id", "verdict_run_id_disagreement"),
                        ("head", "verdict_head_disagreement"),
                        ("terminal", "verdict_terminal_disagreement"),
                        ("evidence", "verdict_evidence_disagreement")):
        if not agreement[facet]:
            issues.append(ContractIssue(
                code,
                f"attested {facet} {compared[facet]['attested']!r} does not agree with the "
                f"local projection {compared[facet]['local']!r}"))
    return {"ok": not issues, "signature_checked": False, "compared": compared, "issues": issues}


def build_verdict(target: str | Path, *, mode: str | None = None) -> dict[str, Any]:
    """Project local run state into a ``verdict@1`` predicate body.

    Pure over the workspace: no environment, network, signing, or verification.
    """
    try:
        paths = resolve_loop_paths(target)
    except (OSError, ValueError, RuntimeError) as exc:
        # RuntimeError is pathlib's symlink-loop signal on Python <= 3.12.
        raise VerdictError(f"cannot resolve a loop workspace at {target}: {exc}") from exc

    # Separate from resolution so an invalid mode= is not reported as a path failure;
    # ValidationModeError is a RuntimeError subclass and would otherwise land above.
    try:
        report = doctor_report(paths.workspace, mode=mode)
    except (OSError, ValueError, RuntimeError) as exc:
        raise VerdictError(f"cannot read the contract at {paths.workspace}: {exc}") from exc

    terminal = _terminal_record(paths)
    try:
        bound = _bound_evidence(paths)
    except RuntimeStoreError:
        evidence = []
    else:
        evidence = _verified_evidence(terminal, paths, bound)
    store = report.get("event_store") or {}
    chain = store.get("chain") or {}
    head = chain.get("head") or {}
    policy = terminal.get("completion_policy")
    policy_mode = policy.get("mode") if isinstance(policy, dict) else None

    return {
        "schema": VERDICT_SCHEMA_ID,
        "run_id": str(store.get("run_id") or paths.workspace.name),
        "tool": {"name": "loop-engineer", "version": _tool_version()},
        "doctor": {
            "ok": bool(report.get("ok")),
            "validation_mode": str(report.get("validation_mode") or "unknown"),
            "issue_codes": sorted({
                str(issue.get("code"))
                for issue in report.get("issues", [])
                if isinstance(issue, dict) and issue.get("code")
            }),
            "schemas_checked": sorted(
                str(schema) for schema in report.get("schemas_checked", [])
            ),
        },
        "chain": {
            "head": head.get("event_hash"),
            "sequence": head.get("sequence"),
            "unchained_prefix": int(chain.get("unchained_prefix") or 0),
        },
        "terminal": {
            "state": terminal.get("state"),
            "completion_policy": policy_mode,
            "false_completion": terminal["false_completion"],
        },
        "evidence": evidence,
    }
