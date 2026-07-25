"""Verifier identity — honest code/policy digests and the declared criterion partition."""
from __future__ import annotations

import hashlib
from pathlib import Path

from loop import verifier
from loop.verifier import (CODE_DIGEST_BASES, POLICY_FIELDS, criterion_partition,
                           executed_verifier_identity, injected_verifier_identity,
                           verification_policy, verification_policy_digest, verifier_code_digest)


def _task(**overrides):
    base = {"id": "T-1", "title": "t", "status": "pending", "criterion_ref": "C-1",
            "verify": "./scripts/verify-fast.sh", "depends_on": [], "attempts": 0, "evidence": None}
    base.update(overrides)
    return base


def _script(workspace: Path, rel: str, body: str = "#!/bin/sh\nexit 0\n") -> Path:
    path = workspace / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_code_digest_hashes_a_workspace_script(tmp_path):
    path = _script(tmp_path, "scripts/verify-fast.sh")
    digest, basis = verifier_code_digest("./scripts/verify-fast.sh --quiet", tmp_path)
    assert basis == "workspace_file"
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()


def test_code_digest_is_null_for_a_bare_program_name_resolved_through_path(tmp_path):
    _script(tmp_path, "pytest")  # a same-named workspace file is NOT what ran
    assert verifier_code_digest("pytest -q", tmp_path) == (None, "path_lookup")


def test_code_digest_is_null_for_an_absolute_path_outside_the_workspace(tmp_path):
    outside = tmp_path.parent / "outside.sh"
    outside.write_text("#!/bin/sh\n", encoding="utf-8")
    assert verifier_code_digest(f"{outside} run", tmp_path) == (None, "outside_workspace")


def test_code_digest_is_null_when_a_symlink_escapes_the_workspace(tmp_path):
    outside = tmp_path.parent / "escape.sh"
    outside.write_text("#!/bin/sh\n", encoding="utf-8")
    link = tmp_path / "verify.sh"
    link.symlink_to(outside)
    assert verifier_code_digest("./verify.sh", tmp_path) == (None, "outside_workspace")


def test_code_digest_is_null_for_a_missing_relative_path(tmp_path):
    assert verifier_code_digest("./scripts/missing.sh", tmp_path) == (None, "not_a_file")


def test_code_digest_is_null_for_a_directory_argv0(tmp_path):
    (tmp_path / "scripts").mkdir()
    assert verifier_code_digest("./scripts", tmp_path) == (None, "not_a_file")


def test_code_digest_says_unresolvable_when_resolution_raises(tmp_path):
    """An OSError while resolving is 'could not determine', NOT 'not a file'."""
    a, b = tmp_path / "a.sh", tmp_path / "b.sh"
    a.symlink_to(b)
    b.symlink_to(a)  # ELOOP on resolve()
    assert verifier_code_digest("./a.sh", tmp_path) == (None, "unresolvable")


def test_code_digest_says_unresolvable_when_the_WORKSPACE_ROOT_cannot_be_resolved(tmp_path):
    """The workspace root is resolved inside the SAME try as argv[0], and must stay there.

    Both interpreter behaviours land on `unresolvable`: on <=3.12 `Path.resolve()` raises
    pathlib's RuntimeError for a symlink loop, while 3.13 returns the loop unresolved and
    `os.stat` raises ELOOP as an OSError. Narrowing that except boundary to argv[0] alone
    is exactly how Slice 2's Task-1 Critical was born, so the root variant is pinned too.
    """
    root, other = tmp_path / "root-a", tmp_path / "root-b"
    root.symlink_to(other)
    other.symlink_to(root)  # ELOOP on resolving the workspace root itself
    assert verifier_code_digest("./scripts/verify-fast.sh", root) == (None, "unresolvable")


def test_code_digest_is_null_and_explained_when_the_file_cannot_be_read(tmp_path, monkeypatch):
    _script(tmp_path, "scripts/verify-fast.sh")
    monkeypatch.setattr(verifier, "_digest_file", lambda path: None)
    assert verifier_code_digest("./scripts/verify-fast.sh", tmp_path) == (None, "unreadable")


def test_code_digest_is_null_for_an_unparseable_command(tmp_path):
    assert verifier_code_digest("echo 'unbalanced", tmp_path) == (None, "unparseable_command")


