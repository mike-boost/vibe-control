"""Readonly scale observability for knowledge sync (counts + last attempt)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vibe_control.knowledge.pending_sync import load_pending_sync
from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.receipt_scope import scoped_state_dir


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def last_sync_report_path(
    project_id: str,
    target: ProviderTarget,
    *,
    home: Path | None = None,
) -> Path:
    return scoped_state_dir(project_id, target, home=home) / "last-sync-report.json"


def write_last_sync_report(
    project_id: str,
    target: ProviderTarget,
    *,
    ok: bool,
    code: str | None = None,
    message: str | None = None,
    desired_count: int | None = None,
    receipt_item_count: int | None = None,
    required_updates_count: int | None = None,
    updated_or_attempted: int | None = None,
    elapsed_ms: int | None = None,
    failed_doc_id: str | None = None,
    home: Path | None = None,
) -> Path:
    path = last_sync_report_path(project_id, target, home=home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "vibe.knowledge.last_sync_report.v1",
        "project_id": project_id,
        "target_key_hash": target.target_key_hash,
        "notebook_alias": target.notebook_alias,
        "ok": bool(ok),
        "code": code,
        "message": message,
        "desired_count": desired_count,
        "receipt_item_count": receipt_item_count,
        "required_updates_count": required_updates_count,
        "updated_or_attempted": updated_or_attempted,
        "elapsed_ms": elapsed_ms,
        "failed_doc_id": failed_doc_id,
        "recorded_at": _now(),
        "mutation": False,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def load_last_sync_report(
    project_id: str,
    target: ProviderTarget,
    *,
    home: Path | None = None,
) -> dict[str, Any] | None:
    path = last_sync_report_path(project_id, target, home=home)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def build_scale_observability(
    *,
    project_id: str | None,
    target: ProviderTarget | None,
    desired_count: int | None = None,
    receipt_item_count: int | None = None,
    required_updates_count: int | None = None,
    probe: dict[str, Any] | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    """Assemble readonly scale fields for status / dry-run envelopes."""
    from vibe_control.agent_surface import knowledge_sync_disclosure

    pending = None
    last_report = None
    if project_id and target is not None:
        pending = load_pending_sync(project_id, target, home=home)
        last_report = load_last_sync_report(project_id, target, home=home)

    probe = probe or {}
    missing = list(probe.get("missing") or [])
    unready = list(probe.get("unready") or [])

    return {
        "schema": "vibe.knowledge.scale.v1",
        "desired_count": desired_count,
        "receipt_item_count": receipt_item_count,
        "required_updates_count": required_updates_count,
        "probe_missing_count": len(missing) if probe else None,
        "probe_unready_count": len(unready) if probe else None,
        "pending_sync": (
            {
                "present": pending is not None,
                "reason": (pending or {}).get("reason"),
                "pending_since": (pending or {}).get("pending_since"),
                "failed_doc_id": (pending or {}).get("failed_doc_id"),
                "elapsed_ms": (pending or {}).get("elapsed_ms"),
                "op": (pending or {}).get("op"),
            }
            if project_id and target is not None
            else {"present": False}
        ),
        "last_sync_report": last_report,
        "sync_policy": knowledge_sync_disclosure(continue_flag_available=True),
        "mutation": False,
    }
