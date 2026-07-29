# Slice 4a — `verdict@1` Emission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the kernel a `loop verdict` verb that projects local run state into a `loop-engineer/verdict@1` predicate document, and give `action.yml` an opt-in step that hands that predicate to `actions/attest` for keyless signing — so a run's chain head becomes a signed, externally timestamped statement instead of a number an operator remembers.

**Architecture:** A new pure leaf module `loop/verdict.py` composes `doctor_report()`, the terminal record, and the chain-bound evidence digests that pass the existing strict verified-evidence bar into one canonical JSON document. It emits the **predicate body only** — `actions/attest` constructs the in-toto Statement from `subject-*` + `predicate-type` + `predicate-path`, so the kernel never builds an envelope, never signs, never verifies a signature, and never reads an environment variable. `action.yml` gains an `attest` input, default off.

**Tech Stack:** Python 3.10+ stdlib only (`json`, `hashlib`, `importlib.metadata`). No new runtime dependencies. Tests via pytest under `uv run`. CI via `actions/attest` in a composite-action step.

**Baseline (fresh worktree, main @ `0025acc` / v0.11.0):** **1305 passed / 18 skipped** with `--with pyyaml --with jsonschema --with pytest`. All zero-regression claims are against this number.

> **Baseline measurement trap.** Running the suite via `uv run --project <worktree>` installs the wheel, which materializes `loop/_bundle/` and makes `scripts/test_resources.py::test_repo_checkout_resolves_to_repo_dirs` fail *correctly*. Measure from inside the worktree (`bash -c 'cd <worktree> && uv run --with … pytest -q … scripts'`), never with `--project`.

**Source of decisions:** `docs/adr/0002-ci-attested-verdict.md`. Where this plan and the ADR disagree, the ADR wins. This plan implements **4a only** — emission. `--compare`, anchor auto-resolution, and signer-trust policy are Slice 4b and are explicitly out of scope.

## Global Constraints

- **Zero new runtime dependencies.** `loop/` imports stdlib only; `pyproject.toml` `[project.optional-dependencies]` stays exactly `yaml`, `schemas`, `dev`.
- **The kernel never signs and never establishes authenticity.** No module under `loop/` may reference a signing stack (sigstore, cosign, fulcio, rekor, DSSE), key material, or an OIDC token.
- **The kernel reads no environment variable.** `grep -rn "environ\|getenv" --include=*.py loop/` returns zero matches today and must still return zero after this slice.
- **The kernel emits a predicate, never a Statement.** No `_type`, no `subject`, no `predicateType` key is produced by `loop/`.
- **Predicate content is digests, enums, and issue codes only.** No free-text detail strings, no workspace paths, no task titles. `run_id` is the single operator-controlled string and is allowlisted deliberately (Task 5).
- **`schemas/verdict.schema.json` is not a contract artifact.** It does not enter `SCHEMA_IDS` (`loop/contract.py:34-39`) — that tuple is manifest/state/tasks/terminal only. Follow the `evidence.py` precedent: own schema-id constant, own loader.
- **No new file in `reference/`.** `evals/cases/structural.json` pins `reference_filenames` at 8. Section 23 is **appended** to `reference/repo-os-contract.md`.
- **No version bumps.** Tasks 1–8 land as one feature PR. Version surfaces (`pyproject.toml`, `.claude-plugin/plugin.json`, README, `scripts/test_docs_version.py`, CHANGELOG) move only in a separate release-cut PR.
- **`main` is protected** — PR required, force-push and deletion blocked, no bypass actors. All work lands via PR.
- Repo env quirks: no system pytest. The Bash deny-list blocks `rm`, bare `cd`, `VAR=` prefixes, `timeout`, `printf`, `source` — use `git -C <path>`, absolute paths, and `bash -c '…'`.

**Canonical test command** (run from the repo root):

```bash
uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts
```

---

## Existing interfaces this slice consumes

Read these before starting. Every signature is verbatim from HEAD `0025acc`.

| Symbol | Location | Signature / behavior |
|---|---|---|
| `doctor_report` | `loop/contract.py:1093` | `(target, *, mode=None, expect_chain_head=None) -> dict`. Returns `{**validate_contract(target, mode=mode), "event_store": …, "issues": [...], "ok": bool}`. Report keys include `ok`, `issues`, `lifecycle`, `schemas_checked`, `validation_mode`. |
| `_strict_evidence_failure` | `loop/contract.py:846` | `(entry, paths, bound) -> str \| None`. **The ONE definition of the verified-evidence bar.** `None` means the entry may back `Succeeded`; a string names which of four sub-checks failed. Reuse it — never restate the bar. |
| `canonical_json` | `loop/chain.py:27` | `(value) -> str`. `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False, allow_nan=False)`. Raises `ChainHashError`. |
| `ChainHashError` | `loop/chain.py:23` | `ValueError` subclass. |
| `EVIDENCE_SCHEMA_ID` | `loop/evidence.py:35` | `"loop-engineer/evidence@1"` — the naming convention to mirror. |
| `verify_bundle_is_green` | `loop/evidence.py:42` | `(bundle) -> bool`. The repo's ONE green-marker rule. |
| `_load_evidence_schema` | `loop/evidence.py:60` | The own-loader pattern to mirror for verdict. |
| `schemas_dir` | `loop/_resources.py:34` | `() -> Path`. Bundle-first, repo-relative fallback. |
| `resolve_loop_paths` | `loop/paths.py` | `(target) -> LoopPaths` with `.workspace`, `.loop_dir`. |
| `_COMMANDS` / `_READ_COMMANDS` / `_USAGE` / `_HELP` | `loop/__main__.py:15,19,21,23` | CLI wiring. `metrics` (line 26 of `_HELP`) is the precedent for a flag-bearing command. |

---

## File structure

