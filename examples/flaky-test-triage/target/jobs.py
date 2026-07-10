"""Toy job scheduler: choose the next jobs to run, highest priority first."""


def load_jobs():
    """Job records as an unordered set — insertion order is not meaningful."""
    return {("archive", 2), ("compact", 2), ("backup", 1)}


def next_jobs(jobs):
    """Job names ordered by priority (highest first), ties broken by name.

    The T1 repair: the sort key used to be priority alone, which left the
    order of equal-priority jobs to set-iteration order — stable within one
    process, different across PYTHONHASHSEED values. The (priority, name)
    key makes the order a function of the data, not the interpreter state.
    """
    return [name for name, _prio in sorted(jobs, key=lambda j: (-j[1], j[0]))]
