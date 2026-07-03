"""Doc/scaffolding bindings for ST1:

  * AC5 — the README Measured-baseline literals are SOURCED from
    docs/metrics-baseline.json, not retyped prose: parse them and assert equality
    so a future baseline change can't leave the README stale.
  * P3 — shipped scaffolding must declare the canonical repair-record location
    (.loop/repair/<iteration_id>.json), never the stale .loop/artifacts path the
    metrics tool cannot read.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent


def _readme_metric(readme: str, label: str) -> float:
    m = re.search(rf"\|\s*`{re.escape(label)}`\s*\|\s*\*\*([0-9.]+)\*\*\s*\|", readme)
    assert m, f"no README Measured-baseline row for {label}"
    return float(m.group(1))


def test_readme_baseline_literals_match_committed_scorecard():
    readme = (_REPO / "README.md").read_text(encoding="utf-8")
    baseline = json.loads((_REPO / "docs" / "metrics-baseline.json").read_text(encoding="utf-8"))
    assert _readme_metric(readme, "false-completion-rate") == baseline["false_completion_rate"]
    assert _readme_metric(readme, "repair-productivity") == baseline["repair_productivity"]


def test_scaffolding_uses_canonical_repair_record_path():
    stale = ".loop/artifacts/repair-record.json"
    scanned = [
        _REPO / "templates" / "manifest.yaml.tmpl",
        _REPO / "reference" / "repo-os-contract.md",
        _REPO / "reference" / "prompt-templates.md",
    ]
    offenders = [str(p.relative_to(_REPO)) for p in scanned if stale in p.read_text(encoding="utf-8")]
    assert not offenders, f"stale repair-record path {stale!r} in: {offenders}"
