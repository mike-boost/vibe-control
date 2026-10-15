"""Readonly knowledge doctor and init-preview aggregators (Phase 10.5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vibe_control.config import (
    ConfigError,
    ControlConfig,
    load_config,
    primary_control_path,
    legacy_control_path,
    template_path,
    validate_config,
)
from vibe_control.json_envelope import next_action
from vibe_control.knowledge.corpus import CorpusError, build_desired_corpus
from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider
from vibe_control.knowledge.notebooks import (
    NotebookError,
    list_notebooks,
    resolve_default_alias,
    resolve_notebook_ref,
    resolve_operation_alias,
    get_notebook_entry,
)
from vibe_control.knowledge.pending_sync import pending_sync_exists
from vibe_control.knowledge.provider_target import ProviderTarget
from vibe_control.knowledge.receipt_scope import load_or_migrate_receipt
from vibe_control.knowledge.snapshot import build_desired_snapshot


def _provider_import_ok() -> dict[str, Any]:
    try:
        from vibe_control.knowledge import notebooklm_provider as _nlm  # noqa: F401

        return {"ok": True, "module": "vibe_control.knowledge.notebooklm_provider"}
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "error": str(exc)}


def _build_snapshot_info(
    config: ControlConfig,
    repo_root: Path,
    *,
    notebook_alias: str | None = None,
) -> dict[str, Any]:
    try:
        from vibe_control.knowledge.corpus import resolve_corpus_for_target

        corpus, sync_scope = resolve_corpus_for_target(
            config,
            notebook_alias=notebook_alias,
            repo_root=repo_root,
        )
        snap = build_desired_snapshot(
            project_id=config.project_id,
            sync_scope=sync_scope,
            documents=[{"doc_id": d.doc_id, "path": d.path} for d in corpus.documents],
            repo_root=repo_root,
        )
        return {
            "build_ok": True,
            "snapshot_hash": snap.snapshot_hash,
            "item_count": len(snap.items),
            "sync_scope": sync_scope,
            "notebook_alias": corpus.notebook_alias or notebook_alias,
            "selector_summary": dict(corpus.selector_summary or {}),
            "error": None,
        }
    except (CorpusError, OSError, ValueError) as exc:
        code = getattr(exc, "code", None) or "SNAPSHOT_BUILD_FAILED"
        return {
            "build_ok": False,
            "snapshot_hash": None,
            "item_count": 0,
            "error": {"code": code, "message": str(getattr(exc, "message", exc))},
        }


def _local_sync_signals(
    *,
    config: ControlConfig,
    repo_root: Path,
    alias: str | None,
) -> dict[str, Any]:
    """Shallow sync summary: no remote list_sources / provider mutation."""
    out: dict[str, Any] = {
        "sync_state": "unavailable",
        "synced": False,
        "code": None,
        "reasons": [],
        "receipt_present": False,
        "pending_sync_present": False,
        "target": None,
        "probe": "skipped_shallow",
    }
    try:
        resolved = resolve_default_alias(config, alias)
        entry = get_notebook_entry(config, resolved)
        ref, _ = resolve_notebook_ref(config, resolved, repo_root=repo_root)
        if not ref:
            out["code"] = "NOTEBOOK_REF_MISSING"
            out["reasons"] = [f"ref env missing for alias {resolved}"]
            return out
        target = ProviderTarget.from_ref(
            provider="notebooklm",
            notebook_alias=entry.alias,
            notebook_ref=ref,
        )
        out["target"] = target.to_dict()
        receipt_result = load_or_migrate_receipt(config.project_id, target)
        if not receipt_result.ok and receipt_result.code == "TARGET_MISMATCH":
            out["sync_state"] = "target_mismatch"
            out["code"] = "TARGET_MISMATCH"
            out["reasons"] = [receipt_result.message or "target mismatch"]
            return out
        receipt = receipt_result.data
        out["receipt_present"] = receipt is not None
        pending = pending_sync_exists(config.project_id, target)
        out["pending_sync_present"] = pending
        if receipt is None:
            out["sync_state"] = "receipt_missing"
            out["code"] = "RECEIPT_MISSING"
            out["reasons"] = ["receipt missing"]
            return out
        if pending:
            out["sync_state"] = "pending"
            out["code"] = "PENDING_SYNC_EXISTS"
            out["reasons"] = ["pending-sync.json present"]
            return out
        # Without remote probe, do not claim synced.
        out["sync_state"] = "drift"
        out["code"] = "DRIFT_EXISTS"
        out["reasons"] = [
            "shallow doctor: receipt present but remote probe skipped; run vibe knowledge status --json"
        ]
        return out
    except NotebookError as exc:
        out["code"] = exc.code
        out["reasons"] = [exc.message]
        return out
    except Exception as exc:  # pragma: no cover
        out["reasons"] = [str(exc)]
        return out


def build_knowledge_doctor(
    *,
    repo_root: Path,
    alias: str | None = None,
    deep: bool = False,
    notebooklm: NotebookLMProvider | None = None,
) -> dict[str, Any]:
    """Readonly knowledge domain precheck. Shallow by default (no remote inventory)."""
    root = repo_root
    primary = primary_control_path(root)
    legacy = legacy_control_path(root)
    config_exists = primary.is_file() or legacy.is_file()
    next_actions: list[dict[str, Any]] = []
    warnings: list[str] = []
    codes: list[str] = []

    data: dict[str, Any] = {
        "depth": "shallow",
        "deep_requested": bool(deep),
        "deep_supported": False,  # deferred: expensive remote probe not wired
        "config": {
            "exists": config_exists,
            "path": (primary if primary.is_file() else legacy if legacy.is_file() else primary).as_posix(),
            "primary_path": primary.as_posix(),
            "legacy_path": legacy.as_posix(),
            "valid": False,
            "errors": [],
        },
        "project_id": None,
        "provider": {
            "configured": False,
            "name": None,
            "adapter_import": _provider_import_ok(),
            "binary": None,
        },
        "notebook": {
            "allow_list_present": False,
            "default_alias": None,
            "default_alias_resolves": False,
            "ref_env": None,
            "ref_env_present": False,
        },
        "auth": {},
        "desired_snapshot": {
            "build_ok": False,
            "snapshot_hash": None,
            "item_count": 0,
            "error": None,
        },
        "receipt": {"present": False},
        "pending_sync": {"present": False},
        "sync": {},
        "ready": False,
        "codes": codes,
    }

    if deep:
        warnings.append(
            "knowledge doctor --deep is defined but deferred; running shallow checks only"
        )

    if not config_exists:
        codes.append("CONFIG_NOT_FOUND")
        next_actions.append(
            next_action(
                code="CONFIG_NOT_FOUND",
                command="vibe knowledge init-preview --json",
                mutation=False,
                reason="Primary or legacy control config is missing",
            )
        )
        next_actions.append(
            next_action(
                code="CONFIG_NOT_FOUND",
                command=f"cp {template_path().as_posix()} {primary.as_posix()}",
                mutation=False,
                reason="Copy template to create .config/vibe-control.yaml",
            )
        )
        data["codes"] = codes
        return {"data": data, "warnings": warnings, "next_actions": next_actions, "ok": False}

    try:
        config = load_config(root)
    except ConfigError as exc:
        codes.append(exc.code if exc.code else "CONFIG_INVALID")
        data["config"]["errors"] = [exc.message]
        next_actions.append(
            next_action(
                code=exc.code or "CONFIG_INVALID",
                command="vibe knowledge init-preview --json",
                mutation=False,
                reason=exc.message,
            )
        )
        data["codes"] = codes
        return {"data": data, "warnings": warnings, "next_actions": next_actions, "ok": False}

    data["project_id"] = config.project_id
    data["config"]["path"] = config.path.as_posix()
    errors = validate_config(config)
    data["config"]["valid"] = not errors
    data["config"]["errors"] = list(errors)
    if errors:
        codes.append("CONFIG_INVALID")
        next_actions.append(
            next_action(
                code="CONFIG_INVALID",
                command="vibe config validate --json",
                mutation=False,
                reason="Config validation failed",
            )
        )

    provider_name = str(config.knowledge.get("provider") or "")
    data["provider"]["configured"] = bool(provider_name)
    data["provider"]["name"] = provider_name or None
    if not provider_name:
        codes.append("PROVIDER_UNAVAILABLE")
        next_actions.append(
            next_action(
                code="PROVIDER_UNAVAILABLE",
                command="vibe knowledge init-preview --json",
                mutation=False,
                reason="knowledge.provider is not configured",
            )
        )

    # local_fts: independent doctor path (no NotebookLM binary/auth/notebook refs).
    if provider_name.strip().lower() == "local_fts":
        from vibe_control.knowledge.local_fts.provider import LocalFtsProvider
        from vibe_control.knowledge.local_fts.store import probe_sqlite_fts5

        data["provider"]["adapter_import"] = {
            "ok": True,
            "module": "vibe_control.knowledge.local_fts.provider",
        }
        sqlite_probe = probe_sqlite_fts5()
        data["provider"]["binary"] = {
            "installed": bool(sqlite_probe.get("ok")),
            "path": None,
            "message": sqlite_probe.get("message"),
            "auth_checked": False,
            "auth_state": "not_applicable",
        }
        data["auth"] = {
            "auth_state": "not_applicable",
            "message": "local_fts requires no remote auth",
            **sqlite_probe,
        }
        data["notebook"] = {
            "allow_list_present": False,
            "default_alias": None,
            "default_alias_resolves": True,
            "ref_env": None,
            "ref_env_present": False,
            "note": "not required for local_fts",
        }
        data["desired_snapshot"] = _build_snapshot_info(config, root, notebook_alias=alias)
        status = LocalFtsProvider().status(config, repo_root=root, notebook_alias=alias)
        index = status.get("index") or {}
        garbage = status.get("fts_garbage") or {}
        data["local_fts"] = {
            "index_exists": bool(index.get("exists")),
            "path": index.get("path"),
            "index_bytes": index.get("index_bytes"),
            "schema_ok": status.get("sync_state") != "unavailable",
            "sync_state": status.get("sync_state"),
            "desired_fingerprint": index.get("desired_fingerprint"),
            "index_fingerprint": index.get("index_fingerprint"),
            "document_count": index.get("document_count"),
            "chunk_count": index.get("chunk_count"),
            "chunking_version": index.get("chunking_version"),
            "fts_garbage": garbage,
            "sqlite": sqlite_probe,
        }
        data["sync"] = {
            "sync_state": status.get("sync_state"),
            "synced": status.get("sync_state") == "synced",
            "provider_ask_clean": status.get("provider_ask_clean"),
            "ask_hygiene": status.get("ask_hygiene"),
        }
        data["receipt"] = {"present": False, "note": "local_fts uses index meta, not NLM receipt"}
        data["pending_sync"] = {"present": False}
        if not sqlite_probe.get("ok"):
            codes.append("PROVIDER_UNAVAILABLE")
            next_actions.extend(list(status.get("next_actions") or []))
        elif status.get("sync_state") != "synced":
            codes.append("SYNC_NOT_CLEAN")
            next_actions.extend(list(status.get("next_actions") or []))
        data["ready"] = (
            not errors
            and bool(sqlite_probe.get("ok"))
            and status.get("sync_state") == "synced"
            and bool(status.get("provider_ask_clean"))
        )
        data["codes"] = codes
        return {
            "data": data,
            "warnings": warnings,
            "next_actions": next_actions,
            "ok": data["ready"],
        }

    nlm = notebooklm or NotebookLMProvider()
    binary = nlm.status(probe_auth=False)
    data["provider"]["binary"] = binary.to_dict()
    if not binary.installed:
        codes.append("PROVIDER_UNAVAILABLE")
        next_actions.append(
            next_action(
                code="PROVIDER_UNAVAILABLE",
                command="vibe knowledge login-guide --json",
                mutation=False,
                reason="NotebookLM CLI binary not found on PATH",
            )
        )

    # Safe existing auth check (passive); not a remote source inventory.
    auth = nlm.auth_check() if binary.installed else binary
    data["auth"] = auth.to_dict()
    if binary.installed and auth.auth_state in {
        "auth_failed",
        "command_failed",
        "command_unsupported",
    }:
        codes.append("AUTH_MISSING")
        next_actions.append(
            next_action(
                code="AUTH_MISSING",
                command="vibe knowledge login-guide --json",
                mutation=False,
                reason=f"Auth state is {auth.auth_state}",
            )
        )
        next_actions.append(
            next_action(
                code="AUTH_MISSING",
                command="vibe knowledge auth-status --json",
                mutation=False,
                reason="Re-check auth after login",
            )
        )

    try:
        nb = list_notebooks(config, repo_root=root)
        allow = nb.get("allow_list") or []
        data["notebook"]["allow_list_present"] = bool(allow)
        data["notebook"]["default_alias"] = nb.get("default_alias") or None
        if not allow or not nb.get("default_alias"):
            codes.append("NOTEBOOK_ALIAS_UNRESOLVED")
            next_actions.append(
                next_action(
                    code="NOTEBOOK_ALIAS_UNRESOLVED",
                    command="vibe knowledge init-preview --json",
                    mutation=False,
                    reason="Notebook allow_list or default_alias missing",
                )
            )
        else:
            try:
                resolved = resolve_operation_alias(config, alias)
                entry = get_notebook_entry(config, resolved)
                ref, source = resolve_notebook_ref(config, resolved, repo_root=root)
                data["notebook"]["default_alias_resolves"] = True
                data["notebook"]["resolved_alias"] = resolved
                data["notebook"]["ref_env"] = entry.ref_env
                data["notebook"]["ref_env_present"] = bool(ref)
                data["notebook"]["ref_source"] = source
                if not ref:
                    codes.append("NOTEBOOK_REF_MISSING")
                    next_actions.append(
                        next_action(
                            code="NOTEBOOK_REF_MISSING",
                            command="vibe knowledge init-preview --json",
                            mutation=False,
                            reason=f"Set {entry.ref_env} via env or .config/.env",
                        )
                    )
            except NotebookError as exc:
                codes.append(exc.code if exc.code else "NOTEBOOK_ALIAS_UNRESOLVED")
                data["notebook"]["default_alias_resolves"] = False
                next_actions.append(
                    next_action(
                        code=exc.code if exc.code else "NOTEBOOK_ALIAS_UNRESOLVED",
                        command=(
                            "vibe knowledge doctor --notebook <alias> --json"
                            if exc.code == "NOTEBOOK_ALIAS_REQUIRED"
                            else "vibe knowledge init-preview --json"
                        ),
                        mutation=False,
                        reason=exc.message,
                    )
                )
    except NotebookError as exc:
        codes.append("NOTEBOOK_ALIAS_UNRESOLVED")
        next_actions.append(
            next_action(
                code="NOTEBOOK_ALIAS_UNRESOLVED",
                command="vibe knowledge init-preview --json",
                mutation=False,
                reason=exc.message,
            )
        )

    resolved_for_corpus = None
    try:
        if isinstance(config.knowledge.get("notebooks"), dict) and (
            data.get("notebook") or {}
        ).get("allow_list_present"):
            resolved_for_corpus = resolve_operation_alias(config, alias)
    except NotebookError:
        resolved_for_corpus = None
    data["desired_snapshot"] = _build_snapshot_info(
        config, root, notebook_alias=resolved_for_corpus
    )

    from vibe_control.knowledge.source_quota import assess_source_quota

    quota = assess_source_quota(
        max_sources=config.knowledge.get("max_sources"),
        warn_sources=config.knowledge.get("warn_sources"),
        desired_count=int((data["desired_snapshot"] or {}).get("item_count") or 0),
        remote_source_count=None,
        provider=str(config.knowledge.get("provider") or "notebooklm"),
    )
    data["source_quota"] = quota
    for w in quota.get("warnings") or []:
        if w not in warnings:
            warnings.append(w)
    if "MAX_SOURCES_EXCEEDS_NOTEBOOKLM_STANDARD" in (quota.get("codes") or []):
        next_actions.append(
            next_action(
                code="REVIEW_SOURCE_QUOTA",
                command="vibe knowledge inventory --json",
                mutation=False,
                reason=(
                    "max_sources exceeds NotebookLM Standard (50/notebook); "
                    "confirm account plan or lower knowledge.max_sources"
                ),
            )
        )

    sync = _local_sync_signals(config=config, repo_root=root, alias=alias)
    data["sync"] = sync
    data["receipt"]["present"] = bool(sync.get("receipt_present"))
    data["pending_sync"]["present"] = bool(sync.get("pending_sync_present"))

    sync_code = sync.get("code")
    if sync_code == "RECEIPT_MISSING":
        codes.append("RECEIPT_MISSING")
        next_actions.append(
            next_action(
                code="RECEIPT_MISSING",
                command="vibe knowledge status --json",
                mutation=False,
                reason="Binding receipt missing for resolved ProviderTarget",
            )
        )
        next_actions.append(
            next_action(
                code="RECEIPT_MISSING",
                command="vibe knowledge sync --dry-run --json",
                mutation=False,
                reason="Preview sync plan before any apply",
            )
        )
    elif sync_code == "PENDING_SYNC_EXISTS":
        codes.append("PENDING_SYNC_EXISTS")
        next_actions.append(
            next_action(
                code="PENDING_SYNC_EXISTS",
                command="vibe knowledge status --json",
                mutation=False,
                reason="pending-sync.json present",
            )
        )
        next_actions.append(
            next_action(
                code="PENDING_SYNC_EXISTS",
                command="vibe knowledge retry --dry-run --json",
                mutation=False,
                reason="Preview retry before explicit --apply",
            )
        )
    elif sync_code == "TARGET_MISMATCH":
        codes.append("TARGET_MISMATCH")
        next_actions.append(
            next_action(
                code="TARGET_MISMATCH",
                command="vibe knowledge status --json",
                mutation=False,
                reason="Receipt ProviderTarget mismatch; do not mutate wrong notebook",
            )
        )
    elif sync_code == "DRIFT_EXISTS":
        codes.append("DRIFT_EXISTS")
        next_actions.append(
            next_action(
                code="DRIFT_EXISTS",
                command="vibe knowledge status --json",
                mutation=False,
                reason="Shallow check cannot confirm synced; run status",
            )
        )
        next_actions.append(
            next_action(
                code="DRIFT_EXISTS",
                command="vibe knowledge sync --dry-run --json",
                mutation=False,
                reason="Preview sync if user intends to converge",
            )
        )
    elif sync_code == "NOTEBOOK_REF_MISSING" and "NOTEBOOK_REF_MISSING" not in codes:
        codes.append("NOTEBOOK_REF_MISSING")

    blocking = {
        "CONFIG_NOT_FOUND",
        "CONFIG_INVALID",
        "PROVIDER_UNAVAILABLE",
        "NOTEBOOK_ALIAS_UNRESOLVED",
        "NOTEBOOK_REF_MISSING",
        "AUTH_MISSING",
        "TARGET_MISMATCH",
    }
    ready = not any(c in blocking for c in codes) and data["config"]["valid"]
    # receipt/pending/drift do not make doctor "not ready" for querying via fallback,
    # but they prevent KNOWLEDGE_READY claim.
    knowledge_ready = ready and sync_code not in {
        "RECEIPT_MISSING",
        "PENDING_SYNC_EXISTS",
        "DRIFT_EXISTS",
        "TARGET_MISMATCH",
        "NOTEBOOK_REF_MISSING",
    }
    data["ready"] = knowledge_ready
    if knowledge_ready:
        codes.append("KNOWLEDGE_READY")
        next_actions.append(
            next_action(
                code="KNOWLEDGE_READY",
                command="vibe knowledge status --json",
                mutation=False,
                reason="Shallow precheck passed; confirm with status before claiming synced",
            )
        )

    data["codes"] = list(dict.fromkeys(codes))
    # Deduplicate next_actions by (code, command)
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for item in next_actions:
        key = (str(item.get("code")), str(item.get("command")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return {
        "data": data,
        "warnings": warnings,
        "next_actions": deduped,
        "ok": config_exists and data["config"]["valid"],
        "project_id": config.project_id,
    }


def build_knowledge_init_preview(
    *,
    repo_root: Path,
    alias: str | None = None,
    notebooklm: NotebookLMProvider | None = None,
) -> dict[str, Any]:
    """Readonly setup plan derived from doctor signals. Never mutates."""
    doctor = build_knowledge_doctor(
        repo_root=repo_root,
        alias=alias,
        deep=False,
        notebooklm=notebooklm,
    )
    data = doctor["data"]
    steps: list[dict[str, Any]] = []
    codes = list(data.get("codes") or [])

    def add_step(code: str, command: str, reason: str, *, mutation: bool = False) -> None:
        steps.append(
            next_action(code=code, command=command, mutation=mutation, reason=reason)
        )

    if "CONFIG_NOT_FOUND" in codes or not data["config"]["exists"]:
        add_step(
            "CONFIG_NOT_FOUND",
            "vibe config validate --json",
            "Create .config/vibe-control.yaml from template, then validate",
        )
    if "CONFIG_INVALID" in codes:
        add_step("CONFIG_INVALID", "vibe config validate --json", "Fix validation errors")
    if "NOTEBOOK_ALIAS_UNRESOLVED" in codes:
        add_step(
            "NOTEBOOK_ALIAS_UNRESOLVED",
            "vibe knowledge init-preview --json",
            "Configure knowledge.notebooks.allow_list and default_alias",
        )
    if "NOTEBOOK_REF_MISSING" in codes:
        add_step(
            "NOTEBOOK_REF_MISSING",
            "vibe knowledge init-preview --json",
            "Export notebook ref env or write ignored .config/.env",
        )
    if "AUTH_MISSING" in codes or "PROVIDER_UNAVAILABLE" in codes:
        add_step("AUTH_MISSING", "vibe knowledge login-guide --json", "Follow login guidance")
        add_step("AUTH_MISSING", "vibe knowledge auth-status --json", "Verify auth after login")
    if "RECEIPT_MISSING" in codes:
        add_step("RECEIPT_MISSING", "vibe knowledge status --json", "Inspect sync state")
        add_step(
            "RECEIPT_MISSING",
            "vibe knowledge sync --dry-run --json",
            "Preview sync plan (no mutation)",
        )
        add_step(
            "RECEIPT_MISSING",
            "vibe knowledge sync --apply --json",
            "Apply sync only after explicit user approval",
            mutation=True,
        )
    if "PENDING_SYNC_EXISTS" in codes:
        add_step("PENDING_SYNC_EXISTS", "vibe knowledge status --json", "Confirm pending sync")
        add_step(
            "PENDING_SYNC_EXISTS",
            "vibe knowledge retry --dry-run --json",
            "Preview retry (no mutation)",
        )
        add_step(
            "PENDING_SYNC_EXISTS",
            "vibe knowledge retry --apply --json",
            "Apply retry only after explicit user approval",
            mutation=True,
        )
    if "DRIFT_EXISTS" in codes:
        add_step("DRIFT_EXISTS", "vibe knowledge status --json", "Inspect drift for ProviderTarget")
        add_step(
            "DRIFT_EXISTS",
            "vibe knowledge sync --dry-run --json",
            "Preview convergence plan",
        )
        add_step(
            "DRIFT_EXISTS",
            "vibe knowledge sync --apply --json",
            "Apply sync only after explicit user approval",
            mutation=True,
        )
    if "TARGET_MISMATCH" in codes:
        add_step(
            "TARGET_MISMATCH",
            "vibe knowledge status --json",
            "Fail closed: resolve ProviderTarget mismatch before any mutation",
        )

    if not steps:
        add_step(
            "KNOWLEDGE_READY",
            "vibe knowledge status --json",
            "No blocking setup steps; confirm status before query/sync",
        )

    from vibe_control.components import (
        build_component_adoption_detection,
        build_component_config_guidance,
        build_component_provider_boundaries,
    )

    guidance = build_component_config_guidance()
    adoption = build_component_adoption_detection()
    boundaries = build_component_provider_boundaries()

    return {
        "data": {
            "doctor": data,
            "steps": steps,
            "mutation_steps": [s for s in steps if s.get("mutation")],
            "readonly_steps": [s for s in steps if not s.get("mutation")],
            "components": guidance["components"],
            "component_config_example": guidance["component_config_example"],
            "component_config_example_yaml": guidance["component_config_example_yaml"],
            "component_config_guidance": guidance["component_config_guidance"],
            "profile_preview": dict(guidance.get("profile_preview") or {}),
            "capability_guidance": dict(guidance.get("capability_guidance") or {}),
            "enable_examples": list(guidance.get("enable_examples") or []),
            "invalid_examples": guidance["invalid_examples"],
            "component_adoption": adoption["component_adoption"],
            "adoption_performed": False,
            "provider_boundaries": boundaries["provider_boundaries"],
            "live_integration": False,
            "mutation_allowed": False,
            "requires_future_acceptance": True,
            "fail_closed": True,
            "readiness_effect": "none",
            "diagnostic_only": True,
            "mutation": False,
            "auto_enable": False,
            "install_adapt_uninstall": False,
        },
        "warnings": list(doctor.get("warnings") or []),
        "next_actions": list(guidance.get("next_actions") or [])
        + [s for s in steps if not s.get("mutation")],
        "ok": True,
        "mutation": False,
        "project_id": doctor.get("project_id") or data.get("project_id"),
    }
