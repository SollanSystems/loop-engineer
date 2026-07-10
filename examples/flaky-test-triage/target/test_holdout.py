import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jobs import next_jobs


def test_order_is_independent_of_input_order():
    base = [("archive", 2), ("compact", 2), ("backup", 1), ("prune", 3)]
    rng = random.Random(7)
    for _ in range(20):
        shuffled = list(base)
        rng.shuffle(shuffled)
        assert next_jobs(shuffled) == ["prune", "archive", "compact", "backup"]
