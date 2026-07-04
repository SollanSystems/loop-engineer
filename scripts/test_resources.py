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
