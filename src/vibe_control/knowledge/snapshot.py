"""Desired SSOT snapshot and binding hash helpers (Phase 8)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vibe_control.knowledge.managed_names import content_sha256_file
from vibe_control.knowledge.provider_target import canonical_json, sha256_hex


@dataclass
class SnapshotItem:
    doc_id: str
    path: str
    content_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "path": self.path,
            "content_sha256": self._norm_sha(self.content_sha256),
        }

    @staticmethod
    def _norm_sha(value: str) -> str:
        text = (value or "").strip()
        if text.startswith("sha256:"):
            return text
        return "sha256:" + text


@dataclass
class DesiredSnapshot:
    project_id: str
    sync_scope: str
    items: list[SnapshotItem] = field(default_factory=list)
    item_hashes_hash: str = ""
    snapshot_hash: str = ""
    item_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "sync_scope": self.sync_scope,
            "item_count": self.item_count,
            "item_hashes_hash": self.item_hashes_hash,
            "snapshot_hash": self.snapshot_hash,
            "items": [i.to_dict() for i in self.items],
        }


def upload_hash_from_sha(content_sha256: str) -> str:
    text = (content_sha256 or "").strip().lower()
    if text.startswith("sha256:"):
        text = text[len("sha256:") :]
    return text[:12]


def item_hashes_hash(items: list[SnapshotItem]) -> str:
    payload = sorted(
        (
            {
                "doc_id": item.doc_id,
                "content_sha256": SnapshotItem._norm_sha(item.content_sha256),
            }
            for item in items
        ),
        key=lambda row: row["doc_id"],
    )
    return sha256_hex(canonical_json(payload))


def snapshot_hash(*, project_id: str, sync_scope: str, items: list[SnapshotItem]) -> str:
    return sha256_hex(
        canonical_json(
            {
                "project_id": project_id,
                "sync_scope": sync_scope,
                "item_hashes_hash": item_hashes_hash(items),
            }
        )
    )


def binding_hash(items: list[dict[str, Any]]) -> str:
    payload = sorted(
        (
            {
                "target_key_hash": row["target_key_hash"],
                "doc_id": row["doc_id"],
                "content_sha256": SnapshotItem._norm_sha(str(row["content_sha256"])),
                "upload_hash": row["upload_hash"],
                "source_id_hash": row["source_id_hash"],
                "ready": bool(row.get("ready")),
            }
            for row in items
        ),
        key=lambda row: row["doc_id"],
    )
    return sha256_hex(canonical_json(payload))


def build_desired_snapshot(
    *,
    project_id: str,
    sync_scope: str,
    documents: list[dict[str, Any]],
    repo_root: Path,
) -> DesiredSnapshot:
    items: list[SnapshotItem] = []
    for doc in documents:
        doc_id = str(doc["doc_id"])
        path = str(doc["path"])
        file_path = repo_root / path
        raw_sha = content_sha256_file(file_path) if file_path.is_file() else ""
        content_sha = SnapshotItem._norm_sha(raw_sha) if raw_sha else "sha256:" + ("0" * 64)
        items.append(SnapshotItem(doc_id=doc_id, path=path, content_sha256=content_sha))
    items.sort(key=lambda item: item.doc_id)
    return DesiredSnapshot(
        project_id=project_id,
        sync_scope=sync_scope,
        items=items,
        item_count=len(items),
        item_hashes_hash=item_hashes_hash(items),
        snapshot_hash=snapshot_hash(project_id=project_id, sync_scope=sync_scope, items=items),
    )
