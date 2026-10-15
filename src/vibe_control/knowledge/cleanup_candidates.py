"""Readonly knowledge cleanup-candidate listing (no provider mutation)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Protocol

from vibe_control.config import ControlConfig
from vibe_control.json_envelope import next_action
from vibe_control.knowledge.ack_stores import LocalMirrorAckStore
from vibe_control.knowledge.ask_hygiene import evaluate_ask_hygiene
from vibe_control.knowledge.corpus import build_desired_corpus
from vibe_control.knowledge.managed_names import managed_name, parse_managed_name, slug_doc, slug_project
from vibe_control.knowledge.phase8_apply import _load_receipt, plan_forward_sync_dry_run
from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.source_identity import classify_title


class ListSourcesProvider(Protocol):
    def list_sources(self, *, notebook_ref: str) -> dict[str, Any]: ...


def _sid_hash(source_id: str | None) -> str | None:
    if not source_id:
        return None
    return "sha256:" + hashlib.sha256(str(source_id).encode("utf-8")).hexdigest()[:16]


def _candidate_id(*, target_key_hash: str, classification: str, key: str) -> str:
    payload = f"{target_key_hash}\n{classification}\n{key}"
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _owner_action_manual(*, display_hint: str, doc_id: str | None) -> str:
    doc_note = f" (doc_id={doc_id})" if doc_id else ""
    return (
        "Open the configured NotebookLM target in the provider UI. "
        f"Locate the source by display hint `{display_hint}`{doc_note} "
        "and/or source_id_hash from this listing. "
        "Confirm it is NOT a current SSOT binding (not vibe_control_spec / DECISION_LOG). "
        "Delete it manually in the provider UI only after visual confirmation. "
        "Then rerun: `vibe knowledge status --json`, "
        "`vibe knowledge sync --dry-run --json`, "
        "`vibe knowledge cleanup-candidates --json`."
    )


def _owner_action_receipt_owned(*, doc_id: str | None) -> str:
    doc_note = f" for doc_id={doc_id}" if doc_id else ""
    return (
        f"Receipt-owned cleanup_pending{doc_note} must not be deleted by this command. "
        "Preview with `vibe knowledge sync --dry-run --json` / "
        "`vibe knowledge retry --dry-run --json`, then only if explicitly approved use bounded "
        "`vibe knowledge sync --apply --json` or `vibe knowledge retry --apply --json`. "
        "Do not run broad notebook cleanup."
    )


def list_cleanup_candidates(
    config: ControlConfig,
    *,
    repo_root: Path,
    target: ProviderTarget,
    notebook_ref: str,
    provider: ListSourcesProvider,
    home: Path | None = None,
) -> dict[str, Any]:
    """Build readonly cleanup-candidate report for the resolved ProviderTarget."""
    ack_store = LocalMirrorAckStore(config.project_id, home=home)
    try:
        dry = plan_forward_sync_dry_run(
            config,
            repo_root=repo_root,
            target=target,
            notebook_ref=notebook_ref,
            provider=provider,  # type: ignore[arg-type]
            ack_store=ack_store,
            home=home,
        )
    except RuntimeError as exc:
        if str(exc) == "TARGET_MISMATCH":
            return {
                "ok": False,
                "code": "TARGET_MISMATCH",
                "message": "ProviderTarget mismatch; refuse cleanup candidate listing",
                "mode": "unavailable",
                "provider": target.provider,
                "target_key_hash": target.target_key_hash,
                "mutation": False,
                "data": {
                    "sync_state": "target_mismatch",
                    "required_updates_count": 0,
                    "current_ssot_doc_ids": [],
                    "candidate_count": 0,
                    "candidates": [],
                },
                "warnings": ["Target mismatch; do not clean sources on the wrong notebook"],
                "next_actions": [
                    next_action(
                        code="TARGET_MISMATCH",
                        command="vibe knowledge status --json",
                        mutation=False,
                        reason="Resolve ProviderTarget before listing cleanup candidates",
                    )
                ],
            }
        raise

    sync_state = str(dry.get("sync_state") or "unavailable")
    if sync_state == "target_mismatch" or dry.get("code") == "TARGET_MISMATCH":
        return {
            "ok": False,
            "code": "TARGET_MISMATCH",
            "message": "ProviderTarget mismatch; refuse cleanup candidate listing",
            "mode": "unavailable",
            "provider": target.provider,
            "target_key_hash": target.target_key_hash,
            "mutation": False,
            "data": {
                "sync_state": "target_mismatch",
                "required_updates_count": 0,
                "current_ssot_doc_ids": [],
                "candidate_count": 0,
                "candidates": [],
            },
            "warnings": ["Target mismatch; do not clean sources on the wrong notebook"],
            "next_actions": [
                next_action(
                    code="TARGET_MISMATCH",
                    command="vibe knowledge status --json",
                    mutation=False,
                    reason="Resolve ProviderTarget before listing cleanup candidates",
                )
            ],
        }

    listed = provider.list_sources(notebook_ref=notebook_ref)
    if not listed.get("ok", True):
        return {
            "ok": True,
            "mode": "unavailable",
            "provider": target.provider,
            "target_key_hash": target.target_key_hash,
            "mutation": False,
            "data": {
                "sync_state": "unavailable",
                "required_updates_count": 0,
                "current_ssot_doc_ids": [],
                "candidate_count": 0,
                "candidates": [],
                "provider_error": {
                    "code": listed.get("code"),
                    "message": listed.get("message"),
                },
            },
            "warnings": ["Provider list_sources unavailable; no cleanup candidates invented"],
            "next_actions": [
                next_action(
                    code="PROVIDER_UNAVAILABLE",
                    command="vibe knowledge cleanup-candidates --json",
                    mutation=False,
                    reason="Rerun when NotebookLM provider is available",
                )
            ],
        }

    sources = list(listed.get("sources") or [])
    already_current_ids: set[str] = set()
    for op in dry.get("operations") or []:
        if op.get("op") == "already_current" and op.get("doc_id"):
            already_current_ids.add(str(op["doc_id"]))

    corpus = build_desired_corpus(config, repo_root=repo_root)
    current_ssot_doc_ids = [d.doc_id for d in corpus.documents]
    desired_ids = set(current_ssot_doc_ids)

    receipt = _load_receipt(config.project_id, target, home=home)
    receipt_items = dict(receipt.get("items") or {})

    by_doc: dict[str, list[dict[str, Any]]] = {}
    remote_rows: list[dict[str, Any]] = []
    project_slug = slug_project(config.project_id)
    for src in sources:
        title = str(src.get("title") or src.get("name") or "")
        sid = src.get("id") or src.get("source_id")
        sid_hash = _sid_hash(None if sid is None else str(sid))
        classified = classify_title(
            title,
            project_id=config.project_id,
            desired_doc_ids=desired_ids,
            path_hints={d.doc_id: d.path for d in corpus.documents},
        )
        parsed = parse_managed_name(title)
        doc_id = classified.get("doc_id")
        if parsed and parsed.get("project_id") == project_slug:
            slug = str(parsed.get("doc_id") or "")
            mapped = None
            for did in desired_ids:
                if did == slug or slug_doc(did) == slug:
                    mapped = did
                    break
            if mapped is None and slug and slug not in desired_ids:
                doc_id = slug
            elif mapped is not None:
                doc_id = mapped
        row = {
            "title": title,
            "source_id_hash": sid_hash,
            "classification": classified.get("classification"),
            "doc_id": doc_id,
        }
        remote_rows.append(row)
        if doc_id:
            by_doc.setdefault(str(doc_id), []).append(row)

    candidates: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    def add_candidate(
        *,
        classification: str,
        doc_id: str | None,
        display_hint: str,
        source_id_hash: str | None,
        evidence: str,
        delete_eligibility: str,
        why_not_auto_delete: str,
        safe_to_auto_delete: bool = False,
        managed_name_hint: str | None = None,
        owner_action: str | None = None,
        allow_current_ssot_doc: bool = False,
    ) -> None:
        key = f"{classification}|{doc_id or ''}|{source_id_hash or display_hint}"
        if key in seen_keys:
            return
        seen_keys.add(key)
        # Never list the current expected binding as a cleanup candidate
        if (
            not allow_current_ssot_doc
            and doc_id
            and doc_id in already_current_ids
            and classification not in {"duplicate_managed", "cleanup_pending"}
        ):
            return
        if classification in {"already_current", "current_ssot"}:
            return
        candidates.append(
            {
                "candidate_id": _candidate_id(
                    target_key_hash=target.target_key_hash,
                    classification=classification,
                    key=key,
                ),
                "classification": classification,
                "doc_id": doc_id,
                "managed_name": managed_name_hint
                or (managed_name(config.project_id, doc_id) if doc_id else None),
                "display_hint": display_hint,
                "source_id_hash": source_id_hash,
                "target_key_hash": target.target_key_hash,
                "evidence": evidence,
                "safe_to_auto_delete": bool(safe_to_auto_delete),
                "delete_eligibility": delete_eligibility,
                "why_not_auto_delete": why_not_auto_delete,
                "owner_action": owner_action
                or _owner_action_manual(display_hint=display_hint, doc_id=doc_id),
            }
        )

    for op in dry.get("operations") or []:
        kind = op.get("op")
        doc_id = op.get("doc_id")
        if kind == "orphan_managed":
            title = str(op.get("source_title") or "")
            matching = [r for r in remote_rows if r.get("title") == title]
            sid_hash = matching[0].get("source_id_hash") if matching else None
            add_candidate(
                classification="orphan_managed",
                doc_id=None if doc_id is None else str(doc_id),
                display_hint=title or str(doc_id),
                source_id_hash=sid_hash,
                evidence=(
                    "Remote managed-looking source is not in current desired SSOT; "
                    "Phase 8 dry-run marks report_only_no_delete"
                ),
                delete_eligibility="manual_only",
                why_not_auto_delete=(
                    "Orphan managed sources are not receipt-owned for auto delete; "
                    "CLI must not delete by title/managed_name heuristic"
                ),
                managed_name_hint=title or None,
            )
        elif kind == "cleanup_pending":
            pending_sid = op.get("provider_source_id")
            if not pending_sid:
                for pending in receipt.get("cleanup_pending") or []:
                    if pending.get("doc_id") == doc_id and pending.get("provider_source_id"):
                        pending_sid = pending.get("provider_source_id")
                        break
            add_candidate(
                classification="cleanup_pending",
                doc_id=None if doc_id is None else str(doc_id),
                display_hint=str(doc_id or "cleanup_pending"),
                source_id_hash=_sid_hash(None if pending_sid is None else str(pending_sid)),
                evidence="Scoped receipt lists this source under cleanup_pending after replace switch",
                delete_eligibility="receipt_owned_apply_possible",
                why_not_auto_delete=(
                    "This command is readonly; receipt-owned cleanup runs only via "
                    "explicit `vibe knowledge sync --apply` / `retry --apply` when approved"
                ),
                safe_to_auto_delete=False,
                owner_action=_owner_action_receipt_owned(
                    doc_id=None if doc_id is None else str(doc_id)
                ),
                allow_current_ssot_doc=True,
            )

    for doc_id, rows in by_doc.items():
        if doc_id not in desired_ids or len(rows) <= 1:
            continue
        bound_hash = _sid_hash(
            None
            if not (receipt_items.get(doc_id) or {}).get("provider_source_id")
            else str((receipt_items.get(doc_id) or {}).get("provider_source_id"))
        )
        for row in rows:
            if bound_hash and row.get("source_id_hash") == bound_hash:
                continue
            title = str(row.get("title") or "")
            add_candidate(
                classification="duplicate_managed",
                doc_id=doc_id,
                display_hint=title,
                source_id_hash=row.get("source_id_hash"),
                evidence=(
                    f"Extra remote managed source for current SSOT doc_id={doc_id} "
                    "(not the receipt-bound source)"
                ),
                delete_eligibility="manual_only",
                why_not_auto_delete=(
                    "Duplicate managed sources require owner confirmation; "
                    "auto-delete is forbidden without exact receipt-owned apply proof"
                ),
                managed_name_hint=title or managed_name(config.project_id, doc_id),
                allow_current_ssot_doc=True,
            )

    for row in remote_rows:
        if row.get("classification") != "unmanaged":
            continue
        title = str(row.get("title") or "")
        add_candidate(
            classification="unmanaged",
            doc_id=None,
            display_hint=title,
            source_id_hash=row.get("source_id_hash"),
            evidence="Remote source title is not a Vibe-managed identity for current project/SSOT",
            delete_eligibility="manual_only",
            why_not_auto_delete="Unmanaged sources must never be auto-deleted by vibe CLI",
            managed_name_hint=None,
        )

    next_actions: list[dict[str, Any]] = [
        next_action(
            code="STATUS",
            command="vibe knowledge status --json",
            mutation=False,
            reason="Confirm current ProviderTarget sync_state",
        ),
        next_action(
            code="SYNC_DRY_RUN",
            command="vibe knowledge sync --dry-run --json",
            mutation=False,
            reason="Confirm current SSOT required_updates_count",
        ),
    ]
    if candidates:
        next_actions.append(
            next_action(
                code="MANUAL_CLEANUP_REVIEW",
                command="vibe knowledge cleanup-candidates --json",
                mutation=False,
                reason="Review candidates; delete only manually in provider UI when confirmed non-SSOT",
            )
        )
        if any(c.get("delete_eligibility") == "receipt_owned_apply_possible" for c in candidates):
            next_actions.append(
                next_action(
                    code="BOUNDED_APPLY_PENDING",
                    command="vibe knowledge sync --dry-run --json",
                    mutation=False,
                    reason=(
                        "Receipt-owned cleanup_pending may be cleaned only by explicit "
                        "approved sync/retry --apply (not this command)"
                    ),
                )
            )
    else:
        next_actions.append(
            next_action(
                code="NO_CLEANUP_NEEDED",
                command="vibe knowledge status --json",
                mutation=False,
                reason="No manual cleanup candidates for current target",
            )
        )

    mode = "readonly"
    if sync_state in {"unavailable", "pending", "drift"}:
        mode = sync_state
    elif sync_state == "receipt_missing":
        mode = "degraded"

    orphan_count = sum(1 for c in candidates if c.get("classification") == "orphan_managed")
    ask_hygiene = evaluate_ask_hygiene(
        sync_state=sync_state,
        required_updates_count=int(dry.get("required_updates_count") or 0),
        candidate_count=len(candidates),
        orphan_managed_count=orphan_count,
    )
    warnings: list[str] = []
    if not ask_hygiene["provider_ask_clean"] and ask_hygiene["condition"] == "orphan_pollution":
        warnings.append(
            "Provider-backed ask is polluted until listed old sources are manually removed "
            "(or owner explicitly accepts the risk)"
        )
        next_actions.insert(
            0,
            next_action(
                code="ASK_POLLUTION",
                command="vibe knowledge cleanup-candidates --json",
                mutation=False,
                reason="Do not declare provider-backed ask clean while candidate_count > 0",
            ),
        )

    return {
        "ok": True,
        "mode": mode,
        "provider": target.provider,
        "target_key_hash": target.target_key_hash,
        "mutation": False,
        "data": {
            "sync_state": sync_state,
            "synced": bool(dry.get("synced")),
            "required_updates_count": int(dry.get("required_updates_count") or 0),
            "current_ssot_doc_ids": current_ssot_doc_ids,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "ask_hygiene": ask_hygiene,
            "planner": "phase8",
            "notebook_alias": target.notebook_alias,
            "snapshot_hash": dry.get("snapshot_hash"),
        },
        "warnings": warnings,
        "next_actions": next_actions,
    }
