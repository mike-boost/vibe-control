"""INTERNAL acceptance-only Phase 6 replace smoke (isolated receipt)."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol

from vibe_control.config import ControlConfig
from vibe_control.knowledge.managed_names import (
    content_sha256_bytes,
    managed_name,
    upload_filename,
)
from vibe_control.knowledge.receipt import ReceiptStore
from vibe_control.knowledge.source_lifecycle import (
    identity_title_state,
    record_verified_add,
    wait_for_source,
)


SMOKE_DOC_ID = "phase6_replace_smoke"
SMOKE_CONTENT_V1 = "Phase 6 replace smoke v1\n"
SMOKE_CONTENT_V2 = "Phase 6 replace smoke v2\n"

# Production managed docs that must never be mutated by this smoke.
PROTECTED_DOC_IDS = frozenset({"vibe_control_v0_5_spec", "DECISION_LOG"})


class SmokeProvider(Protocol):
    def list_sources(self, *, notebook_ref: str) -> dict[str, Any]: ...

    def add_file_source(
        self, *, notebook_ref: str, file_path: str, title: str
    ) -> dict[str, Any]: ...

    def wait_source(
        self, *, notebook_ref: str, source_id: str, timeout: float = 120
    ) -> dict[str, Any]: ...

    def get_source(self, *, notebook_ref: str, source_id: str) -> dict[str, Any]: ...

    def delete_source(self, *, notebook_ref: str, source_id: str) -> dict[str, Any]: ...


def smoke_receipt_path(project_id: str, *, home: Path | None = None) -> Path:
    root = home if home is not None else Path(os.path.expanduser("~"))
    return (
        root
        / ".agents"
        / "state"
        / "vibe-control"
        / project_id
        / "smoke"
        / "phase6-replace-smoke.json"
    )


def allows_title_prefix_bulk_delete() -> bool:
    return False


def protected_managed_titles(project_id: str) -> set[str]:
    return {managed_name(project_id, doc_id) for doc_id in PROTECTED_DOC_IDS}


def _ref_hash(notebook_ref: str) -> str:
    return "sha256:" + hashlib.sha256(notebook_ref.encode("utf-8")).hexdigest()[:16]


def _sid_hash(value: str | None) -> str | None:
    if not value:
        return None
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _poll(provider: SmokeProvider, notebook_ref: str, source_id: str) -> dict[str, Any]:
    got = provider.get_source(notebook_ref=notebook_ref, source_id=source_id)
    if not got.get("found", got.get("ok")):
        return {"found": False, "status": "not_found"}
    source = got.get("source") or {}
    return {"found": True, "status": source.get("status") or "ready"}


def _inventory_titles(provider: SmokeProvider, notebook_ref: str) -> list[str]:
    listed = provider.list_sources(notebook_ref=notebook_ref)
    titles = []
    for item in listed.get("sources") or []:
        if isinstance(item, dict):
            titles.append(str(item.get("title") or item.get("name") or ""))
    return titles


def _inventory_ids(provider: SmokeProvider, notebook_ref: str) -> dict[str, str]:
    """Map title -> source_id for current remote list."""
    listed = provider.list_sources(notebook_ref=notebook_ref)
    out: dict[str, str] = {}
    for item in listed.get("sources") or []:
        if not isinstance(item, dict):
            continue
        sid = item.get("id")
        title = str(item.get("title") or item.get("name") or "")
        if sid and title:
            out[title] = str(sid)
    return out


def safe_delete_smoke_source(
    provider: SmokeProvider,
    *,
    notebook_ref: str,
    source_id: str,
    allowed_ids: set[str],
    protected_ids: set[str],
) -> dict[str, Any]:
    """Delete only if source_id is in allowed smoke set and not protected."""
    if not source_id:
        return {"ok": False, "code": "SOURCE_ID_REQUIRED", "message": "missing source_id"}
    if source_id in protected_ids:
        return {
            "ok": False,
            "code": "PROTECTED_SOURCE",
            "message": "refuses to delete protected production managed source",
        }
    if source_id not in allowed_ids:
        return {
            "ok": False,
            "code": "NOT_SMOKE_OWNED",
            "message": "refuses to delete source not owned by this smoke receipt/run",
        }
    return provider.delete_source(notebook_ref=notebook_ref, source_id=source_id)


def _add_verify(
    provider: SmokeProvider,
    *,
    notebook_ref: str,
    notebook_alias: str,
    project_id: str,
    content: str,
    store: ReceiptStore,
) -> dict[str, Any]:
    raw = content.encode("utf-8")
    sha = content_sha256_bytes(raw)
    mname = managed_name(project_id, SMOKE_DOC_ID)
    up_name = upload_filename(mname, sha)
    with tempfile.TemporaryDirectory(prefix="vibe-smoke-") as tmp:
        upload_path = Path(tmp) / up_name
        upload_path.write_bytes(raw)
        add_result = provider.add_file_source(
            notebook_ref=notebook_ref,
            file_path=upload_path.as_posix(),
            title=mname,
        )
    if not add_result.get("ok"):
        return {
            "ok": False,
            "code": add_result.get("code") or "ADD_FAILED",
            "message": add_result.get("message") or "smoke add failed",
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
            "code": wait.get("code") or "WAIT_FAILED",
            "message": "smoke source did not become ready",
            "wait": wait,
            "provider_source_id": str(source_id),
        }

    got = provider.get_source(notebook_ref=notebook_ref, source_id=str(source_id))
    observed = ((got.get("source") or {}).get("title")) if got.get("ok") else None
    observed = observed or source.get("title") or ""
    title_state = identity_title_state(
        str(observed), managed_name=mname, upload_filename=up_name
    )
    verified = title_state is not None
    receipt_written = False
    if verified:
        record = record_verified_add(
            store,
            verified=True,
            project_id=project_id,
            provider="notebooklm",
            notebook_alias=notebook_alias,
            notebook_ref_hash=_ref_hash(notebook_ref),
            doc_id=SMOKE_DOC_ID,
            path_str=f"smoke/{SMOKE_DOC_ID}.md",
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
        "doc_id": SMOKE_DOC_ID,
        "provider_source_id": str(source_id),
        "managed_name": mname,
        "upload_filename": up_name,
        "remote_title_observed": observed,
        "title_state": title_state or "mismatch",
        "content_sha256": sha,
        "verified": verified,
        "receipt_written": receipt_written,
        "code": None if verified else "NEEDS_MANUAL_REVIEW",
        "message": None if verified else "smoke identity mismatch",
    }


def _mark_smoke_cleaned(path: Path) -> None:
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    data["smoke_state"] = "cleaned"
    data["documents"] = {}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def plan_or_run(
    config: ControlConfig,
    *,
    notebook_alias: str,
    notebook_ref: str,
    provider: SmokeProvider,
    dry_run: bool,
    apply: bool,
    cleanup: bool,
    home: Path | None = None,
) -> dict[str, Any]:
    if not dry_run and not apply:
        return {
            "ok": False,
            "code": "SMOKE_REQUIRES_APPLY_OR_DRY_RUN",
            "message": "Pass --dry-run or --apply",
        }

    project_id = config.project_id
    mname = managed_name(project_id, SMOKE_DOC_ID)
    sha_v1 = content_sha256_bytes(SMOKE_CONTENT_V1.encode("utf-8"))
    sha_v2 = content_sha256_bytes(SMOKE_CONTENT_V2.encode("utf-8"))
    protected_titles = protected_managed_titles(project_id)
    baseline_titles = _inventory_titles(provider, notebook_ref)
    baseline_ids = _inventory_ids(provider, notebook_ref)

    # Protect production managed source IDs present at baseline.
    protected_ids = {baseline_ids[t] for t in protected_titles if t in baseline_ids}

    missing_protected = [t for t in sorted(protected_titles) if t not in baseline_titles]
    plan = {
        "smoke_doc_id": SMOKE_DOC_ID,
        "managed_name": mname,
        "v1_upload_filename": upload_filename(mname, sha_v1),
        "v2_upload_filename": upload_filename(mname, sha_v2),
        "v1_content_sha256": sha_v1,
        "v2_content_sha256": sha_v2,
        "baseline_titles": baseline_titles,
        "protected_titles": sorted(protected_titles),
        "missing_protected": missing_protected,
        "steps": [
            "add_v1",
            "wait_verify_v1",
            "write_smoke_receipt_v1",
            "add_v2",
            "wait_verify_v2",
            "switch_smoke_receipt",
            "delete_superseded_v1",
            "delete_final_v2_if_cleanup",
        ],
        "isolated_receipt_path": smoke_receipt_path(project_id, home=home).as_posix(),
    }

    if dry_run or not apply:
        return {
            "ok": True,
            "data": {
                "dry_run": True,
                "notebook_alias": notebook_alias,
                "plan": plan,
                "hashes_differ": sha_v1 != sha_v2,
            },
        }

    if missing_protected:
        return {
            "ok": False,
            "code": "BASELINE_PROTECTED_MISSING",
            "message": "Expected production managed sources missing from baseline inventory",
            "data": {"missing_protected": missing_protected, "baseline_titles": baseline_titles},
        }

    smoke_path = smoke_receipt_path(project_id, home=home)
    store = ReceiptStore(smoke_path)
    allowed_ids: set[str] = set()

    v1 = _add_verify(
        provider,
        notebook_ref=notebook_ref,
        notebook_alias=notebook_alias,
        project_id=project_id,
        content=SMOKE_CONTENT_V1,
        store=store,
    )
    if not v1.get("ok"):
        return {
            "ok": False,
            "partial_success": True,
            "code": v1.get("code") or "SMOKE_V1_FAILED",
            "message": v1.get("message") or "smoke v1 failed",
            "data": {"v1": v1, "baseline_titles": baseline_titles},
        }
    allowed_ids.add(str(v1["provider_source_id"]))

    v2 = _add_verify(
        provider,
        notebook_ref=notebook_ref,
        notebook_alias=notebook_alias,
        project_id=project_id,
        content=SMOKE_CONTENT_V2,
        store=store,
    )
    if not v2.get("ok"):
        return {
            "ok": False,
            "partial_success": True,
            "code": v2.get("code") or "SMOKE_V2_FAILED",
            "message": v2.get("message") or "smoke v2 failed",
            "data": {
                "v1": v1,
                "v2": v2,
                "baseline_titles": baseline_titles,
                "manual_cleanup_hint": (
                    f"Delete only smoke source id fingerprint for v1 if orphaned "
                    f"(managed_name={mname}); never delete protected titles {sorted(protected_titles)}"
                ),
            },
        }
    allowed_ids.add(str(v2["provider_source_id"]))

    # Receipt already switched by second write_verified; confirm history.
    smoke_data = store.load()
    smoke_doc = (smoke_data.get("documents") or {}).get(SMOKE_DOC_ID) or {}
    history = smoke_doc.get("history") or []
    current = smoke_doc.get("current") or {}
    receipt_switched = str(current.get("provider_source_id")) == str(v2["provider_source_id"])
    v1_superseded = any(
        str(h.get("provider_source_id")) == str(v1["provider_source_id"])
        and h.get("state") == "superseded"
        for h in history
    )
    if not receipt_switched or not v1_superseded:
        return {
            "ok": False,
            "partial_success": True,
            "code": "SMOKE_RECEIPT_SWITCH_FAILED",
            "message": "smoke receipt did not switch current to v2 with v1 superseded",
            "data": {"v1": v1, "v2": v2, "receipt_switched": receipt_switched},
        }

    # Delete superseded v1 only.
    del_v1 = safe_delete_smoke_source(
        provider,
        notebook_ref=notebook_ref,
        source_id=str(v1["provider_source_id"]),
        allowed_ids=allowed_ids,
        protected_ids=protected_ids,
    )
    if not del_v1.get("ok"):
        return {
            "ok": False,
            "partial_success": True,
            "code": del_v1.get("code") or "SMOKE_V1_DELETE_FAILED",
            "message": del_v1.get("message") or "failed to delete superseded smoke v1",
            "data": {"v1": v1, "v2": v2, "delete_v1": del_v1},
        }

    mid_titles = _inventory_titles(provider, notebook_ref)
    if v1.get("remote_title_observed") in mid_titles and str(v1["provider_source_id"]) in {
        _inventory_ids(provider, notebook_ref).get(t) for t in mid_titles
    }:
        # title may still exist as v2; check id gone
        pass
    mid_ids = set(_inventory_ids(provider, notebook_ref).values())
    if str(v1["provider_source_id"]) in mid_ids:
        return {
            "ok": False,
            "partial_success": True,
            "code": "SMOKE_V1_STILL_PRESENT",
            "message": "superseded smoke v1 still present after delete",
            "data": {"mid_titles": mid_titles},
        }
    if str(v2["provider_source_id"]) not in mid_ids:
        return {
            "ok": False,
            "partial_success": True,
            "code": "SMOKE_V2_MISSING",
            "message": "smoke v2 missing after supersede cleanup",
            "data": {"mid_titles": mid_titles},
        }

    final_smoke_deleted = False
    if cleanup:
        del_v2 = safe_delete_smoke_source(
            provider,
            notebook_ref=notebook_ref,
            source_id=str(v2["provider_source_id"]),
            allowed_ids=allowed_ids,
            protected_ids=protected_ids,
        )
        if not del_v2.get("ok"):
            return {
                "ok": False,
                "partial_success": True,
                "code": del_v2.get("code") or "SMOKE_V2_DELETE_FAILED",
                "message": del_v2.get("message") or "failed to delete final smoke v2",
                "data": {"v1": v1, "v2": v2, "delete_v2": del_v2},
            }
        final_smoke_deleted = True
        _mark_smoke_cleaned(smoke_path)

    final_titles = _inventory_titles(provider, notebook_ref)
    final_ok = all(t in final_titles for t in protected_titles)
    if cleanup:
        final_ok = final_ok and mname not in final_titles
    if not final_ok:
        return {
            "ok": False,
            "partial_success": True,
            "code": "FINAL_INVENTORY_MISMATCH",
            "message": "final inventory does not restore expected production managed sources",
            "data": {
                "final_titles": final_titles,
                "protected_titles": sorted(protected_titles),
                "smoke_managed_name": mname,
            },
        }

    def _public(row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        sid = out.get("provider_source_id")
        if sid:
            out["source_id_fingerprint"] = hashlib.sha256(str(sid).encode("utf-8")).hexdigest()[:12]
            out["source_id_hash"] = _sid_hash(str(sid))
        return out

    return {
        "ok": True,
        "data": {
            "dry_run": False,
            "notebook_alias": notebook_alias,
            "plan": {k: v for k, v in plan.items() if k != "isolated_receipt_path"},
            "isolated_receipt_path": smoke_path.as_posix(),
            "baseline_titles": baseline_titles,
            "v1": _public(v1),
            "v2": _public(v2),
            # keep raw ids only for in-process tests via original objects — strip from public
            # Tests need provider_source_id; attach separately under _internal for tests?
            "receipt_switched": receipt_switched,
            "v1_superseded": v1_superseded,
            "superseded_deleted": True,
            "final_smoke_deleted": final_smoke_deleted,
            "mid_inventory_titles": mid_titles,
            "final_inventory_titles": final_titles,
            "hashes_differ": sha_v1 != sha_v2,
            "mutations_log": [
                "add_smoke_v1",
                "add_smoke_v2",
                "delete_smoke_v1_superseded",
                *(["delete_smoke_v2_final"] if final_smoke_deleted else []),
            ],
        },
    }
