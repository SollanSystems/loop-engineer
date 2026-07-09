"""Read-only foreign-harness layout mapping (ST4).

Recognizes a run directory laid out by a foreign harness (currently: the
Superpowers spec/plan convention) and maps it onto the same ``LoopPaths``
surface the inspector already consumes. A MAPPER, never a scorer: it points
the existing signals at foreign files and never manufactures credit — a
harness with no holdout gate and no terminal record scores honestly low,
which is the point. Synthesizing gate or verify artifacts here would be
dishonest and is out of scope by design.

Used by ``inspect`` only; ``doctor`` stays unmapped (a foreign dir has no
contract to validate, and saying otherwise would be a false completion).
"""

from __future__ import annotations

from pathlib import Path

from .paths import LoopPaths

_SPECS_DIR = "docs/superpowers/specs"
_PLANS_DIR = "docs/superpowers/plans"
_JOURNALS = (".superpowers/sdd/progress.md", "docs/superpowers/journal.md")


def _newest_md(directory: Path) -> Path | None:
    """Newest markdown file by name — Superpowers files are date-prefixed, so
    lexicographic order is chronological order."""
    if not directory.is_dir():
        return None
    files = sorted(p for p in directory.glob("*.md") if p.is_file())
    return files[-1] if files else None


def detect_foreign_layout(target: str | Path) -> str | None:
    """Name the foreign layout of ``target``, or None.

    A native contract (``.loop/state.json``) always wins — foreign mapping
    never shadows a real repo-OS contract.
    """
    ws = Path(target)
    if (ws / ".loop" / "state.json").is_file():
        return None
    if _newest_md(ws / _SPECS_DIR) or _newest_md(ws / _PLANS_DIR):
        return "superpowers"
    return None


def map_foreign_paths(target: str | Path) -> LoopPaths | None:
    """A ``LoopPaths`` view of a foreign run dir, or None if not foreign."""
    ws = Path(target).resolve()
    if detect_foreign_layout(ws) != "superpowers":
        return None
    spec = _newest_md(ws / _SPECS_DIR)
    plan = _newest_md(ws / _PLANS_DIR)
    journal = next((ws / j for j in _JOURNALS if (ws / j).is_file()), None)
    loop_dir = ws / ".loop"
    return LoopPaths(
        workspace=ws,
        loop_dir=loop_dir,
        manifest=loop_dir / "manifest.yaml",
        state=loop_dir / "state.json",
        tasks=ws / "TASKS.json",
        runlog=journal if journal is not None else ws / "RUNLOG.md",
        terminal=loop_dir / "terminal_state.json",
        spec=spec if spec is not None else ws / "SPEC.md",
        workflow=plan if plan is not None else ws / "WORKFLOW.md",
        contract=ws / "loop-contract.md",
    )
