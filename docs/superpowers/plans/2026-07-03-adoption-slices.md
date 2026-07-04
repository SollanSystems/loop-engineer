# Adoption Slices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the four adoption slices from `docs/superpowers/specs/2026-07-03-adoption-slices-design.md` — a self-contained PyPI wheel (S0), a stdlib writer API + LangGraph recipe (B1), a Claude Code Stop-hook false-completion firewall (A1), a GitHub Action + pre-commit hook (C1) — plus the README/show-hn launch tie-in, as five independently shippable PRs.

**Architecture:** All slices sit on one packaging substrate: package data (`schemas/`, `templates/`, four tool scripts) lands inside the wheel under `loop/_bundle/` via hatchling `force-include`, and a new `loop/_resources.py` resolves it `importlib.resources`-first with the existing repo-relative layout as the editable-install fallback. B1 (`loop/emit.py`) is a pure writer over the existing scaffold/contract modules that enforces the G1 evidence rule at write time. A1 is a fail-open Stop hook registered inline in `.claude-plugin/plugin.json`. C1 is an in-repo composite `action.yml` plus `.pre-commit-hooks.yaml`, dogfooded by this repo's own CI.

**Tech Stack:** Python ≥3.10 pure stdlib (pyyaml/jsonschema optional extras only), hatchling build backend, GitHub Actions (composite action + `pypa/gh-action-pypi-publish` trusted publishing), pre-commit, LangGraph (dev dependency of the example only).

## Global Constraints

- Canonical test invocation: `uv run --with pytest --with pyyaml python -B -m pytest -q -p no:cacheprovider scripts` (from repo root). Green baseline: **217 passed / 5 skipped** locally, self_eval 13/13 — never regress it. New env-guarded skips are acceptable (CI shows one more skip than local today; that pattern continues).
- The `loop` package stays **zero third-party runtime dependencies**. `yaml`/`jsonschema` remain optional extras. LangGraph is a dev dependency of the example/CI job only.
- Console script stays `loop`; `python3 -m loop` from a clone keeps working. PR1 adds a second console script `loop-engineer` (same `main`) so `uvx loop-engineer inspect .` works — uvx runs the executable named after the package.
- `loop/emit.py` is a **writer only**: no orchestration, no execution, no subprocesses. The v1.0 non-goal ("never an execution engine") carries over verbatim.
- The Stop hook is a strict no-op without a `.loop/` directory and **fail-open on any error** (always exit 0 except when intentionally emitting a block decision, which is also exit 0 with JSON stdout).
- Launch gates only on PR1 + PR5; PR2–PR4 are individually droppable. Do not couple them: no PR may import from or depend on another parallel PR's files (PR2/PR3/PR4 all depend only on PR1 + existing code).
- Copy discipline (contested-term memory): public-facing copy says **"proof-of-done" / "false completion"**, never brands "loop engineering" as a term we own.
- Conventional commits (`feat:`, `docs:`, `test:`, `ci:`, `chore:`); each PR gets a CHANGELOG.md entry section following the existing format.
- Branching: implementation branches cut from `main` **after** the spec branch `docs/adoption-slices-spec` (this plan travels on it) merges. Branch names: `feat/s0-pypi-substrate`, `feat/b1-emit-api`, `feat/a1-stop-hook`, `feat/c1-ci-action`, `docs/adopt-in-your-stack`.
- Verified external facts baked into this plan (re-verify only if something fails):
  - LangGraph current API (Context7, docs.langchain.com/oss/python/langgraph): `from langgraph.graph import StateGraph, START, END`; TypedDict state; plain-function nodes; `builder.add_node(fn)` / `.add_edge(a, b)` / `.compile()` / `.invoke(state)`. Package name `langgraph`.
  - Claude Code Stop hook (code.claude.com/docs/en/hooks + the live cco plugin): stdin JSON carries `session_id`, `transcript_path`, `cwd`, `hook_event_name: "Stop"`; block by printing `{"decision": "block", "reason": "..."}` to stdout and exiting 0; exit 0 with no output allows the stop; `stop_hook_active` is no longer documented — read it defensively with `.get()`. Plugins register hooks inline under a top-level `"hooks"` key in `.claude-plugin/plugin.json`; `${CLAUDE_PLUGIN_ROOT}` is available in command strings.

---

## PR1 — S0: PyPI substrate (`feat/s0-pypi-substrate`) — do first

### Task 1: `loop/_resources.py` — bundle-first resource resolution

**Files:**
- Create: `loop/_resources.py`
- Test: `scripts/test_resources.py`

**Interfaces:**
- Consumes: nothing new (stdlib `importlib.resources`).
- Produces: `schemas_dir() -> Path`, `templates_dir() -> Path`, `tools_dir() -> Path` — used by Task 2 in `loop/contract.py`, `loop/scaffold.py`, `loop/__main__.py`.

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_resources.py
"""PR1/S0: resource resolution must be importlib.resources-first (wheel) with the
repo-relative checkout as the editable-install fallback. In this checkout no
loop/_bundle exists, so every resolver must land on the repo directories."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_repo_checkout_resolves_to_repo_dirs():
    from loop import _resources

    assert _resources.schemas_dir() == REPO_ROOT / "schemas"
    assert _resources.templates_dir() == REPO_ROOT / "templates"
    assert _resources.tools_dir() == REPO_ROOT / "scripts"


def test_resolved_dirs_hold_the_expected_artifacts():
    from loop import _resources

    assert (_resources.schemas_dir() / "terminal.schema.json").is_file()
    assert (_resources.templates_dir() / "manifest.yaml.tmpl").is_file()
    for tool in ("inspect_loop.py", "metrics.py", "holdout_gate.py", "anticheat_scan.py"):
        assert (_resources.tools_dir() / tool).is_file()


def test_bundle_wins_when_present(tmp_path, monkeypatch):
    """When loop/_bundle/<kind> exists (the wheel layout), it wins over the repo path."""
    from loop import _resources

    bundle = tmp_path / "_bundle" / "schemas"
    bundle.mkdir(parents=True)
    monkeypatch.setattr(_resources, "_bundle_root", lambda: tmp_path / "_bundle")
    assert _resources.schemas_dir() == bundle
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run --with pytest --with pyyaml python -B -m pytest -q -p no:cacheprovider scripts/test_resources.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'loop._resources'` (or ImportError inside the test).

- [ ] **Step 3: Implement `loop/_resources.py`**

```python
# loop/_resources.py
"""Bundle-first resource resolution (S0).

A built wheel carries schemas/, templates/, and the CLI-needed tool scripts as
package data under loop/_bundle/ (see [tool.hatch.build.targets.wheel.force-include]
in pyproject.toml). An editable install / repo checkout has no _bundle, so each
resolver falls back to the historical repo-relative layout. Wheels install as
real directories, so Traversable -> Path is safe here.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

_REPO_FALLBACKS = {"schemas": "schemas", "templates": "templates", "tools": "scripts"}


def _bundle_root() -> Path | None:
    try:
        return Path(str(resources.files("loop") / "_bundle"))
    except Exception:
        return None


def _data_dir(kind: str) -> Path:
    root = _bundle_root()
    if root is not None:
        bundled = root / kind
        if bundled.is_dir():
            return bundled
    return Path(__file__).resolve().parent.parent / _REPO_FALLBACKS[kind]


def schemas_dir() -> Path:
    return _data_dir("schemas")


def templates_dir() -> Path:
    return _data_dir("templates")


def tools_dir() -> Path:
    return _data_dir("tools")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --with pytest --with pyyaml python -B -m pytest -q -p no:cacheprovider scripts/test_resources.py`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add loop/_resources.py scripts/test_resources.py
git commit -m "feat(s0): bundle-first resource resolution for wheel installs"
```

### Task 2: Wire resolution into contract/scaffold/CLI + package the wheel

**Files:**
- Modify: `loop/contract.py:266-269` (`_schemas_dir`)
- Modify: `loop/scaffold.py:8-10` (`_TEMPLATES_DIR`)
- Modify: `loop/__main__.py:99,162` (both `scripts_dir` sites)
- Modify: `pyproject.toml` (force-include, `loop-engineer` console script, stale editable-only comments)

**Interfaces:**
- Consumes: `loop._resources.schemas_dir/templates_dir/tools_dir` from Task 1.
- Produces: a wheel whose `loop/_bundle/{schemas,templates,tools}` is self-contained; console scripts `loop` **and** `loop-engineer` both mapping to `loop.__main__:main`.

- [ ] **Step 1: Rewire `loop/contract.py`**

Replace the `_schemas_dir` body:

