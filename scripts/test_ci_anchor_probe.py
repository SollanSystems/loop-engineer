"""Local regression cover for the live CI anchor path (#87).

`loop doctor --expect-chain-head` and the action's `chain-head` output had no
end-to-end coverage because every CI workspace was store-free. These run the
seed helper the way the `anchor-live` job runs it — by path, with no installed
package — so a wiring regression is caught here too, not only in CI.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / "scripts" / "ci_anchor_probe.py"

sys.path.insert(0, str(ROOT))
from loop.__main__ import main  # noqa: E402

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _seed(tmp_path: Path) -> tuple[Path, str]:
    workspace = tmp_path / "anchor-ws"
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, "-B", str(PROBE), str(workspace)],
        cwd=tmp_path, env=env, text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    return workspace, result.stdout.strip()


def test_probe_prints_a_chain_head_when_invoked_by_path(tmp_path):
    workspace, head = _seed(tmp_path)
    assert _HEX64.match(head), head
    assert (workspace / ".loop" / "events.db").is_file()


def test_seeded_workspace_passes_doctor_with_the_printed_anchor(tmp_path):
    workspace, head = _seed(tmp_path)
    assert main(["doctor", "--expect-chain-head", head, str(workspace)]) == 0


def test_seeded_workspace_fails_doctor_with_a_wrong_anchor(tmp_path, capsys):
    workspace, _ = _seed(tmp_path)
    assert main(["doctor", "--expect-chain-head", "0" * 64, str(workspace)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert "chain_anchor_mismatch" in {issue["code"] for issue in report["issues"]}
