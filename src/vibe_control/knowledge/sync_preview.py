"""Sync preview and seed planning (provider-neutral operations)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vibe_control.config import ControlConfig
from vibe_control.knowledge.corpus import DesiredCorpus, build_desired_corpus
from vibe_control.knowledge.managed_names import content_sha256_file, managed_name, upload_filename
from vibe_control.knowledge.managed_titles import parse_managed_title
from vibe_control.knowledge.receipt import receipt_source_index
from vibe_control.knowledge.source_identity import classify_inventory, legacy_possible_blocks_add
from vibe_control.knowledge.source_identity import MANAGED_CLASSES


SEED_MAX_ADD = 3
SEED_ALLOWED_PATHS = {
    "docs/project/VIBE_CONTROL_V0_5_SPEC.md",
    "docs/project/DECISION_LOG.md",
}


@dataclass
class RemoteSource:
    source_id: str | None
    title: str
    raw: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        managed = parse_managed_title(self.title)
        return {
            "source_id_fingerprint": _fp(self.source_id) if self.source_id else None,
            "title": self.title,
            "managed": managed is not None,
            "project_id": None if managed is None else managed.project_id,
            "doc_id": None if managed is None else managed.doc_id,
        }


def classify_remote_inventory(
    sources: list[RemoteSource],
    *,
    project_id: str,
    desired_doc_ids: set[str],
    path_hints: dict[str, str] | None = None,
    receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Legacy-compatible wrapper around source_identity.classify_inventory."""
    classified = classify_inventory(
        sources,
        project_id=project_id,
        desired_doc_ids=desired_doc_ids,
        path_hints=path_hints or {},
        receipt_source_ids=receipt_source_index(receipt),
    )
    managed = []
    unmanaged = []
    for item in classified["items"]:
        public = {
            "source_id_fingerprint": _fp(item.get("source_id")) if item.get("source_id") else None,
            "title": item.get("title"),
            "managed": item["classification"] in MANAGED_CLASSES,
            "classification": item["classification"],
            "project_id": item.get("project_id"),
            "doc_id": item.get("doc_id"),
        }
        if item["classification"] in MANAGED_CLASSES:
            managed.append(public)
        elif item["classification"] == "unmanaged":
            unmanaged.append(public)
        elif item["classification"] == "possible_managed_by_legacy_filename":
            unmanaged.append({**public, "needs_manual_review": True})
    return {
        "managed_count": classified["managed_count"],
        "unmanaged_count": classified["unmanaged_count"],
        "orphan_managed_count": classified["orphan_managed_count"],
        "duplicate_managed_count": classified["duplicate_managed_count"],
        "possible_legacy_count": classified["possible_legacy_count"],
        "managed": managed,
        "unmanaged": unmanaged,
        "orphan_managed": [
            {
                "source_id_fingerprint": _fp(i.get("source_id")) if i.get("source_id") else None,
                "title": i.get("title"),
                "classification": i.get("classification"),
                "doc_id": i.get("doc_id"),
            }
            for i in classified["orphan_managed"]
        ],
        "duplicate_managed": [
            {
                "source_id_fingerprint": _fp(i.get("source_id")) if i.get("source_id") else None,
                "title": i.get("title"),
                "classification": i.get("classification"),
                "doc_id": i.get("doc_id"),
            }
            for i in classified["duplicate_managed"]
        ],
        "items": [
            {
                "classification": i.get("classification"),
                "doc_id": i.get("doc_id"),
                "project_id": i.get("project_id"),
                "title": i.get("title"),
                "source_id_fingerprint": _fp(i.get("source_id")) if i.get("source_id") else None,
            }
            for i in classified["items"]
        ],
    }


