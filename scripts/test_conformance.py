"""ST2 acceptance #8 — the runnable conformance checklist.

One test per ratified checklist item ID (A1–E1); each runs against TWO fixtures:

  * ``terminated`` — the tracked flagship ``examples/coverage-repair`` (a real,
    Succeeded contract that ships a terminal file and a repair record);
  * ``inflight``   — a fresh scaffold built here in a tmp dir from ``templates/``
    (``terminal_state: null``, no terminal file — B1's first arm).

C-items are checked-when-present: a fixture that genuinely ships no receipt /
rollout trail is skipped-with-reason for that item, and the trail the fixture
DOES ship is asserted on. Schema conformance is exercised in BOTH validation
modes where meaningful (the jsonschema path when the library is installed, and
the stdlib structural path — forced by hiding ``jsonschema``).

The scaffold helper is intentionally local to this module. S2 writes a similar
helper in ``test_template_roundtrip.py``; duplication between the two modules is
accepted for this slice — this test does not import from S2's module.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import loop.contract as C  # noqa: E402
from loop.contract import TERMINAL_STATES, validate_contract  # noqa: E402
from loop.paths import resolve_loop_paths  # noqa: E402

TEMPLATES = ROOT / "templates"
EXAMPLE = ROOT / "examples" / "coverage-repair"

CHECKLIST_IDS = ("A1", "A2", "A3", "A4", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1")


# --------------------------------------------------------------------------- #
# Local scaffold helper — fill templates/ into a fresh in-flight contract.
# --------------------------------------------------------------------------- #

_STATE_FILL = {
    "PROJECT_NAME": "conformance-inflight",
    "ITERATION_ID": "0",  # quoted in the template -> string "0" -> lifecycle "planned"
    "PLAN_VERSION": "0",
    "ACTIVE_TASK_ID": "T1",
    "STATE": "intake",
    "BEST_SCORE": "null",
    "FAILURE_MODE": "",
    "PENDING_APPROVAL": "null",
    "TIME_REMAINING": "30m",
    "COST_REMAINING": "1.00usd",
    "CHECKPOINT_PATH": ".loop/checkpoints/none",
    "GOAL_DESCRIPTION": "In-flight conformance scaffold",
    "CRITERION_1": "criterion one is proven by pytest -q",
    "CONSTRAINT_1": "no external side effects",
    "WORKSPACE_PATH": "./",
    "ALLOWED_TOOL_1": "read",
    "RISK_PROFILE": "low",
    "TIME_BUDGET": "30m",
    "COST_BUDGET": "1.00usd",
    "APPROVAL_POLICY": "on_side_effects",
    "REPAIR_ATTEMPTS": "0",
    "REPAIR_CAP": "2",
    "LAST_VERIFY_CMD": "pytest -q",
    "LAST_VERIFY_OUTCOME": "PENDING",
    "LAST_SCORE": "null",
    "EVIDENCE_PATH": ".loop/artifacts/",
    "SHORT_TERM_SUMMARY": "scaffolded, not yet run",
    "LESSONS_PATH": ".loop/memory/lessons.md",
}

_MANIFEST_FILL = {
    "LOOP_NAME": "conformance-inflight",
    "GOAL_DESCRIPTION": "In-flight conformance scaffold",
    "CRITERION_1": "criterion one is proven by pytest -q",
    "CONSTRAINT_1": "no external side effects",
    "WORKSPACE_PATH": "./",
    "ALLOWED_TOOLS": "read, workspace-write",
    "RISK_PROFILE": "low",
    "TIME_BUDGET": "30m",
    "COST_BUDGET": "1.00usd",
    "APPROVAL_POLICY": "on_side_effects",
    "PERMISSION_1": "read-only",
    "APPROVAL_GATE_1": "destructive_commands",
    "REPAIR_CAP": "2",
    "PLAN_THEN_EXECUTE": "false",
}

_TASKS_FILL = {
    "PROJECT_NAME": "conformance-inflight",
    "TASK_ID": "T1",
    "TASK_TITLE": "Do the bounded task",
    "TASK_STATUS": "pending",
    "TASK_CRITERION_REF": "1",
    "TASK_VERIFY": "pytest -q",  # a plain command: a verify surface, not a path.
    "CREATED_AT": "2026-01-01T00:00:00Z",
    "UPDATED_AT": "2026-01-01T00:00:00Z",
}


def _fill(template_name: str, mapping: dict[str, str]) -> str:
    text = (TEMPLATES / template_name).read_text(encoding="utf-8")
    for key, value in mapping.items():
        text = text.replace("{{" + key + "}}", value)
    # `{{PLACEHOLDER}}` is a literal doc token in a manifest YAML comment, not a
    # fillable field; every real placeholder must be substituted.
    remaining = [p for p in re.findall(r"{{(\w+)}}", text) if p != "PLACEHOLDER"]
    assert not remaining, f"unfilled placeholders in {template_name}: {remaining}"
    return text


def _scaffold_inflight(target: Path) -> Path:
    """Write a fresh, in-flight (terminal_state: null, no terminal file) contract
    filled from the shipped templates/ into ``target``."""
    loop_dir = target / ".loop"
    loop_dir.mkdir(parents=True)

    state_text = _fill("state.json.tmpl", _STATE_FILL)
    tasks_text = _fill("TASKS.json.tmpl", _TASKS_FILL)
    # Fail loudly here (not at validate time) if a fill produced invalid JSON.
    json.loads(state_text)
    json.loads(tasks_text)

    (loop_dir / "state.json").write_text(state_text, encoding="utf-8")
    (loop_dir / "manifest.yaml").write_text(_fill("manifest.yaml.tmpl", _MANIFEST_FILL), encoding="utf-8")
    (target / "TASKS.json").write_text(tasks_text, encoding="utf-8")
    (target / "RUNLOG.md").write_text(
        (TEMPLATES / "RUNLOG.md.tmpl").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return target


@pytest.fixture()
def contracts(tmp_path) -> dict[str, Path]:
    """The two fixtures every checklist item is exercised against."""
    return {
        "terminated": EXAMPLE,
        "inflight": _scaffold_inflight(tmp_path / "inflight"),
    }


# --------------------------------------------------------------------------- #
# Shared validation helpers — drive loop.contract's own validators, both modes.
# --------------------------------------------------------------------------- #

def _has_jsonschema() -> bool:
    try:
        import jsonschema  # noqa: F401
        return True
    except Exception:
        return False


_STRUCTURAL = {
    "manifest": C._validate_manifest,
    "state": C._validate_state,
    "tasks": C._validate_tasks,
    "terminal": C._validate_terminal,
}


def _artifact_issues_both_modes(name: str, data: dict, path: Path) -> None:
    """Assert ``data`` validates against ``loop-engineer/<name>@1`` in the stdlib
    structural mode AND (when installed) the real jsonschema mode."""
    structural: list[dict] = []
    _STRUCTURAL[name](data, path, structural)
    assert structural == [], f"{name} structural issues: {structural}"
    if _has_jsonschema():
        js: list[dict] = []
        C._jsonschema_validate(data, name, path, js)
        assert js == [], f"{name} jsonschema issues: {js}"


def _record_issues_both_modes(data: dict, schema_key: str, path: Path) -> None:
    structural: list[dict] = []
    C._validate_record(data, schema_key, path, "structural-fallback", structural)
    assert structural == [], f"{schema_key} structural issues: {structural}"
    if _has_jsonschema():
        js: list[dict] = []
        C._validate_record(data, schema_key, path, "jsonschema", js)
        assert js == [], f"{schema_key} jsonschema issues: {js}"


def _jsonl_issues_both_modes(path: Path, schema_key: str) -> None:
    structural: list[dict] = []
    C._validate_jsonl(path, schema_key, "structural-fallback", structural)
    assert structural == [], f"{path.name} structural issues: {structural}"
    if _has_jsonschema():
        js: list[dict] = []
        C._validate_jsonl(path, schema_key, "jsonschema", js)
        assert js == [], f"{path.name} jsonschema issues: {js}"


def _published_schema_ids() -> set[str]:
    ids: set[str] = set()
    for schema_file in sorted((ROOT / "schemas").glob("*.schema.json")):
        ids.add(json.loads(schema_file.read_text(encoding="utf-8"))["$id"])
    return ids


# --------------------------------------------------------------------------- #
# A. Artifacts present & well-formed.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_a1_manifest_schema(contracts, kind):
    paths = resolve_loop_paths(contracts[kind])
    data = C.read_manifest(paths.manifest)
    assert isinstance(data, dict) and data, "manifest did not parse to a mapping"
    assert data.get("schema") == "loop-engineer/manifest@1"
    # The canonical 7 terminal_states, verbatim and in order.
    assert list(data.get("terminal_states") or []) == list(TERMINAL_STATES)
    _artifact_issues_both_modes("manifest", data, paths.manifest)


@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_a2_state_schema(contracts, kind):
    paths = resolve_loop_paths(contracts[kind])
    data = json.loads(paths.state.read_text(encoding="utf-8"))
    assert data.get("schema") == "loop-engineer/state@1"
    _artifact_issues_both_modes("state", data, paths.state)


@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_a3_tasks_schema(contracts, kind):
    paths = resolve_loop_paths(contracts[kind])
    data = json.loads(paths.tasks.read_text(encoding="utf-8"))
    assert data.get("schema") == "loop-engineer/tasks@1"
    _artifact_issues_both_modes("tasks", data, paths.tasks)
    # Cross-task rules JSON Schema cannot express: id uniqueness, evidence-before-done.
    semantics: list[dict] = []
    C._check_tasks_semantics(data, paths.tasks, semantics)
    assert semantics == [], semantics


@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_a4_runlog_present(contracts, kind):
    paths = resolve_loop_paths(contracts[kind])
    assert paths.runlog.name == "RUNLOG.md"
    assert paths.runlog.is_file(), f"RUNLOG.md missing for {kind}"


# --------------------------------------------------------------------------- #
# B. Lifecycle honesty.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_b1_terminal_pair_exclusivity(contracts, kind):
    paths = resolve_loop_paths(contracts[kind])
    state = json.loads(paths.state.read_text(encoding="utf-8"))
    terminal_state = state.get("terminal_state")
    terminal_present = paths.terminal.exists()

    arm_inflight = terminal_state is None and not terminal_present
    terminal_valid = False
    if terminal_present:
        term_issues: list[dict] = []
        C._validate_terminal(
            json.loads(paths.terminal.read_text(encoding="utf-8")), paths.terminal, term_issues
        )
        terminal_valid = not term_issues
    arm_terminated = terminal_state in TERMINAL_STATES and terminal_present and terminal_valid

    assert arm_inflight ^ arm_terminated, (
        f"B1 requires exactly one arm: inflight={arm_inflight} terminated={arm_terminated}"
    )
    # And the contract as a whole must pass — no contradictory lifecycle issue.
    assert validate_contract(contracts[kind])["ok"] is True


@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_b2_terminal_proof_surface(contracts, kind):
    paths = resolve_loop_paths(contracts[kind])
    if not paths.terminal.exists():
        pytest.skip(f"{kind}: no terminal_state.json — B2 is checked-when-present")
    data = json.loads(paths.terminal.read_text(encoding="utf-8"))
    _artifact_issues_both_modes("terminal", data, paths.terminal)
    assert isinstance(data.get("criteria_met"), dict)
    assert isinstance(data.get("evidence"), list)
    assert isinstance(data.get("false_completion"), bool)
    if data.get("state") == "Succeeded":
        assert data["false_completion"] is False
        assert any(v is True for v in data["criteria_met"].values())
        assert data["evidence"], "Succeeded terminal must carry non-empty evidence"


# --------------------------------------------------------------------------- #
# C. Evidentiary trail (checked when present).
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_c1_receipts_trail(contracts, kind):
    paths = resolve_loop_paths(contracts[kind])
    receipts_dir = paths.loop_dir / "receipts"
    receipts = sorted(receipts_dir.glob("*.jsonl")) if receipts_dir.is_dir() else []
    if not receipts:
        pytest.skip(f"{kind}: no .loop/receipts/*.jsonl trail — C1 is checked-when-present")
    for receipt in receipts:
        _jsonl_issues_both_modes(receipt, "receipt")


@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_c2_repair_trail(contracts, kind):
    paths = resolve_loop_paths(contracts[kind])
    repair_dir = paths.loop_dir / "repair"
    records = sorted(repair_dir.glob("*.json")) if repair_dir.is_dir() else []
    if not records:
        pytest.skip(f"{kind}: no .loop/repair/*.json trail — C2 is checked-when-present")
    for record_path in records:
        data = json.loads(record_path.read_text(encoding="utf-8"))
        assert data.get("schema") == "loop-engineer/repair@1"
        _record_issues_both_modes(data, "repair", record_path)


@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_c3_rollout_trail(contracts, kind):
    paths = resolve_loop_paths(contracts[kind])
    rollout = paths.loop_dir / "rollout.jsonl"
    if not rollout.is_file():
        pytest.skip(f"{kind}: no .loop/rollout.jsonl ledger — C3 is checked-when-present")
    _jsonl_issues_both_modes(rollout, "rollout")


# --------------------------------------------------------------------------- #
# D. Versioning.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_d1_schema_ids_are_published(contracts, kind):
    published = _published_schema_ids()
    paths = resolve_loop_paths(contracts[kind])

    manifest = C.read_manifest(paths.manifest)
    assert manifest.get("schema") in published

    for path in (paths.state, paths.tasks):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("schema") in published, (path.name, data.get("schema"))

    if paths.terminal.exists():
        terminal = json.loads(paths.terminal.read_text(encoding="utf-8"))
        assert terminal.get("schema") in published

    repair_dir = paths.loop_dir / "repair"
    if repair_dir.is_dir():
        for record_path in sorted(repair_dir.glob("*.json")):
            record = json.loads(record_path.read_text(encoding="utf-8"))
            assert record.get("schema") in published, (record_path.name, record.get("schema"))


@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_d2_additive_keys_are_tolerated(contracts, kind, tmp_path, monkeypatch):
    # Copy the whole contract, inject an unknown additive key into every artifact,
    # and assert validation still passes in BOTH modes (a v1 validator never
    # rejects a newer emitter's additive fields).
    dest = tmp_path / f"copy_{kind}"
    shutil.copytree(contracts[kind], dest)
    paths = resolve_loop_paths(dest)

    def _inject_json(path: Path, extra: dict) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update(extra)
        path.write_text(json.dumps(data), encoding="utf-8")

    _inject_json(paths.state, {"x_unknown_additive": {"nested": [1, 2]}})
    tasks = json.loads(paths.tasks.read_text(encoding="utf-8"))
    tasks["x_unknown_additive"] = "additive"
    if tasks.get("tasks"):
        tasks["tasks"][0]["x_unknown_task_key"] = "additive"
    paths.tasks.write_text(json.dumps(tasks), encoding="utf-8")
    if paths.terminal.exists():
        _inject_json(paths.terminal, {"x_unknown_additive": True})
    paths.manifest.write_text(
        paths.manifest.read_text(encoding="utf-8") + "\nx_unknown_additive_key: additive\n",
        encoding="utf-8",
    )

    # Pass 1: whatever mode is installed (jsonschema when present).
    report_default = validate_contract(dest)
    assert report_default["ok"] is True, report_default["issues"]

    # Pass 2: force the stdlib structural mode by hiding jsonschema.
    monkeypatch.setitem(sys.modules, "jsonschema", None)
    report_structural = validate_contract(dest)
    assert report_structural["validation_mode"] == "structural-fallback"
    assert report_structural["ok"] is True, report_structural["issues"]


# --------------------------------------------------------------------------- #
# E. Lifecycle report.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("kind", ["terminated", "inflight"])
def test_e1_doctor_lifecycle_consistent_with_b1(contracts, kind):
    report = validate_contract(contracts[kind])
    expected = "terminated:Succeeded" if kind == "terminated" else "planned"
    assert report["lifecycle"] == expected


# --------------------------------------------------------------------------- #
# Doc-parity guard — the normative doc must publish every checklist ID.
# --------------------------------------------------------------------------- #

def test_conformance_checklist_documented():
    doc = ROOT / "reference" / "repo-os-contract.md"
    text = doc.read_text(encoding="utf-8")
    assert "conformance checklist" in text.lower(), "normative doc lacks a conformance-checklist section"
    for cid in CHECKLIST_IDS:
        assert cid in text, f"checklist ID {cid} missing from normative doc"


# --------------------------------------------------------------------------- #
# §17 policy-digest conformance vector — docs and code cannot drift.
# --------------------------------------------------------------------------- #

from loop.verifier import verification_policy, verification_policy_digest  # noqa: E402

_POLICY_VECTOR_TASK = {"id": "T-1", "title": "ignored", "status": "pending", "criterion_ref": "C-1",
                       "verify": "./scripts/verify-fast.sh", "depends_on": [], "attempts": 0,
                       "evidence": None}
_POLICY_VECTOR_CANONICAL = '{"criterion_ref":"C-1","depends_on":[],"id":"T-1","verify":"./scripts/verify-fast.sh"}'
_POLICY_VECTOR_DIGEST = "cb28ced25ec75a20a153f821e7335464a1734eb781146a9d36a598e713caa9fe"


def test_documented_policy_digest_vector_matches_the_implementation():
    from loop.chain import canonical_json
    assert canonical_json(verification_policy(_POLICY_VECTOR_TASK)) == _POLICY_VECTOR_CANONICAL
    assert verification_policy_digest(_POLICY_VECTOR_TASK) == _POLICY_VECTOR_DIGEST
    doc = (Path(__file__).resolve().parent.parent / "reference" / "repo-os-contract.md").read_text(encoding="utf-8")
    assert _POLICY_VECTOR_DIGEST in doc and _POLICY_VECTOR_CANONICAL in doc


# --------------------------------------------------------------------------- #
# Evidence-wiring doc pins — the shipped surfaces and the normative doc cannot
# drift apart. Every assertion below was proven to FAIL against the tree as it
# stood before the documentation commit; a pin that passes both before and
# after documents nothing.
# --------------------------------------------------------------------------- #

from loop import emit  # noqa: E402
from loop.verifier import injected_verifier_identity  # noqa: E402

_CONTRACT_DOC = ROOT / "reference" / "repo-os-contract.md"

# The retired sentence was written three different ways on the three surfaces
# ("does NOT yet hash-verify", "does not yet hash-verify", "does not
# hash-verify"), so the ban is case-insensitive and the "yet" is optional. A
# case-sensitive substring ban passes against the uppercase one and proves
# nothing about it.
_RETIRED_HASH_VERIFY_CLAIM = re.compile(r"does\s+not\s+(?:yet\s+)?hash-verify", re.IGNORECASE)


def _binding_fixture(tmp_path: Path) -> Path:
    """A minimal in-flight contract that ``build_verify_evidence`` can render
    against — it needs only a readable ``.loop/state.json``."""
    return _scaffold_inflight(tmp_path / "binding")


def _bound_evidence_section() -> str:
    """§17's ``### Bound evidence`` subsection, heading to next heading."""
    text = _CONTRACT_DOC.read_text(encoding="utf-8")
    assert "### Bound evidence" in text, "§17 does not document the bound evidence set"
    start = text.index("### Bound evidence")
    end = text.find("\n### ", start + 1)
    return text[start:] if end == -1 else text[start:end]


