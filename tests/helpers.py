"""Shared fixture helpers for vibe-control tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from vibe_control.config import ControlConfig


def write_control_yaml(root: Path, raw: dict[str, Any] | None = None) -> Path:
    data = raw if raw is not None else minimal_config_dict()
    config_dir = root / ".vibe"
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "control.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def minimal_config_dict(
    *,
    max_sources: int = 100,
    warn_sources: int = 80,
    include_extra: list[str] | None = None,
    exclude_globs: list[str] | None = None,
    registry: str = "docs/project/spec-registry.yml",
    enable_knowledge: bool = True,
    enable_task: bool = True,
) -> dict[str, Any]:
    """Minimal control.yaml for tests that exercise knowledge/task behavior.

    Defaults enable knowledge+task because Capability Profile is default-disabled
    in product templates; tests that need the disabled profile must pass
    ``enable_knowledge=False`` / ``enable_task=False``.
    """
    return {
        "project": {"id": "migration-harness", "name": "Migration-Harness"},
        "components": {
            "knowledge": {"enabled": enable_knowledge},
            "task": {"enabled": enable_task},
            "sdd": {"enabled": False},
            "tdd": {"enabled": False},
        },
        "knowledge": {
            "provider": "notebooklm",
            "fallback_provider": "repo",
            "max_sources": max_sources,
            "warn_sources": warn_sources,
            "authoritative_statuses": ["active"],
            "include_extra": include_extra or [],
            "exclude_globs": exclude_globs
            if exclude_globs is not None
            else [
                "docs/investigation/**",
                "docs/program/plans/**",
                "docs/phases/**/plans/**",
                "docs/superpowers/plans/**",
                "docs/dashboard/**",
                "**/archive/**",
            ],
            "source_title_template": "[vibe:{project_id}:{doc_id}] {title}",
        },
        "specs": {
            "registry": registry,
            "required_fields": ["id", "status", "path"],
            "require_commit_push_for_ssot": True,
        },
        "tasks": {"provider": "beads", "plan_to_tasks": True, "checkpoint_required": True},
    }


def control_config_from_dict(raw: dict[str, Any], path: Path | None = None) -> ControlConfig:
    return ControlConfig(
        raw=raw,
        path=path or Path(".vibe/control.yaml"),
        project_id=str(raw["project"]["id"]),
        project_name=raw["project"].get("name"),
        knowledge=raw["knowledge"],
        specs=raw["specs"],
        tasks=raw["tasks"],
    )


def write_registry(root: Path, entries: list[dict[str, Any]], relative: str = "docs/project/spec-registry.yml") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(entries), encoding="utf-8")
    return path


def write_doc(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


ACTIONABLE_ROADMAP_STATE_MD = """# Roadmap State (test fixture)

```yaml
roadmap_state_version: 1
next_actionable_task: roadmap.phase11b.live_apply
no_actionable_next_task: false
anchors:
  - ssot_anchor: roadmap.phase11a
    task_kind: implementation_phase
    title: "Phase 11A"
    phase_state: completed
    actionable: false
  - ssot_anchor: roadmap.phase11b
    task_kind: implementation_phase
    title: "Phase 11B shell"
    phase_state: completed
    actionable: false
  - ssot_anchor: roadmap.phase11b.live_apply
    task_kind: implementation_task
    title: "Phase 11B live apply"
    phase_state: actionable
    actionable: true
  - ssot_anchor: roadmap.phase11b.post_create_verify
    task_kind: implementation_task
    title: "Phase 11B post create verify"
    phase_state: actionable
    actionable: true
  - ssot_anchor: roadmap.phase11b.update_path_validation
    task_kind: implementation_task
    title: "Phase 11B update path"
    phase_state: actionable
    actionable: true
  - ssot_anchor: roadmap.phase11b.provider_closeout
    task_kind: implementation_task
    title: "Phase 11B provider closeout"
    phase_state: actionable
    actionable: true
  - ssot_anchor: roadmap.phase12
    task_kind: implementation_phase
    title: "Phase 12"
    phase_state: pending
    actionable: true
```
"""


def write_actionable_roadmap_state(root: Path) -> Path:
    """Legacy-style actionable catalog for apply/projection unit tests."""
    return write_doc(root, "docs/project/vibe-control-roadmap-state.md", ACTIONABLE_ROADMAP_STATE_MD)
