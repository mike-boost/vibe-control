"""Phase 4 knowledge notebook / remote / sync / seed command handlers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vibe_control.config import ConfigError, ControlConfig, load_config
from vibe_control.json_envelope import (
    attach_operation_result,
    failure_envelope,
    success_envelope,
)
from vibe_control.knowledge.corpus import CorpusError, build_desired_corpus, resolve_desired_corpus
from vibe_control.knowledge.notebooklm_provider import NotebookLMProvider
from vibe_control.knowledge.notebooks import (
    NotebookError,
    list_notebooks,
    notebook_status,
    require_notebook_ref,
    set_default_alias,
    set_default_alias_preview,
)
from vibe_control.knowledge.sync_preview import (
    RemoteSource,
    build_sync_preview,
    classify_remote_inventory,
)


def _cfg(root: Path, args: Any) -> ControlConfig:
    config_path = getattr(args, "config", None)
    return load_config(root, config_path=config_path)


def _finish_knowledge_mutation(
    env: dict[str, Any],
    *,
    apply: bool,
    effects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Attach operation evidence; keep nested data.mutation aliases aligned."""
    out = attach_operation_result(
        env,
        mutation_intent=bool(apply),
        effects=effects or [],
    )
    performed = bool(out["mutation_performed"])
    data = out.get("data")
    if isinstance(data, dict):
        data["mutation"] = performed
    err = out.get("error")
    if isinstance(err, dict):
        details = err.get("details")
        if isinstance(details, dict):
            details["mutation"] = performed
    return out