```python
def _schemas_dir() -> Path:
    # Bundle-first (wheel package data), repo-relative editable-install fallback.
    from ._resources import schemas_dir

    return schemas_dir()
```

- [ ] **Step 2: Rewire `loop/scaffold.py`**

Replace lines 8–10 (`_TEMPLATES_DIR = ...` and its comment) with:

```python
from ._resources import templates_dir


def _templates_dir() -> Path:
    return templates_dir()
```

and replace both uses of `_TEMPLATES_DIR` inside `scaffold()` (lines 117 and 124) with `_templates_dir()`.

- [ ] **Step 3: Rewire `loop/__main__.py`**

In `_run_metrics` (line 99) and the `inspect` branch (line 162), replace

```python
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
```

with

```python
    from ._resources import tools_dir

    scripts_dir = tools_dir()
```

Also update the `_run_metrics` docstring: `scripts/metrics.py` is now resolved bundle-first, repo-relative fallback (drop "the QW8 editable-install path" phrasing).

- [ ] **Step 4: Update `pyproject.toml`**

Under `[project.scripts]` add the uvx-visible alias:

```toml
[project.scripts]
loop = "loop.__main__:main"
loop-engineer = "loop.__main__:main"
```

Replace the `[tool.hatch.build.targets.wheel]` block and its stale comment with:

```toml
# The wheel is self-contained: schemas/, templates/, and the CLI-needed tool
# scripts ship as package data under loop/_bundle/ (resolved by loop/_resources.py,
# importlib.resources-first with the repo checkout as editable-install fallback).
[tool.hatch.build.targets.wheel]
packages = ["loop"]

[tool.hatch.build.targets.wheel.force-include]
"schemas" = "loop/_bundle/schemas"
"templates" = "loop/_bundle/templates"
"scripts/inspect_loop.py" = "loop/_bundle/tools/inspect_loop.py"
"scripts/metrics.py" = "loop/_bundle/tools/metrics.py"
"scripts/holdout_gate.py" = "loop/_bundle/tools/holdout_gate.py"
"scripts/anticheat_scan.py" = "loop/_bundle/tools/anticheat_scan.py"
```

Also rewrite the now-false `[project.scripts]` comment ("EDITABLE-INSTALL ONLY ... A non-editable wheel does not ship scripts/") to state the new truth: both install modes work; resolution is bundle-first via `loop/_resources.py`.

Note: the bundled `metrics.py`/`inspect_loop.py` compute `_REPO_ROOT` as `loop/_bundle/` and insert it on `sys.path` — harmless, because in a wheel install `from loop.paths import ...` resolves via site-packages. No edits to `scripts/*.py` are needed.

- [ ] **Step 5: Run the full suite**

Run: `uv run --with pytest --with pyyaml python -B -m pytest -q -p no:cacheprovider scripts`
Expected: 220 passed / 5 skipped (baseline 217 + 3 from Task 1), no failures. Also run `python3 -B scripts/self_eval.py` → 13/13.

- [ ] **Step 6: Commit**

```bash
git add loop/contract.py loop/scaffold.py loop/__main__.py pyproject.toml
git commit -m "feat(s0): self-contained wheel — bundle schemas/templates/tools, add loop-engineer console script"
```

### Task 3: Wheel self-containment test

**Files:**
- Test: `scripts/test_wheel_selfcontained.py`

**Interfaces:**
- Consumes: the pyproject force-include from Task 2.
- Produces: the spec's PR1 acceptance gate — wheel built, installed into a fresh venv, `doctor`/`inspect`/`scaffold` run from a temp cwd with the repo checkout absent from `sys.path`.

- [ ] **Step 1: Write the test (env-guarded: skips when pip/network unavailable, runs in CI)**

```python
# scripts/test_wheel_selfcontained.py
"""S0 acceptance: a built wheel must be self-contained. Build the wheel, install
it into a fresh venv, and run scaffold/doctor/inspect from a temp cwd where the
repo checkout is not importable. Env-guarded: building needs pip + network for
the hatchling backend, so this skips in offline/pip-less local envs and runs in CI.
"""

from __future__ import annotations

import json
import subprocess
import sys
import venv
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _pip_available() -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "--version"], capture_output=True, text=True
    )
    return proc.returncode == 0


pytestmark = pytest.mark.skipif(
    not _pip_available(), reason="pip unavailable in this interpreter (wheel build env guard)"
)


@pytest.fixture(scope="module")
def wheel_env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("wheel")
    build = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", str(tmp), str(REPO_ROOT)],
        capture_output=True, text=True,
    )
    if build.returncode != 0:
        pytest.skip(f"wheel build unavailable here (offline?): {build.stderr[-400:]}")
    wheel = next(tmp.glob("loop_engineer-*.whl"))

    venv_dir = tmp / "venv"
    venv.EnvBuilder(with_pip=True).create(venv_dir)
    py = venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    install = subprocess.run(
        [str(py), "-m", "pip", "install", "--no-index", str(wheel)],
        capture_output=True, text=True,
    )
    assert install.returncode == 0, install.stderr
    return py


def _run(py: Path, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    # cwd is OUTSIDE the repo, so the checkout is absent from sys.path.
    return subprocess.run([str(py), "-m", "loop", *args], cwd=cwd, capture_output=True, text=True)


def test_scaffold_doctor_inspect_from_wheel_only(wheel_env, tmp_path):
    workspace = tmp_path / "fresh-loop"

    scaffolded = _run(wheel_env, ["scaffold", str(workspace)], cwd=tmp_path)
    assert scaffolded.returncode == 0, scaffolded.stderr

    doctored = _run(wheel_env, ["doctor", str(workspace)], cwd=tmp_path)
    assert doctored.returncode == 0, doctored.stdout + doctored.stderr
    assert json.loads(doctored.stdout)["ok"] is True

    inspected = _run(wheel_env, ["inspect", str(workspace)], cwd=tmp_path)
    report = json.loads(inspected.stdout)
    assert report["verdict"] in ("weak", "ok", "strong")


def test_both_console_scripts_are_installed(wheel_env, tmp_path):
    bindir = wheel_env.parent
    for name in ("loop", "loop-engineer"):
        exe = bindir / name
        proc = subprocess.run([str(exe), "--version"], cwd=tmp_path, capture_output=True, text=True)
        assert proc.returncode == 0, f"{name}: {proc.stderr}"
        assert proc.stdout.strip()
```

- [ ] **Step 2: Run it**

Run: `uv run --with pytest --with pyyaml python -B -m pytest -q -p no:cacheprovider scripts/test_wheel_selfcontained.py -v`
Expected: 2 passed if this env has pip+network, otherwise 2 skipped (both outcomes acceptable locally; CI must show passed).

- [ ] **Step 3: Sanity-check the wheel contents directly (one-off, not a test)**

```bash
python3 -m pip wheel --no-deps -w /tmp/claude-1000/-mnt-c-Dev-projects-loop-engineer/753451f9-2d87-4514-8d58-db886fa2c22e/scratchpad/wheel . \
  && python3 -c "import zipfile,glob; names=zipfile.ZipFile(glob.glob('/tmp/claude-1000/-mnt-c-Dev-projects-loop-engineer/753451f9-2d87-4514-8d58-db886fa2c22e/scratchpad/wheel/loop_engineer-*.whl')[0]).namelist(); print([n for n in names if '_bundle' in n][:8])"
```

Expected: paths like `loop/_bundle/schemas/manifest.schema.json`, `loop/_bundle/tools/metrics.py`.

- [ ] **Step 4: Commit**

```bash
git add scripts/test_wheel_selfcontained.py
git commit -m "test(s0): wheel self-containment acceptance gate"
```

### Task 4: Tag-triggered PyPI publish workflow

**Files:**
- Create: `.github/workflows/publish.yml`
- Modify: `CHANGELOG.md` (PR1 entry, following the existing per-release format — added under an Unreleased/next heading)

**Interfaces:**
- Consumes: the self-contained wheel from Tasks 2–3.
- Produces: on `v*` tag push, builds sdist+wheel, smoke-tests the wheel, publishes via PyPI **trusted publishing** (no token in the repo).

- [ ] **Step 1: Write `.github/workflows/publish.yml`**

