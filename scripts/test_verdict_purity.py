"""The ADR 0002 boundary, made mechanical.

These tests exist so the kernel/signer boundary cannot decay into an intention:
the kernel may hash, it must never sign, never read the environment, and never
emit anything but the allowlisted, prose-free predicate body.
"""
import ast
import json
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
LOOP = REPO / "loop"

_SIGNING_TOKENS = ("sigstore", "cosign", "fulcio", "rekor", "dsse",
                   "private_key", "PRIVATE KEY", "ACTIONS_ID_TOKEN",
                   "id_token", "oidc")


def test_kernel_never_references_a_signing_stack():
    """ADR 0002: the kernel may hash; it must never sign."""
    offenders = []
    for path in LOOP.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for token in _SIGNING_TOKENS:
            if token.lower() in text:
                offenders.append(f"{path.relative_to(REPO)}:{token}")
    assert offenders == [], offenders


def test_kernel_reads_no_environment_variable():
    """Zero matches at HEAD 0025acc; this keeps it that way. A verdict that
    read GITHUB_SHA would put a vendor identifier inside the portable layer."""
    offenders = []
    for path in LOOP.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "os.environ" in text or "getenv" in text:
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == [], offenders


def test_verdict_module_imports_only_stdlib_and_loop():
    tree = ast.parse((LOOP / "verdict.py").read_text(encoding="utf-8"))
    third_party = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module and node.module.split(".")[0] not in sys.stdlib_module_names:
                third_party.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in sys.stdlib_module_names:
                    third_party.append(alias.name)
    assert third_party == [], third_party


def _predicate():
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "loop", "verdict", "examples/flaky-test-triage"],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_predicate_field_allowlist_holds():
    """Everything here is public, append-only, and permanent. Adding a field is
    a one-way door — this test is the door."""
    doc = _predicate()
    assert set(doc) == {"schema", "run_id", "tool", "doctor", "chain", "terminal", "evidence"}
    assert set(doc["doctor"]) == {"ok", "validation_mode", "issue_codes", "schemas_checked"}
    assert set(doc["chain"]) == {"head", "sequence", "unchained_prefix"}
    assert set(doc["terminal"]) == {"state", "completion_policy", "false_completion"}
    for entry in doc["evidence"]:
        assert set(entry) == {"digest", "code_digest", "policy_digest"}


def test_predicate_carries_no_free_text_but_run_id():
    """run_id is the ONE operator-controlled string, allowlisted deliberately.
    Any other prose in the document is a leak into a permanent public log."""
    doc = _predicate()
    strings = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str):
            strings.append((path, node))

    walk(doc, "")
    for path, value in strings:
        if path == ".run_id":
            continue
        # Whitespace is the proxy for prose. Every other string in the document
        # is a digest, an enum, a snake_case issue code, or a slash-separated
        # schema id — none of which contain a space.
        assert " " not in value, f"free text at {path}: {value!r}"


def test_predicate_validates_against_its_own_schema():
    # importorskip, not bare __import__: in the structural-fallback environment
    # this must skip honestly rather than error.
    jsonschema = pytest.importorskip("jsonschema")
    from loop.verdict import _load_verdict_schema

    jsonschema.validate(_predicate(), _load_verdict_schema())