def _effects_from_apply_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Prefer recorded effects; never invent provider writes from attempt counts."""
    child = result.get("effects")
    if isinstance(child, list):
        return [e for e in child if isinstance(e, dict)]
    return []


def _local_fts_sync_effects(*, apply: bool, data: dict[str, Any]) -> list[dict[str, Any]]:
    if not apply:
        return []
    if not data.get("ok"):
        return []
    # Rebuild (or equivalent retry) wrote the local index.
    if data.get("rebuild") is not None or data.get("mutation"):
        return [
            {
                "kind": "local_state_write",
                "target": "knowledge.local_fts",
                "status": "completed",
            }
        ]
    return []


def cmd_notebook_list(root: Path, args: Any) -> dict[str, Any]:
    try:
        config = _cfg(root, args)
        data = list_notebooks(config, repo_root=root)
    except (ConfigError, NotebookError) as exc:
        return failure_envelope(
            command="vibe knowledge notebook list",
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
    return success_envelope(
        command="vibe knowledge notebook list",
        project_id=config.project_id,
        data=data,
    )


def cmd_notebook_status(root: Path, args: Any) -> dict[str, Any]:
    try:
        config = _cfg(root, args)
        alias = getattr(args, "notebook", None)
        data = notebook_status(config, repo_root=root, alias=alias)
    except (ConfigError, NotebookError) as exc:
        return failure_envelope(
            command="vibe knowledge notebook status",
            code=exc.code,
            message=exc.message,
            details=exc.details,
            next_actions=list((exc.details or {}).get("next_actions") or []),
        )
    return success_envelope(
        command="vibe knowledge notebook status",
        project_id=config.project_id,
        data=data,
        next_actions=list(data.get("next_actions") or []),
    )


def cmd_notebook_set_default(root: Path, args: Any) -> dict[str, Any]:
    alias = args.alias
    dry_run = bool(getattr(args, "dry_run", False))
    try:
        config = _cfg(root, args)
        if dry_run:
            data = set_default_alias_preview(config, alias)
            data["dry_run"] = True
        else:
            data = set_default_alias(config, alias)
            data["dry_run"] = False
    except (ConfigError, NotebookError) as exc:
        return failure_envelope(
            command="vibe knowledge notebook set-default",
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
    return success_envelope(
        command="vibe knowledge notebook set-default",
        project_id=config.project_id,
        data=data,
    )


def cmd_remote_status(root: Path, args: Any) -> dict[str, Any]:
    provider = NotebookLMProvider()
    try:
        config = _cfg(root, args)
        alias = getattr(args, "notebook", None)
        status = notebook_status(config, repo_root=root, alias=alias)
        auth = provider.auth_check()
        configured = bool(status.get("ref_configured"))
        can_list = bool(provider.which()) and auth.auth_state == "available" and configured
        data = {
            "provider": "notebooklm",
            "installed": auth.installed,
            "auth_state": auth.auth_state,
            "notebook_alias": status.get("alias"),
            "notebook_configured": configured,
            "can_list_sources": can_list,
            "safe_to_sync": False,
            "ref_fingerprint": status.get("ref_fingerprint"),
        }
        if not configured:
            return failure_envelope(
                command="vibe knowledge remote-status",
                code="NOTEBOOKLM_NOT_CONFIGURED",
                message="Notebook ref is not configured",
                details=data,
                project_id=config.project_id,
                next_actions=list(status.get("next_actions") or []),
            )
        return success_envelope(
            command="vibe knowledge remote-status",
            project_id=config.project_id,
            data=data,
        )
    except (ConfigError, NotebookError) as exc:
        return failure_envelope(
            command="vibe knowledge remote-status",
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )


def _load_remote_sources(
    provider: NotebookLMProvider,
    notebook_ref: str,
) -> tuple[list[RemoteSource] | None, dict[str, Any] | None]:
    result = provider.list_sources(notebook_ref=notebook_ref)
    if not result.get("ok"):
        return None, result
    sources: list[RemoteSource] = []
    for item in result.get("sources") or []:
        title = str(item.get("title") or item.get("name") or "")
        source_id = item.get("id") or item.get("source_id")
        sources.append(
            RemoteSource(
                source_id=None if source_id is None else str(source_id),
                title=title,
                raw=item,
            )
        )
    return sources, None


def cmd_remote_inventory(root: Path, args: Any) -> dict[str, Any]:
    try:
        config = _cfg(root, args)
    except ConfigError as exc:
        return failure_envelope(
            command="vibe knowledge remote-inventory",
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
    if str(config.knowledge.get("provider") or "").strip().lower() == "local_fts":
        from vibe_control.json_envelope import next_action

        return success_envelope(
            command="vibe knowledge remote-inventory",
            project_id=config.project_id,
            data={
                "provider": "local_fts",
                "applicable": False,
                "message": (
                    "remote-inventory is NotebookLM-only; local_fts uses local indexes. "
                    "Use vibe knowledge inventory / status / fts-purge."
                ),
            },
            next_actions=[
                next_action(
                    code="LOCAL_FTS_USE_INVENTORY",
                    command="vibe knowledge inventory --json",
                    mutation=False,
                    reason="List desired corpus for local_fts",
                ),
                next_action(
                    code="LOCAL_FTS_PURGE_ORPHANS",
                    command="vibe knowledge fts-purge --dry-run --json",
                    mutation=False,
                    reason="Review/purge stale local_fts index dirs",
                ),
            ],
        )

    provider = NotebookLMProvider()
    try:
        from vibe_control.knowledge.receipt import load_receipt_dict

        alias = getattr(args, "notebook", None)
        entry, ref = require_notebook_ref(config, repo_root=root, alias=alias)
        corpus = resolve_desired_corpus(
            config, notebook_alias=entry.alias, repo_root=root
        )
        sources, err = _load_remote_sources(provider, ref)
        if err is not None:
            return failure_envelope(
                command="vibe knowledge remote-inventory",
                code=err.get("code") or "NOTEBOOKLM_COMMAND_FAILED",
                message=err.get("message") or "remote inventory failed",
                details={"provider_error": err, "notebook_alias": entry.alias},
                project_id=config.project_id,
            )
        assert sources is not None
        receipt = load_receipt_dict(config.project_id)
        classified = classify_remote_inventory(
            sources,
            project_id=config.project_id,
            desired_doc_ids={d.doc_id for d in corpus.documents},
            path_hints={d.doc_id: d.path for d in corpus.documents},
            receipt=receipt,
        )
        return success_envelope(
            command="vibe knowledge remote-inventory",
            project_id=config.project_id,
            data={
                "notebook_alias": entry.alias,
                "provider": "notebooklm",
                "desired_count": corpus.source_count,
                **classified,
            },
            warnings=corpus.warnings,
        )
    except (ConfigError, NotebookError, CorpusError) as exc:
        return failure_envelope(
            command="vibe knowledge remote-inventory",
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )


def cmd_sync_preview(root: Path, args: Any) -> dict[str, Any]:
    provider = NotebookLMProvider()
    try:
        from vibe_control.knowledge.receipt import load_receipt_dict

        config = _cfg(root, args)
        alias = getattr(args, "notebook", None) or None
        receipt = load_receipt_dict(config.project_id)
        try:
            entry, ref = require_notebook_ref(config, repo_root=root, alias=alias)
        except NotebookError as exc:
            preview = build_sync_preview(
                config,
                repo_root=root,
                notebook_alias=str(getattr(args, "notebook", None) or "unresolved"),
                remote_sources=None,
                blocked_reason=exc.code,
                receipt=receipt,
            )
            return success_envelope(
                command="vibe knowledge sync-preview",
                project_id=config.project_id,
                data=preview,
                warnings=[exc.message],
                next_actions=list((exc.details or {}).get("next_actions") or []),
            )
        sources, err = _load_remote_sources(provider, ref)
        if err is not None:
            preview = build_sync_preview(
                config,
                repo_root=root,
                notebook_alias=entry.alias,
                remote_sources=None,
                blocked_reason=err.get("code") or "NOTEBOOKLM_COMMAND_FAILED",
                receipt=receipt,
            )
            return success_envelope(
                command="vibe knowledge sync-preview",
                project_id=config.project_id,
                data=preview,
                warnings=[err.get("message") or "remote list failed"],
            )
        assert sources is not None
        preview = build_sync_preview(
            config,
            repo_root=root,
            notebook_alias=entry.alias,
            remote_sources=sources,
            receipt=receipt,
        )
        return success_envelope(
            command="vibe knowledge sync-preview",
            project_id=config.project_id,
            data=preview,
            warnings=preview.get("warnings") or [],
        )
    except (ConfigError, CorpusError) as exc:
        return failure_envelope(
            command="vibe knowledge sync-preview",
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )


def cmd_seed_test_sources(root: Path, args: Any) -> dict[str, Any]:
    dry_run = bool(getattr(args, "dry_run", False))
    allow_add = bool(getattr(args, "allow_add", False))
    if not dry_run and not allow_add:
        return failure_envelope(
            command="vibe knowledge seed-test-sources",
            code="SEED_REQUIRES_ALLOW_ADD",
            message="Real seed requires --allow-add (or use --dry-run)",
            next_actions=[
                "python -m vibe_control knowledge seed-test-sources --notebook OPM-test --dry-run --json",
                "python -m vibe_control knowledge seed-test-sources --notebook OPM-test --allow-add --json",
            ],
        )

    provider = NotebookLMProvider()
    try:
        from vibe_control.knowledge import verified_add

        config = _cfg(root, args)
        alias = getattr(args, "notebook", None)
        entry, ref = require_notebook_ref(config, repo_root=root, alias=alias)
        result = verified_add.plan_or_run(
            config,
            repo_root=root,
            notebook_alias=entry.alias,
            notebook_ref=ref,
            provider=provider,
            dry_run=dry_run,
            allow_add=allow_add,
        )
        if result.get("ok"):
            return success_envelope(
                command="vibe knowledge seed-test-sources",
                project_id=config.project_id,
                data=result.get("data") or {},
            )
        return failure_envelope(
            command="vibe knowledge seed-test-sources",
            code=str(result.get("code") or "SEED_FAILED"),
            message=str(result.get("message") or "seed failed"),
            details=result.get("data") or {},
            project_id=config.project_id,
            partial_success=bool(result.get("partial_success")),
        )
    except (ConfigError, NotebookError, CorpusError) as exc:
        return failure_envelope(
            command="vibe knowledge seed-test-sources",
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )


def cmd_receipt_status(root: Path, args: Any) -> dict[str, Any]:
    try:
        from vibe_control.knowledge import receipt as receipt_mod

        config = _cfg(root, args)
        data = receipt_mod.status(config.project_id)
        if not data.get("ok"):
            return failure_envelope(
                command="vibe knowledge receipt status",
                code=str(data.get("code") or "RECEIPT_ERROR"),
                message=str(data.get("message") or "receipt error"),
                details=data,
                project_id=config.project_id,
                next_actions=list(data.get("next_actions") or []),
            )
        return success_envelope(
            command="vibe knowledge receipt status",
            project_id=config.project_id,
            data=data,
            warnings=list(data.get("warnings") or []),
        )
    except ConfigError as exc:
        return failure_envelope(
            command="vibe knowledge receipt status",
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )


def cmd_receipt_inspect(root: Path, args: Any) -> dict[str, Any]:
    try:
        from vibe_control.knowledge import receipt as receipt_mod

        config = _cfg(root, args)
        data = receipt_mod.inspect(config.project_id, report_mode=True)
        if not data.get("ok"):
            return failure_envelope(
                command="vibe knowledge receipt inspect",
                code=str(data.get("code") or "RECEIPT_ERROR"),
                message=str(data.get("message") or "receipt error"),
                details=data,
                project_id=config.project_id,
                next_actions=list(data.get("next_actions") or []),
            )
        return success_envelope(
            command="vibe knowledge receipt inspect",
            project_id=config.project_id,
            data=data,
        )
    except ConfigError as exc:
        return failure_envelope(
            command="vibe knowledge receipt inspect",
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )


def cmd_source_wait(root: Path, args: Any) -> dict[str, Any]:
    provider = NotebookLMProvider()
    try:
        from vibe_control.knowledge.source_lifecycle import wait_for_source

        config = _cfg(root, args)
        alias = getattr(args, "notebook", None)
        entry, ref = require_notebook_ref(config, repo_root=root, alias=alias)
        source_id = str(args.source_id)
        timeout = float(getattr(args, "timeout", 120) or 120)
        interval = float(getattr(args, "interval", 3) or 3)
        result = wait_for_source(
            source_id,
            poll_status=lambda sid: _poll_status(provider, ref, sid),
            direct_wait=lambda sid, **kw: provider.wait_source(
                notebook_ref=ref,
                source_id=sid,
                timeout=kw.get("timeout", timeout),
                interval=kw.get("interval", interval),
            ),
            timeout_seconds=timeout,
            interval_seconds=interval,
        )
        # redact source id in report-facing payload fingerprint only
        public = dict(result)
        public["source_id_fingerprint"] = _fp_sid(source_id)
        public.pop("source_id", None)
        if result.get("ok"):
            return success_envelope(
                command="vibe knowledge source wait",
                project_id=config.project_id,
                data={"notebook_alias": entry.alias, **public},
            )
        return failure_envelope(
            command="vibe knowledge source wait",
            code=str(result.get("code") or "SOURCE_WAIT_FAILED"),
            message="source wait did not reach ready",
            details={"notebook_alias": entry.alias, **public},
            project_id=config.project_id,
        )
    except (ConfigError, NotebookError) as exc:
        return failure_envelope(
            command="vibe knowledge source wait",
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )


def cmd_knowledge_sync(root: Path, args: Any) -> dict[str, Any]:
    dry_run = bool(getattr(args, "dry_run", False))
    apply = bool(getattr(args, "apply", False))
    if not dry_run and not apply:
        from vibe_control.json_envelope import next_action

        return _finish_knowledge_mutation(
            failure_envelope(
                command="vibe knowledge sync",
                code="SYNC_REQUIRES_DRY_RUN_OR_APPLY",
                message="Pass --dry-run or --apply",
                next_actions=[
                    next_action(
                        code="SYNC_REQUIRES_DRY_RUN_OR_APPLY",
                        command="vibe knowledge sync --dry-run --json",
                        mutation=False,
                        reason="Preview sync plan",
                    ),
                    next_action(
                        code="SYNC_REQUIRES_DRY_RUN_OR_APPLY",
                        command="vibe knowledge sync --apply --json",
                        mutation=True,
                        reason="Apply sync only with explicit approval",
                    ),
                ],
            ),
            apply=False,
            effects=[],
        )

    try:
        config = _cfg(root, args)
    except ConfigError as exc:
        return _finish_knowledge_mutation(
            failure_envelope(
                command="vibe knowledge sync",
                code=exc.code,
                message=exc.message,
                details=exc.details,
            ),
            apply=apply,
            effects=[],
        )

    active = str(config.knowledge.get("provider") or "notebooklm").strip().lower()
    if active == "local_fts":
        from vibe_control.knowledge.local_fts.provider import LocalFtsProvider

        local = LocalFtsProvider()
        data = local.sync(
            config,
            repo_root=root,
            apply=apply and not dry_run,
            notebook_alias=getattr(args, "notebook", None),
        )
        # Closeout / ask-hygiene expect top-level operations list.
        plan = data.get("plan") or {}
        if "operations" not in data:
            data["operations"] = list(plan.get("ops") or [])
        data["required_updates_count"] = (
            len(data["operations"]) if data.get("sync_state") != "synced" else 0
        )
        effects = _local_fts_sync_effects(apply=apply and not dry_run, data=data)
        envelope = success_envelope(
            command="vibe knowledge sync",
            project_id=config.project_id,
            data=data,
            next_actions=list(data.get("next_actions") or []),
        )
        envelope["ok"] = bool(data.get("ok", True))
        return _finish_knowledge_mutation(
            envelope,
            apply=apply and not dry_run,
            effects=effects,
        )

    provider = NotebookLMProvider()
    try:
        from vibe_control.knowledge.ack_stores import NotebookLMNoteAckStore
        from vibe_control.knowledge.phase8_apply import apply_forward_sync
        from vibe_control.knowledge.provider_target import ProviderTarget

        alias = getattr(args, "notebook", None)
        entry, ref = require_notebook_ref(config, repo_root=root, alias=alias)
        from vibe_control.knowledge.notebooks import resolve_default_alias

        default_alias = resolve_default_alias(config)
        if (
            apply
            and entry.alias != default_alias
            and not bool(getattr(args, "confirm_non_default_sync", False))
        ):
            from vibe_control.json_envelope import next_action

            return _finish_knowledge_mutation(
                failure_envelope(
                    command="vibe knowledge sync",
                    code="NON_DEFAULT_NOTEBOOK_APPLY_REQUIRES_CONFIRM",
                    message=(
                        f"sync --apply for non-default notebook {entry.alias!r} "
                        "requires --confirm-non-default-sync (owner/task approval)"
                    ),
                    details={
                        "notebook_alias": entry.alias,
                        "default_alias": default_alias,
                    },
                    project_id=config.project_id,
                    next_actions=[
                        next_action(
                            code="NON_DEFAULT_NOTEBOOK_APPLY_REQUIRES_CONFIRM",
                            command=(
                                f"vibe knowledge sync --apply --notebook {entry.alias} "
                                "--confirm-non-default-sync --json"
                            ),
                            mutation=True,
                            reason="Re-run only after owner/task explicitly allows non-default apply",
                        ),
                        next_action(
                            code="SYNC_DRY_RUN_NON_DEFAULT",
                            command=(
                                f"vibe knowledge sync --dry-run --notebook {entry.alias} --json"
                            ),
                            mutation=False,
                            reason="Dry-run for non-default notebooks remains agent-autonomous",
                        ),
                    ],
                ),
                apply=True,
                effects=[],
            )
        if dry_run and not apply:
            from vibe_control.knowledge.ack_stores import LocalMirrorAckStore
            from vibe_control.knowledge.phase8_apply import plan_forward_sync_dry_run

            target = ProviderTarget.from_ref(
                provider="notebooklm", notebook_alias=entry.alias, notebook_ref=ref
            )
            dry = plan_forward_sync_dry_run(
                config,
                repo_root=root,
                target=target,
                notebook_ref=ref,
                provider=provider,
                ack_store=LocalMirrorAckStore(config.project_id),
            )
            if dry.get("ok"):
                from vibe_control.json_envelope import next_action

                env = success_envelope(
                    command="vibe knowledge sync",
                    project_id=config.project_id,
                    data=dry,
                    next_actions=[
                        next_action(
                            code="SYNC_FAIL_STOP_DEFAULT",
                            command="vibe knowledge sync --apply --json",
                            mutation=True,
                            reason=(
                                "Default fail_stop: stops on first item failure; "
                                "successful items are checkpointed (retry skips them)"
                            ),
                        ),
                        next_action(
                            code="SYNC_PARTIAL_CONTINUE",
                            command=(
                                "vibe knowledge sync --apply --continue-on-item-error --json"
                            ),
                            mutation=True,
                            reason=(
                                "Opt-in: continue after non-fatal item failures; "
                                "emits item_failures DLQ; never claims synced while failures remain"
                            ),
                        ),
                        next_action(
                            code="SYNC_BATCH_MULTI_WAIT",
                            command=(
                                "vibe knowledge sync --apply --batch-size 5 "
                                "--wait-mode multi --json"
                            ),
                            mutation=True,
                            reason=(
                                "CLI ingest only: micro-batch then concurrent waits "
                                "(does not parallelize uploads; default batch_size=1 serial)"
                            ),
                        ),
                        next_action(
                            code="SYNC_API_CONCURRENT_UPLOAD",
                            command=(
                                "vibe knowledge sync --apply --ingest-path api "
                                "--upload-concurrency 8 --batch-size 10 --json"
                            ),
                            mutation=True,
                            reason=(
                                "Multi-file throughput path: notebooklm-py concurrent "
                                "add_file(wait=False) + wait_for_sources"
                            ),
                        ),
                    ],
                )
                return _finish_knowledge_mutation(env, apply=False, effects=[])
            fail = failure_envelope(
                command="vibe knowledge sync",
                code=str(dry.get("code") or "SYNC_DRY_RUN_FAILED"),
                message=str(dry.get("message") or "sync dry-run failed"),
                details=dry,
                project_id=config.project_id,
            )
            return _finish_knowledge_mutation(fail, apply=False, effects=[])

        from vibe_control.knowledge.ack_stores import LocalMirrorAckStore
        from vibe_control.knowledge.ask_hygiene import assert_apply_ops_are_current_ssot_bounded
        from vibe_control.knowledge.phase8_apply import plan_forward_sync_dry_run

        target = ProviderTarget.from_ref(
            provider="notebooklm", notebook_alias=entry.alias, notebook_ref=ref
        )
        # Fail-closed: apply mutations must stay within current desired SSOT docs;
        # orphan/unmanaged deletes are never allowed via sync --apply.
        dry_guard = plan_forward_sync_dry_run(
            config,
            repo_root=root,
            target=target,
            notebook_ref=ref,
            provider=provider,
            ack_store=LocalMirrorAckStore(config.project_id),
        )
        corpus = resolve_desired_corpus(
            config, notebook_alias=entry.alias, repo_root=root
        )
        desired_ids = {d.doc_id for d in corpus.documents}
        bound = assert_apply_ops_are_current_ssot_bounded(
            dry_guard.get("operations") or [],
            desired_doc_ids=desired_ids,
        )
        if not bound.get("ok"):
            return _finish_knowledge_mutation(
                failure_envelope(
                    command="vibe knowledge sync",
                    code="APPLY_SCOPE_VIOLATION",
                    message="sync --apply refused: dry-run ops are not bounded to current SSOT",
                    details=bound,
                    project_id=config.project_id,
                ),
                apply=True,
                effects=[],
            )

        ack_store = NotebookLMNoteAckStore(
            config.project_id,
            provider,
            notebook_ref=ref,
            command="vibe knowledge sync --apply",
        )
        applied = apply_forward_sync(
            config,
            repo_root=root,
            target=target,
            notebook_ref=ref,
            provider=provider,
            ack_store=ack_store,
            command="vibe knowledge sync --apply",
            continue_on_item_error=bool(getattr(args, "continue_on_item_error", False)),
            batch_size=getattr(args, "batch_size", None),
            wait_mode=getattr(args, "wait_mode", None),
            ingest_path=getattr(args, "ingest_path", None),
            upload_concurrency=getattr(args, "upload_concurrency", None),
        )
        effects = _effects_from_apply_result(applied)
        if applied.get("ok"):
            env = success_envelope(
                command="vibe knowledge sync",
                project_id=config.project_id,
                data=applied,
            )
            return _finish_knowledge_mutation(env, apply=True, effects=effects)
        fail = failure_envelope(
            command="vibe knowledge sync",
            code=str(applied.get("code") or "SYNC_FAILED"),
            message=str(applied.get("message") or "sync failed"),
            details=applied,
            project_id=config.project_id,
        )
        return _finish_knowledge_mutation(fail, apply=True, effects=effects)
    except (ConfigError, NotebookError, CorpusError) as exc:
        return _finish_knowledge_mutation(
            failure_envelope(
                command="vibe knowledge sync",
                code=exc.code,
                message=exc.message,
                details=exc.details,
            ),
            apply=apply,
            effects=[],
        )


def cmd_knowledge_retry(root: Path, args: Any) -> dict[str, Any]:
    dry_run = bool(getattr(args, "dry_run", False))
    apply = bool(getattr(args, "apply", False))
    if not dry_run and not apply:
        from vibe_control.json_envelope import next_action

        return _finish_knowledge_mutation(
            failure_envelope(
                command="vibe knowledge retry",
                code="RETRY_REQUIRES_DRY_RUN_OR_APPLY",
                message="Pass --dry-run or --apply",
                next_actions=[
                    next_action(
                        code="RETRY_REQUIRES_DRY_RUN_OR_APPLY",
                        command="vibe knowledge retry --dry-run --json",
                        mutation=False,
                        reason="Preview retry plan",
                    ),
                    next_action(
                        code="RETRY_REQUIRES_DRY_RUN_OR_APPLY",
                        command="vibe knowledge retry --apply --json",
                        mutation=True,
                        reason="Apply retry only with explicit approval",
                    ),
                ],
            ),
            apply=False,
            effects=[],
        )

    try:
        config = _cfg(root, args)
    except ConfigError as exc:
        return _finish_knowledge_mutation(
            failure_envelope(
                command="vibe knowledge retry",
                code=exc.code,
                message=exc.message,
                details=exc.details,
            ),
            apply=apply,
            effects=[],
        )

    # local_fts: retry ≡ rebuild (same as sync apply/dry-run).
    if str(config.knowledge.get("provider") or "").strip().lower() == "local_fts":
        from vibe_control.knowledge.local_fts.provider import LocalFtsProvider

        local = LocalFtsProvider()
        data = local.sync(
            config,
            repo_root=root,
            apply=apply and not dry_run,
            notebook_alias=getattr(args, "notebook", None),
        )
        data["retry_equivalent"] = "local_fts_rebuild"
        effects = _local_fts_sync_effects(apply=apply and not dry_run, data=data)
        envelope = success_envelope(
            command="vibe knowledge retry",
            project_id=config.project_id,
            data=data,
            next_actions=list(data.get("next_actions") or []),
        )
        envelope["ok"] = bool(data.get("ok", True))
        return _finish_knowledge_mutation(
            envelope,
            apply=apply and not dry_run,
            effects=effects,
        )

    provider = NotebookLMProvider()
    try:
        from vibe_control.knowledge.ack_stores import LocalMirrorAckStore, NotebookLMNoteAckStore
        from vibe_control.knowledge.phase8_apply import plan_forward_sync_dry_run, retry_forward_sync
        from vibe_control.knowledge.provider_target import ProviderTarget

        alias = getattr(args, "notebook", None)
        entry, ref = require_notebook_ref(config, repo_root=root, alias=alias)
        from vibe_control.knowledge.notebooks import resolve_default_alias

        default_alias = resolve_default_alias(config)
        if (
            apply
            and entry.alias != default_alias
            and not bool(getattr(args, "confirm_non_default_sync", False))
        ):
            from vibe_control.json_envelope import next_action

            return _finish_knowledge_mutation(
                failure_envelope(
                    command="vibe knowledge retry",
                    code="NON_DEFAULT_NOTEBOOK_APPLY_REQUIRES_CONFIRM",
                    message=(
                        f"retry --apply for non-default notebook {entry.alias!r} "
                        "requires --confirm-non-default-sync"
                    ),
                    details={
                        "notebook_alias": entry.alias,
                        "default_alias": default_alias,
                    },
                    project_id=config.project_id,
                    next_actions=[
                        next_action(
                            code="NON_DEFAULT_NOTEBOOK_APPLY_REQUIRES_CONFIRM",
                            command=(
                                f"vibe knowledge retry --apply --notebook {entry.alias} "
                                "--confirm-non-default-sync --json"
                            ),
                            mutation=True,
                            reason="Re-run only after owner/task explicitly allows non-default apply",
                        ),
                    ],
                ),
                apply=True,
                effects=[],
            )
        if dry_run and not apply:
            target = ProviderTarget.from_ref(
                provider="notebooklm", notebook_alias=entry.alias, notebook_ref=ref
            )
            dry = plan_forward_sync_dry_run(
                config,
                repo_root=root,
                target=target,
                notebook_ref=ref,
                provider=provider,
                ack_store=LocalMirrorAckStore(config.project_id),
            )
            if dry.get("ok"):
                return _finish_knowledge_mutation(
                    success_envelope(
                        command="vibe knowledge retry",
                        project_id=config.project_id,
                        data=dry,
                    ),
                    apply=False,
                    effects=[],
                )
            return _finish_knowledge_mutation(
                failure_envelope(
                    command="vibe knowledge retry",
                    code=str(dry.get("code") or "RETRY_DRY_RUN_FAILED"),
                    message=str(dry.get("message") or "retry dry-run failed"),
                    details=dry,
                    project_id=config.project_id,
                ),
                apply=False,
                effects=[],
            )

        target = ProviderTarget.from_ref(
            provider="notebooklm", notebook_alias=entry.alias, notebook_ref=ref
        )
        # Fail-closed: retry --apply is not an arbitrary mutation escape hatch.
        # Same current-SSOT/default-inventory scope guard as sync --apply.
        from vibe_control.knowledge.ask_hygiene import assert_apply_ops_are_current_ssot_bounded

        dry_guard = plan_forward_sync_dry_run(
            config,
            repo_root=root,
            target=target,
            notebook_ref=ref,
            provider=provider,
            ack_store=LocalMirrorAckStore(config.project_id),
        )
        corpus = resolve_desired_corpus(
            config, notebook_alias=entry.alias, repo_root=root
        )
        desired_ids = {d.doc_id for d in corpus.documents}
        bound = assert_apply_ops_are_current_ssot_bounded(
            dry_guard.get("operations") or [],
            desired_doc_ids=desired_ids,
        )
        if not bound.get("ok"):
            return _finish_knowledge_mutation(
                failure_envelope(
                    command="vibe knowledge retry",
                    code="APPLY_SCOPE_VIOLATION",
                    message="retry --apply refused: dry-run ops are not bounded to current SSOT",
                    details=bound,
                    project_id=config.project_id,
                ),
                apply=True,
                effects=[],
            )

        ack_store = NotebookLMNoteAckStore(
            config.project_id,
            provider,
            notebook_ref=ref,
            command="vibe knowledge retry --apply",
        )
        applied = retry_forward_sync(
            config,
            repo_root=root,
            target=target,
            notebook_ref=ref,
            provider=provider,
            ack_store=ack_store,
            command="vibe knowledge retry --apply",
            continue_on_item_error=bool(getattr(args, "continue_on_item_error", False)),
            batch_size=getattr(args, "batch_size", None),
            wait_mode=getattr(args, "wait_mode", None),
            ingest_path=getattr(args, "ingest_path", None),
            upload_concurrency=getattr(args, "upload_concurrency", None),
        )
        effects = _effects_from_apply_result(applied)
        if applied.get("ok"):
            return _finish_knowledge_mutation(
                success_envelope(
                    command="vibe knowledge retry",
                    project_id=config.project_id,
                    data=applied,
                ),
                apply=True,
                effects=effects,
            )
        return _finish_knowledge_mutation(
            failure_envelope(
                command="vibe knowledge retry",
                code=str(applied.get("code") or "RETRY_FAILED"),
                message=str(applied.get("message") or "retry failed"),
                details=applied,
                project_id=config.project_id,
            ),
            apply=True,
            effects=effects,
        )
    except (ConfigError, NotebookError, CorpusError) as exc:
        return _finish_knowledge_mutation(
            failure_envelope(
                command="vibe knowledge retry",
                code=exc.code,
                message=exc.message,
                details=exc.details,
            ),
            apply=apply,
            effects=[],
        )


def cmd_knowledge_reindex_bindings(root: Path, args: Any) -> dict[str, Any]:
    provider = NotebookLMProvider()
    try:
        from vibe_control.knowledge.corpus import build_desired_corpus
        from vibe_control.knowledge.managed_names import content_sha256_file
        from vibe_control.knowledge.provider_target import ProviderTarget
        from vibe_control.knowledge.reindex_bindings import reindex_bindings
        from vibe_control.knowledge.snapshot import SnapshotItem

        config = _cfg(root, args)
        alias = getattr(args, "notebook", None)
        entry, ref = require_notebook_ref(config, repo_root=root, alias=alias)
        target = ProviderTarget.from_ref(
            provider="notebooklm", notebook_alias=entry.alias, notebook_ref=ref
        )
        corpus = resolve_desired_corpus(
            config, notebook_alias=entry.alias, repo_root=root
        )
        desired_docs = []
        for doc in corpus.documents:
            path = root / doc.path
            sha = content_sha256_file(path) if path.is_file() else ""
            desired_docs.append(
                {
                    "doc_id": doc.doc_id,
                    "path": doc.path,
                    "content_sha256": SnapshotItem._norm_sha(sha) if sha else "sha256:" + ("0" * 64),
                }
            )
        result = reindex_bindings(
            project_id=config.project_id,
            target=target,
            notebook_ref=ref,
            provider=provider,
            desired_docs=desired_docs,
            repo_root=root,
            require_managed_identity=False,
        )
        result = dict(result)
        result["reindexed"] = bool(result.get("ok"))
        if result.get("ok"):
            return success_envelope(
                command="vibe knowledge reindex-bindings",
                project_id=config.project_id,
                data=result,
            )
        return failure_envelope(
            command="vibe knowledge reindex-bindings",
            code=str(result.get("code") or "REINDEX_FAILED"),
            message=str(result.get("message") or "reindex failed"),
            details=result,
            project_id=config.project_id,
        )
    except (ConfigError, NotebookError, CorpusError) as exc:
        return failure_envelope(
            command="vibe knowledge reindex-bindings",
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )


def cmd_knowledge_rebuild(root: Path, args: Any) -> dict[str, Any]:
    """Compatibility alias: rebuild == reindex-bindings (never restores SSOT)."""
    out = cmd_knowledge_reindex_bindings(root, args)
    if isinstance(out, dict):
        out = dict(out)
        out["command"] = "vibe knowledge rebuild"
    return out


def cmd_cleanup_phase4_residue(root: Path, args: Any) -> dict[str, Any]:
    """INTERNAL / acceptance-only helper for exact Phase 4 test residue titles."""
    acceptance = bool(getattr(args, "acceptance_cleanup", False))
    dry_run = bool(getattr(args, "dry_run", False))
    allow_delete = bool(getattr(args, "allow_delete", False))
    if not acceptance:
        return failure_envelope(
            command="vibe knowledge cleanup-phase4-residue",
            code="ACCEPTANCE_CLEANUP_REQUIRED",
            message=(
                "cleanup-phase4-residue is an acceptance/internal helper; "
                "pass --acceptance-cleanup (not a normal user workflow)"
            ),
            next_actions=[
                "Use sync/retry lifecycle for managed sources",
                "For Phase 4 residue only: add --acceptance-cleanup with --dry-run or --allow-delete",
            ],
        )
    if not dry_run and not allow_delete:
        return failure_envelope(
            command="vibe knowledge cleanup-phase4-residue",
            code="CLEANUP_REQUIRES_ALLOW_DELETE",
            message="Pass --dry-run or --allow-delete (with --acceptance-cleanup)",
        )
    provider = NotebookLMProvider()
    try:
        from vibe_control.knowledge import sync_lifecycle

        config = _cfg(root, args)
        alias = getattr(args, "notebook", None)
        entry, ref = require_notebook_ref(config, repo_root=root, alias=alias)
        result = sync_lifecycle.run_phase4_residue_cleanup(
            provider,
            notebook_ref=ref,
            dry_run=dry_run,
            allow_delete=allow_delete and not dry_run,
        )
        # redact source ids in public envelope
        public = dict(result)
        for key in ("matched", "deleted", "planned_deletes"):
            rows = public.get(key)
            if isinstance(rows, list):
                redacted = []
                for row in rows:
                    item = dict(row)
                    sid = item.pop("provider_source_id", None)
                    if sid:
                        item["source_id_fingerprint"] = _fp_sid(str(sid))
                    redacted.append(item)
                public[key] = redacted
        if result.get("ok"):
            return success_envelope(
                command="vibe knowledge cleanup-phase4-residue",
                project_id=config.project_id,
                data={"notebook_alias": entry.alias, **public},
            )
        return failure_envelope(
            command="vibe knowledge cleanup-phase4-residue",
            code=str(result.get("code") or "CLEANUP_FAILED"),
            message=str(result.get("message") or "cleanup failed"),
            details={"notebook_alias": entry.alias, **public},
            project_id=config.project_id,
        )
    except (ConfigError, NotebookError) as exc:
        return failure_envelope(
            command="vibe knowledge cleanup-phase4-residue",
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )


def cmd_smoke_replace(root: Path, args: Any) -> dict[str, Any]:
    """INTERNAL / ACCEPTANCE ONLY: Phase 6 replace smoke with isolated receipt."""
    dry_run = bool(getattr(args, "dry_run", False))
    apply = bool(getattr(args, "apply", False))
    cleanup = bool(getattr(args, "cleanup", False))
    if not dry_run and not apply:
        return failure_envelope(
            command="vibe knowledge smoke replace",
            code="SMOKE_REQUIRES_APPLY_OR_DRY_RUN",
            message="Pass --dry-run or --apply (INTERNAL/acceptance-only command)",
            next_actions=[
                "python -m vibe_control knowledge smoke replace --notebook OPM-test --dry-run --json",
                "python -m vibe_control knowledge smoke replace --notebook OPM-test --apply --cleanup --json",
            ],
        )
    provider = NotebookLMProvider()
    try:
        from vibe_control.knowledge import replace_smoke

        config = _cfg(root, args)
        alias = getattr(args, "notebook", None)
        entry, ref = require_notebook_ref(config, repo_root=root, alias=alias)
        result = replace_smoke.plan_or_run(
            config,
            notebook_alias=entry.alias,
            notebook_ref=ref,
            provider=provider,
            dry_run=dry_run,
            apply=apply and not dry_run,
            cleanup=cleanup,
        )
        data = result.get("data") or {}
        # Redact raw source IDs from CLI envelope.
        for key in ("v1", "v2"):
            row = data.get(key)
            if isinstance(row, dict) and "provider_source_id" in row:
                row = dict(row)
                sid = row.pop("provider_source_id")
                row["source_id_fingerprint"] = _fp_sid(str(sid))
                data[key] = row
        if result.get("ok"):
            return success_envelope(
                command="vibe knowledge smoke replace",
                project_id=config.project_id,
                data=data,
            )
        details = result.get("data") or {}
        for key in ("v1", "v2"):
            row = details.get(key)
            if isinstance(row, dict) and "provider_source_id" in row:
                row = dict(row)
                sid = row.pop("provider_source_id")
                row["source_id_fingerprint"] = _fp_sid(str(sid))
                details[key] = row
        return failure_envelope(
            command="vibe knowledge smoke replace",
            code=str(result.get("code") or "SMOKE_FAILED"),
            message=str(result.get("message") or "smoke replace failed"),
            details=details,
            project_id=config.project_id,
            partial_success=bool(result.get("partial_success")),
        )
    except (ConfigError, NotebookError, CorpusError) as exc:
        return failure_envelope(
            command="vibe knowledge smoke replace",
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )


def cmd_knowledge_cleanup_candidates(root: Path, args: Any) -> dict[str, Any]:
    """Readonly listing of manual cleanup candidates (never deletes)."""
    try:
        config = _cfg(root, args)
    except ConfigError as exc:
        return failure_envelope(
            command="vibe knowledge cleanup-candidates",
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    if str(config.knowledge.get("provider") or "").strip().lower() == "local_fts":
        from vibe_control.json_envelope import next_action
        from vibe_control.knowledge.local_fts.purge import build_purge_plan

        plan = build_purge_plan(config, repo_root=root, purge_all=False)
        orphans = [e.to_dict() for e in plan.entries if e.kind in {"orphan", "tmp"}]
        env = success_envelope(
            command="vibe knowledge cleanup-candidates",
            project_id=config.project_id,
            data={
                "provider": "local_fts",
                "applicable": True,
                "kind": "local_fts_garbage",
                "message": (
                    "NotebookLM orphan cleanup does not apply. "
                    "Stale local_fts scopes/tmp are listed; delete via fts-purge."
                ),
                "candidate_count": len(orphans),
                "candidates": orphans,
                "plan": plan.to_dict(),
            },
            next_actions=[
                next_action(
                    code="LOCAL_FTS_PURGE_ORPHANS",
                    command="vibe knowledge fts-purge --dry-run --json",
                    mutation=False,
                    reason="Preview orphan/tmp local_fts purge",
                )
            ],
        )
        env["mutation"] = False
        return env

    provider = NotebookLMProvider()
    try:
        from vibe_control.knowledge.cleanup_candidates import list_cleanup_candidates
        from vibe_control.knowledge.provider_target import ProviderTarget

        alias = getattr(args, "notebook", None)
        entry, ref = require_notebook_ref(config, repo_root=root, alias=alias)
        target = ProviderTarget.from_ref(
            provider="notebooklm", notebook_alias=entry.alias, notebook_ref=ref
        )
        result = list_cleanup_candidates(
            config,
            repo_root=root,
            target=target,
            notebook_ref=ref,
            provider=provider,
        )
        if not result.get("ok"):
            env = failure_envelope(
                command="vibe knowledge cleanup-candidates",
                code=str(result.get("code") or "CLEANUP_CANDIDATES_FAILED"),
                message=str(result.get("message") or "cleanup candidate listing failed"),
                details=result.get("data") or {},
                project_id=config.project_id,
                warnings=list(result.get("warnings") or []),
                next_actions=list(result.get("next_actions") or []),
            )
            env["mode"] = result.get("mode") or "unavailable"
            env["provider"] = result.get("provider") or target.provider
            env["target_key_hash"] = result.get("target_key_hash") or target.target_key_hash
            env["mutation"] = False
            return env

        env = success_envelope(
            command="vibe knowledge cleanup-candidates",
            project_id=config.project_id,
            data=result.get("data") or {},
            warnings=list(result.get("warnings") or []),
            next_actions=list(result.get("next_actions") or []),
            mode=str(result.get("mode") or "readonly"),
        )
        env["provider"] = result.get("provider") or target.provider
        env["target_key_hash"] = result.get("target_key_hash") or target.target_key_hash
        env["mutation"] = False
        return env
    except (ConfigError, NotebookError, CorpusError) as exc:
        return failure_envelope(
            command="vibe knowledge cleanup-candidates",
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )


def _poll_status(provider: NotebookLMProvider, notebook_ref: str, source_id: str) -> dict[str, Any]:
    got = provider.get_source(notebook_ref=notebook_ref, source_id=source_id)
    if not got.get("found"):
        return {"found": False, "status": "not_found"}
    return {"found": True, "status": got.get("status") or "unknown"}


def _fp_sid(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
