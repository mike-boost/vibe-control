"""Phase 8 forward sync apply/retry with scoped receipt, pending, and ack."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Protocol

from vibe_control.config import ControlConfig
from vibe_control.knowledge.corpus import resolve_corpus_for_target
from vibe_control.knowledge.managed_names import content_sha256_file, managed_name, slug_doc, upload_filename
from vibe_control.knowledge.format_policy import extension_of
from vibe_control.knowledge.pending_sync import clear_pending_sync, write_pending_sync
from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.receipt_scope import load_or_migrate_receipt, scoped_receipt_path
from vibe_control.knowledge.remote_ack import AckStore, read_ack, write_ack
from vibe_control.knowledge.remote_ack_guard import assert_ack_write_allowed
from vibe_control.knowledge.scale_observability import build_scale_observability, write_last_sync_report
from vibe_control.knowledge.snapshot import (
    SnapshotItem,
    binding_hash,
    build_desired_snapshot,
    upload_hash_from_sha,
)
from vibe_control.knowledge.sync_lifecycle_phase8 import replace_item_with_receipt_switch
from vibe_control.knowledge.sync_status import evaluate_sync_status, probe_managed_sources



class ApplyProvider(Protocol):
    def list_sources(self, *, notebook_ref: str) -> dict[str, Any]: ...

    def add_file_source(self, *, notebook_ref: str, file_path: str, title: str) -> dict[str, Any]: ...

    def wait_source(self, *, notebook_ref: str, source_id: str, timeout: float = 120) -> dict[str, Any]: ...

    def get_source(self, *, notebook_ref: str, source_id: str) -> dict[str, Any]: ...

    def delete_source(self, *, notebook_ref: str, source_id: str) -> dict[str, Any]: ...


def _sid_hash(source_id: str) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:16]


def _completed_effect(kind: str, target: str) -> dict[str, str]:
    """Minimal completed-effect fact for command-boundary envelopes."""
    return {"kind": kind, "target": target, "status": "completed"}


def _write_receipt(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _load_receipt(
    project_id: str,
    target: ProviderTarget,
    *,
    home: Path | None,
) -> dict[str, Any]:
    result = load_or_migrate_receipt(project_id, target, home=home)
    if not result.ok:
        raise RuntimeError(result.code or "RECEIPT_LOAD_FAILED")
    if result.data:
        return dict(result.data)
    return {
        "schema_version": 1,
        "project_id": project_id,
        "sync_scope": "ssot_files",
        "provider": target.provider,
        "provider_target": target.to_dict(),
        "items": {},
        "cleanup_pending": [],
    }


def _binding_rows(target: ProviderTarget, items: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for doc_id, row in items.items():
        rows.append(
            {
                "target_key_hash": target.target_key_hash,
                "doc_id": doc_id,
                "content_sha256": row.get("content_sha256"),
                "upload_hash": row.get("upload_hash")
                or upload_hash_from_sha(str(row.get("content_sha256") or "")),
                "source_id_hash": row.get("source_id_hash"),
                "ready": bool(row.get("ready", True)),
            }
        )
    return rows


def plan_forward_sync_dry_run(
    config: ControlConfig,
    *,
    repo_root: Path,
    target: ProviderTarget,
    notebook_ref: str,
    provider: ApplyProvider,
    ack_store: AckStore | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    """Phase 8 dry-run planner aligned with status/apply desired_snapshot + scoped receipt.

    When status is synced for the current target/snapshot, required updates for current
    SSOT docs must be empty. Orphan managed remotes (e.g. old vibe_control_v0_5_spec)
    remain report_only_no_delete and do not force replace_required.
    """
    from vibe_control.knowledge.managed_names import parse_managed_name, slug_project
    from vibe_control.knowledge.remote_ack import read_ack
    from vibe_control.knowledge.source_identity import MANAGED_CLASSES, classify_title

    project_id = config.project_id
    corpus, sync_scope = resolve_corpus_for_target(
        config,
        notebook_alias=target.notebook_alias,
        repo_root=repo_root,
    )
    from vibe_control.knowledge.format_policy import apply_to_desired_corpus

    narrowed, format_report = apply_to_desired_corpus("notebooklm", corpus)
    desired = build_desired_snapshot(
        project_id=project_id,
        sync_scope=sync_scope,
        documents=[{"doc_id": d.doc_id, "path": d.path} for d in narrowed.documents],
        repo_root=repo_root,
    )
    receipt = _load_receipt(project_id, target, home=home)
    items = dict(receipt.get("items") or {})
    desired_ids = {item.doc_id for item in desired.items}

    listed = provider.list_sources(notebook_ref=notebook_ref)
    sources = list(listed.get("sources") or []) if listed.get("ok", True) else []

    operations: list[dict[str, Any]] = []
    for row in format_report.get("rejected") or []:
        operations.append(
            {
                "op": "skip_unsupported_format",
                "path": row["path"],
                "reason": row["reason"],
                "action": "skip_no_upload",
            }
        )
    for item in desired.items:
        path = repo_root / item.path
        sha_raw = content_sha256_file(path) if path.is_file() else ""
        content_sha = SnapshotItem._norm_sha(sha_raw)
        current = items.get(item.doc_id) or {}
        mname = managed_name(project_id, item.doc_id)
        ext = extension_of(item.path) or ".md"
        fname = (
            upload_filename(mname, sha_raw, extension=ext) if sha_raw else None
        )
        if current.get("content_sha256") == content_sha and current.get("provider_source_id"):
            operations.append(
                {
                    "op": "already_current",
                    "doc_id": item.doc_id,
                    "path": item.path,
                    "managed_name": mname,
                    "upload_filename": current.get("upload_filename") or fname,
                }
            )
        elif current.get("provider_source_id"):
            operations.append(
                {
                    "op": "replace_required",
                    "doc_id": item.doc_id,
                    "path": item.path,
                    "managed_name": mname,
                    "action": "add_new_wait_verify_receipt_then_cleanup",
                }
            )
        else:
            operations.append(
                {
                    "op": "add_missing",
                    "doc_id": item.doc_id,
                    "path": item.path,
                    "managed_name": mname,
                    "upload_filename": fname,
                    "source_title": mname,
                }
            )

    seen_orphan_docs: set[str] = set()
    project_slug = slug_project(project_id)
    for src in sources:
        title = str(src.get("title") or src.get("name") or "")
        parsed = parse_managed_name(title)
        orphan_doc: str | None = None
        if parsed and parsed.get("project_id") == project_slug:
            slug = str(parsed.get("doc_id") or "")
            mapped = None
            for doc_id in desired_ids:
                if doc_id == slug or slug_doc(doc_id) == slug:
                    mapped = doc_id
                    break
            if mapped is None and slug:
                orphan_doc = slug
        else:
            classified = classify_title(
                title,
                project_id=project_id,
                desired_doc_ids=desired_ids,
                path_hints={d.doc_id: d.path for d in corpus.documents},
            )
            doc_id = classified.get("doc_id")
            if (
                classified.get("classification") in MANAGED_CLASSES
                and doc_id
                and doc_id not in desired_ids
            ):
                orphan_doc = str(doc_id)
        if orphan_doc and orphan_doc not in seen_orphan_docs:
            seen_orphan_docs.add(orphan_doc)
            operations.append(
                {
                    "op": "orphan_managed",
                    "doc_id": orphan_doc,
                    "source_title": title,
                    "action": "report_only_no_delete",
                }
            )

    for pending in receipt.get("cleanup_pending") or []:
        operations.append(
            {
                "op": "cleanup_pending",
                "doc_id": pending.get("doc_id"),
                "action": "receipt_owned_cleanup_candidate",
            }
        )

    summary: dict[str, int] = {}
    for op in operations:
        summary[str(op.get("op"))] = summary.get(str(op.get("op")), 0) + 1

    required_ops = {"add_missing", "replace_required"}
    required_updates = [
        op for op in operations if op.get("op") in required_ops and op.get("doc_id") in desired_ids
    ]

    remote_ack = read_ack(ack_store, target) if ack_store is not None else None
    status = evaluate_sync_status(
        project_id=project_id,
        target=target,
        desired=desired,
        remote_ack=remote_ack,
        provider=provider,
        notebook_ref=notebook_ref,
        home=home,
    )

    receipt_result = load_or_migrate_receipt(project_id, target, home=home)
    receipt_items = dict((receipt_result.data or {}).get("items") or {})
    return {
        "ok": True,
        "dry_run": True,
        "planner": "phase8",
        "notebook_alias": target.notebook_alias,
        "sync_scope": desired.sync_scope,
        "desired_count": desired.item_count,
        "snapshot_hash": desired.snapshot_hash,
        "format_policy": {
            "rejected_count": format_report.get("rejected_count") or 0,
            "rejected": list(format_report.get("rejected") or []),
            "allowed_extensions": list(format_report.get("allowed_extensions") or []),
        },
        "item_hashes_hash": desired.item_hashes_hash,
        "sync_state": status.get("sync_state"),
        "synced": bool(status.get("synced")),
        "operations": operations,
        "summary": summary,
        "required_updates_count": len(required_updates),
        "required_updates": [
            {"op": o.get("op"), "doc_id": o.get("doc_id"), "path": o.get("path")} for o in required_updates
        ],
        "safe_to_sync": False,
        "scale": build_scale_observability(
            project_id=project_id,
            target=target,
            desired_count=desired.item_count,
            receipt_item_count=len(receipt_items),
            required_updates_count=len(required_updates),
            probe=status.get("probe") if isinstance(status.get("probe"), dict) else None,
            home=home,
        ),
    }


def apply_forward_sync(
    config: ControlConfig,
    *,
    repo_root: Path,
    target: ProviderTarget,
    notebook_ref: str,
    provider: ApplyProvider,
    ack_store: AckStore,
    home: Path | None = None,
    command: str = "vibe knowledge sync --apply",
    continue_on_item_error: bool = False,
    batch_size: int | None = None,
    wait_mode: str | None = None,
    batch_pace_ms: int | None = None,
    ingest_path: str | None = None,
    upload_concurrency: int | None = None,
) -> dict[str, Any]:
    """Create/update managed sources to match latest desired_snapshot; write ack after verify.

    Fault-tolerance (industry batch ingest):
    - Idempotent per-doc upsert via content hash skip
    - Checkpoint receipt after each successful item (retry never re-does successes)
    - Default fail_stop on first item failure (successes already checkpointed)
    - Opt-in continue_on_item_error: skip item_skippable/retryable, collect item_failures (DLQ)
    - Opt-in micro-batch creates + serial|multi wait coalescing
    - Multi-file: prefer Python API concurrent uploads when available (ingest_path=auto|api)
    - Never claim synced while item_failures remain or final probe fails
    """
    assert_ack_write_allowed(command=command)
    import time

    from vibe_control.agent_surface import knowledge_sync_disclosure
    from vibe_control.knowledge.batch_wait import (
        DEFAULT_BATCH_PACE_MS,
        normalize_batch_size,
        normalize_wait_mode,
        wait_many,
    )
    from vibe_control.knowledge.notebooklm_api_ingest import (
        normalize_upload_concurrency,
        notebooklm_api_available,
        resolve_ingest_path,
    )
    from vibe_control.knowledge.partial_continue import (
        DEFAULT_SYNC_MODE,
        PARTIAL_CONTINUE_MODE,
        build_item_failure,
        classify_item_failure,
        should_stop_run,
    )

    started = time.monotonic()
    mode = PARTIAL_CONTINUE_MODE if continue_on_item_error else DEFAULT_SYNC_MODE
    effective_batch_size = normalize_batch_size(batch_size)
    effective_wait_mode = normalize_wait_mode(wait_mode)
    effective_upload_concurrency = normalize_upload_concurrency(upload_concurrency)
    api_ok = bool(
        getattr(provider, "supports_api_bulk_create", lambda: False)()
        if callable(getattr(provider, "supports_api_bulk_create", None))
        else notebooklm_api_available() and callable(getattr(provider, "bulk_create_and_wait", None))
    )
    try:
        resolved_ingest = resolve_ingest_path(ingest_path, api_available=api_ok)
    except RuntimeError as exc:
        return {
            "ok": False,
            "code": "INGEST_PATH_UNAVAILABLE",
            "message": str(exc),
            "replayed_history": False,
            "sync_mode": DEFAULT_SYNC_MODE,
            "continue_on_item_error": bool(continue_on_item_error),
            "batch_size": effective_batch_size,
            "wait_mode": effective_wait_mode,
            "ingest_path": "api",
            "upload_concurrency": effective_upload_concurrency,
            "elapsed_ms": 0,
            "item_failures": [],
            "effects": [],
        }
    use_api_bulk = resolved_ingest == "api" and callable(
        getattr(provider, "bulk_create_and_wait", None)
    )
    pace_ms = int(batch_pace_ms) if batch_pace_ms is not None else DEFAULT_BATCH_PACE_MS
    if pace_ms < 0:
        pace_ms = 0
    project_id = config.project_id
    corpus, sync_scope = resolve_corpus_for_target(
        config,
        notebook_alias=target.notebook_alias,
        repo_root=repo_root,
    )
    from vibe_control.knowledge.format_policy import apply_to_desired_corpus

    narrowed, format_report = apply_to_desired_corpus("notebooklm", corpus)
    desired = build_desired_snapshot(
        project_id=project_id,
        sync_scope=sync_scope,
        documents=[{"doc_id": d.doc_id, "path": d.path} for d in narrowed.documents],
        repo_root=repo_root,
    )
    receipt = _load_receipt(project_id, target, home=home)
    items = dict(receipt.get("items") or {})
    desired_ids = {item.doc_id for item in desired.items}
    attempted = 0
    item_failures: list[dict[str, Any]] = []
    pending_creates: list[dict[str, Any]] = []
    batches_flushed = 0
    stage_add_ms = 0
    stage_wait_ms = 0
    stage_verify_ms = 0
    ingest_path_used = "api_concurrent" if use_api_bulk else "cli_serial"
    upload_root: Path | None = None
    # Evidence only: completed provider/local writes (not approval policy).
    completed_effects: list[dict[str, str]] = []
    seen_effect_keys: set[tuple[str, str]] = set()

    def _record_effect(kind: str, target_name: str) -> None:
        key = (kind, target_name)
        if key in seen_effect_keys:
            return
        seen_effect_keys.add(key)
        completed_effects.append(_completed_effect(kind, target_name))

    def _elapsed_ms() -> int:
        return int((time.monotonic() - started) * 1000)

    def _checkpoint() -> None:
        receipt["items"] = items
        receipt["provider_target"] = target.to_dict()
        _write_receipt(scoped_receipt_path(project_id, target, home=home), receipt)
        _record_effect("local_state_write", "knowledge.sync")

    def _policy_scale(**extra: Any) -> dict[str, Any]:
        scale = {
            "desired_count": desired.item_count,
            "receipt_item_count": len(items),
            "updated_or_attempted": attempted,
            "failed_item_count": len(item_failures),
            "elapsed_ms": _elapsed_ms(),
            "batch_size": effective_batch_size,
            "wait_mode": effective_wait_mode,
            "batches_flushed": batches_flushed,
            "ingest_path": ingest_path_used,
            "upload_concurrency": effective_upload_concurrency if use_api_bulk else 1,
            "stage_ms": {
                "add": stage_add_ms,
                "wait": stage_wait_ms,
                "verify": stage_verify_ms,
            },
            "sync_policy": knowledge_sync_disclosure(
                continue_flag_available=True,
                batch_flag_available=True,
                multi_wait_available=True,
                api_ingest_available=api_ok or notebooklm_api_available(),
                upload_concurrency_available=True,
            ),
        }
        scale.update(extra)
        return scale

    def _finish_failure(
        *,
        code: str,
        message: str,
        doc_id: str | None = None,
        op: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        elapsed = _elapsed_ms()
        _checkpoint()
        write_pending_sync(
            project_id,
            target,
            reason=code,
            home=home,
            failed_doc_id=doc_id,
            elapsed_ms=elapsed,
            op=op,
        )
        _record_effect("local_state_write", "knowledge.sync")
        write_last_sync_report(
            project_id,
            target,
            ok=False,
            code=code,
            message=message,
            desired_count=desired.item_count,
            receipt_item_count=len(items),
            updated_or_attempted=attempted,
            elapsed_ms=elapsed,
            failed_doc_id=doc_id,
            home=home,
        )
        _record_effect("local_state_write", "knowledge.last_sync_report")
        out = {
            "ok": False,
            "code": code,
            "message": message,
            "replayed_history": False,
            "sync_mode": mode,
            "continue_on_item_error": bool(continue_on_item_error),
            "batch_size": effective_batch_size,
            "wait_mode": effective_wait_mode,
            "ingest_path": ingest_path_used,
            "upload_concurrency": effective_upload_concurrency if use_api_bulk else 1,
            "elapsed_ms": elapsed,
            "failed_doc_id": doc_id,
            "item_failures": list(item_failures),
            "scale": _policy_scale(),
            "effects": list(completed_effects),
        }
        if extra:
            out.update(extra)
            # Preserve effects if extra overwrote the key.
            out["effects"] = list(completed_effects)
        return out

    def _handle_item_failure(
        *,
        code: str,
        message: str,
        doc_id: str | None,
        op: str | None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        failure = build_item_failure(
            doc_id=doc_id,
            op=op,
            code=code,
            message=message,
            elapsed_ms=_elapsed_ms(),
        )
        item_failures.append(failure)
        failure_class = classify_item_failure(code, doc_id=doc_id)
        if should_stop_run(mode=mode, failure_class=failure_class):
            return _finish_failure(
                code=code,
                message=message,
                doc_id=doc_id,
                op=op,
                extra=extra,
            )
        _checkpoint()
        return None

    def _record_ready(pend: dict[str, Any], sid: str) -> None:
        items[str(pend["doc_id"])] = {
            "path": pend["path"],
            "content_sha256": pend["content_sha"],
            "provider_source_id": sid,
            "source_id_hash": _sid_hash(sid),
            "managed_name": pend["mname"],
            "upload_filename": pend["fname"],
            "upload_hash": upload_hash_from_sha(pend["sha"]),
            "ready": True,
        }
        receipt["items"] = items
        _record_effect("provider_write", "knowledge.notebooklm")
        _checkpoint()

    def _flush_pending_creates() -> dict[str, Any] | None:
        nonlocal pending_creates, batches_flushed, stage_add_ms, stage_wait_ms, ingest_path_used
        if not pending_creates:
            return None
        batch = list(pending_creates)
        pending_creates = []
        batches_flushed += 1

        if use_api_bulk:
            t0 = time.perf_counter()
            bulk = provider.bulk_create_and_wait(  # type: ignore[attr-defined]
                notebook_ref=notebook_ref,
                items=[
                    {
                        "doc_id": p["doc_id"],
                        "file_path": p["file_path"],
                        "title": p["mname"],
                    }
                    for p in batch
                ],
                upload_concurrency=effective_upload_concurrency,
                wait_timeout=120.0,
            )
            stage = bulk.get("stage_ms") or {}
            stage_add_ms += int(stage.get("add") or 0)
            stage_wait_ms += int(stage.get("wait") or 0)
            ingest_path_used = str(bulk.get("ingest_path") or "api_concurrent")
            by_doc = {
                str(r.get("doc_id")): r
                for r in (bulk.get("results") or [])
                if isinstance(r, dict)
            }
            # Wall clock fallback if provider omitted stage_ms
            if not stage:
                stage_add_ms += int((time.perf_counter() - t0) * 1000)
            for pend in batch:
                row = by_doc.get(str(pend["doc_id"])) or {}
                if not row.get("ok") or not row.get("source_id"):
                    stop = _handle_item_failure(
                        code=str(row.get("code") or "ADD_FAILED"),
                        message=str(row.get("message") or "bulk create/wait failed"),
                        doc_id=str(pend["doc_id"]),
                        op="add" if str(row.get("code") or "").startswith("ADD") else "wait",
                    )
                    if stop is not None:
                        return stop
                    continue
                _record_ready(pend, str(row["source_id"]))
            if pace_ms:
                time.sleep(pace_ms / 1000.0)
            return None

        # CLI serial adds already happened; wait micro-batch only.
        sid_list = [str(p["sid"]) for p in batch]
        t_wait0 = time.perf_counter()
        waits = wait_many(
            provider.wait_source,
            notebook_ref=notebook_ref,
            source_ids=sid_list,
            wait_mode=effective_wait_mode,
        )
        stage_wait_ms += int((time.perf_counter() - t_wait0) * 1000)
        for pend in batch:
            sid = str(pend["sid"])
            waited = waits.get(sid) or {}
            if not waited.get("ok"):
                stop = _handle_item_failure(
                    code="WAIT_FAILED",
                    message=str(waited.get("message") or "wait failed"),
                    doc_id=str(pend["doc_id"]),
                    op="wait",
                )
                if stop is not None:
                    return stop
                continue
            _record_ready(pend, sid)
        if pace_ms:
            time.sleep(pace_ms / 1000.0)
        return None

    try:
        if use_api_bulk:
            upload_root = Path(tempfile.mkdtemp(prefix="vibe-phase8-bulk-"))

        for doc_id in list(items.keys()):
            if doc_id not in desired_ids:
                old = items[doc_id]
                sid = old.get("provider_source_id")
                if sid:
                    listed = provider.list_sources(notebook_ref=notebook_ref)
                    observed = {str(x.get("id")) for x in (listed.get("sources") or []) if x.get("id")}
                    if str(sid) in observed:
                        provider.delete_source(notebook_ref=notebook_ref, source_id=str(sid))
                        attempted += 1
                        _record_effect("provider_write", "knowledge.notebooklm")
                items.pop(doc_id, None)
                _checkpoint()

        for item in desired.items:
            path = repo_root / item.path
            if not path.is_file():
                stop = _handle_item_failure(
                    code="MISSING_LOCAL_FILE",
                    message=f"missing local file: {item.path}",
                    doc_id=item.doc_id,
                    op="add",
                )
                if stop is not None:
                    return stop
                continue

            sha = content_sha256_file(path)
            content_sha = SnapshotItem._norm_sha(sha)
            current = items.get(item.doc_id) or {}
            if current.get("content_sha256") == content_sha and current.get("provider_source_id"):
                continue
            if current.get("provider_source_id"):
                stop = _flush_pending_creates()
                if stop is not None:
                    return stop
                attempted += 1
                result = replace_item_with_receipt_switch(
                    provider,
                    notebook_ref=notebook_ref,
                    target=target,
                    project_id=project_id,
                    doc_id=item.doc_id,
                    path_str=item.path,
                    file_path=path,
                    content_sha256=sha,
                    receipt=receipt,
                )
                if not result.get("ok"):
                    stop = _handle_item_failure(
                        code=str(result.get("code") or "REPLACE_FAILED"),
                        message=str(result.get("message") or "replace failed"),
                        doc_id=item.doc_id,
                        op="replace",
                    )
                    if stop is not None:
                        return stop
                    continue
                _record_effect("provider_write", "knowledge.notebooklm")
                items = dict(receipt.get("items") or {})
                _checkpoint()
                continue

            attempted += 1
            mname = managed_name(project_id, item.doc_id)
            fname = upload_filename(
                mname, sha, extension=extension_of(item.path) or ".md"
            )
            pend_base = {
                "doc_id": item.doc_id,
                "path": item.path,
                "sha": sha,
                "content_sha": content_sha,
                "mname": mname,
                "fname": fname,
            }
            if use_api_bulk:
                assert upload_root is not None
                upload_path = upload_root / fname
                shutil.copy2(path, upload_path)
                pending_creates.append({**pend_base, "file_path": str(upload_path)})
            else:
                t_add0 = time.perf_counter()
                with tempfile.TemporaryDirectory(prefix="vibe-phase8-upload-") as tmp:
                    upload_path = Path(tmp) / fname
                    shutil.copy2(path, upload_path)
                    added = provider.add_file_source(
                        notebook_ref=notebook_ref,
                        file_path=str(upload_path),
                        title=mname,
                    )
                stage_add_ms += int((time.perf_counter() - t_add0) * 1000)
                source = ((added.get("result") or {}).get("source") or {})
                sid = source.get("id")
                if not sid or not added.get("ok", True):
                    stop = _handle_item_failure(
                        code="ADD_FAILED",
                        message="add failed",
                        doc_id=item.doc_id,
                        op="add",
                    )
                    if stop is not None:
                        return stop
                    continue
                # Provider add completed even if a later wait/receipt step fails.
                _record_effect("provider_write", "knowledge.notebooklm")
                pending_creates.append({**pend_base, "sid": str(sid)})
            if len(pending_creates) >= effective_batch_size:
                stop = _flush_pending_creates()
                if stop is not None:
                    return stop

        stop = _flush_pending_creates()
        if stop is not None:
            return stop

        receipt["items"] = items
        receipt["provider_target"] = target.to_dict()
        rows = _binding_rows(target, items)
        bhash = binding_hash(rows)
        receipt["snapshot_hash"] = desired.snapshot_hash
        receipt["binding_hash"] = bhash
        _checkpoint()

        if item_failures:
            return _finish_failure(
                code="PARTIAL_ITEM_FAILURES",
                message=(
                    f"{len(item_failures)} item failure(s); successful items checkpointed; "
                    "retry remaining only"
                ),
                doc_id=str(item_failures[0].get("doc_id") or "") or None,
                op="partial_continue",
                extra={"item_failures": list(item_failures)},
            )

        t_verify0 = time.perf_counter()
        probe = probe_managed_sources(
            provider,
            notebook_ref=notebook_ref,
            target=target,
            desired=desired,
            expected_bindings=items,
        )
        stage_verify_ms = int((time.perf_counter() - t_verify0) * 1000)
        if not probe.ok:
            return _finish_failure(
                code="VERIFY_FAILED",
                message="final probe failed",
                op="verify",
                extra={"reasons": probe.reasons},
            )

        ack = {
            "schema_version": 1,
            "provider_contract": "vibe.knowledge.provider.v1",
            "project_id": project_id,
            "sync_scope": "ssot_files",
            "provider": target.provider,
            "target_key_hash": target.target_key_hash,
            "notebook_alias": target.notebook_alias,
            "notebook_ref_hash": target.notebook_ref_hash,
            "snapshot_hash": desired.snapshot_hash,
            "item_hashes_hash": desired.item_hashes_hash,
            "binding_hash": probe.binding_hash or bhash,
        }
        write_meta = write_ack(ack_store, target, ack)
        _write_receipt(scoped_receipt_path(project_id, target, home=home), receipt)
        _record_effect("local_state_write", "knowledge.sync")
        if write_meta.get("notebooklm_note_written"):
            _record_effect("provider_write", "knowledge.notebooklm")
        clear_pending_sync(project_id, target, home=home)
        elapsed = _elapsed_ms()
        write_last_sync_report(
            project_id,
            target,
            ok=True,
            code="SYNCED",
            message="forward sync verified",
            desired_count=desired.item_count,
            receipt_item_count=len(items),
            required_updates_count=0,
            updated_or_attempted=attempted,
            elapsed_ms=elapsed,
            home=home,
        )
        _record_effect("local_state_write", "knowledge.last_sync_report")
        return {
            "ok": True,
            "sync_state": "synced",
            "snapshot_hash": desired.snapshot_hash,
            "item_count": desired.item_count,
            "replayed_history": False,
            "sync_mode": mode,
            "continue_on_item_error": bool(continue_on_item_error),
            "batch_size": effective_batch_size,
            "wait_mode": effective_wait_mode,
            "ingest_path": ingest_path_used,
            "upload_concurrency": effective_upload_concurrency if use_api_bulk else 1,
            "ack_written": True,
            "ack_store_kind": write_meta.get("ack_store_kind", "unknown"),
            "notebooklm_note_written": bool(write_meta.get("notebooklm_note_written")),
            "ack_persistence": write_meta,
            "elapsed_ms": elapsed,
            "item_failures": [],
            "format_policy": {
                "rejected_count": format_report.get("rejected_count") or 0,
                "rejected": list(format_report.get("rejected") or []),
                "allowed_extensions": list(format_report.get("allowed_extensions") or []),
            },
            "scale": _policy_scale(elapsed_ms=elapsed, failed_item_count=0),
            "effects": list(completed_effects),
        }
    except Exception as exc:
        return _finish_failure(code="SYNC_EXCEPTION", message=str(exc), op="exception")
    finally:
        if upload_root is not None:
            shutil.rmtree(upload_root, ignore_errors=True)


def retry_forward_sync(
    config: ControlConfig,
    *,
    repo_root: Path,
    target: ProviderTarget,
    notebook_ref: str,
    provider: ApplyProvider,
    ack_store: AckStore,
    home: Path | None = None,
    command: str = "vibe knowledge retry --apply",
    continue_on_item_error: bool = False,
    batch_size: int | None = None,
    wait_mode: str | None = None,
    batch_pace_ms: int | None = None,
    ingest_path: str | None = None,
    upload_concurrency: int | None = None,
) -> dict[str, Any]:
    """Recompute latest desired_snapshot and converge; never replay history."""
    return apply_forward_sync(
        config,
        repo_root=repo_root,
        target=target,
        notebook_ref=notebook_ref,
        provider=provider,
        ack_store=ack_store,
        home=home,
        command=command,
        continue_on_item_error=continue_on_item_error,
        batch_size=batch_size,
        wait_mode=wait_mode,
        batch_pace_ms=batch_pace_ms,
        ingest_path=ingest_path,
        upload_concurrency=upload_concurrency,
    )
