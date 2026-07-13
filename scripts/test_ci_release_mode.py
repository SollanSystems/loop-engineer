"""S2 CI release-mode wiring contract."""

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


def _workflow() -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))


def _step(name_fragment: str) -> dict:
    for step in _workflow()["jobs"]["gates"]["steps"]:
        if name_fragment.lower() in str(step.get("name", "")).lower():
            return step
    raise AssertionError(f"no gates step whose name contains {name_fragment!r}")


def test_quickstart_smoke_test_uses_release_mode_only_for_doctor():
    run = _step("Quickstart smoke test")["run"]
    assert "loop doctor --mode release examples/coverage-repair" in run
    assert "loop inspect --mode" not in run
    assert "loop inspect examples/coverage-repair" in run
