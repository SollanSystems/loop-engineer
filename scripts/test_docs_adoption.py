# scripts/test_docs_adoption.py
"""PR5 gate: every 'Adopt in your stack' README claim is backed by a shipped,
wired artifact — the docs cannot advertise an on-ramp that does not exist."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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
    # roadmap/ is gitignored — show-hn.md exists locally but is absent in a fresh
    # CI checkout, so guard on existence the way the wheel/recipe tests env-guard.
    show_hn_path = (
        REPO_ROOT / "roadmap" / "launch" / ".loop" / "artifacts" / "M5-LAUNCH" / "show-hn.md"
    )
    if not show_hn_path.is_file():
        pytest.skip("show-hn.md is a gitignored launch draft — absent in fresh checkouts")
    show_hn = show_hn_path.read_text(encoding="utf-8")
    first_cmd = next(
        line.strip()
        for line in show_hn.splitlines()
        if line.strip().startswith(("uvx ", "$ uvx", "pip ", "$ pip", "python", "loop ", "git clone"))
    )
    assert first_cmd.lstrip("$ ").startswith("uvx loop-engineer inspect"), (
        f"show-hn's first command is {first_cmd!r}, spec requires `uvx loop-engineer inspect .`"
    )
