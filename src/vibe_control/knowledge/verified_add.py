"""Verified add-only seed planning and execution (provider-neutral orchestration)."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Any, Protocol

from vibe_control.config import ControlConfig
from vibe_control.knowledge.corpus import build_desired_corpus
from vibe_control.knowledge.managed_names import content_sha256_file, managed_name, upload_filename
from vibe_control.knowledge.receipt import (
    ReceiptStore,
    load_receipt_dict,
    receipt_path,
    receipt_source_index,
)
from vibe_control.knowledge.source_identity import (
    classify_inventory,
    legacy_possible_blocks_add,
)
from vibe_control.knowledge.source_lifecycle import (
    identity_title_state,
    record_verified_add,
    wait_for_source,
)
from vibe_control.knowledge.sync_preview import (
    SEED_ALLOWED_PATHS,
    SEED_MAX_ADD,
    RemoteSource,
)


class SeedProvider(Protocol):
    def list_sources(self, *, notebook_ref: str) -> dict[str, Any]: ...

    def add_file_source(
        self, *, notebook_ref: str, file_path: str, title: str
    ) -> dict[str, Any]: ...

    def wait_source(self, *, notebook_ref: str, source_id: str, timeout: float = 120) -> dict[str, Any]: ...

    def get_source(self, *, notebook_ref: str, source_id: str) -> dict[str, Any]: ...


def _remote_sources(provider: SeedProvider, notebook_ref: str) -> list[RemoteSource]:
    listed = provider.list_sources(notebook_ref=notebook_ref)
    sources = []
    for item in listed.get("sources") or []:
        if not isinstance(item, dict):
            continue
        sources.append(
            RemoteSource(
                source_id=None if item.get("id") is None else str(item.get("id")),
                title=str(item.get("title") or item.get("name") or ""),
                raw=item,
            )
        )
    return sources


def _planned_docs(config: ControlConfig, repo_root: Path) -> list[dict[str, Any]]:
    corpus = build_desired_corpus(config, repo_root=repo_root)
    planned = []
    for doc in corpus.documents:
        if doc.path not in SEED_ALLOWED_PATHS:
            continue
        path = repo_root / doc.path
        sha = content_sha256_file(path) if path.is_file() else ""
        mname = managed_name(config.project_id, doc.doc_id)
        planned.append(
            {
                "doc_id": doc.doc_id,
                "path": doc.path,
                "managed_name": mname,
                "upload_filename": upload_filename(mname, sha) if sha else None,
                "content_sha256": sha,
            }
        )
        if len(planned) >= SEED_MAX_ADD:
            break
    return planned


def plan_or_run(
    config: ControlConfig,
    *,
    repo_root: Path,
    notebook_alias: str,
    notebook_ref: str,
    provider: SeedProvider,
    dry_run: bool,
    allow_add: bool,
) -> dict[str, Any]:
    receipt_data = load_receipt_dict(config.project_id)
    receipt_state = "missing" if receipt_data is None else "current"
    remote = _remote_sources(provider, notebook_ref)
    path_hints = {d.doc_id: d.path for d in build_desired_corpus(config, repo_root=repo_root).documents}
    classified = classify_inventory(
        remote,
        project_id=config.project_id,
        desired_doc_ids=set(path_hints),
        path_hints=path_hints,
        receipt_source_ids=receipt_source_index(receipt_data),
    )

    planned_rows = []
    for item in _planned_docs(config, repo_root):
        doc_id = item["doc_id"]
        remote_state = "missing"
        planned_action = "add_missing"
        if legacy_possible_blocks_add(classified, doc_id=doc_id):
            remote_state = "possible_legacy"
            planned_action = "needs_manual_review"
        else:
            matches = [
                i
                for i in classified["items"]
                if i.get("doc_id") == doc_id
                and i.get("classification")
                in {
                    "managed_by_receipt",
                    "managed_by_name",
                    "managed_by_hashed_filename",
                    "legacy_managed",
                }
            ]
            if matches:
                remote_state = "managed"
                # receipt hash check
                current = ((receipt_data or {}).get("documents") or {}).get(doc_id, {}).get("current")
                if current and current.get("content_sha256") == item["content_sha256"]:
                    planned_action = "skip_current"
                elif current:
                    planned_action = "replace_required_preview"
                else:
                    planned_action = "needs_manual_review"
        planned_rows.append(
            {
                **item,
                "receipt_state": receipt_state,
                "remote_state": remote_state,
                "planned_action": planned_action,
            }
        )

    if dry_run or not allow_add:
        return {
            "ok": True,
            "data": {
                "dry_run": True,
                "notebook_alias": notebook_alias,
                "planned": planned_rows,
                "planned_adds": planned_rows,  # Phase 4 acceptance alias
                "safe_to_sync": False,
            },
        }

    # real add
    added = []
    needs_manual_review = False
    for row in planned_rows:
        if row["planned_action"] == "needs_manual_review":
            needs_manual_review = True
            continue
        if row["planned_action"] != "add_missing":
            continue
        path = repo_root / row["path"]
        with tempfile.TemporaryDirectory(prefix="vibe-upload-") as tmp:
            upload_path = Path(tmp) / row["upload_filename"]
            shutil.copy2(path, upload_path)
            add_result = provider.add_file_source(
                notebook_ref=notebook_ref,
                file_path=upload_path.as_posix(),
                title=row["managed_name"],
            )
        if not add_result.get("ok"):
            return {
                "ok": False,
                "code": add_result.get("code") or "NOTEBOOKLM_COMMAND_FAILED",
                "message": add_result.get("message") or "add failed",
                "partial_success": bool(added),
                "data": {"added": added, "needs_manual_review": needs_manual_review},
            }
        result = add_result.get("result") or {}
        source = result.get("source") if isinstance(result, dict) else None
        if not isinstance(source, dict):
            source = {}
        source_id = source.get("id")
        if not source_id:
            return {
                "ok": False,
                "partial_success": True,
                "code": "ADD_REQUESTED_BUT_NOT_VERIFIED",
                "message": "add accepted but source_id missing",
                "data": {"added": added},
            }

        wait = wait_for_source(
            str(source_id),
            poll_status=lambda sid: _poll(provider, notebook_ref, sid),
            direct_wait=lambda sid, **kw: provider.wait_source(
                notebook_ref=notebook_ref, source_id=sid, timeout=kw.get("timeout", 120)
            ),
            timeout_seconds=120,
            interval_seconds=0,
        )
        if not wait.get("ok"):
            return {
                "ok": False,
                "partial_success": True,
                "code": wait.get("code") or "ADD_REQUESTED_BUT_NOT_VERIFIED",
                "message": "source did not become ready",
                "data": {"added": added, "wait": wait},
            }

        got = provider.get_source(notebook_ref=notebook_ref, source_id=str(source_id))
        observed = ((got.get("source") or {}).get("title")) if got.get("ok") else None
        observed = observed or source.get("title") or ""
        title_state = identity_title_state(
            str(observed),
            managed_name=row["managed_name"],
            upload_filename=row["upload_filename"],
        )
        verified = title_state is not None
        receipt_written = False
        if verified:
            store = ReceiptStore(receipt_path(config.project_id))
            record = record_verified_add(
                store,
                verified=True,
                project_id=config.project_id,
                provider="notebooklm",
                notebook_alias=notebook_alias,
                notebook_ref_hash="sha256:"
                + hashlib.sha256(notebook_ref.encode("utf-8")).hexdigest()[:16],
                doc_id=row["doc_id"],
                path_str=row["path"],
                managed_name=row["managed_name"],
                current={
                    "provider_source_id": str(source_id),
                    "upload_filename": row["upload_filename"],
                    "remote_title_observed": observed,
                    "title_state": title_state,
                    "status": "ready",
                    "content_sha256": row["content_sha256"],
                },
            )
            receipt_written = bool(record.get("receipt_written"))
        added.append(
            {
                "doc_id": row["doc_id"],
                "provider_source_id": str(source_id),
                "managed_name": row["managed_name"],
                "upload_filename": row["upload_filename"],
                "remote_title_observed": observed,
                "title_state": title_state or "mismatch",
                "receipt_written": receipt_written,
                "verified": verified,
            }
        )
        if not verified:
            return {
                "ok": False,
                "partial_success": True,
                "code": "NEEDS_MANUAL_REVIEW",
                "message": "source ready but identity title mismatch",
                "data": {"added": added, "needs_manual_review": True},
            }

    if needs_manual_review and not added:
        return {
            "ok": False,
            "code": "NEEDS_MANUAL_REVIEW",
            "message": "possible legacy managed source blocks duplicate add",
            "data": {"planned": planned_rows, "needs_manual_review": True, "added": []},
        }
    return {
        "ok": True,
        "data": {
            "dry_run": False,
            "notebook_alias": notebook_alias,
            "added": added,
            "needs_manual_review": needs_manual_review,
            "safe_to_sync": False,
        },
    }


def _poll(provider: SeedProvider, notebook_ref: str, source_id: str) -> dict[str, Any]:
    got = provider.get_source(notebook_ref=notebook_ref, source_id=source_id)
    if not got.get("found", got.get("ok")):
        return {"found": False, "status": "not_found"}
    source = got.get("source") or {}
    return {"found": True, "status": source.get("status") or "ready"}
