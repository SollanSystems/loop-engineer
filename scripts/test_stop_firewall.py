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
    proc = _run_hook(_payload(_lying_workspace(tmp_path)), extra_env={"TMPDIR": str(tmp_path)})
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["decision"] == "block"
    assert "contradictory_terminal" in out["reason"]
    assert "Succeeded" in out["reason"]


def test_blocks_at_most_once_per_session(tmp_path):
    ws = _lying_workspace(tmp_path)
    payload = _payload(ws)
    extra_env = {"TMPDIR": str(tmp_path)}  # shared across both calls: the sentinel must persist between them
    first = _run_hook(payload, extra_env=extra_env)
    assert json.loads(first.stdout)["decision"] == "block"
    second = _run_hook(payload, extra_env=extra_env)  # same session_id, same issues
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


def test_doctor_garbage_output_fails_open(tmp_path):
    """Forced-error fixture: a resolvable loop CLI that prints non-JSON to stdout."""
    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir()
    fake_loop = fake_bin / "loop"
    fake_loop.write_text('#!/bin/sh\necho "not json"\nexit 0\n', encoding="utf-8")
    fake_loop.chmod(0o755)
    proc = _run_hook(
        _payload(_lying_workspace(tmp_path)),
        extra_env={"PATH": f"{fake_bin}:/usr/bin:/bin"},  # fake `loop` wins shutil.which() over the real one
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_hook_is_registered_in_plugin_manifest():
    manifest = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    stop_entries = manifest["hooks"]["Stop"]
    commands = [h["command"] for entry in stop_entries for h in entry["hooks"]]
    assert any("stop_firewall.py" in c and "${CLAUDE_PLUGIN_ROOT}" in c for c in commands)
