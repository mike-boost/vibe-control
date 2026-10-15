"""TDD: Skill Assay snapshot + path safety (red first)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from vibe_control.skill_assay.errors import SkillAssayError
from vibe_control.skill_assay.snapshot import snapshot_skill


def _write_skill(root: Path, body: str = "# Test Skill\n\nDo X.\n") -> Path:
    skill = root / "my-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(body, encoding="utf-8")
    return skill


def test_snapshot_requires_skill_md(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SkillAssayError) as exc:
        snapshot_skill(empty, dest=tmp_path / "snap")
    assert exc.value.code == "SKILL_ASSAY_SKILL_MD_MISSING"


def test_snapshot_copies_companions_and_hashes(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    (skill / "notes.txt").write_text("hello\n", encoding="utf-8")
    dest = tmp_path / "snap"
    result = snapshot_skill(skill, dest=dest)
    assert (dest / "SKILL.md").is_file()
    assert (dest / "notes.txt").is_file()
    assert result["skill_id"] == "my-skill"
    assert isinstance(result["tree_hash"], str) and len(result["tree_hash"]) == 64
    assert result["file_count"] == 2


def test_snapshot_rejects_out_of_tree_symlink(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    outside = tmp_path / "secret.txt"
    outside.write_text("leak\n", encoding="utf-8")
    link = skill / "escape.txt"
    link.symlink_to(outside)
    with pytest.raises(SkillAssayError) as exc:
        snapshot_skill(skill, dest=tmp_path / "snap")
    assert exc.value.code == "SKILL_ASSAY_UNSAFE_SYMLINK"


def test_snapshot_rejects_path_escape_via_dotdot(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    # Create a nested file that somehow resolves outside via symlink name games.
    nested = skill / "sub"
    nested.mkdir()
    outside = tmp_path / "outside-dir"
    outside.mkdir()
    (outside / "x.txt").write_text("x\n", encoding="utf-8")
    (nested / "out").symlink_to(outside)
    with pytest.raises(SkillAssayError) as exc:
        snapshot_skill(skill, dest=tmp_path / "snap")
    assert exc.value.code == "SKILL_ASSAY_UNSAFE_SYMLINK"


@pytest.mark.skipif(os.name == "nt", reason="unix special files")
def test_snapshot_rejects_non_regular_special_file(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    fifo = skill / "pipe.fifo"
    os.mkfifo(fifo)
    with pytest.raises(SkillAssayError) as exc:
        snapshot_skill(skill, dest=tmp_path / "snap")
    assert exc.value.code == "SKILL_ASSAY_UNSAFE_FILE_TYPE"