| File | Change | Responsibility |
|---|---|---|
| `schemas/verdict.schema.json` | **create** | The `loop-engineer/verdict@1` predicate shape. Sole identity of the artifact. |
| `loop/verdict.py` | **create** | Pure projection: `build_verdict()`, `VERDICT_SCHEMA_ID`, `PREDICATE_TYPE`, `VerdictError`. stdlib + `loop.*` only. |
| `loop/__main__.py` | modify | Register `verdict` in `_COMMANDS`, `_READ_COMMANDS`, `_USAGE`, `_HELP`; one dispatch block. |
| `action.yml` | modify | New `attest` input (default `false`), `predicate-path` write step, `actions/attest` step, `attestation-url` output. |
| `.github/workflows/attest.yml` | **create** | Push-to-default-branch job that attests a tracked `examples/*` contract. |
| `reference/repo-os-contract.md` | modify | Append §23 (normative `verdict@1` + conformance vectors). |
| `CHANGELOG.md` | modify | Unreleased entry. |
| `scripts/test_verdict.py` | **create** | Projection, refusal, and conformance tests. |
| `scripts/test_verdict_purity.py` | **create** | The boundary made mechanical: no signing, no env, no Statement, field allowlist. |
| `scripts/test_verdict_cli.py` | **create** | CLI wiring, exit codes, stdout shape. |
| `.github/CODEOWNERS` | **create** | Human review on the three gate-defining paths (ADR 0002 decision 6). |

---

## The predicate shape (binding)

Every task builds toward exactly this document. `null` is legal for `chain.head`, `chain.sequence`, and `tool.version`; every other key is always present.

```json
{
  "schema": "loop-engineer/verdict@1",
  "run_id": "coverage-repair",
  "tool": { "name": "loop-engineer", "version": "0.11.0" },
  "doctor": {
    "ok": true,
    "validation_mode": "jsonschema",
    "issue_codes": [],
    "schemas_checked": ["loop-engineer/manifest@1", "loop-engineer/state@1"]
  },
  "chain": {
    "head": "9f2c…64hex",
    "sequence": 41,
    "unchained_prefix": 0
  },
  "terminal": {
    "state": "Succeeded",
    "completion_policy": "all_required_verified_evidence",
    "false_completion": false
  },
  "evidence": [
    {
      "digest": "a1b2…64hex",
      "code_digest": "c3d4…64hex",
      "policy_digest": "e5f6…64hex"
    }
  ]
}
```

**Why each field earns a slot in a permanent public log:**

- `run_id` — the only operator-controlled string. Deliberately allowlisted so a verdict can be correlated to a run; documented in §23 as public, so run ids must not embed sensitive text.
- `doctor.issue_codes` — **codes only, sorted, de-duplicated.** Never `message`, never `path`. This is the field the allowlist test exists to protect.
- `chain.head` — the subject the signer lane binds. `null` when the store has no chained events.
- `terminal.completion_policy` — distinguishes `all_required` from `all_required_verified_evidence`; without it a reader cannot tell what `Succeeded` meant.
- `evidence[]` — chain-bound entries that passed `_strict_evidence_failure`. Digests only; no URIs, because a URI is a workspace path.

---

## Task 1: The schema and the module skeleton

**Files:**
- Create: `schemas/verdict.schema.json`
- Create: `loop/verdict.py`
- Test: `scripts/test_verdict.py`

**Interfaces:**
- Consumes: `loop/_resources.py::schemas_dir()`.
- Produces: `VERDICT_SCHEMA_ID = "loop-engineer/verdict@1"`, `PREDICATE_TYPE = "urn:loop-engineer:verdict:1"`, `class VerdictError(ValueError)`, `_load_verdict_schema() -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_verdict.py
import json


def test_schema_id_and_predicate_type_are_pinned():
    from loop.verdict import PREDICATE_TYPE, VERDICT_SCHEMA_ID

    assert VERDICT_SCHEMA_ID == "loop-engineer/verdict@1"
    assert PREDICATE_TYPE == "urn:loop-engineer:verdict:1"


def test_schema_file_declares_the_matching_id():
    from loop._resources import schemas_dir
    from loop.verdict import VERDICT_SCHEMA_ID

    schema = json.loads((schemas_dir() / "verdict.schema.json").read_text(encoding="utf-8"))
    assert schema["$id"] == VERDICT_SCHEMA_ID
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_verdict_schema_is_not_a_contract_artifact():
    # SCHEMA_IDS is the contract-object tuple (manifest/state/tasks/terminal).
    # verdict@1 is a projection, not a contract object, and must stay out of it.
    from loop.contract import SCHEMA_IDS
    from loop.verdict import VERDICT_SCHEMA_ID

    assert VERDICT_SCHEMA_ID not in SCHEMA_IDS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_verdict.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop.verdict'`

