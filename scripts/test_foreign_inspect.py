"""ST4/ST5: the foreign-harness inspect adapter is a LAYOUT REGISTRY, not a
scorer change. It maps a foreign spec-driven run dir (Superpowers, Spec Kit,
Agent OS, BMAD, Task Master, CCPM, PRP, OpenSpec, ruflo) onto the LoopPaths
surface the inspector already consumes; the M2/M3-hardened scorer is not
re-litigated. A foreign harness with no holdout gate and no terminal record
scores honestly low — the regression tests pin that no run-recorded credit
appears without an on-disk gate, that every fixture is labeled advisory, and
that doctor does NOT get the mapping (inspect-only)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from loop.foreign import detect_foreign_layout, map_foreign_paths  # noqa: E402

FIXTURE = _REPO / "examples" / "superpowers-run"
NATIVE = _REPO / "examples" / "coverage-repair"

# Every vendored foreign fixture and the layout name it must detect as. Each
# fixture instantiates the SAME fictional csv-dedupe task across nine harness
# layouts, so the scoreboard compares one task against nine on-disk shapes.
FOREIGN_FIXTURES: tuple[tuple[str, str], ...] = (
    ("superpowers-run", "superpowers"),
    ("spec-kit-run", "spec-kit"),
    ("agent-os-run", "agent-os"),
    ("bmad-run", "bmad"),
    ("task-master-run", "task-master"),
    ("ccpm-run", "ccpm"),
    ("prp-run", "prp"),
    ("openspec-run", "openspec"),
    ("ruflo-run", "ruflo"),
)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_detects_superpowers_layout_and_not_native_contracts():
    assert detect_foreign_layout(FIXTURE) == "superpowers"
    assert detect_foreign_layout(NATIVE) is None  # a native contract always wins
    assert detect_foreign_layout(_REPO / "examples" / "naive-loop") is None


def test_mapping_points_at_superpowers_artifacts():
    paths = map_foreign_paths(FIXTURE)
    assert paths is not None
    assert paths.workspace == FIXTURE.resolve()
    assert paths.spec.name == "2026-07-08-csv-dedupe-design.md"
    assert paths.workflow.name == "2026-07-08-csv-dedupe.md"
    assert paths.runlog.name == "progress.md"
    assert map_foreign_paths(NATIVE) is None


@pytest.mark.parametrize("dirname,layout", FOREIGN_FIXTURES)
def test_every_fixture_detects_its_layout(dirname, layout):
    target = _REPO / "examples" / dirname
    assert detect_foreign_layout(target) == layout
    # A registered layout always yields a mapped LoopPaths view.
    assert map_foreign_paths(target) is not None


@pytest.mark.parametrize("dirname,layout", FOREIGN_FIXTURES)
def test_every_fixture_inspects_as_advisory_foreign(dirname, layout):
    inspect_loop = _load("inspect_loop")
    report = inspect_loop.inspect_loop(str(_REPO / "examples" / dirname))
    assert report["foreign_layout"] == layout
    assert report["advisory"] is True
    # honesty: no foreign fixture manufactures held-out invocation credit.
    assert not any("(invoked)" in p for p in report["present"]), report["present"]


@pytest.mark.parametrize("dirname,_layout", FOREIGN_FIXTURES)
def test_inspect_score_is_deterministic(dirname, _layout):
    inspect_loop = _load("inspect_loop")
    target = str(_REPO / "examples" / dirname)
    first = inspect_loop.inspect_loop(target)
    second = inspect_loop.inspect_loop(target)
    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_task_master_tasks_map_to_json_ledger():
    # Task Master is the one layout whose ledger IS genuine JSON, so tasks maps.
    paths = map_foreign_paths(_REPO / "examples" / "task-master-run")
    assert paths is not None
    assert paths.tasks.name == "tasks.json"
    assert paths.tasks.is_file()
    loaded = json.loads(paths.tasks.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)  # parseable JSON, not markdown


def test_markdown_ledger_layouts_keep_native_tasks_default():
    # spec-kit / bmad / openspec ledgers are markdown/YAML, not JSON, so tasks
    # stays the native default and their markdown ledger surfaces via runlog.
    for dirname in ("spec-kit-run", "bmad-run", "openspec-run"):
        paths = map_foreign_paths(_REPO / "examples" / dirname)
        assert paths is not None
        assert paths.tasks.name == "TASKS.json"  # native default, unmapped


def test_inspect_scores_fixture_low_and_labels_it_foreign():
    inspect_loop = _load("inspect_loop")
    report = inspect_loop.inspect_loop(str(FIXTURE))
    assert report["foreign_layout"] == "superpowers"
    assert report["advisory"] is True
    assert report["verdict"] == "weak"
    assert report["score"] < 50
    # honesty regression: NO run-recorded credit without an on-disk gate
    assert not any("(invoked)" in p for p in report["present"]), report["present"]
    assert report["terminal_states_covered"] < 7


def test_repo_root_superpowers_shape_without_journal_does_not_detect(tmp_path):
    # Roadmap follow-up: a spec/plan-only tree (the loop-engineer repo's own
    # shape, minus a journal and minus .loop/state.json) must NOT false-positive
    # as a foreign superpowers run — the journal requirement is what closes it.
    specs = tmp_path / "docs" / "superpowers" / "specs"
    specs.mkdir(parents=True)
    (specs / "2026-07-09-x-design.md").write_text("# x\n", encoding="utf-8")
    plans = tmp_path / "docs" / "superpowers" / "plans"
    plans.mkdir(parents=True)
    (plans / "2026-07-09-x.md").write_text("# x\n", encoding="utf-8")

    assert detect_foreign_layout(tmp_path) is None
    assert map_foreign_paths(tmp_path) is None

    inspect_loop = _load("inspect_loop")
    report = inspect_loop.inspect_loop(str(tmp_path))
    assert "foreign_layout" not in report
    assert "advisory" not in report

    # Adding the journal flips it to a detected foreign run — proves the journal
    # is the discriminating signal, not incidental.
    sdd = tmp_path / ".superpowers" / "sdd"
    sdd.mkdir(parents=True)
    (sdd / "progress.md").write_text("# progress\n", encoding="utf-8")
    assert detect_foreign_layout(tmp_path) == "superpowers"


def test_generic_repo_does_not_detect_any_layout(tmp_path):
    # A plain project tree (README + src, no harness dot-dirs) is not foreign.
    (tmp_path / "README.md").write_text("# project\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")
    assert detect_foreign_layout(tmp_path) is None
    assert map_foreign_paths(tmp_path) is None


def test_native_reports_carry_no_foreign_label():
    inspect_loop = _load("inspect_loop")
    report = inspect_loop.inspect_loop(str(NATIVE))
    assert "foreign_layout" not in report
    assert "advisory" not in report
    assert report["verdict"] == "strong"  # flagship unchanged — scorer untouched


def test_cli_inspect_produces_scored_foreign_report():
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "loop", "inspect", str(FIXTURE)],
        cwd=_REPO, capture_output=True, text=True,
    )
    report = json.loads(proc.stdout)
    assert report["foreign_layout"] == "superpowers"
    assert isinstance(report["score"], int)


def test_doctor_does_not_get_the_mapping():
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "loop", "doctor", str(FIXTURE)],
        cwd=_REPO, capture_output=True, text=True,
    )
    assert proc.returncode != 0  # no .loop contract -> doctor honestly fails
