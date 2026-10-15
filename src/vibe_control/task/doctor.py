"""Readonly task/Beads doctor and status readiness (Phase 10.5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vibe_control.config import ConfigError, load_config, primary_control_path, legacy_control_path
from vibe_control.json_envelope import next_action
from vibe_control.task.beads_provider import BeadsProvider


def beads_dir(repo_root: Path) -> Path:
    return repo_root / ".beads"


def beads_initialized(repo_root: Path) -> bool:
    path = beads_dir(repo_root)
    if not path.is_dir():
        return False
    # Beads init creates metadata/config; accept directory with any recognizable marker.
    markers = ("config.yaml", "metadata.json", "README.md", ".gitignore")
    return any((path / name).exists() for name in markers) or any(path.iterdir())


def build_task_status(
    *,
    repo_root: Path,
    beads: BeadsProvider | None = None,
) -> dict[str, Any]:
    """Readonly task readiness. Never creates tasks or runs bd init."""
    root = repo_root
    provider = beads or BeadsProvider()
    st = provider.status()
    config_found = primary_control_path(root).is_file() or legacy_control_path(root).is_file()
    project_id: str | None = None
    task_provider: str | None = None
    task_configured = False
    if config_found:
        try:
            cfg = load_config(root)
            project_id = cfg.project_id
            task_provider = str((cfg.tasks or {}).get("provider") or "") or None
            task_configured = bool(task_provider)
        except ConfigError:
            task_configured = False

    dir_path = beads_dir(root)
    dir_present = dir_path.is_dir()
    initialized = beads_initialized(root)
    reasons: list[str] = []
    codes: list[str] = []
    next_actions: list[dict[str, Any]] = []

    if not task_configured:
        codes.append("TASK_PROVIDER_NOT_CONFIGURED")
        reasons.append("tasks.provider missing in control config (or config missing)")
        next_actions.append(
            next_action(
                code="TASK_PROVIDER_NOT_CONFIGURED",
                command="vibe config validate --json",
                mutation=False,
                reason="Configure tasks.provider (e.g. beads) in control config",
            )
        )

    if not st.installed:
        readiness = "unavailable"
        codes.append("BEADS_NOT_INSTALLED")
        reasons.append("bd not found on PATH")
        next_actions.append(
            next_action(
                code="BEADS_NOT_INSTALLED",
                command="vibe task install-guide --json",
                mutation=False,
                reason="Install Beads (bd) using install-guide options",
            )
        )
    elif not initialized:
        readiness = "not_ready"
        codes.append("BEADS_NOT_INITIALIZED")
        reasons.append(".beads directory missing or not initialized")
        next_actions.append(
            next_action(
                code="BEADS_NOT_INITIALIZED",
                command="vibe task init-preview --json",
                mutation=False,
                reason="Preview safe bd init options; do not auto-run bd init",
            )
        )
    else:
        readiness = "ready"
        codes.append("TASK_READY")
        reasons.append("bd installed and .beads appears initialized")
        next_actions.append(
            next_action(
                code="TASK_READY",
                command="vibe task reconcile --dry-run --json",
                mutation=False,
                reason="Task provider looks ready; run Phase 11A readonly reconcile (no Beads mutation)",
            )
        )

    # Deduplicate codes/actions
    codes = list(dict.fromkeys(codes))
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for item in next_actions:
        key = (str(item.get("code")), str(item.get("command")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    data = {
        "readiness": readiness,
        "provider": task_provider or "beads",
        "task_provider_configured": task_configured,
        "binary_path": st.executable,
        "version": st.version,
        "beads_dir": dir_path.as_posix(),
        "beads_dir_present": dir_present,
        "initialized": initialized,
        "reasons": reasons,
        "codes": codes,
        "plan_import": {
            "implemented": True,
            "phase": "11B",
            "message": "Use vibe task apply --dry-run --json; --apply --provider fake for local mutation; live Beads blocked without VIBE_BEADS_LIVE_APPLY=1",
            "command": "vibe task apply --dry-run --json",
        },
        "reconcile": {
            "implemented": True,
            "phase": "11A",
            "slice": 1,
            "command": "vibe task reconcile --dry-run --json",
            "mutation": False,
        },
    }
    return {
        "ok": readiness != "unavailable" or task_configured,
        "project_id": project_id,
        "data": data,
        "next_actions": deduped,
        "code": codes[0] if readiness != "ready" and codes else None,
    }


def build_task_doctor(
    *,
    repo_root: Path,
    beads: BeadsProvider | None = None,
) -> dict[str, Any]:
    """Readonly task domain precheck. No bd init / no task create."""
    status = build_task_status(repo_root=repo_root, beads=beads)
    data = dict(status["data"])
    data["status_readable"] = True
    data["mutations"] = {
        "bd_init": False,
        "task_create": False,
        "note": "Phase 10.5 task doctor never mutates Beads",
    }
    return {
        "ok": True,
        "project_id": status.get("project_id"),
        "data": data,
        "warnings": [],
        "next_actions": list(status.get("next_actions") or []),
    }
