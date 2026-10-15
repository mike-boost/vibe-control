"""Provider-neutral NotebookLM sync lifecycle: plan, apply, replace, cleanup."""

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
)
from vibe_control.knowledge.source_lifecycle import (
    identity_title_state,
    record_verified_add,
    wait_for_source,
)
from vibe_control.knowledge.sync_preview import RemoteSource, build_sync_preview


# Exact Phase 4 test residue titles approved for one-shot cleanup.
APPROVED_PHASE4_RESIDUE_TITLES = frozenset(
    {
        "VIBE_CONTROL_V0_5_SPEC.md",
        "[vibe:vibe-control:DECISION_LOG] DECISION_LOG.md",
    }
)


class SyncProvider(Protocol):
    def list_sources(self, *, notebook_ref: str) -> dict[str, Any]: ...

    def add_file_source(
        self, *, notebook_ref: str, file_path: str, title: str
    ) -> dict[str, Any]: ...

    def wait_source(
        self, *, notebook_ref: str, source_id: str, timeout: float = 120
    ) -> dict[str, Any]: ...

    def get_source(self, *, notebook_ref: str, source_id: str) -> dict[str, Any]: ...

    def delete_source(self, *, notebook_ref: str, source_id: str) -> dict[str, Any]: ...


def _remote_sources(provider: SyncProvider, notebook_ref: str) -> list[RemoteSource]:
    listed = provider.list_sources(notebook_ref=notebook_ref)
    sources: list[RemoteSource] = []
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


def _ref_hash(notebook_ref: str) -> str:
    return "sha256:" + hashlib.sha256(notebook_ref.encode("utf-8")).hexdigest()[:16]


def _poll(provider: SyncProvider, notebook_ref: str, source_id: str) -> dict[str, Any]:
    got = provider.get_source(notebook_ref=notebook_ref, source_id=source_id)
    if not got.get("found", got.get("ok")):
        return {"found": False, "status": "not_found"}
    source = got.get("source") or {}
    return {"found": True, "status": source.get("status") or "ready"}


def plan_phase4_residue_cleanup(
    sources: list[dict[str, Any]],
    *,
    approved_titles: frozenset[str] = APPROVED_PHASE4_RESIDUE_TITLES,
) -> dict[str, Any]:
    """Match remote sources to the exact approved Phase 4 residue title set."""
    by_title: dict[str, list[dict[str, Any]]] = {}
    for item in sources:
        title = str(item.get("title") or item.get("name") or "")
        if title in approved_titles:
            by_title.setdefault(title, []).append(item)

    matched_titles = set(by_title)
    if matched_titles != set(approved_titles):
        return {
            "ok": False,
            "code": "RESIDUE_SET_MISMATCH",
            "message": "Matched residue titles are not exactly the approved Phase 4 set",
            "matched_titles": sorted(matched_titles),
            "approved_titles": sorted(approved_titles),
            "matched": [],
        }
    matched: list[dict[str, Any]] = []
    for title in sorted(approved_titles):
        rows = by_title[title]
        if len(rows) != 1:
            return {
                "ok": False,
                "code": "RESIDUE_SET_MISMATCH",
                "message": f"Expected exactly one source for title {title!r}",
                "matched_titles": sorted(matched_titles),
                "approved_titles": sorted(approved_titles),
                "matched": [],
            }
        row = rows[0]
        sid = row.get("id")
        if not sid:
            return {
                "ok": False,
                "code": "RESIDUE_SET_MISMATCH",
                "message": f"Matched title {title!r} is missing source id",
                "matched": [],
            }
        matched.append({"title": title, "provider_source_id": str(sid)})
    return {
        "ok": True,
        "matched": matched,
        "approved_titles": sorted(approved_titles),
    }


