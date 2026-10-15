"""Readonly implementation-next envelope (shared by CLI and Gateway)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vibe_control.json_envelope import next_action, success_envelope
from vibe_control.task.projection import next_actionable_selection


def build_implementation_next(
    *,
    repo_root: Path,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Dogfood next selection from roadmap-state (never invents Phase 13)."""
    selection = next_actionable_selection(repo_root=repo_root)
    no_next = bool(selection.get("no_actionable_next_task"))
    return success_envelope(
        command="vibe implementation next",
        project_id=project_id,
        mode="readonly",
        data={
            **selection,
            "no_actionable_next_task": no_next,
            "do_not_invent_phase13": True,
            "source": "docs/project/vibe-control-roadmap-state.md",
        },
        warnings=(["no_actionable_next_task"] if no_next else []),
        next_actions=[
            next_action(
                code="NO_ACTIONABLE_NEXT_TASK",
                command="cat docs/project/vibe-control-roadmap-state.md",
                mutation=False,
                reason="Roadmap-state has no actionable next; do not invent Phase 13",
            )
        ]
        if no_next
        else [
            next_action(
                code="IMPLEMENTATION_PROMPT",
                command=(
                    "vibe implementation prompt --task "
                    f"{selection.get('next_actionable_task')} --json"
                ),
                mutation=False,
                reason="Generate readonly prompt for next actionable task",
            )
        ],
    )
