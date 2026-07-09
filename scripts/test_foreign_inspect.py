"""ST4: the foreign-harness inspect adapter is a LAYOUT MAPPER, not a scorer
change. It maps a Superpowers-style run dir onto the LoopPaths surface the
inspector already consumes; the M2/M3-hardened scorer is not re-litigated. A
foreign harness with no holdout gate and no terminal record scores honestly
low — the regression tests pin that no run-recorded credit appears without an
on-disk gate, and that doctor does NOT get the mapping (inspect-only)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from loop.foreign import detect_foreign_layout, map_foreign_paths  # noqa: E402

FIXTURE = _REPO / "examples" / "superpowers-run"
NATIVE = _REPO / "examples" / "coverage-repair"


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
