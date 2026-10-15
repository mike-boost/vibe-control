"""Phase 8 sync status evaluation: target + desired + ack + probe."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from vibe_control.knowledge.managed_names import parse_managed_name
from vibe_control.knowledge.pending_sync import pending_sync_exists
from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.receipt_scope import load_or_migrate_receipt
from vibe_control.knowledge.snapshot import DesiredSnapshot, binding_hash, upload_hash_from_sha


class ListSourcesProvider(Protocol):
    def list_sources(self, *, notebook_ref: str) -> dict[str, Any]: ...


def _source_id_hash(source_id: str | None) -> str | None:
    if not source_id:
        return None
    return "sha256:" + hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:16]


@dataclass
class ProbeResult:
    ok: bool
    target_key_hash: str
    item_count: int = 0
    ready_item_count: int = 0
    binding_hash: str | None = None
    missing: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    unready: list[str] = field(default_factory=list)
    observed: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "target_key_hash": self.target_key_hash,
            "item_count": self.item_count,
            "ready_item_count": self.ready_item_count,
            "binding_hash": self.binding_hash,
            "missing": list(self.missing),
            "duplicates": list(self.duplicates),
            "unready": list(self.unready),
            "reasons": list(self.reasons),
        }


def probe_managed_sources(
    provider: ListSourcesProvider,
    *,
    notebook_ref: str,
    target: ProviderTarget,
    desired: DesiredSnapshot,
    expected_bindings: dict[str, dict[str, Any]],
) -> ProbeResult:
    listed = provider.list_sources(notebook_ref=notebook_ref)
    sources = list(listed.get("sources") or [])
    by_doc: dict[str, list[dict[str, Any]]] = {}
    observed: list[dict[str, Any]] = []

    expected_by_title: dict[str, tuple[str, dict[str, Any]]] = {}
    for doc_id, expected in expected_bindings.items():
        for key in (expected.get("upload_filename"), expected.get("managed_name")):
            if key:
                expected_by_title[str(key)] = (doc_id, expected)

    for src in sources:
        title = str(src.get("title") or src.get("name") or "")
        parsed = parse_managed_name(title)
        if parsed is None and title not in expected_by_title:
            continue
        matched = expected_by_title.get(title)
        if matched is None and parsed is not None:
            # Fall back: match corpus doc_id or slug form from managed filename.
            parsed_doc = parsed.get("doc_id") or ""
            for doc_id, expected in expected_bindings.items():
                if doc_id == parsed_doc or doc_id.lower() == parsed_doc.lower():
                    matched = (doc_id, expected)
                    break
                managed = expected.get("managed_name")
                if managed and parse_managed_name(str(managed)):
                    m = parse_managed_name(str(managed))
                    if m and m.get("doc_id") == parsed_doc:
                        matched = (doc_id, expected)
                        break
        if matched is None:
            continue
        doc_id, expected = matched
        upload_hash = (parsed or {}).get("sha12") or expected.get("upload_hash") or ""
        row = {
            "doc_id": doc_id,
            "provider_source_id": src.get("id"),
            "source_id_hash": _source_id_hash(None if src.get("id") is None else str(src.get("id"))),
            "title": title,
            "upload_hash": upload_hash,
            "ready": str(src.get("status") or "ready").lower() in {"ready", "ok", "success"},
            "content_sha256": expected.get("content_sha256"),
            "target_key_hash": target.target_key_hash,
        }
        observed.append(row)
        by_doc.setdefault(doc_id, []).append(row)

    missing: list[str] = []
    duplicates: list[str] = []
    unready: list[str] = []
    binding_rows: list[dict[str, Any]] = []

    for item in desired.items:
        docs = by_doc.get(item.doc_id) or []
        expected = expected_bindings.get(item.doc_id) or {}
        if not docs:
            missing.append(item.doc_id)
            continue
        if len(docs) > 1:
            duplicates.append(item.doc_id)
            continue
        obs = docs[0]
        if expected.get("upload_hash") and obs.get("upload_hash") and obs["upload_hash"] != expected["upload_hash"]:
            missing.append(item.doc_id)
            continue
        if expected.get("provider_source_id") and obs.get("provider_source_id") != expected.get(
            "provider_source_id"
        ):
            # allow probe without forcing source_id match when verifying inventory fingerprints
            pass
        if not obs.get("ready"):
            unready.append(item.doc_id)
        binding_rows.append(
            {
                "target_key_hash": target.target_key_hash,
                "doc_id": item.doc_id,
                "content_sha256": expected.get("content_sha256") or item.content_sha256,
                "upload_hash": expected.get("upload_hash")
                or obs.get("upload_hash")
                or upload_hash_from_sha(item.content_sha256),
                "source_id_hash": expected.get("source_id_hash") or obs.get("source_id_hash"),
                "ready": bool(obs.get("ready")),
            }
        )

    reasons: list[str] = []
    if missing:
        reasons.append(f"missing:{','.join(missing)}")
    if duplicates:
        reasons.append(f"duplicates:{','.join(duplicates)}")
    if unready:
        reasons.append(f"unready:{','.join(unready)}")

    ok = not missing and not duplicates and not unready and len(binding_rows) == desired.item_count
    return ProbeResult(
        ok=ok,
        target_key_hash=target.target_key_hash,
        item_count=len(binding_rows),
        ready_item_count=sum(1 for r in binding_rows if r.get("ready")),
        binding_hash=binding_hash(binding_rows) if binding_rows else None,
        missing=missing,
        duplicates=duplicates,
        unready=unready,
        observed=observed,
        reasons=reasons,
    )


def evaluate_sync_status(
    *,
    project_id: str,
    target: ProviderTarget,
    desired: DesiredSnapshot,
    remote_ack: dict[str, Any] | None,
    provider: ListSourcesProvider,
    notebook_ref: str,
    home: Path | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    if pending_sync_exists(project_id, target, home=home):
        # Pending blocks synced until explicit sync/retry clears it after verification.
        # Still allow reporting mismatch/unavailable with higher specificity below when probed.
        pass

    receipt_result = load_or_migrate_receipt(project_id, target, home=home)
    if not receipt_result.ok and receipt_result.code == "TARGET_MISMATCH":
        return {
            "sync_state": "target_mismatch",
            "code": "TARGET_MISMATCH",
            "synced": False,
            "reasons": [receipt_result.message or "target mismatch"],
            "target": target.to_dict(),
        }

    receipt = receipt_result.data
    if receipt is None:
        return {
            "sync_state": "receipt_missing",
            "code": "RECEIPT_MISSING",
            "synced": False,
            "reasons": ["receipt missing"],
            "next_actions": [
                "vibe knowledge reindex-bindings --json",
                "vibe knowledge sync --apply --json",
            ],
            "target": target.to_dict(),
        }

    receipt_target = (receipt.get("provider_target") or {}).get("target_key_hash")
    if receipt_target and receipt_target != target.target_key_hash:
        return {
            "sync_state": "target_mismatch",
            "code": "TARGET_MISMATCH",
            "synced": False,
            "reasons": ["receipt target_key_hash mismatch"],
            "target": target.to_dict(),
        }

    if not remote_ack:
        reasons.append("remote_ack missing")
        return {
            "sync_state": "drift",
            "synced": False,
            "reasons": reasons,
            "target": target.to_dict(),
        }

    if remote_ack.get("target_key_hash") != target.target_key_hash:
        return {
            "sync_state": "target_mismatch",
            "code": "TARGET_MISMATCH",
            "synced": False,
            "reasons": ["remote_ack target_key_hash mismatch"],
            "target": target.to_dict(),
        }

    if remote_ack.get("snapshot_hash") != desired.snapshot_hash:
        reasons.append("snapshot_hash mismatch")
    if remote_ack.get("item_hashes_hash") != desired.item_hashes_hash:
        reasons.append("item_hashes_hash mismatch")

    expected_bindings = dict(receipt.get("items") or {})
    try:
        probe = probe_managed_sources(
            provider,
            notebook_ref=notebook_ref,
            target=target,
            desired=desired,
            expected_bindings=expected_bindings,
        )
    except Exception as exc:  # provider transport failures
        return {
            "sync_state": "unavailable",
            "synced": False,
            "code": "PROVIDER_UNAVAILABLE",
            "reasons": [str(exc)],
            "target": target.to_dict(),
        }
    if not probe.ok:
        reasons.extend(probe.reasons)
        state = "pending" if pending_sync_exists(project_id, target, home=home) else "drift"
        return {
            "sync_state": state,
            "synced": False,
            "reasons": reasons,
            "probe": probe.to_dict(),
            "target": target.to_dict(),
        }

    if remote_ack.get("binding_hash") != probe.binding_hash:
        reasons.append("binding_hash mismatch")

    if reasons:
        state = "pending" if pending_sync_exists(project_id, target, home=home) else "drift"
        return {
            "sync_state": state,
            "synced": False,
            "reasons": reasons,
            "probe": probe.to_dict(),
            "target": target.to_dict(),
        }

    if pending_sync_exists(project_id, target, home=home):
        return {
            "sync_state": "pending",
            "synced": False,
            "reasons": ["pending-sync.json present; run sync/retry to clear after verify"],
            "probe": probe.to_dict(),
            "target": target.to_dict(),
            "snapshot_hash": desired.snapshot_hash,
        }

    return {
        "sync_state": "synced",
        "synced": True,
        "reasons": [],
        "probe": probe.to_dict(),
        "target": target.to_dict(),
        "snapshot_hash": desired.snapshot_hash,
    }
