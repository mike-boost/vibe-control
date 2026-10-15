"""Parse and load vibe-control-roadmap-state.md (current actionable SSOT)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

DEFAULT_ROADMAP_STATE_ID = "vibe_control_roadmap_state"
DEFAULT_ROADMAP_STATE_PATH = "docs/project/vibe-control-roadmap-state.md"


class RoadmapStateError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _extract_yaml_block(text: str) -> dict[str, Any]:
    match = re.search(r"```yaml\n(.*?)```", text, flags=re.DOTALL)
    if not match:
        raise RoadmapStateError(
            "ROADMAP_STATE_YAML_MISSING",
            "roadmap-state SSOT must contain a fenced ```yaml``` block",
        )
    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict):
        raise RoadmapStateError(
            "ROADMAP_STATE_YAML_INVALID",
            "roadmap-state yaml block must be a mapping",
        )
    return data


def load_roadmap_state(repo_root: Path, *, rel_path: str = DEFAULT_ROADMAP_STATE_PATH) -> dict[str, Any]:
    path = repo_root / rel_path
    if not path.is_file():
        raise RoadmapStateError(
            "ROADMAP_STATE_MISSING",
            f"roadmap-state file not found: {rel_path}",
            {"path": rel_path},
        )
    data = _extract_yaml_block(path.read_text(encoding="utf-8"))
    anchors = data.get("anchors")
    if not isinstance(anchors, list) or not anchors:
        raise RoadmapStateError(
            "ROADMAP_STATE_ANCHORS_MISSING",
            "roadmap-state yaml must include a non-empty anchors list",
        )
    normalized: list[dict[str, Any]] = []
    for item in anchors:
        if not isinstance(item, dict):
            continue
        anchor = str(item.get("ssot_anchor") or "").strip()
        if not anchor:
            continue
        actionable = bool(item.get("actionable"))
        phase_state = str(item.get("phase_state") or ("actionable" if actionable else "completed"))
        normalized.append(
            {
                "ssot_anchor": anchor,
                "task_kind": str(item.get("task_kind") or "implementation_task"),
                "title": str(item.get("title") or anchor),
                "phase_state": phase_state,
                "actionable": actionable,
                "design_only": bool(item.get("design_only")),
                "completed_scope": list(item.get("completed_scope") or []),
            }
        )
    if not normalized:
        raise RoadmapStateError(
            "ROADMAP_STATE_ANCHORS_EMPTY",
            "roadmap-state anchors list produced no usable entries",
        )
    next_task = data.get("next_actionable_task")
    if next_task is not None:
        next_task = str(next_task).strip() or None
    baseline = data.get("current_baseline")
    return {
        "roadmap_state_version": data.get("roadmap_state_version"),
        "next_actionable_task": next_task,
        "no_actionable_next_task": bool(
            data.get("no_actionable_next_task", next_task is None)
        ),
        "current_baseline": dict(baseline) if isinstance(baseline, dict) else None,
        "rules": dict(data.get("rules") or {}),
        "anchors": normalized,
        "path": rel_path,
        "ssot_id": DEFAULT_ROADMAP_STATE_ID,
    }


def select_next_actionable_task(state: dict[str, Any]) -> dict[str, Any]:
    """Return next actionable selection from roadmap-state (never invents phases)."""
    explicit = state.get("next_actionable_task")
    actionable = [a for a in state.get("anchors") or [] if a.get("actionable")]
    if explicit:
        match = next((a for a in actionable if a.get("ssot_anchor") == explicit), None)
        if match is None:
            return {
                "no_actionable_next_task": True,
                "next_actionable_task": None,
                "reason": "explicit_next_not_actionable_or_missing",
                "requested": explicit,
            }
        return {
            "no_actionable_next_task": False,
            "next_actionable_task": match["ssot_anchor"],
            "anchor": match,
        }
    if not actionable:
        return {
            "no_actionable_next_task": True,
            "next_actionable_task": None,
            "reason": "no_actionable_anchors",
        }
    # Deterministic: first actionable anchor in file order (not invented).
    first = actionable[0]
    return {
        "no_actionable_next_task": False,
        "next_actionable_task": first["ssot_anchor"],
        "anchor": first,
        "reason": "first_actionable_in_roadmap_state",
    }
