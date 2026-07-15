"""loop-engineer/evidence@1 — hashed evidence + artifact provenance.

Kernel-side validation and verification only: this module is standalone in v1
and is not yet read by ``loop doctor`` (see reference/repo-os-contract.md #17).
Writer and doctor wiring are deferred to the execution-runtime milestone.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping

from .contract import ContractIssue, _resolve_requested_mode, _schemas_dir


EVIDENCE_SCHEMA_ID = "loop-engineer/evidence@1"
_URI_PATTERN = re.compile(r"^(?!/)(?![A-Za-z][A-Za-z0-9+.\-]*://).+$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class EvidenceError(ValueError):
    """The workspace-root precondition for evidence verification was not met."""


def _load_evidence_schema() -> dict[str, Any]:
    return json.loads((_schemas_dir() / "evidence.schema.json").read_text(encoding="utf-8"))


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _is_valid_uri(value: Any) -> bool:
    return _is_non_empty_string(value) and _URI_PATTERN.fullmatch(value) is not None


def _structural_validate_evidence(data: dict[str, Any]) -> list[ContractIssue]:
    """Stdlib fallback equivalent to the schema's complete evidence surface."""
    issues: list[ContractIssue] = []
    if data.get("schema") != EVIDENCE_SCHEMA_ID:
        issues.append(ContractIssue("invalid_evidence", f"schema must equal {EVIDENCE_SCHEMA_ID!r}"))
    for field in ("id", "kind", "media_type", "created_at"):
        if not _is_non_empty_string(data.get(field)):
            issues.append(ContractIssue("invalid_evidence", f"{field} must be a non-empty string"))
    if not _is_valid_uri(data.get("uri")):
        issues.append(ContractIssue("invalid_uri", "uri must be a non-empty workspace-relative POSIX path without a URI scheme"))
    sha256 = data.get("sha256")
    if not isinstance(sha256, str) or _SHA256_PATTERN.fullmatch(sha256) is None:
        issues.append(ContractIssue("invalid_evidence", "sha256 must be a 64-character lowercase hexadecimal string"))

    produced_by = data.get("produced_by")
    if not isinstance(produced_by, dict):
        issues.append(ContractIssue("invalid_evidence", "produced_by must be an object"))
    else:
        for field in ("run_id", "task_id", "attempt", "executor"):
            if field not in produced_by:
                issues.append(ContractIssue("invalid_evidence", f"produced_by missing required field {field!r}"))
        if not _is_non_empty_string(produced_by.get("run_id")):
            issues.append(ContractIssue("invalid_evidence", "produced_by.run_id must be a non-empty string"))
        task_id = produced_by.get("task_id")
        if task_id is not None and not isinstance(task_id, str):
            issues.append(ContractIssue("invalid_evidence", "produced_by.task_id must be a string or null"))
        attempt = produced_by.get("attempt")
        if attempt is not None and (not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1):
            issues.append(ContractIssue("invalid_evidence", "produced_by.attempt must be an integer >= 1 or null"))
        if not _is_non_empty_string(produced_by.get("executor")):
            issues.append(ContractIssue("invalid_evidence", "produced_by.executor must be a non-empty string"))

    verified_by = data.get("verified_by")
    if verified_by is not None:
        if not isinstance(verified_by, dict):
            issues.append(ContractIssue("invalid_evidence", "verified_by must be an object or null"))
        else:
            for field in ("by", "at"):
                if not _is_non_empty_string(verified_by.get(field)):
                    issues.append(ContractIssue("invalid_evidence", f"verified_by.{field} must be a non-empty string"))

    policy_result = data.get("policy_result")
    if policy_result is not None:
        if not isinstance(policy_result, dict):
            issues.append(ContractIssue("invalid_evidence", "policy_result must be an object or null"))
        elif not isinstance(policy_result.get("ok"), bool):
            issues.append(ContractIssue("invalid_evidence", "policy_result.ok must be a boolean"))
    return issues


def _jsonschema_validate_evidence(data: dict[str, Any]) -> list[ContractIssue]:
    import jsonschema  # type: ignore

    validator = jsonschema.Draft202012Validator(_load_evidence_schema())
    issues: list[ContractIssue] = []
    for error in validator.iter_errors(data):
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        code = "invalid_uri" if tuple(error.absolute_path) == ("uri",) else "invalid_evidence"
        issues.append(ContractIssue(code, f"{location}: {error.message}"))
    return issues