def test_code_digest_is_null_for_an_absent_or_blank_command(tmp_path):
    assert verifier_code_digest(None, tmp_path) == (None, "empty_command")
    assert verifier_code_digest("   ", tmp_path) == (None, "empty_command")


def test_every_returned_basis_is_a_declared_basis(tmp_path):
    commands = [None, "   ", "echo 'x", "pytest -q", "./missing.sh", "/bin/sh -c true"]
    assert {verifier_code_digest(c, tmp_path)[1] for c in commands} <= set(CODE_DIGEST_BASES)


def test_executed_identity_block_names_the_command_it_is_about_to_run(tmp_path):
    path = _script(tmp_path, "scripts/verify-fast.sh")
    block = executed_verifier_identity("./scripts/verify-fast.sh", tmp_path)
    assert block == {"command": "./scripts/verify-fast.sh",
                     "code_digest": hashlib.sha256(path.read_bytes()).hexdigest(),
                     "code_digest_basis": "workspace_file", "source": "declared_command"}


def test_injected_identity_block_fabricates_nothing(tmp_path):
    """No declared command ran, so command and digest are null — never the task's verify."""
    assert injected_verifier_identity() == {
        "command": None, "code_digest": None,
        "code_digest_basis": "injected_verifier", "source": "injected_callable"}
    assert "injected_verifier" in CODE_DIGEST_BASES


def test_policy_digest_ignores_run_state(tmp_path):
    a = verification_policy_digest(_task(attempts=0, status="pending", evidence=None))
    b = verification_policy_digest(_task(attempts=7, status="done", evidence=["RUNLOG.md"]))
    assert a == b
    assert set(verification_policy(_task())) == set(POLICY_FIELDS)


def test_policy_digest_changes_when_the_verify_command_changes():
    assert verification_policy_digest(_task()) != verification_policy_digest(_task(verify="true"))


def test_policy_digest_changes_when_the_criterion_ref_changes():
    assert verification_policy_digest(_task()) != verification_policy_digest(_task(criterion_ref="C-2"))


def test_policy_digest_changes_when_the_task_id_changes():
    """id is deliberately bound: the digest identifies WHICH goalpost, not just its shape."""
    assert verification_policy_digest(_task()) != verification_policy_digest(_task(id="T-2"))


def test_policy_digest_changes_when_depends_on_is_reordered():
    """depends_on is bound as declared ordering; a reorder is a visible policy edit."""
    assert (verification_policy_digest(_task(depends_on=["A", "B"]))
            != verification_policy_digest(_task(depends_on=["B", "A"])))


def test_criterion_partition_derives_visible_from_criterion_ref_when_undeclared():
    assert criterion_partition(_task()) == {
        "visible": ["C-1"], "holdout": [], "declared": False, "holdout_executed": False}


def test_criterion_partition_records_a_declared_split_and_never_claims_execution():
    task = _task(visible_criteria=["C-1", "C-2"], holdout_criteria=["C-9"])
    assert criterion_partition(task) == {
        "visible": ["C-1", "C-2"], "holdout": ["C-9"], "declared": True, "holdout_executed": False}


_ROOT = Path(__file__).resolve().parent.parent
_DOC = _ROOT / "reference" / "repo-os-contract.md"
_SAFETY = _ROOT / "reference" / "safety-and-approvals.md"


def test_every_code_digest_basis_is_documented_and_in_the_schema():
    """The nine values co-move across four surfaces; two of them are pinned here."""
    import json as _json
    text = _DOC.read_text(encoding="utf-8")
    schema = _json.loads((_ROOT / "schemas" / "evidence.schema.json").read_text(encoding="utf-8"))
    enum = schema["properties"]["verified_by"]["properties"]["code_digest_basis"]["enum"]
    assert all(basis in text for basis in CODE_DIGEST_BASES)
    assert set(CODE_DIGEST_BASES) | {None} == set(enum)


def test_safety_reference_names_the_machine_check():
    assert "self_verified_evidence" in _SAFETY.read_text(encoding="utf-8")


def test_no_shipped_surface_still_claims_evidence_is_unread():
    """Task 5 makes both claims false; nothing may still ship them."""
    for path in (_ROOT / "loop" / "evidence.py", _ROOT / "schemas" / "evidence.schema.json"):
        text = path.read_text(encoding="utf-8")
        assert "standalone in v1" not in text and "not yet read by" not in text