def build_sync_preview(
    config: ControlConfig,
    *,
    repo_root: Path,
    notebook_alias: str,
    remote_sources: list[RemoteSource] | None,
    blocked_reason: str | None = None,
    corpus: DesiredCorpus | None = None,
    receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    desired = corpus or build_desired_corpus(config, repo_root=repo_root)
    desired_ids = {d.doc_id for d in desired.documents}
    path_hints = {d.doc_id: d.path for d in desired.documents}
    operations: list[dict[str, Any]] = []

    if blocked_reason:
        operations.append({"op": "blocked", "reason": blocked_reason})
        return {
            "notebook_alias": notebook_alias,
            "provider": "notebooklm",
            "safe_to_sync": False,
            "desired_count": desired.source_count,
            "operations": operations,
            "summary": {"blocked": 1},
            "warnings": list(desired.warnings),
        }

    assert remote_sources is not None
    # source limit
    max_sources = int(config.knowledge.get("max_sources") or 0)
    if max_sources and len(remote_sources) > max_sources:
        operations.append({"op": "blocked", "reason": "source_limit_exceeded"})
        return {
            "notebook_alias": notebook_alias,
            "provider": "notebooklm",
            "safe_to_sync": False,
            "desired_count": desired.source_count,
            "operations": operations,
            "summary": {"blocked": 1},
            "warnings": list(desired.warnings),
        }

    classified = classify_inventory(
        remote_sources,
        project_id=config.project_id,
        desired_doc_ids=desired_ids,
        path_hints=path_hints,
        receipt_source_ids=receipt_source_index(receipt),
    )

    by_doc: dict[str, list[dict[str, Any]]] = {}
    for item in classified["items"]:
        doc_id = item.get("doc_id")
        if not doc_id:
            continue
        if item["classification"] in MANAGED_CLASSES | {"possible_managed_by_legacy_filename"}:
            by_doc.setdefault(str(doc_id), []).append(item)

    for doc in desired.documents:
        matches = by_doc.get(doc.doc_id, [])
        mname = managed_name(config.project_id, doc.doc_id)
        local_path = repo_root / doc.path
        sha = content_sha256_file(local_path) if local_path.is_file() else None
        from vibe_control.knowledge.format_policy import extension_of, is_path_allowed, reject_reason

        if not is_path_allowed("notebooklm", doc.path):
            operations.append(
                {
                    "op": "skip_unsupported_format",
                    "doc_id": doc.doc_id,
                    "path": doc.path,
                    "reason": reject_reason("notebooklm", doc.path),
                    "action": "skip_no_upload",
                }
            )
            continue
        up_name = (
            upload_filename(mname, sha, extension=extension_of(doc.path) or ".md")
            if sha
            else None
        )
        receipt_current = ((receipt or {}).get("documents") or {}).get(doc.doc_id, {}).get("current")

        legacy = [m for m in matches if m["classification"] == "possible_managed_by_legacy_filename"]
        managed_matches = [m for m in matches if m["classification"] in MANAGED_CLASSES]

        if legacy and not managed_matches:
            operations.append(
                {
                    "op": "possible_managed_needs_review",
                    "doc_id": doc.doc_id,
                    "path": doc.path,
                    "source_title": legacy[0].get("title"),
                    "action": "manual_review_no_auto_mutate",
                }
            )
            continue

        if len(managed_matches) > 1:
            operations.append(
                {
                    "op": "duplicate_managed",
                    "doc_id": doc.doc_id,
                    "path": doc.path,
                    "remote_count": len(managed_matches),
                }
            )
            continue

        if len(managed_matches) == 1:
            match = managed_matches[0]
            if receipt_current and receipt_current.get("content_sha256") == sha:
                operations.append(
                    {
                        "op": "already_current",
                        "doc_id": doc.doc_id,
                        "path": doc.path,
                        "managed_name": mname,
                    }
                )
            elif receipt_current and sha and receipt_current.get("content_sha256") != sha:
                operations.append(
                    {
                        "op": "replace_required",
                        "doc_id": doc.doc_id,
                        "path": doc.path,
                        "managed_name": mname,
                        "action": "add_new_wait_verify_receipt_then_cleanup",
                    }
                )
            elif match["classification"] == "managed_by_hashed_filename":
                operations.append(
                    {
                        "op": "managed_by_filename_fallback",
                        "doc_id": doc.doc_id,
                        "path": doc.path,
                        "source_title": match.get("title"),
                    }
                )
            else:
                operations.append(
                    {
                        "op": "already_present_needs_verification",
                        "doc_id": doc.doc_id,
                        "path": doc.path,
                        "managed_name": mname,
                        "source_title": match.get("title"),
                    }
                )
            continue

        if not local_path.is_file():
            operations.append(
                {
                    "op": "blocked",
                    "doc_id": doc.doc_id,
                    "path": doc.path,
                    "reason": "missing_local_file",
                }
            )
        else:
            operations.append(
                {
                    "op": "add_missing",
                    "doc_id": doc.doc_id,
                    "path": doc.path,
                    "managed_name": mname,
                    "upload_filename": up_name,
                    "source_title": mname,
                    # Phase 4 compatibility alias used by older plan_seed_adds callers
                    "legacy_op_alias": "add",
                }
            )

    for orphan in classified["orphan_managed"]:
        operations.append(
            {
                "op": "orphan_managed",
                "doc_id": orphan.get("doc_id"),
                "source_title": orphan.get("title"),
                "action": "report_only_no_delete",
            }
        )
    for item in classified["items"]:
        if item["classification"] == "unmanaged":
            operations.append(
                {
                    "op": "unmanaged_ignore",
                    "source_title": item.get("title"),
                    "action": "never_delete",
                }
            )

    summary: dict[str, int] = {}
    for op in operations:
        summary[op["op"]] = summary.get(op["op"], 0) + 1
        # keep Phase 4 summary key for empty-remote add planning
        if op["op"] == "add_missing":
            summary["add"] = summary.get("add", 0) + 1

    return {
        "notebook_alias": notebook_alias,
        "provider": "notebooklm",
        "safe_to_sync": False,
        "desired_count": desired.source_count,
        "remote": {
            "managed_count": classified["managed_count"],
            "unmanaged_count": classified["unmanaged_count"],
            "orphan_managed_count": classified["orphan_managed_count"],
            "duplicate_managed_count": classified["duplicate_managed_count"],
            "possible_legacy_count": classified["possible_legacy_count"],
        },
        "operations": operations,
        "summary": summary,
        "warnings": list(desired.warnings),
    }


def plan_seed_adds(
    preview: dict[str, Any],
    *,
    max_add: int = SEED_MAX_ADD,
) -> list[dict[str, Any]]:
    adds = [
        op
        for op in preview.get("operations") or []
        if op.get("op") in {"add", "add_missing"}
    ]
    selected = []
    for op in adds:
        path = str(op.get("path") or "")
        if path not in SEED_ALLOWED_PATHS:
            continue
        selected.append(op)
        if len(selected) >= max_add:
            break
    return selected


def _fp(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
