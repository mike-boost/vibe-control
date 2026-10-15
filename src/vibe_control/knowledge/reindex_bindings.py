"""Phase 8: reindex provider bindings into local receipt (never SSOT content)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Protocol

from vibe_control.knowledge.managed_names import managed_name, parse_managed_name
from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.receipt_scope import scoped_receipt_path


class ListSourcesProvider(Protocol):
    def list_sources(self, *, notebook_ref: str) -> dict[str, Any]: ...


def _sid_hash(source_id: str) -> str:
    return "sha256:" + hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:16]


def reindex_bindings(
    *,
    project_id: str,
    target: ProviderTarget,
    notebook_ref: str,
    provider: ListSourcesProvider,
    desired_docs: list[dict[str, Any]],
    home: Path | None = None,
    repo_root: Path | None = None,
    require_managed_identity: bool = False,
) -> dict[str, Any]:
    """Rebuild local binding receipt from provider metadata only.

    Never writes or restores SSOT file contents.
    """
    _ = repo_root  # intentionally unused for content restore
    listed = provider.list_sources(notebook_ref=notebook_ref)
    sources = list(listed.get("sources") or [])
    desired_by_id = {str(d["doc_id"]): d for d in desired_docs}

    items: dict[str, Any] = {}
    for src in sources:
        title = str(src.get("title") or "")
        parsed = parse_managed_name(title)
        if parsed is None:
            continue
        parsed_doc = parsed.get("doc_id") or ""
        doc_id = None
        for candidate in desired_by_id:
            if candidate == parsed_doc or candidate.lower() == parsed_doc.lower():
                doc_id = candidate
                break
        if doc_id is None:
            continue
        desired = desired_by_id[doc_id]
        sid = src.get("id")
        items[doc_id] = {
            "path": desired.get("path"),
            "content_sha256": desired.get("content_sha256"),
            "provider_source_id": sid,
            "source_id_hash": _sid_hash(str(sid)) if sid else None,
            "managed_name": managed_name(project_id, doc_id),
            "upload_filename": title if title.endswith(".md") else None,
            "upload_hash": parsed.get("sha12"),
            "ready": str(src.get("status") or "ready").lower() in {"ready", "ok", "success"},
        }

    if require_managed_identity and not items:
        return {
            "ok": False,
            "code": "INSUFFICIENT_IDENTITY",
            "ssot_restored": False,
            "message": "No managed bindings could be safely identified from provider metadata",
        }

    receipt = {
        "schema_version": 1,
        "project_id": project_id,
        "sync_scope": "ssot_files",
        "provider": target.provider,
        "provider_target": target.to_dict(),
        "items": items,
        "cleanup_pending": [],
        "reindexed": True,
    }
    path = scoped_receipt_path(project_id, target, home=home)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)

    return {
        "ok": True,
        "ssot_restored": False,
        "message": (
            "No SSOT content was restored from provider. "
            "Only provider binding metadata was reindexed."
        ),
        "receipt_path": path.as_posix(),
        "item_count": len(items),
    }