def test_documented_artifact_binding_vector_matches_the_writer(tmp_path):
    """The three bound paths and their order are normative, not incidental."""
    workspace = _binding_fixture(tmp_path)
    built = emit.build_verify_evidence(workspace, run_id="run-1", iteration_id=1,
                                       task=_POLICY_VECTOR_TASK, passed=True,
                                       code_identity=injected_verifier_identity())
    # Order is the WRITER'S CONVENTION, not a correctness property — the doctor
    # walk builds a path->digest map and `event_hash` recomputes over the stored
    # list exactly as written, so any order verifies. It is pinned to the SHIPPED
    # order (bundle -> record -> object) purely so it cannot drift silently away
    # from the ordered list §17 publishes.
    assert [entry["path"] for entry in built.artifact_hashes] == [
        ".loop/artifacts/verify-iter1.json",
        ".loop/evidence/evidence-iter1.json",
        f".loop/artifacts/objects/{built.sha256[:2]}/{built.sha256}",
    ]
    # And the doc's numbered list must enumerate the same three in the same order.
    section = _bound_evidence_section()
    markers = (".loop/artifacts/verify-iter", ".loop/evidence/evidence-iter",
               ".loop/artifacts/objects/")
    for marker in markers:
        assert marker in section, f"§17 bound-evidence set omits {marker}"
    positions = [section.index(marker) for marker in markers]
    assert positions == sorted(positions), (
        f"§17 lists the bound set out of writer order: {positions}")


