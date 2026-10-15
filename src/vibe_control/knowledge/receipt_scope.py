"""Target-scoped receipt / pending paths and legacy flat-receipt migration."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vibe_control.knowledge.provider_target import ProviderTarget


TARGET_MISMATCH = "TARGET_MISMATCH"


def _state_root(home: Path | None = None) -> Path:
    root = home if home is not None else Path(os.path.expanduser("~"))
    return root / ".agents" / "state" / "vibe-control"


def legacy_receipt_path(project_id: str, *, home: Path | None = None) -> Path:
    return _state_root(home) / project_id / "knowledge-sync.json"


def scoped_state_dir(project_id: str, target: ProviderTarget, *, home: Path | None = None) -> Path:
    return _state_root(home) / project_id / target.provider / target.target_key_hash


def scoped_receipt_path(project_id: str, target: ProviderTarget, *, home: Path | None = None) -> Path:
    return scoped_state_dir(project_id, target, home=home) / "knowledge-sync.json"


def pending_sync_path(project_id: str, target: ProviderTarget, *, home: Path | None = None) -> Path:
    return scoped_state_dir(project_id, target, home=home) / "pending-sync.json"


@dataclass
class ReceiptLoadResult:
    ok: bool
    data: dict[str, Any] | None = None
    migrated: bool = False
    code: str | None = None
    message: str | None = None
    path: str | None = None


def _normalize_scoped(data: dict[str, Any], target: ProviderTarget) -> dict[str, Any]:
    out = dict(data)
    out["schema_version"] = int(out.get("schema_version") or 1)
    out["provider"] = target.provider
    out["provider_target"] = target.to_dict()
    if "items" not in out and "documents" in out:
        # legacy shape uses documents; keep as items for Phase 8 consumers
        docs = out.get("documents") or {}
        items: dict[str, Any] = {}
        if isinstance(docs, dict):
            for doc_id, row in docs.items():
                if isinstance(row, dict):
                    items[doc_id] = {
                        "path": row.get("path"),
                        "content_sha256": (row.get("current") or {}).get("content_sha256")
                        or row.get("content_sha256"),
                        "provider_source_id": (row.get("current") or {}).get("provider_source_id")
                        or row.get("provider_source_id"),
                        "source_id_hash": (row.get("current") or {}).get("source_id_hash")
                        or row.get("source_id_hash"),
                        "managed_name": row.get("managed_name"),
                        "upload_filename": (row.get("current") or {}).get("upload_filename")
                        or row.get("upload_filename"),
                        "ready": True,
                    }
        out["items"] = items
    out.setdefault("items", {})
    out.setdefault("cleanup_pending", [])
    return out


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_or_migrate_receipt(
    project_id: str,
    target: ProviderTarget,
    *,
    home: Path | None = None,
) -> ReceiptLoadResult:
    scoped = scoped_receipt_path(project_id, target, home=home)
    if scoped.is_file():
        try:
            data = json.loads(scoped.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return ReceiptLoadResult(
                ok=False,
                code="RECEIPT_CORRUPTED",
                message=str(exc),
                path=scoped.as_posix(),
            )
        if not isinstance(data, dict):
            return ReceiptLoadResult(
                ok=False,
                code="RECEIPT_CORRUPTED",
                message="Receipt root must be an object",
                path=scoped.as_posix(),
            )
        return ReceiptLoadResult(
            ok=True,
            data=_normalize_scoped(data, target),
            migrated=False,
            path=scoped.as_posix(),
        )

    legacy = legacy_receipt_path(project_id, home=home)
    if not legacy.is_file():
        return ReceiptLoadResult(ok=True, data=None, migrated=False, path=scoped.as_posix())

    try:
        legacy_data = json.loads(legacy.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ReceiptLoadResult(
            ok=False,
            code="RECEIPT_CORRUPTED",
            message=str(exc),
            path=legacy.as_posix(),
        )
    if not isinstance(legacy_data, dict):
        return ReceiptLoadResult(
            ok=False,
            code="RECEIPT_CORRUPTED",
            message="Legacy receipt root must be an object",
            path=legacy.as_posix(),
        )

    legacy_ref_hash = legacy_data.get("notebook_ref_hash")
    legacy_target_hash = (legacy_data.get("provider_target") or {}).get("target_key_hash")
    matches = legacy_ref_hash == target.notebook_ref_hash or legacy_target_hash == target.target_key_hash
    if not matches:
        return ReceiptLoadResult(
            ok=False,
            code=TARGET_MISMATCH,
            message="Legacy receipt notebook target does not match current ProviderTarget",
            path=legacy.as_posix(),
        )

    migrated = _normalize_scoped(legacy_data, target)
    migrated["project_id"] = project_id
    _write_json(scoped, migrated)
    return ReceiptLoadResult(
        ok=True,
        data=migrated,
        migrated=True,
        path=scoped.as_posix(),
    )
