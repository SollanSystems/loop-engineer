#!/usr/bin/env python3
"""Seed a minimal doctor-clean, hash-chained workspace and print its chain head.

The CI anchor path (`loop doctor --expect-chain-head`, the action's
`expect-chain-head` input and `chain-head` output) can only be exercised over a
store-backed contract, and every other CI workspace is store-free. This builds
one through the real writer path — store appends materialized into state.json by
`loop.emit`, exactly as `loop.runner.dispatch_once` does — and emits the head the
`anchor-live` job pins.

Run::

    python3 scripts/ci_anchor_probe.py <target-dir>

Exit codes:
  0  workspace seeded; the chain head is on stdout
  1  the seeded workspace is not a doctor-clean chained contract
  2  wrong argument count
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from loop import emit  # noqa: E402
from loop.contract import doctor_report  # noqa: E402
from loop.events import SQLiteEventStore  # noqa: E402
from loop.paths import resolve_loop_paths  # noqa: E402

RUN_ID = "ci-anchor-probe"
ACTOR = "ci_anchor_probe"
TASK_ID = "T1"


class AnchorProbeError(RuntimeError):
    """The seeded workspace is not a doctor-clean chained contract."""


def seed(target: str | Path) -> str:
    """Build the workspace and return the chain head doctor observes over it."""
    emit.open_contract(target)
    store = SQLiteEventStore(resolve_loop_paths(target).loop_dir / "events.db")
    opened = store.append(RUN_ID, "contract_opened", {"workspace": Path(target).name}, actor=ACTOR)
    # A second chained event so the anchor pins a real link, not just a genesis hash.
    linked = store.append(
        RUN_ID, "iteration_appended",
        {"iteration_id": 1, "outcome": "task_passed", "state": "plan", "task_id": TASK_ID},
        actor=ACTOR, causation_id=opened["event_id"], expected_sequence=1,
    )
    emit.append_iteration(target, iteration_id=1, outcome="task_passed", state="plan", task_id=TASK_ID)

    report = doctor_report(target)
    if not report["ok"]:
        raise AnchorProbeError(f"seeded workspace is not doctor-clean: {report['issues']}")
    head = ((report["event_store"].get("chain") or {}).get("head") or {}).get("event_hash")
    if head != linked["event_hash"]:
        raise AnchorProbeError(
            f"doctor reports chain head {head!r}, but the last append recorded {linked['event_hash']!r}"
        )
    return head


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("ci_anchor_probe.py expects exactly one <target-dir>", file=sys.stderr)
        return 2
    try:
        head = seed(argv[0])
    except AnchorProbeError as exc:
        print(f"ci_anchor_probe: {exc}", file=sys.stderr)
        return 1
    print(head)
    return 0


if __name__ == "__main__":
    sys.exit(main())
