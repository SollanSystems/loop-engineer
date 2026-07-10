"""Read-only foreign-harness layout registry (ST4/ST5).

Recognizes a run directory laid out by a foreign spec-driven harness and maps
its artifacts onto the same ``LoopPaths`` surface the inspector already
consumes. A MAPPER, never a scorer: it points the existing signals at foreign
files and never manufactures credit — a harness with no holdout gate and no
terminal record scores honestly low, which is the point. Synthesizing gate or
verify artifacts here would be dishonest and is out of scope by design.

The registry is an ordered tuple of :class:`_Layout` entries. Each entry pairs
a *detection predicate* (distinctive dot-dir / characteristic nested file, kept
mutually exclusive across layouts and inert on a generic repo) with per-role
*path resolvers* for the four mappable roles — ``spec``, ``workflow`` (the
harness's plan), ``tasks``, and ``runlog``. Any role a layout does not resolve
keeps the native default path unchanged, exactly as the original superpowers
mapper did. ``tasks`` is mapped **only** when the harness's task ledger is
genuine JSON (the inspector parses ``tasks`` as JSON); a markdown/YAML task file
is surfaced through the ``workflow`` or ``runlog`` role instead, decided
per-layout and documented on the entry.

Used by ``inspect`` only; ``doctor`` stays unmapped (a foreign dir has no
contract to validate, and saying otherwise would be a false completion). A
native contract (``.loop/state.json``) always wins over any foreign signature.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from .paths import LoopPaths

Predicate = Callable[[Path], bool]
Resolver = Callable[[Path], "Path | None"]


# --- filesystem helpers ---------------------------------------------------


def _newest(paths: Iterable[Path]) -> Path | None:
    """Newest existing file from ``paths``, chosen by name.

    Foreign harnesses date- or number-prefix their run files/dirs, so
    lexicographic order is chronological order (mirrors the original
    ``_newest_md`` selection).
    """
    files = sorted(p for p in paths if p.is_file())
    return files[-1] if files else None


def _newest_dir(parent: Path) -> Path | None:
    """Newest immediate subdirectory of ``parent`` by name, or None."""
    if not parent.is_dir():
        return None
    dirs = sorted(p for p in parent.iterdir() if p.is_dir())
    return dirs[-1] if dirs else None


def _newest_md(directory: Path) -> Path | None:
    """Newest markdown file in ``directory`` (kept for the superpowers detect)."""
    return _newest(directory.glob("*.md")) if directory.is_dir() else None


# --- resolver factories ---------------------------------------------------


def _fixed(rel: str) -> Resolver:
    """Resolve a file at a fixed workspace-relative path."""
    def resolve(ws: Path) -> Path | None:
        p = ws / rel
        return p if p.is_file() else None
    return resolve


def _first_of(*rels: str) -> Resolver:
    """First of several fixed relative paths that exists as a file."""
    def resolve(ws: Path) -> Path | None:
        for rel in rels:
            p = ws / rel
            if p.is_file():
                return p
        return None
    return resolve


def _preferred_newest(*globs: tuple[str, str]) -> Resolver:
    """Newest match from the first ``(reldir, pattern)`` pair that yields one.

    Ordering the pairs expresses preference (e.g. an archived ``completed/``
    plan before the live one). Patterns may nest a ``/`` for the run-file-in-a
    -dated-subdir shape (``*/proposal.md``).
    """
    def resolve(ws: Path) -> Path | None:
        for reldir, pattern in globs:
            hit = _newest((ws / reldir).glob(pattern))
            if hit is not None:
                return hit
        return None
    return resolve


def _in_newest_subdir(reldir: str, filename: str) -> Resolver:
    """A fixed ``filename`` inside the newest subdirectory of ``reldir``.

    The run-file-in-a-dated/numbered-feature-dir shape (spec-kit's
    ``specs/001-slug/spec.md``, agent-os's ``specs/<HHMM-slug>/shape.md``).
    """
    def resolve(ws: Path) -> Path | None:
        sub = _newest_dir(ws / reldir)
        if sub is None:
            return None
        p = sub / filename
        return p if p.is_file() else None
    return resolve


# --- detection-predicate factories ----------------------------------------


def _dir(rel: str) -> Predicate:
    return lambda ws: (ws / rel).is_dir()


def _file(rel: str) -> Predicate:
    return lambda ws: (ws / rel).is_file()


def _glob(reldir: str, pattern: str) -> Predicate:
    return lambda ws: any((ws / reldir).glob(pattern))


def _has_md(reldir: str) -> Predicate:
    return lambda ws: _newest_md(ws / reldir) is not None


def _any(*preds: Predicate) -> Predicate:
    return lambda ws: any(p(ws) for p in preds)


def _all(*preds: Predicate) -> Predicate:
    return lambda ws: all(p(ws) for p in preds)


# --- the registry ---------------------------------------------------------


@dataclass(frozen=True)
class _Layout:
    """One foreign-harness layout: how to detect it and where its roles live.

    ``spec`` / ``workflow`` / ``tasks`` / ``runlog`` are per-role resolvers;
    ``None`` means the role is unmapped and keeps the native default path. The
    ``note`` records the mapping decision (esp. why ``tasks`` is or is not
    mapped) so the honesty rationale travels with the data.
    """

    name: str
    detect: Predicate
    note: str
    spec: Resolver | None = None
    workflow: Resolver | None = None
    tasks: Resolver | None = None
    runlog: Resolver | None = None


_REGISTRY: tuple[_Layout, ...] = (
    _Layout(
        name="superpowers",
        # Tightened per the roadmap follow-up: a spec/plan alone is not enough
        # (the loop-engineer repo root carries docs/superpowers/{specs,plans}
        # with no journal and must NOT read as a foreign run). Require a journal
        # AND a spec-or-plan.
        detect=_all(
            _any(
                _file(".superpowers/sdd/progress.md"),
                _file("docs/superpowers/journal.md"),
            ),
            _any(_has_md("docs/superpowers/specs"), _has_md("docs/superpowers/plans")),
        ),
        note=(
            "Superpowers SDD layout. tasks unmapped: the plan's checkboxes are "
            "markdown, not a JSON ledger. runlog -> the sdd progress journal."
        ),
        spec=_preferred_newest(("docs/superpowers/specs", "*.md")),
        workflow=_preferred_newest(("docs/superpowers/plans", "*.md")),
        runlog=_first_of(".superpowers/sdd/progress.md", "docs/superpowers/journal.md"),
    ),
    _Layout(
        name="spec-kit",
        # The .specify/ dot-dir is unique to GitHub Spec Kit; pair it with a
        # characteristic install/state file so a bare directory named .specify
        # cannot alone trip it.
        detect=_all(
            _dir(".specify"),
            _any(
                _file(".specify/feature.json"),
                _file(".specify/memory/constitution.md"),
                _file(".specify/templates/spec-template.md"),
            ),
        ),
        note=(
            "Spec Kit. spec/plan/tasks are the specs/<NNN-slug>/ triad. tasks "
            "unmapped: tasks.md is a markdown checkbox ledger, not JSON — it is "
            "the on-disk progress record, so it maps to runlog instead."
        ),
        spec=_in_newest_subdir("specs", "spec.md"),
        workflow=_in_newest_subdir("specs", "plan.md"),
        runlog=_in_newest_subdir("specs", "tasks.md"),
    ),
    _Layout(
        name="agent-os",
        # standards/index.yml under the non-dotted agent-os/ root is the single
        # strongest Agent OS v3 fingerprint (distinguishes v3 from .agent-os/ v1/v2).
        detect=_file("agent-os/standards/index.yml"),
        note=(
            "Agent OS v3. spec -> shape.md, workflow -> plan.md inside the "
            "minute-stamped spec dir. tasks unmapped: the plan doubles as the "
            "task list (markdown). runlog unmapped: v3 ships no on-disk journal."
        ),
        spec=_in_newest_subdir("agent-os/specs", "shape.md"),
        workflow=_in_newest_subdir("agent-os/specs", "plan.md"),
    ),
    _Layout(
        name="bmad",
        detect=_any(
            _file("_bmad-output/implementation-artifacts/sprint-status.yaml"),
            _file("_bmad/bmm/config.yaml"),
        ),
        note=(
            "BMAD Method. spec -> planning prd.md, workflow -> epics.md, runlog "
            "-> the epic retrospective journal. tasks unmapped: sprint-status "
            "is the ledger but it is YAML, not JSON."
        ),
        spec=_fixed("_bmad-output/planning-artifacts/prd.md"),
        workflow=_fixed("_bmad-output/planning-artifacts/epics.md"),
        runlog=_preferred_newest(
            ("_bmad-output/implementation-artifacts", "epic-*-retro-*.md")
        ),
    ),
    _Layout(
        name="task-master",
        detect=_file(".taskmaster/tasks/tasks.json"),
        note=(
            "Task Master. The one layout whose ledger IS genuine JSON, so tasks "
            "-> tasks.json (parsed). runlog -> tasks.json too (the run journal "
            "is appended into subtasks[].details). spec -> the PRD; workflow -> "
            "the newest human-readable per-task file."
        ),
        spec=_fixed(".taskmaster/docs/prd.txt"),
        workflow=_preferred_newest((".taskmaster/tasks", "task_*.txt")),
        tasks=_fixed(".taskmaster/tasks/tasks.json"),
        runlog=_fixed(".taskmaster/tasks/tasks.json"),
    ),
    _Layout(
        name="ccpm",
        # .claude/epics/<slug>/epic.md or .claude/prds/*.md — CCPM's own subdirs
        # under the shared .claude/ root (distinct from prp's PRPs/ and ruflo's
        # checkpoints/, so no cross-fire on a plain .claude/ dir).
        detect=_any(_glob(".claude/epics", "*/epic.md"), _glob(".claude/prds", "*.md")),
        note=(
            "CCPM. spec -> the PRD, workflow -> the technical epic.md, runlog -> "
            "the per-issue progress journal. tasks unmapped: per-task files are "
            "markdown (renamed to the GitHub issue number), not JSON."
        ),
        spec=_preferred_newest((".claude/prds", "*.md")),
        workflow=_preferred_newest((".claude/epics", "*/epic.md")),
        runlog=_preferred_newest((".claude/epics", "*/updates/*/progress.md")),
    ),
    _Layout(
        name="prp",
        # Capitalized .claude/PRPs/ (plans|prds) or the loop FSM state file —
        # 'prds' vs 'PRPs' differ by a real letter (d vs p) so ccpm and prp stay
        # exclusive even on a case-insensitive filesystem.
        detect=_any(
            _dir(".claude/PRPs/plans"),
            _dir(".claude/PRPs/prds"),
            _file(".claude/prp-loop.state.json"),
        ),
        note=(
            "PRPs-agentic-eng. spec -> the .prd.md, workflow -> the .plan.md "
            "(prefer plans/completed/), runlog -> the implementation report. "
            "tasks unmapped: the task ledger is a markdown checkbox list "
            "embedded in the plan file, not a separate JSON ledger."
        ),
        spec=_preferred_newest((".claude/PRPs/prds", "*.prd.md")),
        workflow=_preferred_newest(
            (".claude/PRPs/plans/completed", "*.plan.md"),
            (".claude/PRPs/plans", "*.plan.md"),
        ),
        runlog=_preferred_newest((".claude/PRPs/reports", "*-report.md")),
    ),
    _Layout(
        name="openspec",
        detect=_any(
            _file("openspec/config.yaml"),
            _dir("openspec/changes"),
            _dir("openspec/specs"),
        ),
        note=(
            "OpenSpec. spec -> the living capability spec, workflow -> the "
            "change proposal, runlog -> the change's tasks.md (its checkbox "
            "progress is the only durable on-disk record). tasks unmapped: "
            "markdown checkbox ledger, not JSON."
        ),
        spec=_preferred_newest(("openspec/specs", "*/spec.md")),
        workflow=_preferred_newest(("openspec/changes/archive", "*/proposal.md")),
        runlog=_preferred_newest(("openspec/changes/archive", "*/tasks.md")),
    ),
    _Layout(
        name="ruflo",
        # ruflo (claude-flow v3) runtime dirs. .claude-flow/ and .hive-mind/ are
        # both ruflo-specific; its .claude/ only holds checkpoints/ (no epics/PRPs).
        detect=_any(_dir(".claude-flow"), _dir(".hive-mind")),
        note=(
            "ruflo / claude-flow v3. spec -> the on-disk swarm objective prompt, "
            "runlog -> the checkpoint session summary. workflow + tasks unmapped: "
            "plan and task ledger are SQLite-backed (memory.db / hive.db), not "
            "on-disk files this mapper can point a text signal at."
        ),
        spec=_preferred_newest((".hive-mind/sessions", "hive-mind-prompt-*.txt")),
        runlog=_preferred_newest((".claude/checkpoints", "summary-session-*.md")),
    ),
)


def _find_layout(ws: Path) -> _Layout | None:
    for layout in _REGISTRY:
        if layout.detect(ws):
            return layout
    return None


def detect_foreign_layout(target: str | Path) -> str | None:
    """Name the foreign layout of ``target``, or None.

    A native contract (``.loop/state.json``) always wins — foreign mapping
    never shadows a real repo-OS contract.
    """
    ws = Path(target)
    if (ws / ".loop" / "state.json").is_file():
        return None
    layout = _find_layout(ws)
    return layout.name if layout is not None else None


def map_foreign_paths(target: str | Path) -> LoopPaths | None:
    """A ``LoopPaths`` view of a foreign run dir, or None if not foreign.

    The four mappable roles (spec / workflow / tasks / runlog) are pointed at
    the recognized layout's artifacts when its resolvers find them; every other
    role — and any role the layout leaves unmapped or that resolves to nothing —
    keeps the native default path.
    """
    ws = Path(target).resolve()
    if (ws / ".loop" / "state.json").is_file():
        return None
    layout = _find_layout(ws)
    if layout is None:
        return None

    loop_dir = ws / ".loop"

    def _resolved(resolver: Resolver | None, default: Path) -> Path:
        if resolver is None:
            return default
        hit = resolver(ws)
        return hit if hit is not None else default

    return LoopPaths(
        workspace=ws,
        loop_dir=loop_dir,
        manifest=loop_dir / "manifest.yaml",
        state=loop_dir / "state.json",
        tasks=_resolved(layout.tasks, ws / "TASKS.json"),
        runlog=_resolved(layout.runlog, ws / "RUNLOG.md"),
        terminal=loop_dir / "terminal_state.json",
        spec=_resolved(layout.spec, ws / "SPEC.md"),
        workflow=_resolved(layout.workflow, ws / "WORKFLOW.md"),
        contract=ws / "loop-contract.md",
    )
