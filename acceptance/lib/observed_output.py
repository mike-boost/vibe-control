"""Shared acceptance observed-output routing (no tracked overwrite by default)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


UPDATE_ENV = "UPDATE_ACCEPTANCE_OBSERVED"
LOCAL_ENV = "VIBE_ACCEPTANCE_LOCAL"


def update_tracked_observed_enabled() -> bool:
    return os.environ.get(UPDATE_ENV, "").strip() in {"1", "true", "yes"}


def acceptance_local_mode() -> bool:
    """When set, acceptance runners skip real NotebookLM / provider network calls."""
    return os.environ.get(LOCAL_ENV, "").strip() in {"1", "true", "yes"}


def resolve_observed_dir(phase_dir: Path) -> Path:
    """Return output dir for acceptance evidence.

    Default: ``observed-runtime/`` (gitignored), never tracked ``observed/``.
    Opt-in: ``UPDATE_ACCEPTANCE_OBSERVED=1`` writes tracked ``observed/``.
    """
    phase_dir = Path(phase_dir)
    if update_tracked_observed_enabled():
        return phase_dir / "observed"
    return phase_dir / "observed-runtime"


def save_observed(phase_dir: Path, name: str, payload: dict[str, Any] | list[Any] | str) -> Path:
    out_dir = resolve_observed_dir(phase_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    if isinstance(payload, str):
        text = payload if payload.endswith("\n") else payload + "\n"
    else:
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def tracked_observed_path(phase_dir: Path, name: str) -> Path:
    return Path(phase_dir) / "observed" / name
