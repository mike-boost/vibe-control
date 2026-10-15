"""Opt-in real host smoke for Skill Assay (excluded from default gates)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from vibe_control.skill_assay.registry import build_adapter_registry

pytestmark = [
    pytest.mark.real_skill_host,
    pytest.mark.serial,
]


def _hsp_skill() -> Path:
    candidates = [
        Path(os.environ.get("SKILL_ASSAY_SMOKE_SKILL", "")),
        Path.home() / ".agents/skills/high-speed-communication",
        Path.home() / "Documents/repo/ai/ai-manager/skills/high-speed-communication",
    ]
    for path in candidates:
        if path.is_dir() and (path / "SKILL.md").is_file():
            return path
    pytest.skip("HSP skill not found")


@pytest.mark.parametrize("host_id", ["cursor", "github-copilot"])
def test_real_host_doctor_ready(host_id: str) -> None:
    if host_id == "github-copilot":
        try:
            import copilot  # noqa: F401
        except ImportError:
            pytest.skip("github-copilot-sdk not installed")
    if host_id == "cursor":
        import shutil

        if shutil.which("agent") is None:
            pytest.skip("cursor agent CLI not installed")
    registry = build_adapter_registry(include_fake=False)
    result = registry[host_id].doctor()
    assert result.ok is True, result.blockers
    assert result.support_state == "supported"
    assert _hsp_skill().is_dir()
