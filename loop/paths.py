from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class LoopPaths:
    """Resolved filesystem paths for one loop contract instance."""

    workspace: Path
    loop_dir: Path
    manifest: Path
    state: Path
    tasks: Path
    runlog: Path
    terminal: Path

    def to_json(self) -> dict[str, str]:
        return {k: str(v) for k, v in asdict(self).items()}


def _workspace_from(target: Path) -> Path:
    target = target.resolve()
    if target.name == ".loop":
        return target.parent
    if (target / ".loop").is_dir():
        return target
    if (target / "state.json").is_file() and target.parent.name != ".loop":
        return target.parent
    return target


def _first_existing(*paths: Path) -> Path:
    for p in paths:
        if p.exists():
            return p
    return paths[0]


def resolve_loop_paths(target: str | Path) -> LoopPaths:
    """Resolve repo-OS contract paths from either workspace root or `.loop/`.

    Canonical layout keeps RUNLOG.md at workspace root and machine state under
    `.loop/`. The resolver accepts the historical `.loop/RUNLOG.md` fallback so
    old test fixtures and partially migrated loops still produce actionable
    reports instead of tracebacks.
    """

    workspace = _workspace_from(Path(target))
    loop_dir = workspace / ".loop"
    return LoopPaths(
        workspace=workspace,
        loop_dir=loop_dir,
        manifest=_first_existing(loop_dir / "manifest.yaml", workspace / "manifest.yaml"),
        state=loop_dir / "state.json",
        tasks=workspace / "TASKS.json",
        runlog=_first_existing(workspace / "RUNLOG.md", loop_dir / "RUNLOG.md"),
        terminal=_first_existing(loop_dir / "terminal_state.json", workspace / "terminal_state.json"),
    )