- [ ] **Step 3: Write the schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "loop-engineer/verdict@1",
  "title": "Loop Engineer Verdict @1",
  "description": "A CI-attestable projection of a loop run's doctor verdict, chain head, terminal record, and verified-evidence digests. Emitted as an in-toto predicate body; the signer constructs the Statement.",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema", "run_id", "tool", "doctor", "chain", "terminal", "evidence"],
  "properties": {
    "schema": { "const": "loop-engineer/verdict@1" },
    "run_id": { "type": "string", "minLength": 1, "maxLength": 256 },
    "tool": {
      "type": "object",
      "additionalProperties": false,
      "required": ["name", "version"],
      "properties": {
        "name": { "const": "loop-engineer" },
        "version": { "type": ["string", "null"], "maxLength": 64 }
      }
    },
    "doctor": {
      "type": "object",
      "additionalProperties": false,
      "required": ["ok", "validation_mode", "issue_codes", "schemas_checked"],
      "properties": {
        "ok": { "type": "boolean" },
        "validation_mode": { "type": "string", "maxLength": 64 },
        "issue_codes": {
          "type": "array",
          "items": { "type": "string", "pattern": "^[a-z0-9_]{1,64}$" }
        },
        "schemas_checked": {
          "type": "array",
          "items": { "type": "string", "maxLength": 128 }
        }
      }
    },
    "chain": {
      "type": "object",
      "additionalProperties": false,
      "required": ["head", "sequence", "unchained_prefix"],
      "properties": {
        "head": { "type": ["string", "null"], "pattern": "^[0-9a-f]{64}$", "maxLength": 64 },
        "sequence": { "type": ["integer", "null"], "minimum": 0 },
        "unchained_prefix": { "type": "integer", "minimum": 0 }
      }
    },
    "terminal": {
      "type": "object",
      "additionalProperties": false,
      "required": ["state", "completion_policy", "false_completion"],
      "properties": {
        "state": {
          "enum": ["Succeeded", "FailedUnverifiable", "FailedBlocked", "FailedBudget",
                   "FailedSafety", "FailedSpecGap", "AbortedByHuman"]
        },
        "completion_policy": { "type": ["string", "null"], "maxLength": 64 },
        "false_completion": { "type": "boolean" }
      }
    },
    "evidence": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["digest", "code_digest", "policy_digest"],
        "properties": {
          "digest": { "type": "string", "pattern": "^[0-9a-f]{64}$", "maxLength": 64 },
          "code_digest": { "type": ["string", "null"], "pattern": "^[0-9a-f]{64}$", "maxLength": 64 },
          "policy_digest": { "type": ["string", "null"], "pattern": "^[0-9a-f]{64}$", "maxLength": 64 }
        }
      }
    }
  }
}
```

> `maxLength` accompanies every `pattern` deliberately. jsonschema's `pattern` is `re.search` semantics, so a bare `^[0-9a-f]{64}$` accepts a trailing newline — the exact hole closed in PR #89.

- [ ] **Step 4: Write the module skeleton**

```python
# loop/verdict.py
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_verdict.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add schemas/verdict.schema.json loop/verdict.py scripts/test_verdict.py
git commit -m "feat(verdict): add verdict@1 schema and module skeleton"
```

---

## Task 2: Project doctor, chain, and terminal

**Files:**
- Modify: `loop/verdict.py`
- Test: `scripts/test_verdict.py`

**Interfaces:**
- Consumes: `VerdictError` (Task 1); `loop.contract.doctor_report`; `loop.paths.resolve_loop_paths`.
- Produces: `build_verdict(target, *, mode=None) -> dict` — the full predicate minus `evidence`, which Task 3 fills. Callers rely on the exact key set in "The predicate shape (binding)".

- [ ] **Step 1: Write the failing test**

```python
# append to scripts/test_verdict.py
import pytest


def _scaffold_terminal(tmp_path, name, state="Succeeded", policy="all_required"):
    """A doctor-clean scaffold advanced to a terminal record."""
    from loop.scaffold import scaffold

    target = tmp_path / name
    scaffold(target)
    terminal = {
        "schema": "loop-engineer/terminal@1",
        "state": state,
        "iteration_id": 1,
        "false_completion": False,
        "completion_policy": {"mode": policy},
        "evidence": [],
    }
    (target / ".loop" / "terminal_state.json").write_text(
        json.dumps(terminal), encoding="utf-8")
    return target


def test_build_verdict_projects_doctor_terminal_and_chain(tmp_path):
    from loop.verdict import build_verdict

    target = _scaffold_terminal(tmp_path, "projected")
    verdict = build_verdict(target)

    assert verdict["schema"] == "loop-engineer/verdict@1"
    assert set(verdict) == {"schema", "run_id", "tool", "doctor", "chain", "terminal", "evidence"}
    assert verdict["terminal"]["state"] == "Succeeded"
    assert verdict["terminal"]["completion_policy"] == "all_required"
    assert verdict["terminal"]["false_completion"] is False
    assert set(verdict["doctor"]) == {"ok", "validation_mode", "issue_codes", "schemas_checked"}
    assert set(verdict["chain"]) == {"head", "sequence", "unchained_prefix"}
    assert verdict["tool"]["name"] == "loop-engineer"


def test_issue_codes_are_sorted_deduplicated_and_carry_no_detail(tmp_path):
    from loop.verdict import build_verdict

    target = _scaffold_terminal(tmp_path, "with-issues")
    (target / "scripts" / "verify-fast").unlink()
    (target / "scripts" / "verify-full").unlink()

    codes = build_verdict(target)["doctor"]["issue_codes"]
    assert codes == sorted(set(codes))
    assert all(isinstance(c, str) and " " not in c for c in codes), codes


def test_build_verdict_refuses_a_workspace_with_no_terminal_record(tmp_path):
    from loop.scaffold import scaffold
    from loop.verdict import VerdictError, build_verdict

    target = tmp_path / "no-terminal"
    scaffold(target)

    with pytest.raises(VerdictError, match="no terminal record"):
        build_verdict(target)


def test_build_verdict_refuses_a_nonexistent_target(tmp_path):
    from loop.verdict import VerdictError, build_verdict

    with pytest.raises(VerdictError):
        build_verdict(tmp_path / "does-not-exist")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_verdict.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_verdict'`

> Verified at HEAD: the scaffold entry point is `loop.scaffold.scaffold(target)` (`loop/scaffold.py:104`). There is no `scaffold_contract`. `LoopPaths` also exposes `.terminal` directly (`loop/paths.py:24`), so prefer `paths.terminal` over `paths.loop_dir / "terminal_state.json"`.

- [ ] **Step 3: Implement the projection**

