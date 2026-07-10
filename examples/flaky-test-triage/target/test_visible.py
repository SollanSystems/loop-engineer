import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jobs import load_jobs, next_jobs


def test_equal_priority_jobs_run_in_stable_order():
    assert next_jobs(load_jobs()) == ["archive", "compact", "backup"]