def run_phase4_residue_cleanup(
    provider: SyncProvider,
    *,
    notebook_ref: str,
    dry_run: bool,
    allow_delete: bool,
    approved_titles: frozenset[str] = APPROVED_PHASE4_RESIDUE_TITLES,
) -> dict[str, Any]:
    listed = provider.list_sources(notebook_ref=notebook_ref)
    if not listed.get("ok", True) and listed.get("sources") is None:
        return {
            "ok": False,
            "code": listed.get("code") or "LIST_FAILED",
            "message": listed.get("message") or "list_sources failed",
        }
    plan = plan_phase4_residue_cleanup(
        list(listed.get("sources") or []),
        approved_titles=approved_titles,
    )
    if not plan.get("ok"):
        return plan
    if dry_run or not allow_delete:
        return {
            "ok": True,
            "dry_run": True,
            "matched": plan["matched"],
            "deleted": [],
            "planned_deletes": plan["matched"],
        }
    deleted = []
    for item in plan["matched"]:
        sid = item["provider_source_id"]
        result = provider.delete_source(notebook_ref=notebook_ref, source_id=sid)
        if not result.get("ok"):
            return {
                "ok": False,
                "code": result.get("code") or "DELETE_FAILED",
                "message": result.get("message") or "delete failed",
                "partial_success": bool(deleted),
                "deleted": deleted,
                "failed": item,
            }
        deleted.append(item)
    return {"ok": True, "dry_run": False, "deleted": deleted, "matched": plan["matched"]}


def _build_preview(
    config: ControlConfig,
    *,
    repo_root: Path,
    notebook_alias: str,
    provider: SyncProvider,
    notebook_ref: str,
) -> dict[str, Any]:
    receipt_data = load_receipt_dict(config.project_id)
    remote = _remote_sources(provider, notebook_ref)
    return build_sync_preview(
        config,
        repo_root=repo_root,
        notebook_alias=notebook_alias,
        remote_sources=remote,
        receipt=receipt_data,
    )


def _add_and_verify(
    config: ControlConfig,
    *,
    repo_root: Path,
    notebook_alias: str,
    notebook_ref: str,
    provider: SyncProvider,
    doc_id: str,
    path_str: str,
) -> dict[str, Any]:
    path = repo_root / path_str
    sha = content_sha256_file(path)
    mname = managed_name(config.project_id, doc_id)
    up_name = upload_filename(mname, sha)
    with tempfile.TemporaryDirectory(prefix="vibe-sync-upload-") as tmp:
        upload_path = Path(tmp) / up_name
        shutil.copy2(path, upload_path)
        add_result = provider.add_file_source(
            notebook_ref=notebook_ref,
            file_path=upload_path.as_posix(),
            title=mname,
        )
    if not add_result.get("ok"):
        return {
            "ok": False,
            "code": add_result.get("code") or "NOTEBOOKLM_COMMAND_FAILED",
            "message": add_result.get("message") or "add failed",
        }
    result = add_result.get("result") or {}
    source = result.get("source") if isinstance(result, dict) else None
    if not isinstance(source, dict):
        source = {}
    source_id = source.get("id")
    if not source_id:
        return {
            "ok": False,
            "code": "ADD_REQUESTED_BUT_NOT_VERIFIED",
            "message": "add accepted but source_id missing",
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
            "code": wait.get("code") or "ADD_REQUESTED_BUT_NOT_VERIFIED",
            "message": "source did not become ready",
            "wait": wait,
            "provider_source_id": str(source_id),
        }

    got = provider.get_source(notebook_ref=notebook_ref, source_id=str(source_id))
    observed = ((got.get("source") or {}).get("title")) if got.get("ok") else None
    observed = observed or source.get("title") or ""
    title_state = identity_title_state(
        str(observed),
        managed_name=mname,
        upload_filename=up_name,
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
            notebook_ref_hash=_ref_hash(notebook_ref),
            doc_id=doc_id,
            path_str=path_str,
            managed_name=mname,
            current={
                "provider_source_id": str(source_id),
                "upload_filename": up_name,
                "remote_title_observed": observed,
                "title_state": title_state,
                "status": "ready",
                "content_sha256": sha,
            },
        )
        receipt_written = bool(record.get("receipt_written"))
    return {
        "ok": verified and receipt_written,
        "doc_id": doc_id,
        "provider_source_id": str(source_id),
        "managed_name": mname,
        "upload_filename": up_name,
        "remote_title_observed": observed,
        "title_state": title_state or "mismatch",
        "verified": verified,
        "receipt_written": receipt_written,
        "code": None if verified else "NEEDS_MANUAL_REVIEW",
        "message": None if verified else "source ready but identity title mismatch",
    }


