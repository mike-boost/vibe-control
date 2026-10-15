"""Secure skill directory snapshot for Skill Assay."""

from __future__ import annotations

import hashlib
import stat
from pathlib import Path
from typing import Any

from vibe_control.skill_assay.errors import SkillAssayError


def snapshot_skill(skill_dir: Path, *, dest: Path) -> dict[str, Any]:
    src = Path(skill_dir).resolve()
    if not src.is_dir():
        raise SkillAssayError(
            "SKILL_ASSAY_SKILL_DIR_INVALID",
            f"skill path is not a directory: {skill_dir}",
            {"path": str(skill_dir)},
        )
    skill_md = src / "SKILL.md"
    if not skill_md.is_file():
        raise SkillAssayError(
            "SKILL_ASSAY_SKILL_MD_MISSING",
            "skill directory must contain SKILL.md",
            {"path": str(src)},
        )

    dest = Path(dest)
    if dest.exists():
        raise SkillAssayError(
            "SKILL_ASSAY_SNAPSHOT_EXISTS",
            f"snapshot destination already exists: {dest}",
            {"dest": str(dest)},
        )
    dest.mkdir(parents=True)

    hasher = hashlib.sha256()
    file_count = 0
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        # Skip destination if somehow nested (should not happen with resolved paths).
        if path.is_symlink():
            target = path.resolve()
            try:
                target.relative_to(src)
            except ValueError as exc:
                raise SkillAssayError(
                    "SKILL_ASSAY_UNSAFE_SYMLINK",
                    f"symlink escapes skill directory: {rel}",
                    {"path": rel.as_posix(), "target": str(target)},
                ) from exc
            # Symlink to a directory outside is already rejected; inside-dir
            # directory symlinks that expand outside via resolve are also caught.
            if not target.is_file() and not target.is_dir():
                raise SkillAssayError(
                    "SKILL_ASSAY_UNSAFE_FILE_TYPE",
                    f"symlink target is not a regular file/dir: {rel}",
                    {"path": rel.as_posix()},
                )
            # Refuse directory symlinks entirely (expand risk / duplicate trees).
            if target.is_dir():
                raise SkillAssayError(
                    "SKILL_ASSAY_UNSAFE_SYMLINK",
                    f"directory symlink not allowed in skill snapshot: {rel}",
                    {"path": rel.as_posix()},
                )
            # Copy link target content as a regular file (dereferenced, still inside).
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            data = target.read_bytes()
            out.write_bytes(data)
            hasher.update(rel.as_posix().encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(data)
            file_count += 1
            continue

        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            (dest / rel).mkdir(parents=True, exist_ok=True)
            continue
        if not stat.S_ISREG(mode):
            raise SkillAssayError(
                "SKILL_ASSAY_UNSAFE_FILE_TYPE",
                f"non-regular file not allowed in skill snapshot: {rel}",
                {"path": rel.as_posix()},
            )
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        data = path.read_bytes()
        out.write_bytes(data)
        hasher.update(rel.as_posix().encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(data)
        file_count += 1

    # Ensure SKILL.md made it.
    if not (dest / "SKILL.md").is_file():
        raise SkillAssayError(
            "SKILL_ASSAY_SKILL_MD_MISSING",
            "snapshot missing SKILL.md after copy",
            {"dest": str(dest)},
        )

    git_meta = _git_meta(src)
    return {
        "skill_id": src.name,
        "source_path": src.as_posix(),
        "snapshot_path": dest.as_posix(),
        "tree_hash": hasher.hexdigest(),
        "file_count": file_count,
        "git": git_meta,
    }


def _git_meta(skill_dir: Path) -> dict[str, Any]:
    """Best-effort git commit / dirty for the skill path (never raises)."""
    try:
        import subprocess

        def _run(args: list[str]) -> str | None:
            proc = subprocess.run(
                args,
                cwd=skill_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                return None
            return (proc.stdout or "").strip() or None

        commit = _run(["git", "rev-parse", "HEAD"])
        dirty_out = _run(["git", "status", "--porcelain", "--", str(skill_dir)])
        dirty = bool(dirty_out) if dirty_out is not None else None
        return {"commit": commit, "dirty": dirty}
    except Exception:
        return {"commit": None, "dirty": None}
