"""Content contract tests for packaged thin skills."""

from __future__ import annotations

from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[1] / "src" / "vibe_control" / "skills"


def test_vibe_knowledge_skill_commands_and_forbids():
    text = (SKILLS_ROOT / "vibe-knowledge" / "SKILL.md").read_text(encoding="utf-8")
    assert "vibe knowledge inventory" in text
    assert "vibe knowledge status" in text
    assert "vibe knowledge query" in text
    assert "vibe knowledge doctor" in text
    assert "vibe knowledge init-preview" in text
    assert "Do not call raw NotebookLM add/delete" in text
    assert "sync --apply" in text
    assert "Auto-run only when" in text or "mutation: false" in text


def test_vibe_implementation_skill_forbids_and_fallback():
    text = (SKILLS_ROOT / "vibe-implementation" / "SKILL.md").read_text(encoding="utf-8")
    assert "GitHub Issues" in text
    assert "GitHub Projects" in text
    assert "Jira" in text
    assert "prompt-only fallback" in text
    assert "vibe task doctor" in text
    assert "vibe task init-preview" in text
    assert ".beads" in text
    assert "Phase 11" in text
