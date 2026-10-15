"""Target-scoped pending-sync.json helpers."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.receipt_scope import pending_sync_path


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_pending_sync(
    project_id: str,
    target: ProviderTarget,
    *,
    reason: str,
    home: Path | None = None,
    target_ref: str | None = None,
    target_commit: str | None = None,
    next_action: str = "vibe knowledge retry --dry-run --json",
    failed_doc_id: str | None = None,
    elapsed_ms: int | None = None,
    op: str | None = None,
) -> Path:
    path = pending_sync_path(project_id, target, home=home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "project_id": project_id,
        "sync_scope": "ssot_files",
        "provider": target.provider,
        "target_key_hash": target.target_key_hash,
        "notebook_alias": target.notebook_alias,
        "reason": reason,
        "target_ref": target_ref,
        "target_commit": target_commit,
        "pending_since": _now(),
        "next_action": next_action,
        "failed_doc_id": failed_doc_id,
        "elapsed_ms": elapsed_ms,
        "op": op,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def clear_pending_sync(
    project_id: str,
    target: ProviderTarget,
    *,
    home: Path | None = None,
) -> bool:
    path = pending_sync_path(project_id, target, home=home)
    if path.is_file():
        path.unlink()
        return True
    return False


def pending_sync_exists(
    project_id: str,
    target: ProviderTarget,
    *,
    home: Path | None = None,
) -> bool:
    return pending_sync_path(project_id, target, home=home).is_file()


def load_pending_sync(
    project_id: str,
    target: ProviderTarget,
    *,
    home: Path | None = None,
) -> dict[str, Any] | None:
    path = pending_sync_path(project_id, target, home=home)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None