```python
# add to loop/verdict.py
from importlib import metadata
from pathlib import Path

from .contract import doctor_report
from .paths import resolve_loop_paths


def _tool_version() -> str | None:
    try:
        return metadata.version("loop-engineer")
    except metadata.PackageNotFoundError:
        return None


def _terminal_record(paths) -> dict[str, Any]:
    path = paths.loop_dir / "terminal_state.json"
    if not path.is_file():
        raise VerdictError(
            "no terminal record: a verdict projects a finished run "
            f"({path.name} is absent)")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerdictError(f"terminal record is unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise VerdictError("terminal record is not an object")
    return data


def build_verdict(target: str | Path, *, mode: str | None = None) -> dict[str, Any]:
    """Project local run state into a verdict@1 predicate body.

    Pure over the workspace: no environment, no network, no signing.
    """
    try:
        paths = resolve_loop_paths(target)
    except (OSError, ValueError) as exc:
        raise VerdictError(f"cannot resolve a loop workspace at {target}: {exc}") from exc

    report = doctor_report(paths.workspace, mode=mode)
    terminal = _terminal_record(paths)

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
                str(i.get("code")) for i in report.get("issues", [])
                if isinstance(i, dict) and i.get("code")
            }),
            "schemas_checked": sorted(str(s) for s in report.get("schemas_checked", [])),
        },
        "chain": {
            "head": head.get("event_hash"),
            "sequence": head.get("sequence"),
            "unchained_prefix": int(chain.get("unchained_prefix") or 0),
        },
        "terminal": {
            "state": terminal.get("state"),
            "completion_policy": policy_mode,
            "false_completion": bool(terminal.get("false_completion")),
        },
        "evidence": [],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_verdict.py -v`
Expected: all pass

- [ ] **Step 5: Confirm the `event_store` key names against reality**

Run:

```bash
uv run --with pyyaml --with jsonschema python3 -B -m loop doctor examples/coverage-repair | python3 -c "import json,sys;print(json.dumps(json.load(sys.stdin).get('event_store'), indent=2))"
```

If `run_id`, `chain.head.event_hash`, `chain.head.sequence`, or `chain.unchained_prefix` are named differently, fix `build_verdict` to match the real shape and re-run Step 4. Do not adapt the tests to a wrong projection.

- [ ] **Step 6: Commit**

```bash
git add loop/verdict.py scripts/test_verdict.py
git commit -m "feat(verdict): project doctor, chain, and terminal into verdict@1"
```

---

## Task 3: The verified-evidence digest set

**Files:**
- Modify: `loop/verdict.py`
- Test: `scripts/test_verdict.py`

**Interfaces:**
- Consumes: `build_verdict` (Task 2); `loop.contract._strict_evidence_failure`.
- Produces: `build_verdict` now returns a populated `evidence` list of `{digest, code_digest, policy_digest}` objects, sorted by `digest`.

The predicate carries **only** chain-bound evidence that satisfies the strict bar — not everything the terminal record cites. A cited-but-unverified entry in a signed document would be exactly the false completion this kernel exists to refuse.

- [ ] **Step 1: Write the failing test**

```python
# append to scripts/test_verdict.py

def test_evidence_carries_only_entries_that_pass_the_strict_bar(tmp_path, monkeypatch):
    """A cited entry that fails the strict bar must not reach the predicate."""
    import loop.verdict as verdict_mod
    from loop.verdict import build_verdict

    target = _scaffold_terminal(tmp_path, "mixed-evidence",
                                policy="all_required_verified_evidence")
    terminal_path = target / ".loop" / "terminal_state.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    terminal["evidence"] = [".loop/evidence/good.json", ".loop/evidence/bad.json"]
    terminal_path.write_text(json.dumps(terminal), encoding="utf-8")

    # Patch the bar where verdict.py BINDS it, not where it is defined —
    # patching loop.contract is a verified no-op under from-import binding.
    def fake_bar(entry, paths, bound):
        return None if str(entry).endswith("good.json") else "digest_mismatch"

    monkeypatch.setattr(verdict_mod, "_strict_evidence_failure", fake_bar)
    monkeypatch.setattr(verdict_mod, "_evidence_digests",
                        lambda entry, paths: {"digest": "a" * 64,
                                              "code_digest": None,
                                              "policy_digest": None})

    evidence = build_verdict(target)["evidence"]
    assert len(evidence) == 1, evidence
    assert evidence[0]["digest"] == "a" * 64


def test_evidence_entries_carry_digests_only(tmp_path):
    """No URIs, no paths — a URI is a workspace path and this document is public."""
    from loop.verdict import build_verdict

    target = _scaffold_terminal(tmp_path, "digest-only")
    for entry in build_verdict(target)["evidence"]:
        assert set(entry) == {"digest", "code_digest", "policy_digest"}


def test_evidence_is_sorted_by_digest(tmp_path, monkeypatch):
    """Canonical output: the same run always projects the same bytes."""
    import loop.verdict as verdict_mod
    from loop.verdict import build_verdict

    target = _scaffold_terminal(tmp_path, "sorted")
    terminal_path = target / ".loop" / "terminal_state.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    terminal["evidence"] = ["b.json", "a.json"]
    terminal_path.write_text(json.dumps(terminal), encoding="utf-8")

    monkeypatch.setattr(verdict_mod, "_strict_evidence_failure",
                        lambda entry, paths, bound: None)
    monkeypatch.setattr(
        verdict_mod, "_evidence_digests",
        lambda entry, paths: {"digest": ("b" if "b.json" in str(entry) else "a") * 64,
                              "code_digest": None, "policy_digest": None})

    digests = [e["digest"] for e in build_verdict(target)["evidence"]]
    assert digests == sorted(digests)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_verdict.py -v`
Expected: FAIL — `_evidence_digests` does not exist; `evidence` is empty.

- [ ] **Step 3: Implement**