def _new_issue_codes_table() -> str:
    """§22's ``**New issue codes.**`` table, heading row to the end of the table."""
    text = _CONTRACT_DOC.read_text(encoding="utf-8")
    marker = "**New issue codes.**"
    assert marker in text, "§22 does not publish a new-issue-codes table"
    start = text.index(marker)
    end = text.find("\n\n", text.index("|---|---|", start))
    return text[start:] if end == -1 else text[start:end]


def test_every_new_doctor_code_is_documented_in_section_22():
    """Scoped to the §22 TABLE, not the whole file.

    Grepping the whole document could not fail: every one of these codes also appears
    in §17's tier list, so deleting all four §22 rows left the pin green — the pin a PR
    body would cite as proof that the codes are documented.
    """
    table = _new_issue_codes_table()
    for code in ("evidence_chain_mismatch", "missing_bound_evidence",
                 "policy_digest_mismatch", "unverified_evidence_terminal",
                 "bound_evidence_escape"):
        assert f"`{code}`" in table, f"§22's new-issue-codes table does not document {code}"


def test_no_shipped_surface_still_claims_evidence_is_unverified():
    for path in (ROOT / "loop" / "evidence.py", ROOT / "schemas" / "evidence.schema.json",
                 _CONTRACT_DOC):
        text = path.read_text(encoding="utf-8")
        assert not _RETIRED_HASH_VERIFY_CLAIM.search(text), (
            f"{path.name} still disclaims hash verification")
        # Whitespace-normalised: the retired tier bullet wrapped between the "**"
        # and `policy_digest`, so a raw substring ban never matched it either.
        normalised = " ".join(text.split())
        assert "not checked by any shipped surface:** `policy_digest`" not in normalised, (
            f"{path.name} still files policy_digest under the unchecked tier")
    # decision 14: the strict mode's two residuals must be named where the mode is
    # documented, not only in this plan. A capability paragraph without its limits is
    # the overclaim this slice exists to prevent.
    contract = " ".join(_CONTRACT_DOC.read_text(encoding="utf-8").split())
    assert "no event store" in contract and "--expect-chain-head" in contract
    # §17 closes with the trust-domain sentence rather than the plan's
    # "detectable against an anchor" wording (that phrasing ships in the README).
    # Pinned against the sentence the contract actually carries — absent before
    # this release, so the assertion discriminates.
    assert "trust domain can anchor" in contract
    # Deliberately NOT asserting the absence of "tamper-proof": §17 names it as the
    # forbidden claim, so a substring ban would fire on the honesty sentence itself.


def test_section_16_event_type_list_matches_the_code():
    from loop.events import EVENT_TYPES
    doc = _CONTRACT_DOC.read_text(encoding="utf-8")
    # §16 renders the nine members inside one wrapped backtick span, so a bare
    # name is as good as a backticked one here.
    assert all(f"`{name}`" in doc or name in doc for name in EVENT_TYPES)
    assert "one-to-one with `loop.emit`'s four writer operations" not in doc
