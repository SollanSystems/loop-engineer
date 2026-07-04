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
        capture_output=True, text=True, timeout=60, env=_cli_env(),  # < manifest's 90s hook timeout, so this dies first
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
