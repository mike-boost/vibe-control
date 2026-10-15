"""Install thin Vibe skills into ~/.agents/skills (symlink-first)."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Any, Literal


SKILL_NAMES = ("vibe-control", "vibe-knowledge", "vibe-implementation")
InstallMode = Literal["symlink", "copy"]


class SkillsError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def package_skills_root() -> Path:
    return Path(__file__).resolve().parent / "skills"


def default_install_root() -> Path:
    override = os.environ.get("VIBE_SKILLS_ROOT")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".agents" / "skills"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_if_symlink(path: Path) -> Path | None:
    if not path.is_symlink():
        return None
    try:
        return path.resolve()
    except OSError:
        return None


def _dir_skill_md_hash(directory: Path) -> str | None:
    skill_md = directory / "SKILL.md"
    if not skill_md.is_file():
        return None
    return file_sha256(skill_md)


def inspect_skill(name: str, *, install_root: Path | None = None) -> dict[str, Any]:
    source_root = package_skills_root()
    target_root = install_root or default_install_root()
    source = (source_root / name).resolve()
    target = target_root / name
    source_exists = source.is_dir() and (source / "SKILL.md").is_file()

    target_exists = target.exists() or target.is_symlink()
    target_is_symlink = target.is_symlink()
    points_to_source = False
    install_mode = "missing"
    content_matches: bool | None = None
    warnings: list[str] = []

    if not target_exists:
        install_mode = "missing"
    elif target_is_symlink:
        resolved = _resolve_if_symlink(target)
        if resolved is not None and source_exists and resolved == source:
            install_mode = "symlink"
            points_to_source = True
            content_matches = True
        else:
            install_mode = "mismatch"
            points_to_source = False
            content_matches = False
    elif target.is_dir():
        source_hash = _dir_skill_md_hash(source) if source_exists else None
        target_hash = _dir_skill_md_hash(target)
        if source_hash and target_hash and source_hash == target_hash:
            install_mode = "copy"
            content_matches = True
            warnings.append(
                "Target is a copied directory; symlink install is preferred"
            )
        else:
            install_mode = "mismatch"
            content_matches = False
    else:
        install_mode = "unknown"
        content_matches = False

    installed = install_mode in {"symlink", "copy"} and bool(content_matches)
    return {
        "name": name,
        "source_path": source.as_posix(),
        "target_path": target.as_posix(),
        "source_exists": source_exists,
        "installed": installed,
        "install_mode": install_mode,
        "target_exists": target_exists,
        "target_is_symlink": target_is_symlink,
        "points_to_source": points_to_source,
        "content_matches": content_matches,
        "warnings": warnings,
    }


def skills_status(*, install_root: Path | None = None) -> dict[str, Any]:
    target_root = install_root or default_install_root()
    source_root = package_skills_root()
    skills = [inspect_skill(name, install_root=target_root) for name in SKILL_NAMES]
    preferred = all(
        s["install_mode"] == "symlink" and s["points_to_source"] for s in skills
    )
    warnings: list[str] = []
    for skill in skills:
        warnings.extend(skill.get("warnings") or [])
    return {
        "source_exists": all(s["source_exists"] for s in skills),
        "source_root": source_root.as_posix(),
        "install_root": target_root.as_posix(),
        "preferred_mode": "symlink",
        "installed": preferred,
        "skills": skills,
        "warnings": warnings,
    }


def skills_readiness(*, install_root: Path | None = None) -> dict[str, Any]:
    """Readonly readiness + next_actions for doctor / install guidance.

    ``aligned`` means every packaged vibe-* skill is a symlink pointing at the
    currently installed package. Missing or mismatched skills are agent-facing
    debt (stale routes), not a product_ready blocker.
    """
    status = skills_status(install_root=install_root)
    skills = list(status.get("skills") or [])
    missing = [s["name"] for s in skills if s.get("install_mode") == "missing"]
    mismatch = [
        s["name"]
        for s in skills
        if s.get("install_mode") in {"mismatch", "unknown"}
    ]
    # copy with content_matches is acceptable but not preferred
    copy_ok = [
        s["name"]
        for s in skills
        if s.get("install_mode") == "copy" and s.get("content_matches")
    ]

    if status.get("installed"):
        condition = "aligned"
    elif missing and not mismatch and not copy_ok:
        condition = "missing"
    elif mismatch:
        condition = "mismatch"
    elif copy_ok and not missing and not mismatch:
        condition = "copy_ok"
    else:
        condition = "partial"

    warnings: list[str] = list(status.get("warnings") or [])
    next_actions: list[str] = []
    if condition == "aligned":
        pass
    elif condition == "missing":
        warnings.append("Vibe thin skills not installed into ~/.agents/skills")
        next_actions.append("vibe skills install --dry-run --json")
        next_actions.append("vibe skills install --apply --json")
    elif condition == "mismatch":
        warnings.append(
            "Vibe thin skills exist but do not point at the current package "
            f"(mismatch: {', '.join(mismatch)})"
        )
        next_actions.append("vibe skills install --apply --force --json")
    elif condition == "copy_ok":
        warnings.append(
            "Vibe thin skills are copied directories; symlink install is preferred"
        )
        next_actions.append("vibe skills install --apply --force --json")
    else:
        warnings.append("Vibe thin skills are only partially installed or aligned")
        next_actions.append("vibe skills install --apply --force --json")

    return {
        "installed": bool(status.get("installed")),
        "condition": condition,
        "missing": missing,
        "mismatch": mismatch,
        "copy_ok": copy_ok,
        "install_root": status.get("install_root"),
        "source_root": status.get("source_root"),
        "skills": skills,
        "warnings": warnings,
        "next_actions": next_actions,
    }


def plan_install(
    *,
    install_root: Path | None = None,
    force: bool = False,
    mode: InstallMode = "symlink",
) -> list[dict[str, Any]]:
    if mode not in {"symlink", "copy"}:
        raise SkillsError("SKILL_INSTALL_FAILED", f"Unsupported install mode: {mode}")

    source_root = package_skills_root()
    target_root = install_root or default_install_root()
    operations: list[dict[str, Any]] = []

    for name in SKILL_NAMES:
        source = (source_root / name).resolve()
        target = target_root / name
        if not source.is_dir() or not (source / "SKILL.md").is_file():
            raise SkillsError(
                "SKILL_SOURCE_NOT_FOUND",
                f"Skill source not found: {source.as_posix()}",
                {"source": source.as_posix()},
            )

        status = inspect_skill(name, install_root=target_root)
        exists = status["target_exists"]
        same_symlink = (
            mode == "symlink"
            and status["install_mode"] == "symlink"
            and status["points_to_source"]
        )
        same_copy = (
            mode == "copy"
            and status["install_mode"] == "copy"
            and status["content_matches"]
        )
        noop = same_symlink or same_copy
        conflict = exists and not noop
        operations.append(
            {
                "action": "symlink" if mode == "symlink" else "copy",
                "skill": name,
                "source": source.as_posix(),
                "target": target.as_posix(),
                "would_overwrite": conflict,
                "target_exists": exists,
                "noop": noop,
                "force_required": bool(conflict and not force),
                "current_install_mode": status["install_mode"],
            }
        )
    return operations


def _remove_target(target: Path) -> None:
    if target.is_symlink() or target.is_file():
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        target.unlink()


def install_skills(
    *,
    install_root: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
    mode: InstallMode = "symlink",
) -> dict[str, Any]:
    target_root = install_root or default_install_root()
    operations = plan_install(install_root=target_root, force=force, mode=mode)

    blocked = [op for op in operations if op.get("force_required")]
    if blocked and not dry_run:
        raise SkillsError(
            "SKILL_TARGET_EXISTS",
            (
                "Target skill(s) exist and are not the expected symlink; "
                "re-run with --force to replace only vibe-* targets"
            ),
            {"operations": blocked, "preferred_mode": "symlink"},
        )

    if dry_run:
        return {
            "dry_run": True,
            "mode": mode,
            "install_root": target_root.as_posix(),
            "operations": operations,
            "status": skills_status(install_root=target_root),
        }

    performed: list[dict[str, Any]] = []
    try:
        target_root.mkdir(parents=True, exist_ok=True)
        for op in operations:
            if op.get("noop"):
                performed.append({**op, "result": "noop"})
                continue
            source = Path(op["source"])
            target = Path(op["target"])
            if target.exists() or target.is_symlink():
                if not force and op.get("would_overwrite"):
                    raise SkillsError(
                        "SKILL_TARGET_EXISTS",
                        f"Refusing to overwrite {target.as_posix()} without --force",
                        {"target": target.as_posix()},
                    )
                _remove_target(target)
            if mode == "symlink":
                target.symlink_to(source, target_is_directory=True)
            else:
                shutil.copytree(source, target)
            performed.append({**op, "result": "created"})
    except SkillsError:
        raise
    except OSError as exc:
        raise SkillsError(
            "SKILL_INSTALL_FAILED",
            f"Failed to install skills: {exc}",
            {"install_root": target_root.as_posix(), "mode": mode},
        ) from exc

    return {
        "dry_run": False,
        "mode": mode,
        "install_root": target_root.as_posix(),
        "operations": performed,
        "status": skills_status(install_root=target_root),
    }