```python
# add to loop/verdict.py imports
from .contract import _strict_evidence_failure, doctor_report

# add to loop/verdict.py
def _evidence_digests(entry: object, paths) -> dict[str, Any] | None:
    """Read the evidence@1 record a terminal entry cites and lift its digests.

    Returns None when the record cannot be read as an object — the strict bar
    has already vetted it, so this is a defensive read, not a second gate.
    """
    record_path = paths.workspace / str(entry)
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(record, dict):
        return None
    verified_by = record.get("verified_by")
    verified_by = verified_by if isinstance(verified_by, dict) else {}
    digest = record.get("digest")
    if not isinstance(digest, str):
        return None
    return {
        "digest": digest,
        "code_digest": verified_by.get("code_digest"),
        "policy_digest": verified_by.get("policy_digest"),
    }


def _verified_evidence(terminal: dict[str, Any], paths, bound) -> list[dict[str, Any]]:
    entries = terminal.get("evidence")
    if not isinstance(entries, list):
        return []
    collected = []
    for entry in entries:
        if _strict_evidence_failure(entry, paths, bound) is not None:
            continue
        digests = _evidence_digests(entry, paths)
        if digests is not None:
            collected.append(digests)
    return sorted(collected, key=lambda d: d["digest"])
```

Then replace `"evidence": []` in `build_verdict` with:

```python
        "evidence": _verified_evidence(terminal, paths, _bound_evidence(paths)),
```

- [ ] **Step 4: Wire the chain-bound map**

`_strict_evidence_failure`'s third parameter is the chain-bound evidence map. Find how `loop/contract.py` builds it for its own strict check:

```bash
grep -n "_strict_evidence_failure(" loop/contract.py
```

Reuse that exact producer as `_bound_evidence(paths)` — import it if it is a named function, or lift the two or three lines verbatim with a comment naming the source line. **Do not re-derive the binding.** If the producer needs the doctor report, thread it through rather than calling `doctor_report` twice.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_verdict.py -v`
Expected: all pass

- [ ] **Step 6: Verify against a real contract**

```bash
uv run --with pyyaml --with jsonschema python3 -B -c "
from loop.verdict import build_verdict
import json; print(json.dumps(build_verdict('examples/flaky-test-triage'), indent=2))"
```

Expected: a populated predicate. Confirm `evidence[].digest` values are real 64-hex digests from that contract, not empty.

- [ ] **Step 7: Commit**

```bash
git add loop/verdict.py scripts/test_verdict.py
git commit -m "feat(verdict): carry only chain-bound evidence that passes the strict bar"
```

---

## Task 4: CLI wiring

**Files:**
- Modify: `loop/__main__.py:15,19,21,23`
- Test: `scripts/test_verdict_cli.py`

**Interfaces:**
- Consumes: `build_verdict` (Tasks 2–3).
- Produces: `python3 -m loop verdict [--mode basic|strict|release] <workspace>` writing canonical JSON to stdout, exit 0 on success and exit 2 with a typed one-line stderr message on `VerdictError`.

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_verdict_cli.py
import json
import subprocess
import sys


def _run(*args, cwd=None):
    return subprocess.run([sys.executable, "-B", "-m", "loop", *args],
                          capture_output=True, text=True, cwd=cwd)


def test_verdict_emits_canonical_json_and_exits_zero(repo_root):
    proc = _run("verdict", "examples/flaky-test-triage", cwd=repo_root)
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    assert doc["schema"] == "loop-engineer/verdict@1"


def test_verdict_output_is_byte_stable(repo_root):
    a = _run("verdict", "examples/flaky-test-triage", cwd=repo_root)
    b = _run("verdict", "examples/flaky-test-triage", cwd=repo_root)
    assert a.stdout == b.stdout


def test_verdict_emits_no_statement_envelope(repo_root):
    """The kernel emits a predicate body. actions/attest builds the Statement."""
    doc = json.loads(_run("verdict", "examples/flaky-test-triage", cwd=repo_root).stdout)
    for forbidden in ("_type", "subject", "predicateType", "predicate"):
        assert forbidden not in doc, f"{forbidden} belongs to the signer lane"


def test_verdict_fails_loud_without_a_terminal_record(tmp_path, repo_root):
    _run("scaffold", str(tmp_path / "fresh"), cwd=repo_root)
    proc = _run("verdict", str(tmp_path / "fresh"), cwd=repo_root)
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert "Traceback" not in proc.stderr
    assert "no terminal record" in proc.stderr


def test_verdict_appears_in_usage_and_help(repo_root):
    proc = _run("--help", cwd=repo_root)
    assert "verdict" in proc.stdout
```

Add a `repo_root` fixture to the file if `scripts/conftest.py` does not already provide one:

```python
import pathlib
import pytest


@pytest.fixture
def repo_root():
    return pathlib.Path(__file__).resolve().parent.parent
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_verdict_cli.py -v`
Expected: FAIL — `verdict` is not a known command.

- [ ] **Step 3: Wire the CLI**

In `loop/__main__.py`, add `"verdict"` to both `_COMMANDS` (line 15) and `_READ_COMMANDS` (line 19), add it to the `_USAGE` alternation (line 21), and add a `_HELP` usage line beside `metrics` plus a command description:

```
       {_PROG} verdict [--mode basic|strict|release] <workspace>
```

```
  verdict    Project the run into a loop-engineer/verdict@1 predicate body for
             CI attestation. Emits the predicate ONLY — the signer constructs
             the in-toto Statement. Never signs and never verifies a signature.
```

Then add the dispatch block, following the `metrics` flag-pre-parsing precedent:

```python
    if command == "verdict":
        from .verdict import VerdictError, build_verdict
        from .chain import canonical_json

        try:
            document = build_verdict(target, mode=mode)
        except VerdictError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(canonical_json(document))
        return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_verdict_cli.py -v`
Expected: all pass

- [ ] **Step 5: Run the full suite — `_USAGE` and `_HELP` are asserted elsewhere**

