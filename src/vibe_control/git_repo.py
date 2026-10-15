"""Lightweight git repository detection helpers."""

from __future__ import annotations

from pathlib import Path


def find_git_root(start: Path | None = None) -> Path | None:
    """Walk parents looking for a `.git` directory. Returns None if not found."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def is_git_repo(path: Path | None = None) -> bool:
    return find_git_root(path) is not None
