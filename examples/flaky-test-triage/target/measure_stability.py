"""Deterministic flakiness probe: run the visible suite under 5 fixed
PYTHONHASHSEED values; the score is the passing fraction. Before the T1
repair the tie order tracked set-iteration order, so some seeds failed
(committed red bundle: score 0.6); after it, 5/5 pass every time."""

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEEDS = ("0", "1", "2", "3", "4")


def main() -> int:
    passed = 0
    for seed in SEEDS:
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run(
            [sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
             str(HERE / "test_visible.py")],
            env=env, capture_output=True, text=True, cwd=HERE,
        )
        passed += proc.returncode == 0
    score = passed / len(SEEDS)
    print(json.dumps({"seeds": len(SEEDS), "passed": passed, "score": score}))
    return 0 if passed == len(SEEDS) else 1


if __name__ == "__main__":
    sys.exit(main())