Run: `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts`
Expected: **1305 + new tests passed / 18 skipped**, zero failures. Existing CLI-surface tests that pin the usage string will need their fixtures updated — update the *fixture* to include `verdict`, never weaken the assertion.

- [ ] **Step 6: Commit**

```bash
git add loop/__main__.py scripts/test_verdict_cli.py
git commit -m "feat(cli): add the loop verdict verb"
```

---

## Task 5: The boundary, made mechanical

**Files:**
- Create: `scripts/test_verdict_purity.py`

**Interfaces:**
- Consumes: `loop/verdict.py`, the whole `loop/` package.
- Produces: nothing. This task exists so ADR 0002's boundary cannot decay into an intention.

- [ ] **Step 1: Write the tests**

```python
# scripts/test_verdict_purity.py
import ast
import json
import pathlib
import subprocess
import sys

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
    jsonschema = __import__("jsonschema")
    from loop.verdict import _load_verdict_schema

    jsonschema.validate(_predicate(), _load_verdict_schema())
```

- [ ] **Step 2: Run tests**

Run: `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts/test_verdict_purity.py -v`

Expected: all pass. **If `test_kernel_never_references_a_signing_stack` or `test_kernel_reads_no_environment_variable` fails, that is a real finding — fix the code, not the test.** If a token produces a false positive (e.g. the substring `oidc` inside an unrelated identifier), narrow the token, and add a comment naming the false positive so the narrowing is not mistaken for weakening.

- [ ] **Step 3: Prove the tests have teeth (mutation probe)**

Temporarily add `import os; os.environ.get("GITHUB_SHA")` to `loop/verdict.py`, re-run, confirm `test_kernel_reads_no_environment_variable` FAILS, then revert. Temporarily add a `"debug"` key to the returned dict, re-run, confirm `test_predicate_field_allowlist_holds` FAILS, then revert. A gate that cannot fail is not a gate.

- [ ] **Step 4: Commit**

```bash
git add scripts/test_verdict_purity.py
git commit -m "test(verdict): make the ADR 0002 boundary mechanical"
```

---

## Task 6: The action step

**Files:**
- Modify: `action.yml`

**Interfaces:**
- Consumes: the `loop verdict` CLI (Task 4); the existing `chain-head` step (`action.yml:85-107`), which already extracts `event_store.chain.head.event_hash` into the `chain-head` output.
- Produces: action input `attest` (default `"false"`); outputs `attestation-url`, `attestation-id`.

- [ ] **Step 1: Add the input**

Append to `inputs:` in `action.yml`:

```yaml
  attest:
    description: >-
      Emit a loop-engineer/verdict@1 predicate and attest it keylessly via
      GitHub OIDC. Requires the CALLING JOB to declare `id-token: write` and
      `attestations: write` — a composite action cannot declare its own
      permissions. Default false. The predicate is PUBLIC and permanent for
      public repositories.
    required: false
    default: "false"
```

- [ ] **Step 2: Add the outputs**

Append to `outputs:`:

```yaml
  attestation-url:
    description: "URL of the attestation created by this run ('' when attest is false)."
    value: ${{ steps.attest.outputs.attestation-url }}
  attestation-id:
    description: "ID of the attestation created by this run ('' when attest is false)."
    value: ${{ steps.attest.outputs.attestation-id }}
```

- [ ] **Step 3: Add the predicate + permission-precheck step**

Insert after the existing `chain head (anchor surface)` step:

```yaml
    - name: verdict predicate
      id: verdict
      if: ${{ inputs.attest == 'true' }}
      shell: bash
      env:
        LOOP_PATH: "${{ inputs.path }}"
      run: |
        # Fail with a legible message rather than a raw OIDC 403 from the attest
        # step: a composite action cannot declare permissions, so the CALLING
        # job must. ACTIONS_ID_TOKEN_REQUEST_URL is present only when the job
        # declared id-token: write.
        if [ -z "${ACTIONS_ID_TOKEN_REQUEST_URL:-}" ]; then
          echo "::error::attest: true requires the calling job to declare" \
               "'permissions: { id-token: write, attestations: write }'." \
               "A composite action cannot declare its own permissions."
          exit 1
        fi
        loop verdict "$LOOP_PATH" > "${RUNNER_TEMP}/verdict.json"
        echo "predicate-path=${RUNNER_TEMP}/verdict.json" >> "$GITHUB_OUTPUT"

    - name: attest verdict
      id: attest
      if: ${{ inputs.attest == 'true' }}
      uses: actions/attest@v4
      with:
        subject-name: loop-chain-head
        subject-digest: sha256:${{ steps.chain-head.outputs.chain-head }}
        predicate-type: urn:loop-engineer:verdict:1
        predicate-path: ${{ steps.verdict.outputs.predicate-path }}
        push-to-registry: false
```

> **Verify before merging** (ADR 0002 open items 1 and 5): confirm `actions/attest@v4` is the current major, confirm `subject-digest` accepts the `sha256:` prefix form with a separate `subject-name`, and confirm whether `create-storage-record` exists as an input and what it defaults to. If it exists, pass it explicitly as `false`. Run `gh api repos/actions/attest/contents/action.yml --jq '.content' | base64 -d` and read the real input list. Do not ship an input name from memory.

- [ ] **Step 4: Guard the empty-head case**

A run with no chained events produces an empty `chain-head`, and `subject-digest: sha256:` is malformed. Change the `attest verdict` step's condition to:

```yaml
      if: ${{ inputs.attest == 'true' && steps.chain-head.outputs.chain-head != '' }}
```

and add a step that warns when attestation was requested but skipped:

```yaml
    - name: attest skipped (no chained events)
      if: ${{ inputs.attest == 'true' && steps.chain-head.outputs.chain-head == '' }}
      shell: bash
      run: echo "::warning::attest requested but the store has no chained events; nothing to attest."
```

