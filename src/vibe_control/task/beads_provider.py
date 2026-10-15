"""Beads task provider — PATH checks, install guidance, guarded init preview."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BeadsStatus:
    installed: bool
    executable: str | None
    message: str
    version: str | None = None
    init_available: bool = False
    init_safe_mode: str = "unavailable"
    recommended_init: str | None = None
    help_flags: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "installed": self.installed,
            "path": self.executable,
            "executable": self.executable,
            "version": self.version,
            "message": self.message,
            "init_available": self.init_available,
            "init_safe_mode": self.init_safe_mode,
            "recommended_init": self.recommended_init,
            "help_flags": dict(self.help_flags),
        }


class BeadsProvider:
    """Readonly Beads probes. Does not run bd init or create tasks."""

    name = "beads"
    command_name = "bd"

    def __init__(self, runner: Any | None = None):
        self._runner = runner or _default_run

    def which(self) -> str | None:
        return shutil.which(self.command_name)

    def status(self) -> BeadsStatus:
        path = self.which()
        if not path:
            return BeadsStatus(
                installed=False,
                executable=None,
                message="bd not found on PATH",
                init_available=False,
                init_safe_mode="unavailable",
            )
        version = self._probe_version(path)
        return BeadsStatus(
            installed=True,
            executable=path,
            version=version,
            message="bd found on PATH (Beads mutation not enabled in this pass)",
            init_available=False,
            init_safe_mode="unknown",
        )

    def install_guide(self) -> dict[str, Any]:
        path = self.which()
        managers = {
            "npm": shutil.which("npm") is not None,
            "go": shutil.which("go") is not None,
            "brew": shutil.which("brew") is not None,
        }
        options: list[dict[str, Any]] = [
            {
                "id": "A",
                "label": "npm package if available: @beads/bd",
                "commands": [
                    "npm view @beads/bd version",
                    "npm install -g @beads/bd",
                ],
                "available_locally": managers["npm"],
            },
            {
                "id": "B",
                "label": "Go install / official repository path if verified locally or documented",
                "commands": [
                    "go install <official-beads-module>@latest  # verify module path in official docs first",
                ],
                "available_locally": managers["go"],
            },
            {
                "id": "C",
                "label": "Manual install from official Beads docs",
                "commands": [
                    "Follow official Beads documentation for your platform",
                ],
                "available_locally": True,
            },
        ]
        if path:
            return {
                "installed": True,
                "path": path,
                "version": self._probe_version(path),
                "package_managers": managers,
                "options": options,
                "recommended_actions": [
                    "bd is already installed; run python -m vibe_control task init-preview --json",
                ],
                "note": "Do not run install automatically from vibe CLI; use install-guide then approve manually.",
            }
        return {
            "installed": False,
            "path": None,
            "version": None,
            "package_managers": managers,
            "options": options,
            "recommended_actions": [
                "Choose an install option after verifying official Beads docs",
                "If npm is available: npm view @beads/bd version && npm install -g @beads/bd",
                "Then run: python -m vibe_control task init-preview --json",
            ],
            "note": "Do not run install automatically from vibe CLI; use install-guide then approve manually.",
        }

    def init_preview(self) -> BeadsStatus:
        path = self.which()
        if not path:
            return BeadsStatus(
                installed=False,
                executable=None,
                message="bd not found on PATH",
                init_available=False,
                init_safe_mode="unavailable",
            )

        version = self._probe_version(path)
        code, stdout, stderr = self._runner([path, "init", "--help"])
        help_text = f"{stdout}\n{stderr}"
        if code not in (0, 1, 2) and not help_text.strip():
            return BeadsStatus(
                installed=True,
                executable=path,
                version=version,
                message="bd init --help failed",
                init_available=False,
                init_safe_mode="unavailable",
            )

        has_skip = "--skip-agents" in help_text
        has_stealth = "--stealth" in help_text
        flags = {"skip_agents": has_skip, "stealth": has_stealth}

        if has_skip:
            return BeadsStatus(
                installed=True,
                executable=path,
                version=version,
                message="bd init supports --skip-agents",
                init_available=True,
                init_safe_mode="skip_agents",
                recommended_init="bd init --skip-agents",
                help_flags=flags,
            )
        if has_stealth:
            return BeadsStatus(
                installed=True,
                executable=path,
                version=version,
                message="bd init supports --stealth",
                init_available=True,
                init_safe_mode="stealth",
                recommended_init="bd init --stealth",
                help_flags=flags,
            )
        return BeadsStatus(
            installed=True,
            executable=path,
            version=version,
            message=(
                "bd init may modify AGENTS.md or integrations; "
                "manual review required before running"
            ),
            init_available=True,
            init_safe_mode="unavailable",
            recommended_init=None,
            help_flags=flags,
        )

    def _probe_version(self, path: str) -> str | None:
        code, stdout, stderr = self._runner([path, "--version"])
        text = (stdout or stderr or "").strip()
        if code != 0 or not text:
            return None
        return text.splitlines()[0].strip()


def _default_run(argv: list[str], timeout: float = 15.0) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return 127, "", "executable not found"
    except subprocess.TimeoutExpired:
        return 124, "", "command timed out"
