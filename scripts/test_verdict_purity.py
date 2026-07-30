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


# --- slice 4b: the boundary extended to the consumption surfaces --------------

# The network and the shell live in scripts/, never in loop/. ONE deliberate exception:
# loop/runner.py runs the contract's own verify command through subprocess (the slice-3b
# subprocess-ISOLATED verifier — shlex argv, shell=False, cwd=workspace, wall-clock cap).
# `loop run` cannot execute a verifier without it, so it is named rather than banned;
# every other module under loop/ must still be shell-free, and a new shell-out site
# anywhere else fails this test.
_SUBPROCESS_ALLOWED = frozenset({"runner.py"})
_NETWORK_MODULES = ("socket", "urllib", "http", "requests", "httpx", "ftplib", "smtplib")
_SHELL_MODULES = ("subprocess", "pty")


def _imported_modules(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module)
    return modules


def _catches_import_error(node: ast.Try) -> bool:
    return any(
        (isinstance(handler.type, ast.Name) and handler.type.id == "ImportError")
        or (isinstance(handler.type, ast.Tuple)
            and any(isinstance(elt, ast.Name) and elt.id == "ImportError"
                    for elt in handler.type.elts))
        for handler in node.handlers
    )


def _third_party_import_sites(path: pathlib.Path) -> list[tuple[str, bool]]:
    """(module, is_guarded) for every non-stdlib import SITE in the file.

    Per site, never per name: a module that is imported once inside a
    try/except ImportError and once at module level is NOT optional, and a
    name-keyed check would wave the unguarded site through.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    guarded_sites = {
        id(inner)
        for node in ast.walk(tree) if isinstance(node, ast.Try) and _catches_import_error(node)
        for statement in node.body
        for inner in ast.walk(statement) if isinstance(inner, (ast.Import, ast.ImportFrom))
    }
    sites: list[tuple[str, bool]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        for name in names:
            if name.split(".")[0] not in sys.stdlib_module_names:
                sites.append((name, id(node) in guarded_sites))
    return sites


@pytest.mark.parametrize("module", ["anchor.py", "attestation.py", "verdict.py"])
def test_new_modules_import_only_stdlib_and_loop(module):
    """Zero NEW runtime dependencies. `jsonschema` is the one declared optional extra and
    is permitted only at a site a try/except ImportError guards — the idiom every
    schema-validating module here already uses. An UNGUARDED jsonschema import would
    silently promote an optional extra into a hard requirement."""
    offenders = [
        name for name, guarded in _third_party_import_sites(LOOP / module)
        if not (name.split(".")[0] == "jsonschema" and guarded)
    ]
    assert offenders == [], offenders


def test_no_module_under_loop_reaches_the_network_or_shells_out():
    """D10.9's new leg. Scoped to import sites, so accurate prose about what the kernel
    does NOT do cannot fail it — and so the one named exception stays visible."""
    network_offenders, shell_offenders = [], []
    for path in sorted(LOOP.rglob("*.py")):
        roots = {name.split(".")[0] for name in _imported_modules(path)}
        network_offenders.extend(f"{path.relative_to(REPO)}:{name}"
                                 for name in _NETWORK_MODULES if name in roots)
        if path.name not in _SUBPROCESS_ALLOWED:
            shell_offenders.extend(f"{path.relative_to(REPO)}:{name}"
                                   for name in _SHELL_MODULES if name in roots)
    assert network_offenders == [], network_offenders
    assert shell_offenders == [], shell_offenders
    # The exception is real, not aspirational: if runner.py ever stops shelling out,
    # tighten _SUBPROCESS_ALLOWED rather than leaving a stale carve-out standing.
    assert "subprocess" in _imported_modules(LOOP / "runner.py")


def _compare_report(document: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", "-m", "loop", "verdict", "--compare", str(document),
         "examples/flaky-test-triage"], capture_output=True, text=True, cwd=REPO)


@pytest.mark.parametrize("surface", ["predicate", "comparison"])
def test_kernel_emits_no_statement_key_anywhere(tmp_path, surface):
    """Neither the predicate nor the comparison report is ever an envelope."""
    predicate = _predicate()
    if surface == "predicate":
        emitted = predicate
    else:
        document = tmp_path / "attested.json"
        document.write_text(json.dumps(predicate), encoding="utf-8")
        proc = _compare_report(document)
        assert proc.returncode == 0, proc.stderr
        emitted = json.loads(proc.stdout)
    assert not {"_type", "subject", "predicateType", "predicate"} & emitted.keys()


def test_compare_report_compared_block_carries_no_free_text(tmp_path):
    """Scoped to report["compared"]: digests, enums and run_id only. issues[].message is
    deliberately exempt — a local report may explain itself; a PREDICATE may not."""
    predicate = _predicate()
    predicate["chain"]["head"] = "b" * 64                    # force a disagreement
    document = tmp_path / "attested.json"
    document.write_text(json.dumps(predicate), encoding="utf-8")
    proc = _compare_report(document)
    assert proc.returncode == 1, proc.stderr                 # a disagreement, as arranged
    report = json.loads(proc.stdout)

    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)

    prose = [text for text in strings(report["compared"]) if " " in text]
    assert prose == [], prose
    # Non-vacuous: the exempt surface really does carry prose, so the scoping matters.
    assert any(" " in issue["message"] for issue in report["issues"])


def test_signature_checked_literal_is_always_false():
    """AST-level over loop/: no assignment and no dict value is anything but False."""
    seen = 0
    for path in sorted(LOOP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value == "signature_checked":
                        seen += 1
                        assert isinstance(value, ast.Constant) and value.value is False, path
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "signature_checked":
                        seen += 1
                        assert isinstance(node.value, ast.Constant) and node.value.value is False
    assert seen >= 2, f"expected the compare report and the policy verdict, found {seen}"