- [ ] **Step 5: Lint the workflow syntax**

```bash
uv run --with pyyaml python3 -B -c "
import yaml, pathlib
doc = yaml.safe_load(pathlib.Path('action.yml').read_text(encoding='utf-8'))
print('inputs:', sorted(doc['inputs']))
print('outputs:', sorted(doc['outputs']))
print('steps:', [s.get('name') for s in doc['runs']['steps']])"
```

Expected: `attest` in inputs; `attestation-url`, `attestation-id` in outputs; the new steps in order.

- [ ] **Step 6: Commit**

```bash
git add action.yml
git commit -m "feat(action): opt-in keyless attestation of the verdict predicate"
```

---

## Task 7: The repo's own attestation job

**Files:**
- Create: `.github/workflows/attest.yml`

**Interfaces:**
- Consumes: the composite action from Task 6; the existing `scripts/ci_anchor_probe.py`.
- Produces: a real attestation on every push to the default branch, over a **seeded chained workspace**.

**Pre-flight correction.** An earlier draft pointed this job at `examples/flaky-test-triage`. That is
wrong: **no tracked `examples/*` contract ships an `events.db`** (verified — event stores are runtime
artifacts and `.loop/` is gitignored). With no store the chain head is empty, Task 6 Step 4's guard
skips the attest step, and the job goes green having attested nothing — an unfalsifiable CI job, which
is the exact false-completion shape this project exists to refuse.

Reuse the pattern the repo already proved. `ci.yml`'s `chain anchor (live end-to-end)` job seeds a
chained workspace via `python -B scripts/ci_anchor_probe.py "$workspace"`, which prints the resulting
head; its own comment states the rationale verbatim — *"action-dogfood gates a store-free example, so
the anchor surface has no live cover there."* Never point this at the live gitignored `.loop/`.

- [ ] **Step 1: Write the workflow**

```yaml
name: attest

on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verdict:
    # Push-to-default-branch only, by ADR 0002 decision 5: attesting on a PR
    # would mint a signed verdict under the repository's identity before review.
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
      attestations: write
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"

      - name: Install probe dependencies
        run: python -m pip install --upgrade pip pyyaml jsonschema

      - name: Seed a chained workspace
        id: seed
        # Same probe the chain-anchor job uses. A store-free example would make
        # the attest step skip and this job unfalsifiable.
        run: |
          workspace="${RUNNER_TEMP}/verdict-ws"
          head="$(python -B scripts/ci_anchor_probe.py "$workspace")"
          echo "head=$head" >> "$GITHUB_OUTPUT"
          echo "workspace=$workspace" >> "$GITHUB_OUTPUT"

      - id: gate
        uses: ./
        with:
          path: ${{ steps.seed.outputs.workspace }}
          attest: "true"

      - name: assert an attestation was actually created
        # Without this the job passes when the attest step skips, which is the
        # failure mode this whole task exists to avoid.
        env:
          SEEDED_HEAD: ${{ steps.seed.outputs.head }}
          OBSERVED_HEAD: ${{ steps.gate.outputs.chain-head }}
          ATTESTATION: ${{ steps.gate.outputs.attestation-url }}
        run: |
          if [ -z "$ATTESTATION" ]; then
            echo "::error::attest was requested but no attestation URL was produced"
            exit 1
          fi
          if [ "$OBSERVED_HEAD" != "$SEEDED_HEAD" ]; then
            echo "::error::gate observed head '$OBSERVED_HEAD', seed produced '$SEEDED_HEAD'"
            exit 1
          fi
          echo "chain head: $OBSERVED_HEAD" >> "$GITHUB_STEP_SUMMARY"
          echo "attestation: $ATTESTATION" >> "$GITHUB_STEP_SUMMARY"
```

- [ ] **Step 2: Confirm the action majors match the repo's other workflows**

```bash
grep -rn "actions/checkout@\|actions/setup-python@" .github/workflows/
```

Pre-flight observed `actions/checkout@v7` and `actions/setup-python@v7` in `ci.yml`; confirm before
committing. A mismatched pin is a dependabot PR waiting to happen.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/attest.yml
git commit -m "ci: attest the verdict for a tracked example contract on push to main"
```

- [ ] **Step 4: Note for the PR body**

This job cannot be validated before merge — `push: branches: [main]` fires only after landing. State that explicitly in the PR description, and check the first post-merge run. If it fails, the fix is a follow-up PR, not a revert: the action input defaults to `false`, so nothing else is affected.

---

## Task 8: Normative documentation

**Files:**
- Modify: `reference/repo-os-contract.md` (append §23)
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: everything above.
- Produces: the normative spec third parties implement against.

- [ ] **Step 1: Append §23**

Add after §22, matching the numbered-section style of §16 and §17. It must cover:

1. The predicate shape, field by field, with the exact JSON from "The predicate shape (binding)" above as a machine-pinned conformance vector.
2. `PREDICATE_TYPE = urn:loop-engineer:verdict:1` and why it names no vendor host (ADR 0002 decision 3).
3. **The subject is the chain head**, and — critically — that the chain head is a SHA-256 over a synthesized event preimage (§16), **not** over retrievable bytes. A consumer must never conclude "fetch bytes, re-hash, compare."
4. The separation: the kernel emits the predicate; the signer builds the Statement.
5. That `run_id` is operator-controlled and lands in a permanent public log, so run ids must not embed sensitive text.
6. The honest limits, copied in substance from ADR 0002's Standing Limits — especially that a worker with merge rights can loosen the gate and then mint a genuine attestation for it.

- [ ] **Step 2: Verify the reference-file count is unchanged**

```bash
uv run --with pyyaml python3 -B scripts/self_eval.py
```

Expected: 13/13 PASS. If `reference_filenames` fails, a new file was created in `reference/` — move the content into `repo-os-contract.md` §23 instead.

- [ ] **Step 3: Add the CHANGELOG entry**

Under an `## [Unreleased]` heading, describing: the `loop verdict` verb, the `verdict@1` schema, the opt-in `attest` action input, and — in the project's established voice — what the attestation does **not** buy. Name the one-run detection latency and the worker-can-edit-the-verifier path. Do not use the word "tamper-proof".