def superseded_cleanup_candidates(receipt_data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return receipt-owned superseded source IDs eligible for cleanup."""
    if not receipt_data:
        return []
    candidates: list[dict[str, Any]] = []
    for doc_id, doc in (receipt_data.get("documents") or {}).items():
        current = doc.get("current") or {}
        current_id = current.get("provider_source_id")
        for item in doc.get("history") or []:
            if item.get("state") != "superseded":
                continue
            if item.get("cleanup_state") == "deleted":
                continue
            sid = item.get("provider_source_id")
            if not sid:
                continue
            if current_id and str(sid) == str(current_id):
                continue
            candidates.append(
                {
                    "doc_id": str(doc_id),
                    "provider_source_id": str(sid),
                    "managed_name": doc.get("managed_name"),
                    "op": "cleanup_superseded",
                }
            )
    return candidates


def cleanup_superseded_sources(
    config: ControlConfig,
    *,
    notebook_alias: str,
    notebook_ref: str,
    provider: SyncProvider,
    dry_run: bool,
    allow_delete: bool,
) -> dict[str, Any]:
    """Delete only receipt-owned superseded managed source IDs."""
    receipt_data = load_receipt_dict(config.project_id)
    candidates = superseded_cleanup_candidates(receipt_data)
    if dry_run or not allow_delete:
        return {
            "ok": True,
            "dry_run": True,
            "notebook_alias": notebook_alias,
            "planned": candidates,
            "deleted": [],
        }
    if not candidates:
        return {
            "ok": True,
            "dry_run": False,
            "notebook_alias": notebook_alias,
            "planned": [],
            "deleted": [],
        }

    deleted: list[dict[str, Any]] = []
    store = ReceiptStore(receipt_path(config.project_id))
    data = store.load()
    for cand in candidates:
        sid = cand["provider_source_id"]
        result = provider.delete_source(notebook_ref=notebook_ref, source_id=sid)
        if not result.get("ok"):
            return {
                "ok": False,
                "code": result.get("code") or "DELETE_FAILED",
                "message": result.get("message") or "cleanup delete failed",
                "partial_success": bool(deleted),
                "deleted": deleted,
                "failed": cand,
            }
        deleted.append(cand)
        # mark history item cleaned
        doc = (data.get("documents") or {}).get(cand["doc_id"]) or {}
        history = []
        for item in doc.get("history") or []:
            hist = dict(item)
            if (
                hist.get("state") == "superseded"
                and str(hist.get("provider_source_id")) == sid
                and hist.get("cleanup_state") != "deleted"
            ):
                hist["cleanup_state"] = "deleted"
            history.append(hist)
        doc = dict(doc)
        doc["history"] = history
        documents = dict(data.get("documents") or {})
        documents[cand["doc_id"]] = doc
        data["documents"] = documents
    store.path.parent.mkdir(parents=True, exist_ok=True)
    import json

    store.path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "dry_run": False,
        "notebook_alias": notebook_alias,
        "planned": candidates,
        "deleted": deleted,
    }


def plan_or_run_sync(
    config: ControlConfig,
    *,
    repo_root: Path,
    notebook_alias: str,
    notebook_ref: str,
    provider: SyncProvider,
    dry_run: bool,
    apply: bool,
    cleanup_superseded: bool = True,
) -> dict[str, Any]:
    preview = _build_preview(
        config,
        repo_root=repo_root,
        notebook_alias=notebook_alias,
        provider=provider,
        notebook_ref=notebook_ref,
    )
    cleanup_plan = superseded_cleanup_candidates(load_receipt_dict(config.project_id))
    operations = list(preview.get("operations") or [])
    for cand in cleanup_plan:
        operations.append(cand)

    summary: dict[str, int] = {}
    for op in operations:
        summary[op["op"]] = summary.get(op["op"], 0) + 1

    if dry_run or not apply:
        return {
            "ok": True,
            "data": {
                "dry_run": True,
                "notebook_alias": notebook_alias,
                "desired_count": preview.get("desired_count"),
                "operations": operations,
                "summary": summary,
                "safe_to_sync": False,
            },
        }

    added: list[dict[str, Any]] = []
    replaced: list[dict[str, Any]] = []
    cleaned: list[dict[str, Any]] = []

    for op in preview.get("operations") or []:
        kind = op.get("op")
        if kind == "add_missing":
            row = _add_and_verify(
                config,
                repo_root=repo_root,
                notebook_alias=notebook_alias,
                notebook_ref=notebook_ref,
                provider=provider,
                doc_id=str(op["doc_id"]),
                path_str=str(op["path"]),
            )
            if not row.get("ok"):
                return {
                    "ok": False,
                    "partial_success": bool(added or replaced),
                    "code": row.get("code") or "SYNC_ADD_FAILED",
                    "message": row.get("message") or "add/verify failed",
                    "data": {"added": added, "replaced": replaced, "failed": row},
                }
            added.append(row)
        elif kind == "replace_required":
            # Strict order: add-new -> wait -> verify -> receipt-switch -> later cleanup
            row = _add_and_verify(
                config,
                repo_root=repo_root,
                notebook_alias=notebook_alias,
                notebook_ref=notebook_ref,
                provider=provider,
                doc_id=str(op["doc_id"]),
                path_str=str(op["path"]),
            )
            if not row.get("ok"):
                return {
                    "ok": False,
                    "partial_success": bool(added or replaced),
                    "code": row.get("code") or "SYNC_REPLACE_FAILED",
                    "message": row.get("message") or "replace add/verify failed",
                    "data": {"added": added, "replaced": replaced, "failed": row},
                }
            replaced.append(row)

    if cleanup_superseded:
        cleanup = cleanup_superseded_sources(
            config,
            notebook_alias=notebook_alias,
            notebook_ref=notebook_ref,
            provider=provider,
            dry_run=False,
            allow_delete=True,
        )
        if not cleanup.get("ok"):
            return {
                "ok": False,
                "partial_success": True,
                "code": cleanup.get("code") or "CLEANUP_FAILED",
                "message": cleanup.get("message") or "cleanup failed",
                "data": {
                    "added": added,
                    "replaced": replaced,
                    "cleanup": cleanup,
                },
            }
        cleaned = list(cleanup.get("deleted") or [])

    return {
        "ok": True,
        "data": {
            "dry_run": False,
            "notebook_alias": notebook_alias,
            "desired_count": preview.get("desired_count"),
            "operations": operations,
            "summary": summary,
            "added": added,
            "replaced": replaced,
            "cleaned": cleaned,
            "safe_to_sync": False,
        },
    }


def plan_or_run_retry(
    config: ControlConfig,
    *,
    repo_root: Path,
    notebook_alias: str,
    notebook_ref: str,
    provider: SyncProvider,
    dry_run: bool,
    apply: bool = False,
) -> dict[str, Any]:
    """Retry uses the latest desired corpus, not stale pending operations."""
    # Force rebuild of desired corpus from disk/config.
    _ = build_desired_corpus(config, repo_root=repo_root)
    return plan_or_run_sync(
        config,
        repo_root=repo_root,
        notebook_alias=notebook_alias,
        notebook_ref=notebook_ref,
        provider=provider,
        dry_run=dry_run,
        apply=apply and not dry_run,
        cleanup_superseded=True,
    )


def plan_rebuild(
    config: ControlConfig,
    *,
    repo_root: Path,
    notebook_alias: str,
    notebook_ref: str,
    provider: SyncProvider,
) -> dict[str, Any]:
    """Dry-run rebuild: report exact planned managed operations."""
    result = plan_or_run_sync(
        config,
        repo_root=repo_root,
        notebook_alias=notebook_alias,
        notebook_ref=notebook_ref,
        provider=provider,
        dry_run=True,
        apply=False,
        cleanup_superseded=True,
    )
    if result.get("ok"):
        data = dict(result["data"])
        data["mode"] = "rebuild"
        data["dry_run"] = True
        # Keep only managed-oriented ops in rebuild report emphasis
        managed_ops = [
            op
            for op in data.get("operations") or []
            if op.get("op")
            in {
                "add_missing",
                "replace_required",
                "already_current",
                "cleanup_superseded",
                "already_present_needs_verification",
                "possible_managed_needs_review",
            }
        ]
        data["planned_managed_operations"] = managed_ops
        result = {"ok": True, "data": data}
    return result