def validate_evidence(data: dict[str, Any], *, mode: str | None = None) -> dict[str, Any]:
    """Validate a standalone evidence@1 record in the requested validation mode."""
    requested_mode, resolved_mode = _resolve_requested_mode(mode)
    if not isinstance(data, dict):
        issues = [ContractIssue("invalid_evidence", "evidence record must be an object")]
    elif resolved_mode == "jsonschema":
        issues = _jsonschema_validate_evidence(data)
    else:
        issues = _structural_validate_evidence(data)
    return {"ok": not issues, "validation_mode": resolved_mode, "requested_mode": requested_mode,
            "schemas_checked": [EVIDENCE_SCHEMA_ID], "issues": issues}


def verify_evidence(evidence: Mapping[str, Any], *, workspace_root: str | Path) -> dict[str, Any]:
    """Verify one evidence record's workspace containment and SHA-256 content."""
    root = Path(workspace_root)
    if not root.is_dir():
        raise EvidenceError(f"workspace_root must be an existing directory: {root}")

    checks: dict[str, bool | None] = {
        "structural": None, "within_workspace": None, "path_exists": None, "hash_match": None,
    }
    record = dict(evidence) if isinstance(evidence, Mapping) else evidence
    report = validate_evidence(record, mode="basic")
    checks["structural"] = report["ok"]
    if not report["ok"]:
        return {"ok": False, "checks": checks, "issues": report["issues"]}

    uri = record["uri"]
    if not _is_valid_uri(uri):
        checks["structural"] = False
        return {"ok": False, "checks": checks,
                "issues": [ContractIssue("invalid_uri", "uri must be a workspace-relative POSIX path without a URI scheme")]}
    try:
        resolved = (root / uri).resolve(strict=True)
    except ValueError:
        return {"ok": False, "checks": checks,
                "issues": [ContractIssue("invalid_uri", f"uri cannot be resolved as a path: {uri}")]}
    except (OSError, FileNotFoundError, RuntimeError):
        checks["path_exists"] = False
        return {"ok": False, "checks": checks,
                "issues": [ContractIssue("missing_evidence_path", f"evidence path does not exist: {uri}")]}

    checks["path_exists"] = True
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        checks["within_workspace"] = False
        return {"ok": False, "checks": checks,
                "issues": [ContractIssue("workspace_escape", f"evidence path escapes workspace: {uri}")]}
    checks["within_workspace"] = True
    try:
        fd = os.open(
            resolved,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        )
    except OSError:
        checks["path_exists"] = False
        return {"ok": False, "checks": checks,
                "issues": [ContractIssue("missing_evidence_path", f"evidence path is unavailable: {uri}")]}
    try:
        file_stat = os.fstat(fd)
    except OSError:
        os.close(fd)
        checks["path_exists"] = False
        return {"ok": False, "checks": checks,
                "issues": [ContractIssue("missing_evidence_path", f"evidence path is unavailable: {uri}")]}
    if not stat.S_ISREG(file_stat.st_mode):
        os.close(fd)
        return {"ok": False, "checks": checks,
                "issues": [ContractIssue("not_a_file", f"evidence path is not a file: {uri}")]}

    digest = hashlib.sha256()
    try:
        with os.fdopen(fd, "rb") as source:
            while chunk := source.read(64 * 1024):
                digest.update(chunk)
    except OSError:
        checks["path_exists"] = False
        return {"ok": False, "checks": checks,
                "issues": [ContractIssue("missing_evidence_path", f"evidence path is unavailable: {uri}")]}
    checks["hash_match"] = digest.hexdigest() == record["sha256"]
    if not checks["hash_match"]:
        return {"ok": False, "checks": checks,
                "issues": [ContractIssue("hash_mismatch", f"sha256 does not match evidence path: {uri}")]}
    return {"ok": True, "checks": checks, "issues": []}


def artifact_object_path(workspace_root: str | Path, sha256: str) -> Path:
    """Return evidence@1's content-addressed artifact location without I/O."""
    return Path(workspace_root) / ".loop" / "artifacts" / "objects" / sha256[:2] / sha256