- [ ] **Step 4: Run the full suite**

Run: `uv run --with pyyaml --with jsonschema --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts`
Expected: **1305 + new tests passed / 18 skipped**, zero failures.

- [ ] **Step 5: Run the structural-fallback leg**

Run: `uv run --with pyyaml --with pytest python3 -B -m pytest -q -p no:cacheprovider scripts`
Expected: zero failures. `test_predicate_validates_against_its_own_schema` (Task 5) imports `jsonschema` directly and must be skipped rather than failed in this leg — mark it `@pytest.mark.skipif` on the import, following how existing schema tests handle the fallback mode.

- [ ] **Step 6: Commit**

```bash
git add reference/repo-os-contract.md CHANGELOG.md
git commit -m "docs: normative verdict@1 section and honest limits"
```

---

## Task 9: The governance change (ADR 0002 decision 6)

**Files:**
- Create: `.github/CODEOWNERS`

**Interfaces:**
- Consumes: nothing.
- Produces: a review requirement on the three paths that define what the gate checks.

This is the control for the largest limit in ADR 0002 — an agent with ordinary
merge rights can loosen the gate and then mint a genuine attestation for it. No
code fixes that. This slice is the first PR that touches all three paths, so the
requirement lands with it.

- [ ] **Step 1: Write CODEOWNERS**

```
# Changes to what the gate checks require human review (ADR 0002, decision 6).
# Everything else in this repo stays autonomous.
/loop/                  @SollanSystems
/action.yml             @SollanSystems
/.github/workflows/     @SollanSystems
/.github/CODEOWNERS     @SollanSystems
```

- [ ] **Step 2: Verify GitHub parses it**

After pushing the branch:

```bash
gh api "repos/SollanSystems/loop-engineer/codeowners/errors" --jq '.errors'
```

Expected: `[]`. A malformed CODEOWNERS fails silently — GitHub simply enforces
nothing — so this check is the deliverable, not the file.

- [ ] **Step 3: Commit**

```bash
git add .github/CODEOWNERS
git commit -m "chore: require human review on the gate-defining paths"
```

- [ ] **Step 4: OPERATOR ACTION — the ruleset half**

**CODEOWNERS alone enforces nothing.** The `main protection` ruleset currently
requires a PR with **0 approvals**, so a code-owner file without a matching rule
is decoration. The operator must set the ruleset to require review from Code
Owners (Settings → Rules → `main protection` → "Require review from Code
Owners", and raise required approvals to 1).

Do not attempt this from an agent session — branch-protection edits are operator
territory, and a half-applied change is worse than none. Record in the PR body
whether it has been applied; until it is, ADR 0002's decision 6 is documented but
not in force, and the Standing Limits section is the operative truth.

---

## Definition of done

- [ ] Full suite green in both dependency legs, against the 1305/18 baseline, measured from **inside** a fresh worktree (not `--project`).
- [ ] `uv run --with pyyaml python3 -B scripts/self_eval.py` → 13/13.
- [ ] `uv run --with pyyaml python3 -B scripts/validate_frontmatter.py` → 9/9.
- [ ] The two mutation probes in Task 5 Step 3 were run and both gates failed as predicted.
- [ ] `grep -rn "environ\|getenv" --include=*.py loop/` → zero matches.
- [ ] `python3 -m loop verdict examples/flaky-test-triage` emits a predicate with no `_type`, `subject`, or `predicateType` key.
- [ ] `actions/attest` input names were read from the live action definition, not from this plan.
- [ ] PR body states that `.github/workflows/attest.yml` is unvalidatable pre-merge and names the first post-merge run as the check.
- [ ] `gh api repos/SollanSystems/loop-engineer/codeowners/errors` → `[]`.
- [ ] PR body records whether the ruleset half of Task 9 has been applied by the operator.
- [ ] No version bump in this PR.

## Out of scope — Slice 4b

`loop verdict --compare`, anchor auto-resolution from a prior attestation, and signer-trust policy evaluation. Do not add a `--compare` flag, a `--sign` flag, or any bundle-parsing code in this slice. If a task seems to need one, the task is wrong.

## Open items to resolve during execution

Carried from ADR 0002. None blocks starting; each blocks the task that touches it.

1. **Subject digest algorithm** (Task 6). The chain head is not a hash of retrievable bytes, so the `sha256` DigestSet key licenses a false inference. A namespaced key is correct in in-toto terms but `actions/attest`'s `subject-digest` may accept only `sha256:`. Resolve by experiment. If the input constrains us, §23 must carry the disambiguation instead.
2. **`create-storage-record` / `push-to-registry` defaults** (Task 6). Pass both explicitly so the two-permission claim is true by construction.
3. ~~`scaffold_contract` name~~ — **RESOLVED in pre-flight.** The entry point is `loop.scaffold.scaffold`; the plan now uses it.
4. **`event_store` key names** (Task 2 Step 5). Pre-flight confirmed the store-absent shape is exactly `{"present": false}` and that `doctor_report` also returns `paths` (absolute filesystem paths — deliberately excluded from the predicate) and `requested_mode`. `validation_mode` is the single token `"jsonschema"`, so Task 5's no-whitespace assertion is safe. The populated `chain.head.*` key names still need confirming against a seeded store.
5. **The chain-bound evidence map producer** (Task 3 Step 4). Reuse `loop/contract.py`'s, never re-derive.
