"""Adapter registry for Skill Assay."""

from __future__ import annotations

from vibe_control.skill_assay.adapters import HostAdapter
from vibe_control.skill_assay.adapters.cursor import CursorHostAdapter
from vibe_control.skill_assay.adapters.fake import FakeHostAdapter
from vibe_control.skill_assay.adapters.github_copilot import GitHubCopilotHostAdapter


def build_adapter_registry(*, include_fake: bool = True) -> dict[str, HostAdapter]:
    registry: dict[str, HostAdapter] = {
        "cursor": CursorHostAdapter(),
        "github-copilot": GitHubCopilotHostAdapter(),
    }
    if include_fake:
        registry["fake"] = FakeHostAdapter()
    return registry
