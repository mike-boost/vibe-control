"""Phase 8 replace lifecycle: receipt switch before cleanup."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Protocol

from vibe_control.knowledge.managed_names import managed_name, upload_filename
from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.snapshot import SnapshotItem, upload_hash_from_sha


class LifecycleProvider(Protocol):
    def add_file_source(self, *, notebook_ref: str, file_path: str, title: str) -> dict[str, Any]: ...

    def wait_source(self, *, notebook_ref: str, source_id: str, timeout: float = 120) -> dict[str, Any]: ...

    def get_source(self, *, notebook_ref: str, source_id: str) -> dict[str, Any]: ...

    def delete_source(self, *, notebook_ref: str, source_id: str) -> dict[str, Any]: ...

    def list_sources(self, *, notebook_ref: str) -> dict[str, Any]: ...


def _sid_hash(source_id: str) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:16]


def safe_delete_binding(
    *,
    target: ProviderTarget,
    receipt: dict[str, Any],
    candidate_source_id: str,
    candidate_title: str,
    observed_ids: set[str],
) -> dict[str, Any]:
    """Refuse delete unless exact receipt/cleanup ownership in current target."""
    receipt_target = (receipt.get("provider_target") or {}).get("target_key_hash")
    if receipt_target and receipt_target != target.target_key_hash:
        return {"ok": False, "code": "TARGET_MISMATCH"}

    owned: set[str] = set()
    for row in (receipt.get("items") or {}).values():
        sid = row.get("provider_source_id")
        if sid:
            owned.add(str(sid))
    for row in receipt.get("cleanup_pending") or []:
        sid = row.get("provider_source_id")
        if sid:
            owned.add(str(sid))

    if candidate_source_id not in owned:
        return {"ok": False, "code": "NOT_RECEIPT_OWNED"}
    if candidate_source_id not in observed_ids:
        return {"ok": False, "code": "NOT_OBSERVED"}

    # Title/prefix alone is never enough; require receipt ownership already checked.
    managed = False
    for row in (receipt.get("items") or {}).values():
        if str(row.get("provider_source_id")) == candidate_source_id:
            if candidate_title in {
                row.get("upload_filename"),
                row.get("managed_name"),
            }:
                managed = True
            break
    for row in receipt.get("cleanup_pending") or []:
        if str(row.get("provider_source_id")) == candidate_source_id:
            if candidate_title in {
                row.get("upload_filename"),
                row.get("managed_name"),
            }:
                managed = True
            break
    if not managed:
        return {"ok": False, "code": "IDENTITY_MISMATCH"}
    return {"ok": True, "code": "SAFE_TO_DELETE"}


def replace_item_with_receipt_switch(
    provider: LifecycleProvider,
    *,
    notebook_ref: str,
    target: ProviderTarget,
    project_id: str,
    doc_id: str,
    path_str: str,
    file_path: Path,
    content_sha256: str,
    receipt: dict[str, Any],
    on_receipt_switched: Callable[[dict[str, Any]], None] | None = None,
    on_before_delete: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    receipt_target = (receipt.get("provider_target") or {}).get("target_key_hash")
    if receipt_target and receipt_target != target.target_key_hash:
        return {
            "ok": False,
            "code": "TARGET_MISMATCH",
            "message": "Receipt target does not match current ProviderTarget",
        }

    items = dict(receipt.get("items") or {})
    old = dict(items.get(doc_id) or {})
    old_sid = old.get("provider_source_id")

    mname = managed_name(project_id, doc_id)
    from vibe_control.knowledge.format_policy import extension_of

    fname = upload_filename(
        mname, content_sha256, extension=extension_of(path_str) or ".md"
    )
    with tempfile.TemporaryDirectory(prefix="vibe-phase8-replace-") as tmp:
        upload_path = Path(tmp) / fname
        shutil.copy2(file_path, upload_path)
        added = provider.add_file_source(
            notebook_ref=notebook_ref,
            file_path=str(upload_path),
            title=mname,
        )
    source = ((added.get("result") or {}).get("source") or {})
    new_sid = source.get("id")
    if not new_sid:
        return {"ok": False, "code": "ADD_FAILED", "message": "add did not return source id"}

    waited = provider.wait_source(notebook_ref=notebook_ref, source_id=str(new_sid))
    if not waited.get("ok"):
        return {"ok": False, "code": "WAIT_FAILED", "message": "new source not ready"}

    got = provider.get_source(notebook_ref=notebook_ref, source_id=str(new_sid))
    if not got.get("found", got.get("ok")):
        return {"ok": False, "code": "VERIFY_FAILED", "message": "new source not found"}

    new_binding = {
        "doc_id": doc_id,
        "path": path_str,
        "content_sha256": SnapshotItem._norm_sha(content_sha256),
        "provider_source_id": str(new_sid),
        "source_id_hash": _sid_hash(str(new_sid)),
        "managed_name": mname,
        "upload_filename": fname,
        "upload_hash": upload_hash_from_sha(content_sha256),
        "ready": True,
    }

    cleanup_pending = list(receipt.get("cleanup_pending") or [])
    if old_sid:
        cleanup_pending.append(
            {
                "doc_id": doc_id,
                "provider_source_id": old_sid,
                "upload_filename": old.get("upload_filename"),
                "content_sha256": old.get("content_sha256"),
            }
        )

    items[doc_id] = new_binding
    receipt["items"] = items
    receipt["cleanup_pending"] = cleanup_pending
    receipt["provider_target"] = target.to_dict()

    if on_receipt_switched:
        on_receipt_switched(receipt)

    if old_sid:
        if on_before_delete:
            on_before_delete(str(old_sid))
        # Safe delete: must still be observed in current notebook inventory
        listed = provider.list_sources(notebook_ref=notebook_ref)
        observed_ids = {str(x.get("id")) for x in (listed.get("sources") or []) if x.get("id")}
        if str(old_sid) not in observed_ids:
            return {
                "ok": False,
                "code": "CLEANUP_NOT_OBSERVED",
                "message": "old binding not observed in current notebook",
                "receipt": receipt,
            }
        deleted = provider.delete_source(notebook_ref=notebook_ref, source_id=str(old_sid))
        if not deleted.get("ok"):
            return {
                "ok": False,
                "code": "CLEANUP_FAILED",
                "message": "failed to delete old binding",
                "receipt": receipt,
            }
        receipt["cleanup_pending"] = [
            row for row in cleanup_pending if row.get("provider_source_id") != old_sid
        ]

    return {"ok": True, "receipt": receipt, "new_source_id": str(new_sid)}
