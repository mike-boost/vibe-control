"""Live local-embedded Beads task-cache clear (Vibe-managed namespace only).

Separate from Option A create/update apply and from BeadsReadonlyProvider.
Delete is allowed only as whole Vibe-managed cache invalidation under
``vibe task cache reset --apply`` when ``task_cache_mode=local_embedded_ephemeral``.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from typing import Any, Callable

from vibe_control.task.marker import parse_marker_from_text
from vibe_control.task.models import TaskRecord

Runner = Callable[[list[str]], dict[str, Any]]


class BeadsCacheResetError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _id_hash(provider_task_id: str | None) -> str | None:
    if not provider_task_id:
        return None
    digest = hashlib.sha256(provider_task_id.encode("utf-8")).hexdigest()[:12]
    return f"sha256:{digest}"


def build_bd_delete_argv(
    provider_task_ids: list[str],
    *,
    bd_bin: str = "bd",
    force: bool = True,
) -> list[str]:
    """Build ``bd delete`` argv for Vibe-managed cache clear only."""
    ids = [str(i).strip() for i in provider_task_ids if str(i).strip()]
    if not ids:
        raise BeadsCacheResetError("BD_DELETE_EMPTY", "delete requires at least one provider_task_id")
    for pid in ids:
        if not re.fullmatch(r"[A-Za-z0-9._:-]+", pid):
            raise BeadsCacheResetError(
                "BD_DELETE_ID_INVALID",
                "provider_task_id failed safety pattern",
                {"provider_task_id_hash": _id_hash(pid)},
            )
    argv = [bd_bin, "delete", *ids]
    if force:
        argv.append("--force")
    return argv


def assert_cache_reset_delete_argv(argv: list[str]) -> None:
    """Allow only ``bd delete … --force`` (no close/claim/sql)."""
    if len(argv) < 2:
        raise BeadsCacheResetError("BD_DELETE_ARGV_SHORT", "delete argv too short", {"argv": argv})
    sub = None
    for part in argv[1:]:
        if part.startswith("-"):
            continue
        sub = part
        break
    if sub != "delete":
        raise BeadsCacheResetError(
            "BD_CACHE_RESET_VERB_FORBIDDEN",
            f"cache reset clear only allows delete, got {sub!r}",
            {"argv_verb": sub},
        )
    forbidden = {"close", "claim", "--claim", "sql", "create", "update"}
    for part in argv:
        if part in forbidden:
            raise BeadsCacheResetError(
                "BD_CACHE_RESET_TOKEN_FORBIDDEN",
                f"forbidden token in cache-reset argv: {part}",
            )
    if "--force" not in argv:
        raise BeadsCacheResetError(
            "BD_DELETE_FORCE_REQUIRED",
            "cache reset delete requires --force",
        )


def subprocess_bd_cache_runner(argv: list[str], *, timeout_sec: float = 120.0) -> dict[str, Any]:
    assert_cache_reset_delete_argv(argv)
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_sec,
    )
    return {
        "argv_verb": "delete",
        "returncode": proc.returncode,
        "stdout_len": len(proc.stdout or ""),
        "stderr_len": len(proc.stderr or ""),
        # Never echo raw stdout/stderr into envelopes (may contain ids).
        "ok": proc.returncode == 0,
    }


def classify_vibe_managed_tasks(tasks: list[TaskRecord]) -> list[dict[str, Any]]:
    """Return Vibe-managed inventory rows for cache reset planning (ids hashed)."""
    rows: list[dict[str, Any]] = []
    for task in tasks:
        try:
            marker = parse_marker_from_text(task.description or "")
        except Exception:  # noqa: BLE001 — treat parse failure as non-managed for reset scope
            continue
        if marker is None:
            continue
        if marker.managed_by != "vibe-control":
            continue
        rows.append(
            {
                "managed_key": marker.managed_key,
                "ssot_anchor": marker.ssot_anchor,
                "provider_task_id_hash": _id_hash(task.provider_task_id),
                "provider_task_id": task.provider_task_id,  # internal only; strip before emit
            }
        )
    return rows


def redact_managed_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "managed_key": row.get("managed_key"),
                "ssot_anchor": row.get("ssot_anchor"),
                "provider_task_id_hash": row.get("provider_task_id_hash"),
            }
        )
    return out


def clear_vibe_managed_beads_cache(
    *,
    tasks: list[TaskRecord],
    runner: Runner | None = None,
    bd_bin: str = "bd",
) -> dict[str, Any]:
    """Delete all Vibe-managed Beads tasks (local ephemeral cache invalidation)."""
    rows = classify_vibe_managed_tasks(tasks)
    use_runner = runner or subprocess_bd_cache_runner
    if not rows:
        return {
            "cleared_count": 0,
            "anchors": [],
            "managed_keys": [],
            "records": [],
            "results": [],
        }

    ids = [str(r["provider_task_id"]) for r in rows if r.get("provider_task_id")]
    argv = build_bd_delete_argv(ids, bd_bin=bd_bin, force=True)
    assert_cache_reset_delete_argv(argv)
    result = use_runner(argv)
    if isinstance(result, dict) and result.get("ok") is False:
        raise BeadsCacheResetError(
            "BD_CACHE_RESET_DELETE_FAILED",
            "bd delete failed during local ephemeral cache reset",
            {"returncode": result.get("returncode"), "cleared_attempt": len(ids)},
        )
    if isinstance(result, dict) and result.get("returncode") not in (None, 0):
        raise BeadsCacheResetError(
            "BD_CACHE_RESET_DELETE_FAILED",
            "bd delete failed during local ephemeral cache reset",
            {"returncode": result.get("returncode"), "cleared_attempt": len(ids)},
        )

    return {
        "cleared_count": len(rows),
        "anchors": [r.get("ssot_anchor") for r in rows],
        "managed_keys": [r.get("managed_key") for r in rows],
        "records": redact_managed_rows(rows),
        "results": [
            {
                "argv_verb": "delete",
                "returncode": (result or {}).get("returncode", 0) if isinstance(result, dict) else 0,
                "count": len(ids),
            }
        ],
    }
