"""Bundle-first resource resolution (S0).

A built wheel carries schemas/, templates/, and the CLI-needed tool scripts as
package data under loop/_bundle/ (see [tool.hatch.build.targets.wheel.force-include]
in pyproject.toml). An editable install / repo checkout has no _bundle, so each
resolver falls back to the historical repo-relative layout. Wheels install as
real directories, so Traversable -> Path is safe here.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

_REPO_FALLBACKS = {"schemas": "schemas", "templates": "templates", "tools": "scripts"}


def _bundle_root() -> Path | None:
    try:
        return Path(str(resources.files("loop") / "_bundle"))
    except Exception:
        return None


def _data_dir(kind: str) -> Path:
    root = _bundle_root()
    if root is not None:
        bundled = root / kind
        if bundled.is_dir():
            return bundled
    return Path(__file__).resolve().parent.parent / _REPO_FALLBACKS[kind]


def schemas_dir() -> Path:
    return _data_dir("schemas")


def templates_dir() -> Path:
    return _data_dir("templates")


def tools_dir() -> Path:
    return _data_dir("tools")
