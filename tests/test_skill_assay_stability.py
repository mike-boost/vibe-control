"""TDD: Skill Assay stability / comparison (red first)."""

from __future__ import annotations

from vibe_control.skill_assay.comparison import compute_stability


def test_stability_all_agree() -> None:
    runs = [
        {"fields": {"thesis": "a", "steps": ["1"]}},
        {"fields": {"thesis": "a", "steps": ["1"]}},
        {"fields": {"thesis": "a", "steps": ["1"]}},
    ]
    result = compute_stability(runs)
    assert result["stable_fields"] == ["steps", "thesis"]
    assert result["unstable_fields"] == []
    assert result["absent_fields"] == []


def test_stability_marks_absent_and_unstable() -> None:
    runs = [
        {"fields": {"thesis": "a", "evidence_paths": ["/a"]}},
        {"fields": {"thesis": "a"}},
        {"fields": {"thesis": "b"}},
    ]
    result = compute_stability(runs)
    assert "thesis" in result["unstable_fields"]
    assert "evidence_paths" in result["unstable_fields"]
    assert result["stable_fields"] == []


def test_stability_absent_when_missing_everywhere() -> None:
    runs = [
        {"fields": {"thesis": "a"}},
        {"fields": {"thesis": "a"}},
        {"fields": {"thesis": "a"}},
    ]
    result = compute_stability(runs, expected_fields=["thesis", "evidence_paths"])
    assert "evidence_paths" in result["absent_fields"]
    assert "thesis" in result["stable_fields"]