```yaml
name: publish

on:
  push:
    tags: ["v*"]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Tag matches pyproject version
        run: |
          tag="${GITHUB_REF_NAME#v}"
          version="$(python -c 'import tomllib; print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')"
          if [ "$tag" != "$version" ]; then
            echo "tag v$tag != pyproject version $version" >&2
            exit 1
          fi

      - name: Build sdist + wheel
        run: |
          python -m pip install --upgrade build
          python -m build

      - name: Smoke-test the wheel from a temp dir
        run: |
          python -m venv /tmp/smoke
          /tmp/smoke/bin/pip install --no-index dist/*.whl
          cd /tmp
          /tmp/smoke/bin/loop-engineer --version
          /tmp/smoke/bin/loop scaffold /tmp/smoke-loop
          /tmp/smoke/bin/loop doctor /tmp/smoke-loop
          /tmp/smoke/bin/loop inspect /tmp/smoke-loop || true

      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/

  publish:
    needs: build
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/

      - uses: pypa/gh-action-pypi-publish@release/v1
```

(Note: `inspect` on a fresh scaffold exits 1 on a `weak` verdict by design — hence `|| true`; the smoke asserts it *runs*, `doctor` is the hard gate.)

- [ ] **Step 2: Validate the workflow YAML parses**

Run: `uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('.github/workflows/publish.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Add the CHANGELOG entry** (match the existing heading style; content: self-contained wheel, `loop-engineer` console script, publish workflow, wheel acceptance test).

- [ ] **Step 4: Full suite + commit + PR**

```bash
uv run --with pytest --with pyyaml python -B -m pytest -q -p no:cacheprovider scripts
git add .github/workflows/publish.yml CHANGELOG.md
git commit -m "ci(s0): tag-triggered PyPI publish via trusted publishing"
git push -u origin feat/s0-pypi-substrate
gh pr create --title "feat(s0): self-contained wheel + PyPI substrate" --body-file <(...)  # summarize Tasks 1-4, cite spec PR1 acceptance
```

Expected: CI green (the wheel test runs for real there).

### Task 5: Release 0.6.1 — claim the PyPI name (post-merge, human-gated)

**Files:**
- Modify: `pyproject.toml` (version 0.6.0 → 0.6.1), `CHANGELOG.md` (cut the 0.6.1 heading), `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` (version fields if they track the release, matching prior release commits — check `git log --oneline --grep 'chore(release)'` for the exact file set).

**Interfaces:**
- Consumes: merged PR1; the publish workflow.
- Produces: `loop-engineer==0.6.1` live on PyPI; the `uvx loop-engineer` funnel working.

- [ ] **Step 1 (HUMAN GATE — do not skip):** Configure the PyPI **pending trusted publisher** before pushing any tag: on pypi.org → Account → Publishing → add pending publisher for project `loop-engineer`, owner `SollanSystems`, repo `loop-engineer`, workflow `publish.yml`, environment `pypi`. Also create the `pypi` environment in the GitHub repo settings. Ask the operator to confirm this is done.
- [ ] **Step 2:** Cut the release commit on `main` (version bump + CHANGELOG) mirroring the prior `chore(release)` commits, via PR or direct per repo convention (prior releases merged via PR — use a PR).
- [ ] **Step 3 (HUMAN GATE):** Tag and push: `git tag v0.6.1 && git push origin v0.6.1`. Tag push is the publish trigger — confirm with the operator before pushing.
- [ ] **Step 4:** Watch `publish` workflow to green; then verify the funnel end-to-end from a scratch dir:

```bash
cd "$(mktemp -d)" && uvx loop-engineer@0.6.1 inspect . ; uvx loop-engineer@0.6.1 scaffold demo && uvx loop-engineer@0.6.1 doctor demo
```

Expected: `inspect .` exits 1 with a `weak`/gap report (no contract here — that IS the funnel moment); `scaffold` + `doctor` succeed.

---

## PR2 — B1: `loop/emit.py` + LangGraph recipe (`feat/b1-emit-api`)

### Task 6: `loop/emit.py` writer API (TDD)

**Files:**
- Create: `loop/emit.py`
- Test: `scripts/test_emit.py`

**Interfaces:**
- Consumes: `loop.scaffold.scaffold`, `loop.contract` internals (`TERMINAL_STATES`, `_validate_terminal`, `_validate_record`, `_validation_mode`), `loop.paths.resolve_loop_paths`.
- Produces (used verbatim by Task 7's example and PR5's docs):
  - `open_contract(target: str | Path) -> dict` — delegates to the scaffold renderer.
  - `append_iteration(target, *, iteration_id: int, outcome: str, task_id: str = "", actions: Sequence[str] = (), verify_cmd: str = "", verify_outcome: str = "", notes: str = "") -> Path` — appends a RUNLOG.md block the metrics parser reads; updates `.loop/state.json` `iteration_id`/`active_task`.
  - `append_receipt(target, *, iteration_id: int, role: str, model: str, outcome: str, dispatch_id: str | None = None, tokens: int | None = None, cost_usd: float | None = None, ts: str | None = None) -> Path` — appends one schema-valid line to `.loop/receipts/receipts.jsonl`.
  - `terminate(target, *, state: str, criteria_met: dict[str, bool], evidence: list[str], reason: str = "", iteration_id: int | None = None, false_completion: bool = False, lessons_ref: str | None = None) -> Path` — writes `.loop/terminal_state.json` + sets `state.json.terminal_state`; **refuses an evidence-free `Succeeded`**.
  - `class EmitError(ValueError)` — raised on any refused/invalid write; nothing is written when it raises.

- [ ] **Step 1: Write the failing tests**

```python
# scripts/test_emit.py
"""B1 acceptance: emit writes schema-valid artifacts by construction and refuses
an evidence-free Succeeded at write time (G1 enforced before validate time)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from loop import emit
from loop.contract import validate_contract


@pytest.fixture()
def workspace(tmp_path):
    ws = tmp_path / "demo"
    report = emit.open_contract(ws)
    assert report["ok"] is True
    return ws


def test_open_contract_is_doctor_clean(workspace):
    assert validate_contract(workspace)["ok"] is True


def test_append_iteration_writes_parseable_runlog_and_updates_state(workspace):
    runlog = emit.append_iteration(
        workspace, iteration_id=1, outcome="task_passed", task_id="T1",
        actions=["did the thing"], verify_cmd="scripts/verify-fast", verify_outcome="pass",
    )
    text = runlog.read_text(encoding="utf-8")
    assert "## Iteration 1" in text
    assert "`task_passed`" in text

    state = json.loads((workspace / ".loop" / "state.json").read_text(encoding="utf-8"))
    assert state["iteration_id"] == "1"
    assert state["active_task"] == "T1"
    assert validate_contract(workspace)["ok"] is True


def test_append_iteration_rejects_unknown_outcome(workspace):
    with pytest.raises(emit.EmitError):
        emit.append_iteration(workspace, iteration_id=1, outcome="totally_done")


def test_append_receipt_is_schema_valid(workspace):
    path = emit.append_receipt(
        workspace, iteration_id=1, role="write", model="claude-opus", outcome="ok"
    )
    assert path == workspace / ".loop" / "receipts" / "receipts.jsonl"
    # doctor validates .loop/receipts/*.jsonl against loop-engineer/receipt@1
    report = validate_contract(workspace)
    assert report["ok"] is True
    assert "loop-engineer/receipt@1" in report["schemas_checked"]


def test_append_receipt_rejects_bad_role(workspace):
    with pytest.raises(emit.EmitError):
        emit.append_receipt(workspace, iteration_id=1, role="wizard", model="m", outcome="ok")


def test_terminate_succeeded_with_evidence_passes_doctor(workspace):
    terminal = emit.terminate(
        workspace, state="Succeeded", criteria_met={"1": True},
        evidence=["artifact.txt"], reason="verified", iteration_id=1,
    )
    data = json.loads(terminal.read_text(encoding="utf-8"))
    assert data["schema"] == "loop-engineer/terminal@1"
    assert data["false_completion"] is False
    state = json.loads((workspace / ".loop" / "state.json").read_text(encoding="utf-8"))
    assert state["terminal_state"] == "Succeeded"
    assert validate_contract(workspace)["ok"] is True


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(criteria_met={"1": True}, evidence=[]),                      # evidence-free
        dict(criteria_met={"1": False}, evidence=["a.txt"]),              # no met criterion
        dict(criteria_met={}, evidence=["a.txt"]),                        # empty criteria
        dict(criteria_met={"1": True}, evidence=["a.txt"], false_completion=True),  # G1 contradiction
    ],
)
def test_terminate_refuses_dishonest_succeeded(workspace, kwargs):
    with pytest.raises(emit.EmitError):
        emit.terminate(workspace, state="Succeeded", reason="claimed", **kwargs)
    assert not (workspace / ".loop" / "terminal_state.json").exists()


def test_terminate_honest_failure_needs_no_evidence(workspace):
    emit.terminate(
        workspace, state="FailedUnverifiable", criteria_met={"1": False},
        evidence=[], reason="could not verify",
    )
    assert validate_contract(workspace)["ok"] is True


def test_terminate_rejects_unknown_state(workspace):
    with pytest.raises(emit.EmitError):
        emit.terminate(workspace, state="Done", criteria_met={"1": True}, evidence=["a"])


def test_writes_refused_without_a_contract(tmp_path):
    with pytest.raises(emit.EmitError):
        emit.append_iteration(tmp_path / "nowhere", iteration_id=1, outcome="task_passed")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --with pytest --with pyyaml python -B -m pytest -q -p no:cacheprovider scripts/test_emit.py`
Expected: FAIL — `ImportError: cannot import name 'emit'`.

- [ ] **Step 3: Implement `loop/emit.py`**

```python
# loop/emit.py
"""Writer API for foreign runtimes (B1). A writer, never a runtime: it renders
contract artifacts and refuses dishonest ones — no orchestration, no execution.

