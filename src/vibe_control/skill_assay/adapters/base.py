"""Shared helpers for real Skill Assay host adapters."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from vibe_control.skill_assay.errors import SkillAssayError

# Env vars allowed through to host subprocesses (auth/login reuse).
_ENV_ALLOW_PREFIXES = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "TMPDIR",
    "TMP",
    "TEMP",
    "LANG",
    "LC_",
    "TERM",
    "SHELL",
    "XDG_",
    "SSH_AUTH_SOCK",
    "DISPLAY",
)


def scrub_env(
    base: dict[str, str] | None = None,
    *,
    extra_allow: tuple[str, ...] = (),
) -> dict[str, str]:
    """Keep login/home/path vars; drop secrets and unrelated ambient env."""
    source = dict(base if base is not None else os.environ)
    # Never forward API keys into adapters that should reuse local login.
    for deny in (
        "CURSOR_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "COPILOT_GITHUB_TOKEN",
        "GH_TOKEN",
        "GITHUB_TOKEN",
    ):
        source.pop(deny, None)
    allow = set(_ENV_ALLOW_PREFIXES) | set(extra_allow)
    out: dict[str, str] = {}
    for key, value in source.items():
        if key in extra_allow:
            out[key] = value
            continue
        if any(key == p or key.startswith(p) for p in allow):
            out[key] = value
    return out


def inject_skill_tree(
    *,
    skill_snapshot: Path,
    workspace: Path,
    layout: str,
) -> Path:
    """Copy skill snapshot into host-specific discovery path. Returns skill dest."""
    skill_id = Path(skill_snapshot).name
    if layout == "cursor":
        dest = workspace / ".cursor" / "skills" / skill_id
    elif layout == "agents":
        dest = workspace / ".agents" / "skills" / skill_id
    elif layout == "copilot_parent":
        dest = workspace / "skills" / skill_id
    else:
        raise SkillAssayError(
            "SKILL_ASSAY_LAYOUT_INVALID",
            f"unknown skill injection layout: {layout}",
            {"layout": layout},
        )
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skill_snapshot, dest)
    return dest


def mount_target_repo(*, workspace: Path, target_repo: Path) -> Path:
    """Expose a real target repository inside the assay workspace via symlink."""
    src = Path(target_repo).resolve()
    if not src.is_dir():
        raise SkillAssayError(
            "SKILL_ASSAY_TARGET_REPO_INVALID",
            f"target_repo is not a directory: {target_repo}",
            {"target_repo": str(target_repo)},
        )
    dest = Path(workspace) / "target-repo"
    if dest.exists() or dest.is_symlink():
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    dest.symlink_to(src, target_is_directory=True)
    return dest

    dest.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        for path in src.rglob("*"):
            if path.is_file():
                rel = path.relative_to(src)
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
    return dest


def run_subprocess(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int,
    stdin_text: str | None = None,
) -> dict[str, Any]:
    """Run a host process with process-group timeout handling."""
    started = time.monotonic()
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise SkillAssayError(
            "SKILL_ASSAY_HOST_BINARY_MISSING",
            f"host binary not found: {argv[0]}",
            {"argv0": argv[0]},
        ) from exc

    try:
        stdout, stderr = proc.communicate(
            input=stdin_text,
            timeout=max(1, int(timeout_seconds)),
        )
        return {
            "returncode": int(proc.returncode or 0),
            "stdout": stdout or "",
            "stderr": stderr or "",
            "timed_out": False,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "signal": None,
        }
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        stdout, stderr = proc.communicate(timeout=5)
        return {
            "returncode": int(proc.returncode or -1),
            "stdout": stdout or "",
            "stderr": stderr or "",
            "timed_out": True,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "signal": "SIGKILL",
        }


def _kill_process_group(proc: subprocess.Popen[str]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        proc.kill()
        return
    try:
        proc.wait(timeout=3)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        proc.kill()


def safe_rmtree(path: Path) -> list[str]:
    warnings: list[str] = []
    target = Path(path)
    if not target.exists():
        return warnings
    try:
        shutil.rmtree(target)
    except OSError as exc:
        warnings.append(f"cleanup_failed:{target.as_posix()}:{exc}")
    return warnings