The G1 cross-check (a Succeeded terminal needs evidence and a met criterion)
is enforced HERE, at write time, before doctor ever sees the file.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .contract import (
    TERMINAL_STATES,
    _validate_record,
    _validate_terminal,
    _validation_mode,
)
from .paths import resolve_loop_paths
from .scaffold import scaffold

_ITERATION_OUTCOMES = (
    "task_passed",
    "task_failed",
    "repair_triggered",
    "approval_requested",
    "replanned",
    "terminal",
)
_RECEIPT_ROLES = ("read", "reason", "write", "orchestrate")
_RECEIPT_OUTCOMES = ("ok", "fail", "escalated")


class EmitError(ValueError):
    """A write was refused: it would produce a dishonest or schema-invalid artifact."""


def open_contract(target: str | Path) -> dict[str, Any]:
    """Render a fresh, doctor-clean contract. Delegates to the scaffold renderer."""
    return scaffold(target)


def _require_contract(target: str | Path):
    paths = resolve_loop_paths(target)
    if not paths.state.is_file():
        raise EmitError(
            f"no loop contract at {paths.workspace} (missing .loop/state.json) — "
            f"call emit.open_contract() first"
        )
    return paths


def _read_state(paths) -> dict[str, Any]:
    try:
        data = json.loads(paths.state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EmitError(f"unreadable state.json: {exc}") from exc
    if not isinstance(data, dict):
        raise EmitError("state.json must hold a JSON object")
    return data


def _write_state(paths, state: dict[str, Any]) -> None:
    paths.state.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def append_iteration(
    target: str | Path,
    *,
    iteration_id: int,
    outcome: str,
    task_id: str = "",
    actions: Sequence[str] = (),
    verify_cmd: str = "",
    verify_outcome: str = "",
    notes: str = "",
) -> Path:
    """Append one iteration block to RUNLOG.md (the shape scripts/metrics.py
    parses: `## Iteration <id>` header + a backticked outcome token) and advance
    .loop/state.json's iteration_id/active_task."""
    if outcome not in _ITERATION_OUTCOMES:
        raise EmitError(f"unknown iteration outcome {outcome!r}; expected one of {_ITERATION_OUTCOMES}")
    paths = _require_contract(target)

    lines = [
        "",
        f"## Iteration {iteration_id} — {datetime.now(timezone.utc).date().isoformat()}",
        "",
    ]
    if task_id:
        lines.append(f"**Active task:** `{task_id}`")
        lines.append("")
    if actions:
        lines.append("### Actions taken")
        lines.append("")
        lines.extend(f"- {a}" for a in actions)
        lines.append("")
    if verify_cmd or verify_outcome:
        lines.append("### Verification result")
        lines.append("")
        lines.append(f"- **Gate:** `{verify_cmd}` — {verify_outcome}")
        lines.append("")
    lines.append("### Outcome")
    lines.append("")
    lines.append(f"`{outcome}`")
    lines.append("")
    if notes:
        lines.append("### Notes")
        lines.append("")
        lines.append(notes)
        lines.append("")

    runlog = paths.runlog
    if not runlog.exists():
        runlog = paths.workspace / "RUNLOG.md"
        runlog.write_text(f"# RUNLOG.md — {paths.workspace.name}\n", encoding="utf-8")
    with runlog.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    state = _read_state(paths)
    state["iteration_id"] = str(iteration_id)
    if task_id:
        state["active_task"] = task_id
    _write_state(paths, state)
    return runlog


def append_receipt(
    target: str | Path,
    *,
    iteration_id: int,
    role: str,
    model: str,
    outcome: str,
    dispatch_id: str | None = None,
    tokens: int | None = None,
    cost_usd: float | None = None,
    ts: str | None = None,
) -> Path:
    """Append one loop-engineer/receipt@1 line to .loop/receipts/receipts.jsonl."""
    if role not in _RECEIPT_ROLES:
        raise EmitError(f"unknown receipt role {role!r}; expected one of {_RECEIPT_ROLES}")
    if outcome not in _RECEIPT_OUTCOMES:
        raise EmitError(f"unknown receipt outcome {outcome!r}; expected one of {_RECEIPT_OUTCOMES}")
    if not isinstance(iteration_id, int) or isinstance(iteration_id, bool) or iteration_id < 0:
        raise EmitError("iteration_id must be a non-negative integer")
    paths = _require_contract(target)

    record: dict[str, Any] = {
        "schema": "loop-engineer/receipt@1",
        "iteration_id": iteration_id,
        "dispatch_id": dispatch_id,
        "role": role,
        "model": model,
        "outcome": outcome,
        "tokens": tokens,
        "cost_usd": cost_usd,
        "ts": ts,
    }
    receipts = paths.loop_dir / "receipts" / "receipts.jsonl"
    issues: list[dict] = []
    _validate_record(record, "receipt", receipts, _validation_mode(), issues)
    if issues:
        raise EmitError(f"receipt failed schema validation: {issues}")
    receipts.parent.mkdir(parents=True, exist_ok=True)
    with receipts.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return receipts


def terminate(
    target: str | Path,
    *,
    state: str,
    criteria_met: dict[str, bool],
    evidence: list[str],
    reason: str = "",
    iteration_id: int | None = None,
    false_completion: bool = False,
    lessons_ref: str | None = None,
) -> Path:
    """Write .loop/terminal_state.json (and stamp state.json.terminal_state).

    Refuses an evidence-free Succeeded — the G1 cross-check at write time:
    Succeeded requires non-empty evidence, at least one met criterion, and
    false_completion=False.
    """
    if state not in TERMINAL_STATES:
        raise EmitError(f"unknown terminal state {state!r}; expected one of {TERMINAL_STATES}")
    if state == "Succeeded":
        if false_completion:
            raise EmitError("refusing Succeeded with false_completion=True (G1 contradiction)")
        if not evidence:
            raise EmitError("refusing evidence-free Succeeded: evidence[] is empty (G1)")
        if not any(v is True for v in criteria_met.values()):
            raise EmitError("refusing Succeeded with no met (true) entry in criteria_met (G1)")
    paths = _require_contract(target)
    current = _read_state(paths)

    terminal: dict[str, Any] = {
        "schema": "loop-engineer/terminal@1",
        "project": paths.workspace.name,
        "state": state,
        "criteria_met": dict(criteria_met),
        "evidence": list(evidence),
        "false_completion": false_completion,
        "terminated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if reason:
        terminal["reason"] = reason
    if iteration_id is not None:
        terminal["iteration_id"] = iteration_id
    if lessons_ref is not None:
        terminal["lessons_ref"] = lessons_ref

    terminal_path = paths.loop_dir / "terminal_state.json"
    issues: list[dict] = []
    _validate_terminal(terminal, terminal_path, issues)
    if issues:
        raise EmitError(f"terminal failed validation before write: {issues}")

    terminal_path.write_text(json.dumps(terminal, indent=2) + "\n", encoding="utf-8")
    current["terminal_state"] = state
    _write_state(paths, current)
    return terminal_path
```

- [ ] **Step 4: Run the tests**

Run: `uv run --with pytest --with pyyaml python -B -m pytest -q -p no:cacheprovider scripts/test_emit.py`
Expected: all pass (12 tests). Then the full suite — no regressions.

- [ ] **Step 5: Commit**

```bash
git add loop/emit.py scripts/test_emit.py
git commit -m "feat(b1): loop/emit.py writer API — G1 evidence rule enforced at write time"
```

### Task 7: LangGraph recipe — runnable example + docs + CI job

**Files:**
- Create: `examples/langgraph-emit/graph_example.py`
- Create: `examples/langgraph-emit/README.md`
- Create: `docs/integrations/langgraph.md`
- Test: `scripts/test_langgraph_recipe.py`
- Modify: `.github/workflows/ci.yml` (add `recipe-langgraph` job)

**Interfaces:**
- Consumes: `loop.emit` exactly as defined in Task 6.
- Produces: a runnable graph whose terminal node calls `emit.terminate(...)`; the emitted contract passes `doctor` (spec PR2 acceptance).

- [ ] **Step 1: Write the failing recipe test (env-guarded on langgraph)**

```python
# scripts/test_langgraph_recipe.py
"""B1 acceptance: the LangGraph recipe example runs end-to-end and its emitted
contract passes doctor. Env-guarded: langgraph is a dev dependency of the
example only — the package stays zero-dependency."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("langgraph")

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "langgraph-emit" / "graph_example.py"


def test_recipe_runs_end_to_end_and_passes_doctor(tmp_path):
    workspace = tmp_path / "graph-run"
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
    proc = subprocess.run(
        [sys.executable, "-B", str(EXAMPLE), str(workspace)],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    doctored = subprocess.run(
        [sys.executable, "-B", "-m", "loop", "doctor", str(workspace)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert doctored.returncode == 0, doctored.stdout
    assert json.loads(doctored.stdout)["ok"] is True

    terminal = json.loads((workspace / ".loop" / "terminal_state.json").read_text())
    assert terminal["state"] == "Succeeded"
    assert terminal["evidence"], "Succeeded must carry evidence"
```

Run: `uv run --with pytest --with pyyaml --with langgraph python -B -m pytest -q -p no:cacheprovider scripts/test_langgraph_recipe.py`
Expected: FAIL — example file missing. (Without `--with langgraph` it must SKIP — check that too.)

- [ ] **Step 2: Write the example**

```python
# examples/langgraph-emit/graph_example.py
"""A minimal LangGraph graph that ships proof-of-done through loop.emit.

The graph does real (tiny) work, verifies it from the filesystem, and the
terminal node records the outcome via emit.terminate(...) — which refuses an
evidence-free Succeeded. Run:

    python graph_example.py <fresh-workspace-dir>
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from loop import emit


class State(TypedDict):
    workspace: str
    verified: bool


def do_work(state: State) -> dict:
    out = Path(state["workspace"]) / "artifact.txt"
    out.write_text("hello from langgraph\n", encoding="utf-8")
    return {}


def verify(state: State) -> dict:
    artifact = Path(state["workspace"]) / "artifact.txt"
    ok = artifact.is_file() and "hello" in artifact.read_text(encoding="utf-8")
    return {"verified": ok}


def conclude(state: State) -> dict:
    ws = state["workspace"]
    passed = state["verified"]
    emit.append_iteration(
        ws, iteration_id=1, outcome="task_passed" if passed else "task_failed",
        task_id="T1", actions=["wrote artifact.txt", "re-read and checked content"],
        verify_cmd="verify node (filesystem re-read)", verify_outcome="pass" if passed else "fail",
    )
    if passed:
        emit.terminate(
            ws, state="Succeeded", criteria_met={"1": True},
            evidence=["artifact.txt"], reason="artifact written and independently re-read",
            iteration_id=1,
        )
    else:
        emit.terminate(
            ws, state="FailedUnverifiable", criteria_met={"1": False},
            evidence=[], reason="verification failed", iteration_id=1,
        )
    return {}


def main(workspace: str) -> int:
    emit.open_contract(workspace)
    graph = (
        StateGraph(State)
        .add_node(do_work)
        .add_node(verify)
        .add_node(conclude)
        .add_edge(START, "do_work")
        .add_edge("do_work", "verify")
        .add_edge("verify", "conclude")
        .add_edge("conclude", END)
        .compile()
    )
    graph.invoke({"workspace": workspace, "verified": False})
    print(f"contract emitted at {workspace}/.loop — run: python3 -m loop doctor {workspace}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python graph_example.py <fresh-workspace-dir>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
```

- [ ] **Step 3: Write `examples/langgraph-emit/README.md`** — short: what it shows (a graph whose terminal node writes the contract; a lying `Succeeded` raises `EmitError` before anything hits disk), how to run it (`pip install loop-engineer langgraph`, `python graph_example.py demo-run/`, `loop doctor demo-run/`), and a pointer to `docs/integrations/langgraph.md`.

- [ ] **Step 4: Write `docs/integrations/langgraph.md`** — the 10-line integration, verbatim-runnable:

````markdown
# LangGraph — proof-of-done in 10 lines

`loop.emit` is a pure-stdlib writer: your graph keeps its own runtime, and the
terminal node records evidence-backed state the `loop` CLI can independently
validate. `pip install loop-engineer` (LangGraph itself stays your dependency).

```python
from loop import emit

emit.open_contract("run/")                                   # once, before the graph runs

def conclude(state):                                          # your graph's terminal node
    emit.append_iteration("run/", iteration_id=1, outcome="task_passed",
                          task_id="T1", verify_cmd="pytest -q", verify_outcome="pass")
    emit.terminate("run/", state="Succeeded",
                   criteria_met={"tests": True}, evidence=["reports/pytest.txt"])
    return {}
```

`emit.terminate` **refuses an evidence-free `Succeeded`** (raises `EmitError`) —
the same cross-check `loop doctor` enforces, applied before the file exists.

Gate it in CI:

```yaml
- run: pip install loop-engineer
- run: loop doctor run/
```

Full runnable example: [`examples/langgraph-emit/`](../../examples/langgraph-emit/).
````

- [ ] **Step 5: Add the CI job to `.github/workflows/ci.yml`**

```yaml
  recipe-langgraph:
    name: recipe (langgraph)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install recipe dependencies
        run: python -m pip install --upgrade pip pyyaml pytest jsonschema langgraph
      - name: LangGraph recipe end-to-end
        run: python -B -m pytest -q -p no:cacheprovider scripts/test_langgraph_recipe.py
```

- [ ] **Step 6: Run everything**

Run: `uv run --with pytest --with pyyaml --with langgraph python -B -m pytest -q -p no:cacheprovider scripts/test_langgraph_recipe.py scripts/test_emit.py` → all pass.
Run the full canonical suite (no langgraph) → recipe test SKIPS, everything else green.

- [ ] **Step 7: CHANGELOG entry + commit + PR**

```bash
git add examples/langgraph-emit docs/integrations scripts/test_langgraph_recipe.py .github/workflows/ci.yml CHANGELOG.md
git commit -m "feat(b1): LangGraph recipe — runnable emit example + CI job"
git push -u origin feat/b1-emit-api
gh pr create --title "feat(b1): loop/emit.py writer API + LangGraph recipe" --body-file <(...)
```

---

## PR3 — A1: Stop-hook false-completion firewall (`feat/a1-stop-hook`)

### Task 8: `hooks/stop_firewall.py` (TDD, fixtures offline)

**Files:**
- Create: `hooks/stop_firewall.py`
- Test: `scripts/test_stop_firewall.py`

**Interfaces:**
- Consumes: the `loop` CLI (`shutil.which("loop")` first, else `python3 -m loop` with `CLAUDE_PLUGIN_ROOT` on `PYTHONPATH`); Claude Code Stop-hook stdin/stdout contract (see Global Constraints).
- Produces: exit 0 always; stdout `{"decision": "block", "reason": ...}` only when the contract claims `Succeeded` and doctor says `ok:false`. Task 9 registers it.

- [ ] **Step 1: Write the failing tests**

```python
# scripts/test_stop_firewall.py
"""A1 acceptance, exercised offline: honest contract passes silently, lying
contract blocks with the doctor issues named, absent .loop is a strict no-op,
and any error path fails OPEN (a broken firewall must never lock a session)."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "hooks" / "stop_firewall.py"

sys.path.insert(0, str(REPO_ROOT))
from loop.scaffold import scaffold  # noqa: E402


def _run_hook(payload: dict, plugin_root: Path | None = REPO_ROOT, extra_env: dict | None = None):
    env = {
        "PATH": "/usr/bin:/bin",  # no `loop` console script on PATH: forces the plugin-root path
        "CLAUDE_PLUGIN_ROOT": str(plugin_root) if plugin_root else "",
    }
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-B", str(HOOK)],
        input=json.dumps(payload), env=env, capture_output=True, text=True, timeout=120,
    )


def _payload(cwd: Path, **overrides) -> dict:
    base = {
        "session_id": f"test-{uuid.uuid4().hex}",  # unique: the once-per-session sentinel must not leak across tests
        "transcript_path": "/dev/null",
        "cwd": str(cwd),
        "hook_event_name": "Stop",
    }
    base.update(overrides)
    return base


def _lying_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "lying"
    scaffold(ws)
    (ws / ".loop" / "terminal_state.json").write_text(json.dumps({
        "schema": "loop-engineer/terminal@1",
        "state": "Succeeded",
        "criteria_met": {"1": False},        # no met criterion → doctor ok:false (G1)
        "evidence": [],
        "false_completion": True,            # contradiction → doctor ok:false
    }), encoding="utf-8")
    return ws


def _honest_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "honest"
    scaffold(ws)
    (ws / ".loop" / "terminal_state.json").write_text(json.dumps({
        "schema": "loop-engineer/terminal@1",
        "state": "Succeeded",
        "criteria_met": {"1": True},
        "evidence": ["artifact.txt"],
        "false_completion": False,
    }), encoding="utf-8")
    state_path = ws / ".loop" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["terminal_state"] = "Succeeded"
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return ws


def test_no_loop_dir_is_a_strict_noop(tmp_path):
    proc = _run_hook(_payload(tmp_path))
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_honest_succeeded_passes_silently(tmp_path):
    proc = _run_hook(_payload(_honest_workspace(tmp_path)))
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_inflight_contract_passes_silently(tmp_path):
    ws = tmp_path / "inflight"
    scaffold(ws)  # no terminal claim at all
    proc = _run_hook(_payload(ws))
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_lying_succeeded_blocks_with_doctor_issues(tmp_path):
    proc = _run_hook(_payload(_lying_workspace(tmp_path)))
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["decision"] == "block"
    assert "contradictory_terminal" in out["reason"]
    assert "Succeeded" in out["reason"]


def test_blocks_at_most_once_per_session(tmp_path):
    ws = _lying_workspace(tmp_path)
    payload = _payload(ws)
    first = _run_hook(payload)
    assert json.loads(first.stdout)["decision"] == "block"
    second = _run_hook(payload)  # same session_id, same issues
    assert second.returncode == 0
    assert second.stdout.strip() == ""


def test_stop_hook_active_never_blocks(tmp_path):
    proc = _run_hook(_payload(_lying_workspace(tmp_path), stop_hook_active=True))
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_malformed_stdin_fails_open():
    proc = subprocess.run(
        [sys.executable, "-B", str(HOOK)], input="not json{{{",
        env={"PATH": "/usr/bin:/bin", "CLAUDE_PLUGIN_ROOT": str(REPO_ROOT)},
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_unresolvable_cli_fails_open(tmp_path):
    """Forced-error fixture: lying contract but no reachable loop CLI."""
    proc = _run_hook(_payload(_lying_workspace(tmp_path)), plugin_root=tmp_path / "empty")
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --with pytest --with pyyaml python -B -m pytest -q -p no:cacheprovider scripts/test_stop_firewall.py`
Expected: FAIL — hook file missing.

- [ ] **Step 3: Implement `hooks/stop_firewall.py`**

```python
#!/usr/bin/env python3
"""Stop-hook false-completion firewall (A1).

On session stop, if the CWD holds a .loop/ contract that claims Succeeded while
`loop doctor` reports ok:false, emit blocking feedback carrying the doctor
issues so the agent cannot end the turn on a false "done".

Invariants:
  * strict no-op when no .loop/ exists — zero cost for every other repo;
  * fail-open on ANY error — a broken firewall must never lock a session;
  * blocks at most once per session per issue-set (tempdir sentinel), and never
    when stop_hook_active is set — no livelock.

Stdlib only. Runs under whatever python3 Claude Code invokes.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_MAX_ISSUES_IN_REASON = 5


def _cli_command() -> list[str] | None:
    exe = shutil.which("loop")
    if exe:
        return [exe]
    root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if root and (Path(root) / "loop" / "__main__.py").is_file():
        return [sys.executable or "python3", "-m", "loop"]
    return None


def _cli_env() -> dict[str, str]:
    env = dict(os.environ)
    root = env.get("CLAUDE_PLUGIN_ROOT", "")
    if root:
        env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _claims_succeeded(loop_dir: Path) -> bool:
    for candidate, key in (
        (loop_dir / "terminal_state.json", "state"),
        (loop_dir / "state.json", "terminal_state"),
    ):
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get(key) == "Succeeded":
            return True
    return False


def _blocked_before(session_id: str, digest: str) -> bool:
    sentinel = Path(tempfile.gettempdir()) / f"loop-engineer-stop-{session_id or 'nosession'}"
    try:
        if sentinel.is_file() and sentinel.read_text(encoding="utf-8") == digest:
            return True
        sentinel.write_text(digest, encoding="utf-8")
    except OSError:
        return True  # cannot track repeats → err on the never-lock side
    return False


def main() -> int:
    payload = json.load(sys.stdin)
    cwd = Path(payload.get("cwd") or os.getcwd())
    loop_dir = cwd / ".loop"
    if not loop_dir.is_dir():
        return 0
    if payload.get("stop_hook_active"):
        return 0
    if not _claims_succeeded(loop_dir):
        return 0

    cli = _cli_command()
    if cli is None:
        return 0
    proc = subprocess.run(
        cli + ["doctor", str(cwd)],
        capture_output=True, text=True, timeout=60, env=_cli_env(),
    )
    report = json.loads(proc.stdout)
    if report.get("ok") is True:
        return 0

    issues = [i for i in report.get("issues", []) if isinstance(i, dict)]
    digest = hashlib.sha256(json.dumps(issues, sort_keys=True).encode("utf-8")).hexdigest()
    if _blocked_before(str(payload.get("session_id", "")), digest):
        return 0

    summary = "; ".join(
        f"{i.get('code', '?')}: {i.get('message', '')}" for i in issues[:_MAX_ISSUES_IN_REASON]
    ) or "doctor reported ok:false"
    if len(issues) > _MAX_ISSUES_IN_REASON:
        summary += f"; … {len(issues) - _MAX_ISSUES_IN_REASON} more"
    print(json.dumps({
        "decision": "block",
        "reason": (
            "loop-engineer stop firewall: this workspace's loop contract claims "
            f"Succeeded, but `loop doctor` reports {len(issues)} issue(s): {summary}. "
            "Fix the contract or record an honest terminal state "
            "(e.g. FailedUnverifiable) before ending the turn."
        ),
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # fail-open, always
```

- [ ] **Step 4: Run the tests**

Run: `uv run --with pytest --with pyyaml python -B -m pytest -q -p no:cacheprovider scripts/test_stop_firewall.py`
Expected: 8 passed. Then the full suite — no regressions.

- [ ] **Step 5: Commit**

```bash
git add hooks/stop_firewall.py scripts/test_stop_firewall.py
git commit -m "feat(a1): Stop-hook false-completion firewall — fail-open, no-op without .loop"
```

### Task 9: Register the hook in the plugin manifest

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Test: extend `scripts/test_stop_firewall.py`

**Interfaces:**
- Consumes: `hooks/stop_firewall.py` from Task 8.
- Produces: marketplace installs get the firewall with zero config.

- [ ] **Step 1: Write the failing registration test (append to `scripts/test_stop_firewall.py`)**

```python
def test_hook_is_registered_in_plugin_manifest():
    manifest = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    stop_entries = manifest["hooks"]["Stop"]
    commands = [h["command"] for entry in stop_entries for h in entry["hooks"]]
    assert any("stop_firewall.py" in c and "${CLAUDE_PLUGIN_ROOT}" in c for c in commands)
```

Run it → FAIL (`KeyError: 'hooks'`).

- [ ] **Step 2: Add to `.claude-plugin/plugin.json`** (top-level key, alongside `"license"`):

```json
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/stop_firewall.py",
            "timeout": 90
          }
        ]
      }
    ]
  }
```

- [ ] **Step 3: Run** the registration test + the CI JSON-validity gate locally (`python3 -B -c "import json; json.load(open('.claude-plugin/plugin.json'))"`) → pass.

- [ ] **Step 4: CHANGELOG entry + commit + PR**

```bash
git add .claude-plugin/plugin.json scripts/test_stop_firewall.py CHANGELOG.md
git commit -m "feat(a1): register the stop firewall in the plugin manifest"
git push -u origin feat/a1-stop-hook
gh pr create --title "feat(a1): Stop-hook false-completion firewall" --body-file <(...)
```

- [ ] **Step 5 (manual, once, after merge):** reinstall/refresh the local plugin cache from HEAD (`git archive HEAD | tar -x -C <cache>` per the known local-marketplace staleness), restart Claude Code, and live-smoke the hook in a scratch repo: scaffold, write the lying terminal from the test fixture, end a session → the block message must appear. Record the result in the PR thread.

---

## PR4 — C1: GitHub Action + pre-commit (`feat/c1-ci-action`)

### Task 10: Composite `action.yml` + CI dogfood

**Files:**
- Create: `action.yml` (repo root — required location for `uses: SollanSystems/loop-engineer@<ref>`)
- Modify: `.github/workflows/ci.yml` (add `action-dogfood` job)

**Interfaces:**
- Consumes: the published wheel (pinned `version` input) **or** the action's own checkout (default — the dogfood/source mode).
- Produces: `doctor` hard gate + `inspect` scorecard in `$GITHUB_STEP_SUMMARY`; optional PR comment; configurable `fail-under-score` (inspect emits `score` 0–100 and `verdict` weak/ok/strong).

- [ ] **Step 1: Write `action.yml`**

```yaml
name: "loop-engineer gate"
description: "Proof-of-done gate for agent-loop contracts: hard-fails on doctor, scores with inspect (warn-only by default)."
branding:
  icon: "check-circle"
  color: "green"

inputs:
  path:
    description: "Workspace (or .loop dir) holding the loop contract"
    required: false
    default: "."
  version:
    description: "loop-engineer version to install from PyPI (e.g. 0.6.1). Empty installs from the action's own checkout."
    required: false
    default: ""
  fail-under-score:
    description: "Fail the job when the inspect score (0-100) is below this. 0 keeps inspect warn-only."
    required: false
    default: "0"
  python-version:
    description: "Python version for the gate"
    required: false
    default: "3.12"
  github-token:
    description: "Token for the optional PR scorecard comment. Empty skips the comment."
    required: false
    default: ""

runs:
  using: "composite"
  steps:
    - uses: actions/setup-python@v5
      with:
        python-version: ${{ inputs.python-version }}

    - name: Install loop-engineer
      shell: bash
      run: |
        if [ -n "${{ inputs.version }}" ]; then
          python -m pip install --quiet "loop-engineer==${{ inputs.version }}"
        else
          python -m pip install --quiet "${{ github.action_path }}"
        fi

    - name: loop doctor (hard gate)
      shell: bash
      run: loop doctor "${{ inputs.path }}"

    - name: loop inspect (scorecard)
      shell: bash
      run: |
        set +e
        loop inspect "${{ inputs.path }}" > "${RUNNER_TEMP}/inspect.json"
        set -e
        python - "${RUNNER_TEMP}/inspect.json" "${{ inputs.fail-under-score }}" <<'PY'
        import json, os, sys

        report = json.load(open(sys.argv[1]))
        fail_under = int(sys.argv[2])
        score, verdict = report.get("score", 0), report.get("verdict", "?")
        lines = [
            "## loop-engineer scorecard",
            "",
            f"| metric | value |",
            f"|---|---|",
            f"| verdict | **{verdict}** |",
            f"| score | {score}/100 |",
            f"| gaps | {len(report.get('gaps', []))} |",
            "",
        ]
        for gap in report.get("gaps", [])[:10]:
            lines.append(f"- {gap}")
        summary = "\n".join(lines) + "\n"
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(summary)
        open(os.path.join(os.environ["RUNNER_TEMP"], "scorecard.md"), "w", encoding="utf-8").write(summary)
        if verdict == "weak":
            print(f"::warning::loop inspect verdict is weak (score {score}/100)")
        if fail_under and score < fail_under:
            print(f"::error::inspect score {score} < fail-under-score {fail_under}")
            raise SystemExit(1)
        PY

    - name: PR scorecard comment (optional)
      if: ${{ inputs.github-token != '' && github.event_name == 'pull_request' }}
      shell: bash
      env:
        GH_TOKEN: ${{ inputs.github-token }}
      run: |
        gh api "repos/${GITHUB_REPOSITORY}/issues/${{ github.event.pull_request.number }}/comments" \
          -f body="$(cat "${RUNNER_TEMP}/scorecard.md")" || echo "::warning::PR comment failed (non-fatal)"
```

(Heredoc indentation caution: the `<<'PY' ... PY` block inside a composite `run:` must be flush with the run block's indentation — copy exactly, then validate.)

- [ ] **Step 2: Validate the action YAML**

Run: `uv run --with pyyaml python -c "import yaml; d=yaml.safe_load(open('action.yml')); assert d['runs']['using']=='composite'; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Add the dogfood job to `.github/workflows/ci.yml`** — the "passes its own gate" story extended to CI:

```yaml
  action-dogfood:
    name: action (dogfood on own contract)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ./
        with:
          path: "."
          fail-under-score: "90"
```

(This repo's own contract currently scores 100/strong and passes doctor — verified during planning — so 90 is a real, non-vacuous gate.)

- [ ] **Step 4: Commit**

```bash
git add action.yml .github/workflows/ci.yml
git commit -m "feat(c1): composite GitHub Action — doctor hard gate + inspect scorecard, dogfooded in CI"
```

### Task 11: `.pre-commit-hooks.yaml` + consumer-side fixture test

**Files:**
- Create: `.pre-commit-hooks.yaml` (repo root)
- Test: `scripts/test_precommit_hook.py`
- Modify: `.github/workflows/ci.yml` (`action-dogfood` job gains the pre-commit fixture step)

**Interfaces:**
- Consumes: the pip-installable repo (PR1's self-contained wheel makes `language: python` work from a consumer's `.pre-commit-config.yaml`).
- Produces: hook id `loop-doctor`.

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_precommit_hook.py
"""C1 acceptance: the pre-commit hook definition is sound (always), and it runs
from a consumer-side .pre-commit-config.yaml fixture (env-guarded on the
pre-commit tool; the CI dogfood job installs it and runs this for real)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT))
from loop.scaffold import scaffold  # noqa: E402


def _hooks() -> list[dict]:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load((REPO_ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))


def test_hook_definition_is_sound():
    (hook,) = _hooks()
    assert hook["id"] == "loop-doctor"
    assert hook["entry"] == "loop doctor ."
    assert hook["language"] == "python"
    assert hook["pass_filenames"] is False
    assert hook["always_run"] is True


def test_entry_command_matches_a_declared_console_script():
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'loop = "loop.__main__:main"' in text


@pytest.mark.skipif(shutil.which("pre-commit") is None, reason="pre-commit tool not installed")
def test_hook_runs_from_a_consumer_fixture(tmp_path):
    consumer = tmp_path / "consumer"
    scaffold(consumer)
    subprocess.run(["git", "init", "-q"], cwd=consumer, check=True)
    subprocess.run(["git", "add", "-A"], cwd=consumer, check=True)
    proc = subprocess.run(
        ["pre-commit", "try-repo", str(REPO_ROOT), "loop-doctor", "--all-files"],
        cwd=consumer, capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
```

Run: `uv run --with pytest --with pyyaml python -B -m pytest -q -p no:cacheprovider scripts/test_precommit_hook.py`
Expected: FAIL — `.pre-commit-hooks.yaml` missing (fixture test skips locally without pre-commit).

(Note: `pre-commit try-repo` uses the repo's **committed** tree — in CI it runs on the PR checkout, which is exactly what we want; locally uncommitted edits to the hook file won't be seen by try-repo, only by the yaml assertions.)

- [ ] **Step 2: Write `.pre-commit-hooks.yaml`**

```yaml
- id: loop-doctor
  name: loop doctor (loop-contract validity gate)
  description: "Validate the repo's .loop/ contract objects; fails on a dishonest or malformed contract."
  entry: loop doctor .
  language: python
  pass_filenames: false
  always_run: true
```

- [ ] **Step 3: Extend the `action-dogfood` CI job** with the real consumer-side run:

```yaml
      - name: pre-commit consumer fixture
        run: |
          python -m pip install --quiet pre-commit pytest pyyaml
          python -B -m pytest -q -p no:cacheprovider scripts/test_precommit_hook.py
```

- [ ] **Step 4: Run locally** (yaml assertions pass, fixture skips), then full suite → green.

- [ ] **Step 5: CHANGELOG entry + commit + PR**

```bash
git add .pre-commit-hooks.yaml scripts/test_precommit_hook.py .github/workflows/ci.yml CHANGELOG.md
git commit -m "feat(c1): pre-commit hook id loop-doctor + consumer fixture test"
git push -u origin feat/c1-ci-action
gh pr create --title "feat(c1): GitHub Action + pre-commit gate" --body-file <(...)
```

Expected: the `action-dogfood` CI job green on this PR — that is the spec's PR4 acceptance ("action smoke-run green in this repo's CI on its own contract").

---

## PR5 — docs + launch tie-in (`docs/adopt-in-your-stack`)

### Task 12: README "Adopt in your stack" + Install refresh

**Files:**
- Modify: `README.md` (new `## Adopt in your stack` section between `## Install` and `## Claude Code reference workflow`; refresh the now-stale editable-only language in `### Portable validator / inspector`, README lines ~243–265)

**Interfaces:**
- Consumes: everything PR1–PR4 shipped. If a parallel PR was dropped, its subsection is dropped with it — write only what merged.
- Produces: the README claims that Task 14's docs-claims tests pin.

- [ ] **Step 1: Refresh `### Portable validator / inspector`.** Lead with the wheel:

````markdown
```bash
uvx loop-engineer inspect .        # zero-install score of any repo's loop contract
pip install loop-engineer          # or install the CLI: `loop doctor`, `loop inspect`, ...
```

From a clone, `python3 -m loop <cmd>` and `pip install -e .` keep working; the
wheel is self-contained (schemas, templates, and the inspect/metrics tooling
ship inside it). The core is pure-stdlib — PyYAML/jsonschema are optional extras.
````

Keep the existing schema-id list. Delete the sentence claiming the CLI only resolves from the repo root.

- [ ] **Step 2: Add the section (adapt to what actually merged):**

````markdown
## Adopt in your stack

Three thin, enforcing on-ramps — each one makes a false "done" fail somewhere
that already exists in your workflow. Start where your loop lives:

**Claude Code** — the plugin ships a Stop-hook firewall: if the session's repo
holds a `.loop/` contract that claims `Succeeded` while `loop doctor` says
otherwise, the stop is blocked with the exact doctor issues. No-op without
`.loop/`, fail-open on error, zero config beyond installing the plugin.

**Any Python runtime** — `loop.emit` is a pure-stdlib writer for foreign
orchestrators (LangGraph, or anything that can call four functions):
`open_contract`, `append_iteration`, `append_receipt`, `terminate`. The writer
refuses an evidence-free `Succeeded` at write time. Recipe:
[docs/integrations/langgraph.md](docs/integrations/langgraph.md).

**CI** — one workflow step validates the contract and publishes a scorecard:

```yaml
- uses: SollanSystems/loop-engineer@v0.7.0
  with:
    path: "."
```

`doctor` failure fails the job; the inspect verdict is warn-only unless you set
`fail-under-score`. Pre-commit users: hook id `loop-doctor`. This repo runs the
same action against its own contract — the gate gates its maker.
````

- [ ] **Step 3: Run the doc-coupled tests** (`scripts/test_docs_baseline.py`, `scripts/self_eval.py` → 13/13 — the differentiation-section markers are untouched) and eyeball-render the README.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: Adopt in your stack — uvx funnel, emit recipe, CI action, stop firewall"
```

### Task 13: show-hn.md leads with uvx

**Files:**
- Modify: `roadmap/launch/.loop/artifacts/M5-LAUNCH/show-hn.md`

- [ ] **Step 1:** Read the draft's command block and make `uvx loop-engineer inspect .` the **first command** shown (the before/after-on-their-own-repo moment), adjusting surrounding copy minimally. Keep the title and FCR/RP claims untouched — they are baseline-pinned.
- [ ] **Step 2:** Commit: `git commit -am "docs(launch): show-hn first command is uvx loop-engineer inspect ."`

### Task 14: Docs-claims gate for every new README claim

**Files:**
- Test: `scripts/test_docs_adoption.py`

**Interfaces:**
- Consumes: README/show-hn text from Tasks 12–13 and the artifacts from PR1–PR4.
- Produces: the spec's "every new README claim is gate-backed" acceptance.

- [ ] **Step 1: Write the test (drop the assertions for any PR that was dropped)**

```python
# scripts/test_docs_adoption.py
"""PR5 gate: every 'Adopt in your stack' README claim is backed by a shipped,
wired artifact — the docs cannot advertise an on-ramp that does not exist."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def test_uvx_funnel_claim_is_backed_by_console_script():
    if "uvx loop-engineer" not in README:
        return
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'loop-engineer = "loop.__main__:main"' in pyproject, (
        "README sells `uvx loop-engineer ...` but the package declares no "
        "loop-engineer console script (uvx runs the executable named after the package)"
    )


def test_emit_claim_names_only_real_functions():
    if "loop.emit" not in README:
        return
    import loop.emit as emit

    for name in ("open_contract", "append_iteration", "append_receipt", "terminate"):
        assert name not in README or callable(getattr(emit, name, None)), (
            f"README names loop.emit.{name} but it does not exist"
        )
    assert (REPO_ROOT / "docs" / "integrations" / "langgraph.md").is_file()


def test_stop_firewall_claim_is_backed_by_registered_hook():
    if "Stop-hook" not in README and "stop firewall" not in README.lower():
        return
    manifest = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    commands = [
        h["command"]
        for entry in manifest.get("hooks", {}).get("Stop", [])
        for h in entry.get("hooks", [])
    ]
    hook_files = [c.split("${CLAUDE_PLUGIN_ROOT}/")[-1].split()[0] for c in commands]
    assert any((REPO_ROOT / f).is_file() for f in hook_files), (
        "README sells the Stop-hook firewall but plugin.json registers no existing Stop hook file"
    )


def test_ci_action_claim_is_backed_by_action_and_precommit():
    if "uses: SollanSystems/loop-engineer@" not in README:
        return
    assert (REPO_ROOT / "action.yml").is_file()
    if "loop-doctor" in README:
        assert "id: loop-doctor" in (REPO_ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8")


def test_show_hn_leads_with_the_uvx_funnel():
    show_hn = (
        REPO_ROOT / "roadmap" / "launch" / ".loop" / "artifacts" / "M5-LAUNCH" / "show-hn.md"
    ).read_text(encoding="utf-8")
    first_cmd = next(
        line.strip()
        for line in show_hn.splitlines()
        if line.strip().startswith(("uvx ", "$ uvx", "pip ", "$ pip", "python", "loop ", "git clone"))
    )
    assert first_cmd.lstrip("$ ").startswith("uvx loop-engineer inspect"), (
        f"show-hn's first command is {first_cmd!r}, spec requires `uvx loop-engineer inspect .`"
    )
```

- [ ] **Step 2: Run it** — must pass against the real tree. Then the full suite + `self_eval.py` (13/13).

- [ ] **Step 3: CHANGELOG entry + commit + PR**

```bash
git add scripts/test_docs_adoption.py CHANGELOG.md
git commit -m "test(docs): adoption claims are gate-backed"
git push -u origin docs/adopt-in-your-stack
gh pr create --title "docs: Adopt in your stack + show-hn uvx funnel (PR5)" --body-file <(...)
```

### Task 15: Final pre-launch release (post-merge, human-gated)

- [ ] **Step 1:** After PR5 (and whichever of PR2–PR4 shipped) merges, cut `0.7.0`: version bump, CHANGELOG heading, plugin/marketplace version fields — same file set as Task 5.
- [ ] **Step 2:** Verify README's action pin (`@v0.7.0`) matches the tag being cut; fix if drifted.
- [ ] **Step 3 (HUMAN GATE):** tag `v0.7.0`, push → publish workflow → confirm on PyPI.
- [ ] **Step 4:** End-to-end launch rehearsal from a scratch directory: `uvx loop-engineer@0.7.0 inspect .` (weak verdict on an empty repo), `uvx loop-engineer@0.7.0 scaffold demo && uvx loop-engineer@0.7.0 doctor demo`, and a consumer workflow file using `SollanSystems/loop-engineer@v0.7.0`. This is `M5-LAUNCH`'s first command working for a stranger.

---

## Self-review notes (spec coverage)

- Spec PR1 acceptance ↔ Tasks 3 (wheel+temp-dir test), 4 (publish workflow), 2/full-suite (editable install still green). `uvx loop-engineer` funnel ↔ Task 2 console-script alias + Task 5 verification.
- Spec PR2 acceptance ↔ Task 6 (`test_emit.py`: schema-valid outputs + evidence-free-Succeeded refusal), Task 7 (recipe end-to-end + doctor). LangGraph API verified via Context7 during planning.
- Spec PR3 acceptance ↔ Task 8 fixtures: honest/lying/absent/forced-error (+ livelock guards beyond spec). CLI resolution order ↔ `_cli_command()`.
- Spec PR4 acceptance ↔ Task 10 dogfood job green on own contract; Task 11 consumer-side pre-commit fixture.
- Spec PR5 ↔ Tasks 12–14; launch minimally gated on PR1+PR5 ↔ Tasks 12/14 written to degrade if PR2–PR4 drop.
- Risks: name squat ↔ Task 5 immediately after PR1; hook annoyance ↔ no-op/fail-open/actionable-reason tests; emit-drift ↔ writer-only constraint + no subprocess/orchestration in `emit.py`.
